"""Ralts/Ness: restore the complete source head; replace tangled lower panels with a continuous gown.

The source face rides Bone_48 and the hair Bone_55. Both belong to Ness's head,
not his neck and head separately. The gown uses one shared ring surface, with
continuous hip/thigh weights, and simple feet beneath it. All joints stay vanilla.
"""

from cast_paths import WORK, TARGETS
import json
import math
from collections import Counter
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector, Matrix
from PIL import Image

R = Path(str(WORK / ''))
H = R/'hand/ralts-Ness'
B = H/'3-build'
data = json.loads((H/'inspect.json').read_text(encoding='utf-8'))
source = data['source']

bpy.ops.wm.open_mainfile(filepath=str(R/'mons/ralts/1-load/models/1-g3_ralts.blend'))
head_parts = {}
for name in ('ralts_mesh_09','ralts_mesh_13','ralts_mesh_14','ralts_mesh_15','ralts_mesh_16'):
    ob=bpy.data.objects[name]
    record=source['meshes'][name]
    faces=[p for p in ob.data.polygons if name!='ralts_mesh_09' or all(record['weights'][v].get('Bone_48',0)>0.99 for v in p.vertices)]
    head_parts[name]=dict(points=record['points'], faces=[list(p.vertices) for p in faces],
        uv=[[tuple(ob.data.uv_layers.active.data[i].uv) for i in p.loop_indices] for p in faces])

bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
arm=bpy.data.objects['Armature']
white=bpy.data.materials['ralts_mat_7']

def surface(name,points,faces,weights,material,uv=None):
    me=bpy.data.meshes.new(name)
    me.from_pydata(points,[],faces)
    me.update()
    me.materials.append(material)
    layer=me.uv_layers.new(name='UVMap')
    for p in me.polygons:
        p.use_smooth=True
        for k,i in enumerate(p.loop_indices):
            layer.data[i].uv=uv[p.index][k] if uv else (0.5,0.5)
    ob=bpy.data.objects.new(name,me)
    bpy.context.scene.collection.objects.link(ob)
    mod=ob.modifiers.new('Armature','ARMATURE')
    mod.object=arm
    for i,w in enumerate(weights):
        for joint,share in w.items():
            if share>1e-7:
                (ob.vertex_groups.get(joint) or ob.vertex_groups.new(name=joint)).add([i],share,'REPLACE')
    return ob

# Keep the original, mapped arm surfaces, including their tapered hands.
arms=[]
for name,groups in [('ralts_mesh_09',{'Bone_38','Bone_39','Bone_41'}),
                    ('ralts_mesh_10',{'Bone_43','Bone_44','Bone_46'})]:
    ob=bpy.data.objects[name]
    s=source['meshes'][name]
    fs=[p for p in ob.data.polygons if all(set(s['weights'][v]) & groups for v in p.vertices)]
    arms.append((name, [tuple(v.co) for v in ob.data.vertices], [list(p.vertices) for p in fs],
                 data['base']['meshes'][name]['weights'],
                 [[tuple(ob.data.uv_layers.active.data[i].uv) for i in p.loop_indices] for p in fs]))
materials={n:bpy.data.materials[n] for n in ['ralts_mat_7','ralts_mat_14','ralts_mat_15','ralts_mat_16']}
eye_material=bpy.data.materials['eyes']
for ob in list(bpy.data.objects):
    if ob.type=='MESH':
        bpy.data.objects.remove(ob,do_unlink=True)
for name,p,f,w,uv in arms:
    # The raw arm's four-vertex root needs a continuous bridge inside the chest.
    counts=Counter(tuple(sorted((a,b))) for poly in f for a,b in zip(poly,poly[1:]+poly[:1]))
    edges=[(a,b) for poly in f for a,b in zip(poly,poly[1:]+poly[:1]) if counts[tuple(sorted((a,b)))]==1]
    inner={}
    for v in sorted({i for edge in edges for i in edge}):
        x,y,z=p[v]
        inner[v]=len(p)
        p.append((x*.35,y*.65,z))
        w.append({'JOBJ_5':1})
    for a,b in edges:
        f.extend([(b,a,inner[a]),(b,inner[a],inner[b])])
        uv.extend([[(.5,.5)]*3,[(.5,.5)]*3])
    surface(name+'_arm',p,f,w,white,uv)

# Undo the source head's bind-pose lean, with its face, bowl and horns kept together.
neck=np.array(source['bones']['Bone_48']['head'])
crown=np.array(source['bones']['Bone_55']['head'])
rot=np.array(Vector(crown-neck).rotation_difference(Vector((0,0,1))).to_matrix())
head_origin=np.array([0,0.10,7.75])
head_scale=28.0
atlas=Image.open(H/'pkx-1c8e0.png')
for state,row in [('open',0),('half',1),('closed',3)]:
    atlas.crop((0,row*64,64,(row+1)*64)).save(B/'eyes'/f'{state}.png')
