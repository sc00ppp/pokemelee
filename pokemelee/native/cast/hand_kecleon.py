"""Kecleon on Yoshi: original eye tiles, upright head, intact coil, grounded feet.

Run from the campaign directory. Always reads the untouched pre-prep base.
Source arrays use the original vertex order, which base keeps outside its eye split.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np
from PIL import Image
from mathutils import Vector

R=Path(str(WORK / ''))
H=R/'hand/kecleon-Yoshi'
B=H/'3-build'
KHEAD=17.0
KTAIL=12.5  # gives the complete coil 0.1 unit floor clearance in forward smash
KFOOT=22.0

def norm(v): return v/np.linalg.norm(v)
def read(ob):
    names={g.index:g.name for g in ob.vertex_groups}
    return dict(points=np.array([ob.matrix_world@v.co for v in ob.data.vertices]),
                weights=[{names[g.group]:g.weight for g in v.groups if g.weight>0} for v in ob.data.vertices])
def weights(ob,i,w):
    for g in ob.vertex_groups: g.remove([i])
    for n,k in w.items():
        if k>1e-6: (ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n)).add([i],float(k),'REPLACE')
def rotation(a,b):
    return np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())

bpy.ops.wm.open_mainfile(filepath=str(R/'mons/kecleon/1-load/models/1-g3_kakureon.blend'))
source={o.name:read(o) for o in bpy.data.objects if o.type=='MESH'}
sa=next(o for o in bpy.data.objects if o.type=='ARMATURE')
sm={b.name:np.array(sa.matrix_world@b.matrix_local) for b in sa.data.bones}
sp={n:m[:3,3] for n,m in sm.items()}
# Two pupil centres and their surface normals define the face's own axes.
o=bpy.data.objects['kakureon_mesh_06'];uv=o.data.uv_layers.active
eye=[]
for p in o.data.polygons:
    a=np.array([uv.data[i].uv[:] for i in p.loop_indices]);m=np.vstack((a.T,np.ones(3)))
    if abs(np.linalg.det(m))<1e-8: continue
    w=np.linalg.solve(m,[28/64,1-22/64,1])
    if min(w)>-1e-6: eye.append((w@source[o.name]['points'][list(p.vertices)],np.array(p.normal)))
eye.sort(key=lambda p:p[0][0])
right=norm(eye[1][0]-eye[0][0]);front=eye[0][1]+eye[1][1]
front=norm(front-right*np.dot(front,right));up=norm(np.cross(front,right))
headrot=np.array([right,-front,up])
# The tail's local Z is the coil plane's normal, and local Y is up.
right=sm['Bone_105'][:3,2];up=sm['Bone_105'][:3,1]
tailrot=np.array([right,np.cross(up,right),up])

bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
arm=bpy.data.objects['Armature']
tp={b.name:np.array(arm.matrix_world@b.head_local) for b in arm.data.bones}
# Recover original source coordinates from the unchanged rigid crest's affine map.
src=source['kakureon_mesh_02']['points'];dst=read(bpy.data.objects['kakureon_mesh_02'])['points']
aff=np.linalg.lstsq(np.c_[src,np.ones(len(src))],dst,rcond=None)[0]
inv=np.linalg.inv(aff[:3,:])
def source_head(p): return (p-aff[3])@inv

for ob in [o for o in bpy.data.objects if o.type=='MESH']:
    gn={g.index:g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        old=np.array(v.co)
        hw=sum(g.weight for g in v.groups if gn[g.group]=='JOBJ_38')
        if hw>0:
            p=source[ob.name]['points'][v.index] if ob.name in source else source_head(old)
            new=headrot@(p-sp['Bone_067'])*KHEAD+tp['JOBJ_38']
            v.co=old*(1-hw)+new*hw

# Keep the entire coil on the first tail joint; blend only its attachment to the body.
for name,d in source.items():
    ob=bpy.data.objects.get(name)
    if not ob: continue
    for v,p,w in zip(ob.data.vertices,d['points'],d['weights']):
        share=sum(k for n,k in w.items() if n.startswith('Bone_') and 105<=int(n[5:])<=116)
        if share<=0: continue
        target=tailrot@(p-sp['Bone_105'])*KTAIL+tp['JOBJ_19']
        v.co=np.array(v.co)*(1-share)+target*share
        old={ob.vertex_groups[g.group].name:g.weight for g in v.groups if g.weight>0}
        held={n:k for n,k in old.items() if n not in ('JOBJ_19','JOBJ_20','JOBJ_21')}
        held['JOBJ_19']=share
        total=sum(held.values());weights(ob,v.index,{n:k/total for n,k in held.items()})

# Re-place the feet from source, undoing their bind-pose roll. Source local X points
# along the toes, local Y points down. Both feet get the actual ankle/foot joints.
footbasis=np.array([[0,0,1],[-1,0,0],[0,-1,0]])
for hip,knee,ankle,foot,jhip,jshin,jfoot in [
    ('Bone_005','Bone_007','Bone_008','Bone_009','JOBJ_6','JOBJ_7','JOBJ_9'),
    ('Bone_018','Bone_020','Bone_021','Bone_022','JOBJ_13','JOBJ_14','JOBJ_16')]:
    fr=footbasis@sm[foot][:3,:3].T
    heel=tp[jfoot].copy()
    fpoints=[]
    for n in ('kakureon_mesh_07','kakureon_mesh_08'):
        for p,w in zip(source[n]['points'],source[n]['weights']):
            if w.get(foot,0)>0: fpoints.append(fr@(p-sp[ankle])*KFOOT+heel)
    heel[2]-=min(p[2] for p in fpoints)
    sr=rotation(sp[ankle]-sp[knee],heel-tp[jshin])
    ss=np.linalg.norm(heel-tp[jshin])/np.linalg.norm(sp[ankle]-sp[knee])
    axis=norm(sp[ankle]-sp[knee])
    thigh='Bone_006' if hip=='Bone_005' else 'Bone_019'
    for n,d in source.items():
        ob=bpy.data.objects.get(n)
        if not ob: continue
        for v,p,w in zip(ob.data.vertices,d['points'],d['weights']):
            fw=sum(k for g,k in w.items() if g==foot or (g.startswith('Bone_') and (10<=int(g[5:])<=12 if foot=='Bone_009' else 23<=int(g[5:])<=25)))
            sw=w.get(knee,0)
            share=fw+sw
            if share<=0: continue
            f=fr@(p-sp[ankle])*KFOOT+heel
            delta=p-sp[knee];along=axis*np.dot(delta,axis)
            s=sr@(along*ss+(delta-along)*20)+tp[jshin]
            v.co=np.array(v.co)*(1-share)+f*fw+s*sw
            old={ob.vertex_groups[g.group].name:g.weight for g in v.groups if g.weight>0}
            # Use source region shares so toe influences cannot remain on the shin.
            held={k:x for k,x in old.items() if k not in (jshin,jfoot,'JOBJ_10' if foot=='Bone_009' else 'JOBJ_17')}
            other=sum(held.values())
            held={k:x*(1-share)/other for k,x in held.items()} if other>1e-8 else {}
            held[jshin]=sw;held[jfoot]=fw
            if sum(held.values())<.999: held[jhip]=1-sum(held.values())
            weights(ob,v.index,held)

# The finger mapper stretched three tiny claws along Yoshi's finger chains.
# Restore the source palms/claws as rigid hands, attached at the real wrists.
for elbow,wrist,hand,digits,je,jw in [
    ('Bone_056','Bone_057','Bone_058',(59,60,61),'JOBJ_27','JOBJ_28'),
    ('Bone_044','Bone_045','Bone_046',(47,48,49),'JOBJ_57','JOBJ_58')]:
    rot=rotation(sp[wrist]-sp[elbow],tp[jw]-tp[je])
    handgroups={hand,*[f'Bone_{i:03d}' for i in digits]}
    for name,d in source.items():
        ob=bpy.data.objects.get(name)
        if not ob: continue
        for v,p,w in zip(ob.data.vertices,d['points'],d['weights']):
            share=sum(k for g,k in w.items() if g in handgroups)
            if share<=0: continue
            target=rot@(p-sp[wrist])*17+tp[jw]
            v.co=np.array(v.co)*(1-share)+target*share
            old={ob.vertex_groups[g.group].name:g.weight for g in v.groups if g.weight>0}
            finger_range=range(28,37) if jw=='JOBJ_28' else range(58,68)
            held={g:k for g,k in old.items() if int(g[5:]) not in finger_range}
            total=sum(held.values())
            held={g:k*(1-share)/total for g,k in held.items()} if total>1e-8 else {}
            held[jw]=share
            if sum(held.values())<.999: held[je]=1-sum(held.values())
            weights(ob,v.index,held)

# Its own tongue, stiff on the head until now. Yoshi's grab stretches JOBJ_41 along its z (forward) up to 23 times about
# a pivot in the mouth; this tongue runs three times as far past the pivot as Yoshi's, so 30% of that lands it at his reach.
tongue=bpy.data.objects['kakureon_mesh_26']
for v in tongue.data.vertices:
    weights(tongue,v.index,{'JOBJ_41':.3,'JOBJ_38':.7} if v.co.y<tp['JOBJ_41'][1] else {'JOBJ_38':1})

# Crop a single 64-square expression. This is exactly the HSD scale (1,4)
# represented by glTF's scale (1,.25) and Blender offset (0,.75).
# The image's own pixels: look/source-tex_3F78.png went through save_render, which tints it by the scene's view transform.
source=bpy.data.images['tex_3F78']
pixels=np.array(source.pixels[:]).reshape(source.size[1],source.size[0],4)[::-1]
atlas=Image.fromarray(np.round(pixels*255).astype(np.uint8),'RGBA')
opened=atlas.crop((0,0,64,64));closed=atlas.crop((0,64,64,128))
half=np.array(opened);cl=np.array(closed)
yy,xx=np.mgrid[:64,:64]
# The upper lid uses the original green eyelid and shuts halfway to the real seam.
mask=(((xx-28)/13)**2+((yy-22)/19)**2<1)&(yy<22)
half[mask]=cl[mask]
for state,im in [('open',opened),('half',Image.fromarray(half)),('closed',closed)]:
    im.save(B/'eyes'/f'{state}.png')
m=bpy.data.materials['eyes']
for n in list(m.node_tree.nodes):
    if n.type=='MAPPING': m.node_tree.nodes.remove(n)
old=bpy.data.images.get('eyes_open')
if old: old.name='unused_original_atlas'
im=bpy.data.images.load(str(B/'eyes/open.png'));im.name='eyes_open';im.pack()
for n in m.node_tree.nodes:
    if n.type=='TEX_IMAGE': n.image=im;n.extension='EXTEND'
record=json.loads((B/'eyes.json').read_text(encoding='utf-8'))
record.update(eye_texture_size=[64,64],crop=[0,0,64,64],made={'open':'Original pkx atlas tile 0','half':'Original closed eyelid over the upper half of tile 0 pupil','closed':'Original pkx atlas tile 1'},notes=['No lost layer: KHR_texture_transform was ignored by preview and eye extraction/export.','Tiles 2 and 3 are dizzy and happy, not intermediate blink states.'])
record.pop('drawn',None)
(B/'eyes.json').write_text(json.dumps(record,indent=1),encoding='utf-8')
for o in bpy.data.objects:
    if o.type=='MESH': o.data.update()
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
print('Saved corrected face, upright head, rigid coil and restored feet.')
