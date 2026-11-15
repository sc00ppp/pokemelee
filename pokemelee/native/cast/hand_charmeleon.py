"""Hand port Charmeleon to Roy, from the untouched pre-prep build and source geometry.

Reconstruct the head, trunk and articulated limbs from the source instead of trying
to uncrumple rigswap's foot transforms. No vanilla sword geometry or joints change.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import bmesh
import numpy as np
from PIL import Image

R = Path(str(WORK / ''))
H = R / 'hand/charmeleon-Roy'
B = H / '3-build'
S = json.loads((H / 'look/source-geometry.json').read_text(encoding='utf-8'))
BASE = json.loads((H / 'look/base-geometry.json').read_text(encoding='utf-8'))
def sj(n): return np.array(S['bones'][f'Bone_{n:02}']['head'])
def tj(n): return np.array(BASE['bones'][f'JOBJ_{n}']['head'])
def smooth(a,b,x):
    t=float(np.clip((x-a)/(b-a),0,1))
    return t*t*(3-2*t)
def mix(a,b,t): return a*(1-t)+b*t
def weights_along(z, levels, joints):
    if z <= levels[0]: return {f'JOBJ_{joints[0]}':1.}
    if z >= levels[-1]: return {f'JOBJ_{joints[-1]}':1.}
    i=int(np.searchsorted(levels,z)-1)
    t=(z-levels[i])/(levels[i+1]-levels[i])
    return {f'JOBJ_{joints[i]}':1-t,f'JOBJ_{joints[i+1]}':t}
def rotation(a,b):
    a=a/np.linalg.norm(a); b=b/np.linalg.norm(b)
    v=np.cross(a,b); c=a@b
    m=np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
    return np.eye(3)+m+m@m/(1+c)
HEAD_FROM=sj(36)
HEAD_TO=np.array([0.,-.22,13.9])
HEAD_SCALE=10.
def head(p): return (p-HEAD_FROM)*HEAD_SCALE+HEAD_TO
def trunk(p):
    x,y,z=p
    old=[.16,.247,.4123,.5883,.6708,.75]
    new=[7.3,8.8,10.3,13.25,13.9,14.692]
    centre=np.interp(z,[.16,.247,.4123,.5883,.6708],[.06,.045,.045,-.1111,-.1839])
    out=np.array([x*10.,(y-centre)*10.-.3,np.interp(z,old,new)])
    t=smooth(.60,.69,z)
    out=mix(out,head(p),t)
    return out,weights_along(out[2],[8.8,10.3,12.3,13.5,14.3],[4,23,24,61,62])

def path_map(p, src, dst, width, segment=None):
    """Keep the cross section, with a continuous frame at each bend."""
    dirs=np.diff(src,axis=0)
    lens=np.linalg.norm(dirs,axis=1)
    tang=dirs/lens[:,None]
    candidates=[]
    for i in range(len(dirs)):
        u=float(np.clip((p-src[i])@tang[i]/lens[i],0,1))
        at=src[i]+u*dirs[i]
        candidates.append((np.linalg.norm(p-at),i,u,at))
    _,i,u,at=candidates[segment] if segment is not None else min(candidates,key=lambda x:x[0])
    # Cross-section plane blends adjacent directions, preventing inverted rings.
    ta=tang[i] if i==0 else tang[i-1]+tang[i]
    tb=tang[i] if i==len(tang)-1 else tang[i]+tang[i+1]
    axis=mix(ta/np.linalg.norm(ta),tb/np.linalg.norm(tb),u)
    axis/=np.linalg.norm(axis)
    newaxis=dst[i+1]-dst[i]
    rot=rotation(axis,newaxis)
    offset=p-at
    # Do not reintroduce a longitudinal offset from the oblique frame.
    offset-=axis*(offset@axis)
    return mix(dst[i],dst[i+1],u)+width*(rot@offset),i+u

# The real knee cross-section, not the height nearest the fighter's knee.
leg=S['objects']['lizardo_mesh_17']
lc=np.array(leg['co'])
KNEE_IDS=[6,14,16,18,20,33]
ANKLE_IDS=[19,21,26,34,36,38,45]
knee=lc[KNEE_IDS].mean(0)
ankle=lc[ANKLE_IDS].mean(0)

def leg_map(p, bone):
    left=bone in (4,5,7)
    sign=1 if left else -1
    q=p*np.array([sign,1,1])
    j=(6,7,9) if left else (14,15,17)
    foot_src=sj(6)*[1,1,1]
    foot_dst=tj(j[2])*[sign,1,1]
    def foot(q):
        return (q-foot_src)*[9.5,12.,14.2]+foot_dst
    if bone in (7,27):
        out=foot(q)
        out[2]=max(0.,out[2])
        return out*[sign,1,1],{f'JOBJ_{j[2]}':1.}
    src=np.array([[.185,.045,.31],knee,ankle])
    dst=np.array([tj(j[0])*[sign,1,1],tj(j[1])*[sign,1,1],foot(ankle)])
    # Same ring on both legs, despite tiny bind-pose asymmetry.
    kn=np.min(np.linalg.norm(lc[KNEE_IDS]-q,axis=1))<.013
    an=np.min(np.linalg.norm(lc[ANKLE_IDS]-q,axis=1))<.013
    if kn:
        axis=(src[2]-src[0]); offset=q-knee
        offset-=axis*(offset@axis)/(axis@axis)
        out=dst[1]+11.*(rotation(axis,np.array([0,0,-1.]))@offset)
        out[2]=dst[1,2]
        w={f'JOBJ_{j[0]}':.5,f'JOBJ_{j[1]}':.5}
    elif an:
        out=foot(q)
        w={f'JOBJ_{j[1]}':.65,f'JOBJ_{j[2]}':.35}
    else:
        out,t=path_map(q,src,dst,11.,segment=0 if bone in (4,24) else 1)
        w=weights_along(t,[0,.8,1.2,2],[j[0],j[0],j[1],j[2]])
    return out*[sign,1,1],w

def arm_map(p,bone):
    left=bone in (49,50,52)
    src=np.array([sj(i) for i in ((48,50,51) if left else (58,60,61))])
    j=(30,31,33) if left else (72,73,75)
    dst=np.array([tj(i) for i in j])
    src=np.vstack([src,src[-1]+(src[-1]-src[-2])*.7])
    dst=np.vstack([dst,dst[-1]+(dst[-1]-dst[-2])*.5])
    segment={49:0,59:0,50:1,60:1,52:2,62:2}[bone]
    out,t=path_map(p,src,dst,10.5,segment)
    w=weights_along(t,[0,.78,1.22,1.8,2.15,3],[j[0],j[0],j[1],j[1],j[2],j[2]])
    if t<.23:
        tr,tw=trunk(p)
        blend=smooth(0,.23,t)
        out=mix(tr,out,blend)
        w={k:v*blend for k,v in w.items()}
        for k,v in tw.items(): w[k]=w.get(k,0)+v*(1-blend)
    return out,w

tail_root=sj(14)
tail_at=trunk(tail_root)[0]
def tail_map(p):
    a=smooth(.18,.31,p[1])
    tr,_=trunk(p)
    tail=(p-tail_root)*[12.,12.,7.8]+tail_at
    tail[0]-=1.35*smooth(.18,.59,p[1])
    out=mix(tr,tail,a)
    t=.18*smooth(.18,.59,p[1])
    return out,{'JOBJ_4':1-t,'JOBJ_23':t}

def mapped(p,bone):
    if bone in (37,39): return head(p),{'JOBJ_62':1.}
    if bone in (4,5,7,24,25,27): return leg_map(p,bone)
    if bone in (49,50,52,59,60,62): return arm_map(p,bone)
    if bone in (15,16,17,18,19): return tail_map(p)
    return trunk(p)

def rig(ob,weights):
    ob.vertex_groups.clear()
    for i,row in enumerate(weights):
        for n,v in row.items():
            if v>1e-6:
                (ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n)).add([i],float(v),'REPLACE')
def put(ob,co,weights):
    ob.data.vertices.foreach_set('co',np.asarray(co).ravel())
    if 'custom_normal' in ob.data.attributes:
        ob.data.attributes.remove(ob.data.attributes['custom_normal'])
    ob.data.update()
    rig(ob,weights)

def surface(name,co,faces,material,uv,weights):
    me=bpy.data.meshes.new(name)
    me.from_pydata(co,[],faces); me.update()
    me.materials.append(material)
    layer=me.uv_layers.new(name='UVMap')
    for i,l in enumerate(me.loops): layer.data[i].uv=uv[i]
    for p in me.polygons: p.use_smooth=True
    ob=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(ob)
    ob.modifiers.new('Armature','ARMATURE').object=bpy.data.objects['Armature']
    rig(ob,weights)
    return ob

def eyes():
    # Bake the actual CLAMP footprint, without wrapping overhanging triangles.
    atlas=np.array(Image.open(H/'look/source-tex_3694.png').convert('RGBA'))
    x0,y0,w,h=-10,-1,54,41
    for state,dy in [('open',0),('half',48),('closed',96)]:
        yy=np.clip(np.arange(y0,y0+h)+dy,0,len(atlas)-1)
        xx=np.clip(np.arange(x0,x0+w),0,atlas.shape[1]-1)
        Image.fromarray(atlas[yy[:,None],xx[None,:]]).save(B/'eyes'/f'{state}.png')
    material=bpy.data.materials['eyes']
    for n in ('eyes_left','eyes_right'):
        bpy.data.objects.remove(bpy.data.objects[n],do_unlink=True)
    source=S['objects']['lizardo_mesh_08']
    co=np.array(source['co']); uv=np.array(source['uv']['UVMap'])
    cursor=0
    side={'left':([],[],[]),'right':([],[],[])}
    for f in source['faces']:
        pts,faces,uvs=side['left' if co[f,0].mean()>0 else 'right']
        faces.append(list(range(len(pts),len(pts)+len(f))))
        pts.extend(head(p).tolist() for p in co[f])
        for u,v in uv[cursor:cursor+len(f)]:
            uvs.append(((u*32-x0)/w,1-((1-v)*128-y0)/h))
        cursor+=len(f)
    for name,(pts,faces,uvs) in side.items():
        surface('eyes_'+name,pts,faces,material,uvs,[{'JOBJ_62':1.} for p in pts])
    old=bpy.data.images.get('eyes_open')
    im=bpy.data.images.load(str(B/'eyes/open.png')); im.pack()
    for node in material.node_tree.nodes:
        if node.type=='TEX_IMAGE': node.image=im
    if old: bpy.data.images.remove(old)
    im.name='eyes_open'
    record=json.loads((B/'eyes.json').read_text(encoding='utf-8'))
    record['eye_texture_size']=[w,h]
    record['crop']=[x0,y0,w,h]
    record['made']={s:f'Source CLAMP atlas, offset {k}, no triangle wrapping' for s,k in [('open',0),('half',48),('closed',96)]}
    record['notes']=['hand_charmeleon.py restores UVs and all three native eye states.']
    (B/'eyes.json').write_text(json.dumps(record,indent=2),encoding='utf-8')

def flame():
    """Small solid flame, with a yellow core visible from either game side."""
    tip=np.array(S['objects']['lizardo_mesh_18']['co'])
    tip=tip[np.argmax(tip[:,2])]
    anchor=tail_map(tip)[0]
    for name,colour,scale,offset in [('outer',(1.,.22,.008,1),.8,0.),('core',(1.,.8,.035,1),.62,-.18)]:
        mat=bpy.data.materials.new('charmeleon_flame_'+name); mat.diffuse_color=colour; mat.use_nodes=True
        bs=mat.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=colour
        # Texture survives the export's material baking just like source colours.
        im=bpy.data.images.new('flame_'+name,width=8,height=8)
        im.pixels=list(colour)*64; im.pack()
        tex=mat.node_tree.nodes.new('ShaderNodeTexImage'); tex.image=im
        mat.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color'])
        co=[]
        for z,r,dy in [(0,.16,0),(.5,.6,0),(1.15,.47,.05),(1.75,.24,.2),(2.5,.015,-.1)]:
            for i in range(8):
                a=2*np.pi*i/8
                # Core is slightly wider in x so its bright centre shows on both sides.
                co.append((anchor+np.array([r*np.cos(a)*(1.16 if name=='core' else .72),
                    (r*np.sin(a)+dy)*scale,(z*scale)+offset])).tolist())
        faces=[]
        for k in range(4):
            for i in range(8):
                a=k*8+i;b=k*8+(i+1)%8;c=(k+1)*8+(i+1)%8;d=(k+1)*8+i
                faces.extend([[a,b,c],[a,c,d]])
        faces.extend([[0,i+1,i] for i in range(1,7)])
        surface('charmeleon_flame_'+name,co,faces,mat,[(.5,.5)]*(len(faces)*3),
                [{'JOBJ_4':.82,'JOBJ_23':.18} for p in co])

def smooth_seams():
    """Source UV splits must not become sharp lighting seams after reshaping.

    Accumulate face areas at coincident positions across the body's pieces, and
    explicitly write the shared corner normals for the export.
    """
    meshes=[o for o in bpy.data.objects if o.type=='MESH']
    normals={}
    for ob in meshes:
        me=ob.data
        for poly in me.polygons:
            pts=np.array([me.vertices[v].co for v in poly.vertices])
            area=np.cross(pts[1]-pts[0],pts[2]-pts[0])
            for p in pts:
                key=tuple(np.round(p,4))
                normals[key]=normals.get(key,np.zeros(3))+area
    for ob in meshes:
        me=ob.data
        for poly in me.polygons: poly.use_smooth=True
        if 'sharp_edge' in me.attributes: me.attributes.remove(me.attributes['sharp_edge'])
        custom=[]
        for loop in me.loops:
            n=normals[tuple(np.round(me.vertices[loop.vertex_index].co,4))]
            length=np.linalg.norm(n)
            custom.append((n/length if length>1e-8 else np.array([0.,0.,1.])).tolist())
        me.normals_split_custom_set(custom)
        me.update()

def main():
    bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
    for name,source in S['objects'].items():
        if name=='lizardo_mesh_08': continue
        ob=bpy.data.objects[name]
        assert len(ob.data.vertices)==len(source['co'])
        result=[mapped(np.array(p),int(max(w,key=w.get)[5:])) for p,w in zip(source['co'],source['weights'])]
        put(ob,[r[0] for r in result],[r[1] for r in result])
    eyes()
    flame()
    smooth_seams()
    bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
    print('Saved hand Charmeleon',B/'edited.blend')

if __name__=='__main__': main()