new=bpy.data.images.load(str(B/'eyes/open.png'),check_existing=False)
new.pack()
for node in eye_material.node_tree.nodes:
    if node.type=='TEX_IMAGE':
        node.image=new
new.name='ralts_eyes_open'
for name,part in head_parts.items():
    pts=(np.array(part['points'])-neck) @ rot.T * head_scale + head_origin
    uv=part['uv']
    if name=='ralts_mesh_13':
        material=eye_material
        uv=[[(u,1-(1-v)*8) for u,v in poly] for poly in uv]
        outname='eyes_left'
    else:
        material=materials['ralts_mat_7' if name=='ralts_mesh_09' else name.replace('mesh','mat').replace('_0','_')]
        outname=name+'_head'
    surface(outname,pts.tolist(),part['faces'],[{'JOBJ_24':1} for _ in pts],material,uv)

# Continuous gown and neck; shared vertices mean no independently moving panels.
N=32
rings=[(.28,2.28,1.55),(.7,2.15,1.48),(1.4,1.93,1.35),(2.2,1.68,1.15),
       (2.65,1.55,1.05),(3.1,1.40,.96),(3.55,1.28,.86),(4.0,1.16,.78),
       (4.5,1.03,.70),(5.2,1.02,.65),(6.1,1.12,.61),
       (6.8,1.43,.57),(7.1,1.20,.51),(7.4,.56,.40),(7.85,.43,.34)]
points=[];weights=[];faces=[]
def gown_weights(z,x):
    if z>=7.1:
        neck_share=min(1,(z-7.1)/.75)
        return {'JOBJ_5':1-neck_share,'JOBJ_23':neck_share}
    if z>=4.5:
        chest=min(1,(z-4.5)/1.4)
        return {'JOBJ_4':1-chest,'JOBJ_5':chest}
    hip=float(np.clip((z-3.3)/.7,0,1))
    shin=float(np.clip((3.1-z)/.9,0,1))
    ankle=0.0  # Independent foot twists must not turn the gown's hem inside out.
    left=.5+.5*math.tanh(x/.55)
    return {'JOBJ_4':hip,
            'JOBJ_48':(1-hip)*left*(1-shin),
            'JOBJ_55':(1-hip)*(1-left)*(1-shin),
            'JOBJ_49':(1-hip)*left*shin*(1-ankle),
            'JOBJ_56':(1-hip)*(1-left)*shin*(1-ankle),
            'JOBJ_51':(1-hip)*left*shin*ankle,
            'JOBJ_58':(1-hip)*(1-left)*shin*ankle}
for z,rx,ry in rings:
    for k in range(N):
        t=2*math.pi*k/N
        x,y=rx*math.cos(t),ry*math.sin(t)+.10
        points.append((x,y,z))
        weights.append(gown_weights(z,x))
for r in range(len(rings)-1):
    for k in range(N):
        a=r*N+k;b=r*N+(k+1)%N;c=(r+1)*N+(k+1)%N;d=(r+1)*N+k
        faces.extend([(a,b,c),(a,c,d)])
surface('ralts_gown',points,faces,weights,white)
# An exact reversed twin provides independently lit inside faces and tells prep to cull.
surface('ralts_gown_inside',points,[f[::-1] for f in faces],weights,white)

# Small rounded white feet, visible only when a step lifts the hem.
for side,joint in [(1,'JOBJ_51'),(-1,'JOBJ_58')]:
    p=[];w=[];f=[]
    for z,rx,ry in [(0.01,.31,.64),(.18,.43,.80),(.43,.38,.68),(.64,.20,.36)]:
        for k in range(12):
            t=2*math.pi*k/12
            p.append((side*1.10+rx*math.cos(t),-.25+ry*math.sin(t),z))
            w.append({joint:1})
    for r in range(3):
        for k in range(12):
            a=r*12+k;b=r*12+(k+1)%12;c=(r+1)*12+(k+1)%12;d=(r+1)*12+k
            f.extend([(a,b,c),(a,c,d)])
    f.append(tuple(range(11,-1,-1)));f.append(tuple(range(36,48)))
    surface('ralts_foot_'+str(side),p,f,w,white)

record=json.loads((B/'eyes.json').read_text(encoding='utf-8'))
record['objects']=[{'name':'eyes_left','side':'left','surfaces':['ralts_mesh_13 / ralts_mat_13'],'triangles':16}]
record['image']=new.name
record['eye_texture_size']=[64,64]
record['crop']=[0,0,64,64]
record['made']={s:f'Ralts PKX eye atlas row {r}; 64-pixel tile, clamp preserved' for s,r in [('open',0),('half',1),('closed',3)]}
record['notes']=['Source head geometry and natural hair occlusion preserved; all head surfaces ride JOBJ_24.']
(B/'eyes.json').write_text(json.dumps(record,indent=1),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
print('Ralts head restored; continuous gown and feet saved.')
