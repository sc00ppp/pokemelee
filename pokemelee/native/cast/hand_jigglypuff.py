"""Hand port purin to Melee Jigglypuff, preserving the source meshes and normals."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from PIL import Image

R=Path(str(WORK / 'hand/jigglypuff-Jigglypuff'))
B=R/'3-build'

def vertices(ob): return np.array([ob.matrix_world@v.co for v in ob.data.vertices])
def weights(ob):
    names={g.index:g.name for g in ob.vertex_groups}
    return [{names[g.group]:g.weight for g in v.groups if g.weight>0} for v in ob.data.vertices]

bpy.ops.wm.open_mainfile(filepath=str(WORK / "mons" / 'jigglypuff/1-load/models/1-039_Jigglypuff.blend'))
source={o.name:(vertices(o),weights(o)) for o in bpy.data.objects if o.type=='MESH'}
arm_roots={1:{30,33,35,32,31,43,45,42,41,40,39,138,146,157,158,136,37,38,137,36,34,46,27,28,29,44,145},-1:{7,446,447,445,444,443,439,438,459,461,467,468,453,452,22,55,58,450,451,449,448,19,15,13,10,442,441}}
arm_ids={s:ids|{i for i,w in enumerate(source['purin_mesh_07'][1]) if ({'Bone_21','Bone_22'} if s==1 else {'Bone_25','Bone_26'}).intersection(w)} for s,ids in arm_roots.items()}
arm_faces={s:{f.index for f in bpy.data.objects['purin_mesh_07'].data.polygons if set(f.vertices)<=ids} for s,ids in arm_ids.items()}
hair_ids={i for i,w in enumerate(source['purin_mesh_07'][1]) if {'Bone_17','Bone_18'}.intersection(w)}
hair_roots={i for f in bpy.data.objects['purin_mesh_07'].data.polygons if set(f.vertices)&hair_ids for i in f.vertices if i not in hair_ids}
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE')
heads={b.name:np.array(arm.matrix_world@b.head_local) for b in arm.data.bones}
# Undo the small yaw and forward tilt in Colosseum's bind pose.
rot=np.array(Matrix.Rotation(.1097,3,'X')@Matrix.Rotation(.07115,3,'Z'))
body=source['purin_mesh_07'][0]
core=np.array([p for p,w in zip(*source['purin_mesh_07']) if 'Bone_01' in w])@rot.T
centre=(core.min(0)+core.max(0))/2
scale=np.array([10.5,10.5,10.5])/np.ptp(core,axis=0)
def whole(p): return (p@rot.T-centre)*scale+[0,0,5.25]

bpy.ops.wm.open_mainfile(filepath=str(R/'look/vanilla.blend'))
van={o.name:(vertices(o),weights(o),[list(p.vertices) for p in o.data.polygons]) for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('Joint_')}

def subset(names, groups=None):
    ps=[]; ws=[]; fs=[]
    for name in names:
        p,w,f=van[name]; selected=[i for i,a in enumerate(w) if groups is None or sum(v for k,v in a.items() if k in groups)>.39]
        chosen=set(selected); remap={i:len(ps)+k for k,i in enumerate(selected)}
        ps.extend(p[selected]); ws.extend(w[i] for i in selected)
        fs.extend([remap[i] for i in t] for t in f if all(i in chosen for i in t))
    return np.array(ps),ws,fs

def transfer(points, target):
    p,ws,fs=target
    tree=BVHTree.FromPolygons(p.tolist(),fs,all_triangles=False)
    result=[]
    for q in points:
        at,_,idx,_=tree.find_nearest(Vector(q))
        face=fs[idx]
        a,b,c=p[face[:3]]
        uv=np.linalg.lstsq(np.column_stack([b-a,c-a]),np.array(at)-a,rcond=None)[0]
        bc=np.maximum([1-uv.sum(),*uv],0); bc/=bc.sum()
        out={}
        for i,k in zip(face[:3],bc):
            for name,value in ws[i].items(): out[name]=out.get(name,0)+k*value
        out=dict(sorted(out.items(),key=lambda x:-x[1])[:4]); total=sum(out.values())
        result.append({k:float(v/total) for k,v in out.items() if v>1e-6})
    return result

def fit_bounds(p,target):
    a=target[0]
    return (p-p.min(0))/np.maximum(np.ptp(p,axis=0),1e-8)*np.ptp(a,axis=0)+a.min(0)

target_body=subset(['Joint_0_Object_0'])
target_hair=subset(['Joint_0_Object_0'],{'JOBJ_7','JOBJ_8','JOBJ_9'})
target_ears={1:subset(['Joint_0_Object_0','Joint_0_Object_1'],{'JOBJ_12'}),-1:subset(['Joint_0_Object_0','Joint_0_Object_1'],{'JOBJ_26'})}
target_arms={1:subset(['Joint_0_Object_6']),-1:subset(['Joint_0_Object_12'])}
target_feet={1:subset(['Joint_0_Object_11']),-1:subset(['Joint_0_Object_5'])}

bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
for sign in (1,-1):
    original=bpy.data.objects['purin_mesh_07']
    ob=original.copy(); ob.data=original.data.copy(); ob.name=f'purin_arm_{sign}'
    bpy.context.collection.objects.link(ob)
    source[ob.name]=source['purin_mesh_07']
for side in ('back',):
    original=bpy.data.objects['purin_mesh_07']
    ob=original.copy(); ob.data=original.data.copy(); ob.name=f'purin_ball_{side}'
    bpy.context.collection.objects.link(ob)
    source[ob.name]=source['purin_mesh_07']
for ob in [o for o in bpy.data.objects if o.type=='MESH']:
    p,w=source[ob.name]; q=whole(p); out=[{'JOBJ_6':1.0} for _ in p]
    if ob.name.startswith('purin_arm_'):
        for sign in (int(ob.name.split('_')[-1]),):
            idx=sorted(arm_ids[sign])
            a=p[idx]
            root=heads['Bone_21' if sign==1 else 'Bone_25']
            tip=heads['Bone_24_HandLeft' if sign==1 else 'Bone_28_HandRight']
            axis=(tip-root); axis/=np.linalg.norm(axis)
            # Retain the little pointed hand, straightened along the vanilla arm.
            turn=np.array(Vector(axis).rotation_difference(Vector((sign,0,0))).to_matrix())
            moved=(a-root)@turn.T
            # Fit the projecting hand, leaving the broad root tucked into the ball.
            tipidx=[j for j,i in enumerate(idx) if ({'Bone_21','Bone_22'} if sign==1 else {'Bone_25','Bone_26'}).intersection(w[i])]
            a=target_arms[sign][0]
            q[idx]=(moved-moved[tipidx].min(0))/np.maximum(np.ptp(moved[tipidx],axis=0),1e-8)*np.ptp(a,axis=0)+a.min(0)
            for i in arm_roots[sign]:
                q[i]=[sign*3.9,float(np.clip(q[i,1],-.55,.55)),float(np.clip(q[i,2],4.45,5.55))]
            for i,wi in zip(idx,transfer(q[idx],target_arms[sign])): out[i]=wi
    if ob.name=='purin_mesh_07':
        idx=[i for i,wi in enumerate(w) if {'Bone_17','Bone_18'}.intersection(wi)]
        hair_before=q[idx].copy()
        mapped=(q-hair_before.min(0))/np.maximum(np.ptp(hair_before,axis=0),1e-8)*np.ptp(target_hair[0],axis=0)+target_hair[0].min(0)
        q[idx]=mapped[idx]
        # Move the original attachment ring with the curl, then tuck it into the
        # balloon along its new direction; the old root made a stretched dark web.
        for i in hair_roots:
            d=mapped[i]-[0,0,5.25];q[i]=d/np.linalg.norm(d)*5.18+[0,0,5.25]
        for i,wi in zip(idx,transfer(q[idx],target_hair)): out[i]=wi
        for sign,bone in [(1,'Bone_19'),(-1,'Bone_20')]:
            idx=[i for i,wi in enumerate(w) if bone in wi]
            # Ear tips match vanilla; retain the original ear-root positions on the ball.
            for i,wi in zip(idx,transfer(q[idx],target_ears[sign])): out[i]=wi
    elif ob.name=='purin_mesh_08':
        for sign,bone in [(1,'Bone_09'),(-1,'Bone_13')]:
            idx=[i for i,wi in enumerate(w) if bone in wi]
            a=q[idx]
            root=whole(heads[bone]); tip=whole(heads['Bone_11_FootLeft' if sign==1 else 'Bone_15_FootRight'])
            axis=tip-root; axis[2]=0; axis/=np.linalg.norm(axis)
            turn=np.array(Vector(axis).rotation_difference(Vector((0,-1,0))).to_matrix())
            q[idx]=fit_bounds((a-root)@turn.T,target_feet[sign])
            for i,wi in zip(idx,transfer(q[idx],target_feet[sign])): out[i]=wi
    elif ob.name in ('purin_mesh_12','purin_mesh_13'):
        out=transfer(q,target_ears[1 if ob.name.endswith('12') else -1])
    if ob.name.startswith('purin_ball_') or ob.name in ('purin_mesh_09','purin_mesh_10','purin_mesh_11'):
        d=q-[0,0,5.25]
        radius=5.25 if ob.name.startswith('purin_ball_') else 5.28
        q=d/np.linalg.norm(d,axis=1)[:,None]*radius+[0,0,5.25]
    if ob.name=='purin_mesh_07':
        for i,wi in enumerate(w):
            if set(wi)=={'Bone_01'}:
                d=q[i]-[0,0,5.25];q[i]=d/np.linalg.norm(d)*5.18+[0,0,5.25]
    for v,pt in zip(ob.data.vertices,q): v.co=pt
    ob.vertex_groups.clear()
    for i,wi in enumerate(out):
        for name,value in wi.items(): (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i],value,'REPLACE')
    ob.data.update()
    if ob.name=='purin_mesh_07' or ob.name.startswith(('purin_arm_','purin_ball_')):
        bm=bmesh.new(); bm.from_mesh(ob.data); bm.faces.ensure_lookup_table()
        feature={i for i,wi in enumerate(w) if {'Bone_17','Bone_18','Bone_19','Bone_20'}.intersection(wi)}
        if ob.name.startswith('purin_ball_'):
            baseq=whole(p)
            delete=[f for f in bm.faces if not all(set(w[v.index])=={'Bone_01'} for v in f.verts)]
        else:
            delete=[f for f in bm.faces if (not (any(v.index in feature for v in f.verts) and min(q[v.index,2] for v in f.verts)>7.3) if ob.name=='purin_mesh_07' else f.index not in arm_faces[int(ob.name.split('_')[-1])])]
        bmesh.ops.delete(bm,geom=delete,context='FACES')
        loose=[v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm,geom=loose,context='VERTS')
        if ob.name=='purin_ball_back':
            bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=.00001,plane_co=(0,0,5.25),plane_no=(0,1,0),clear_inner=True,clear_outer=False)
            for v in bm.verts:
                d=v.co-Vector((0,0,5.25));v.co=Vector((0,0,5.25))+d.normalized()*5.25
            bmesh.ops.triangulate(bm,faces=[f for f in bm.faces if len(f.verts)>3])
        bm.to_mesh(ob.data); bm.free(); ob.data.update()

back=bpy.data.objects['purin_ball_back']
front=back.copy();front.data=back.data.copy();front.name='purin_ball_front'
bpy.context.collection.objects.link(front)
front.data.transform(Matrix.Diagonal((1,-1,1,1)))
front.data.flip_normals()
# Make the two source hemispheres one continuous mesh at their cut boundary.
bpy.ops.object.select_all(action='DESELECT')
back.select_set(True);front.select_set(True);bpy.context.view_layer.objects.active=back
bpy.ops.object.join();back.name='purin_balloon'
bm=bmesh.new();bm.from_mesh(back.data)
bmesh.ops.remove_doubles(bm,verts=[v for v in bm.verts if abs(v.co.y)<1e-4],dist=1e-4)
bm.to_mesh(back.data);bm.free();back.data.update()


# The game's CI8 eye atlas has four 64-row bands: open, half, nearly shut, shut.
# Crop a padded clamp footprint, applying the KHR_texture_transform to the UVs first.
(B/'eyes').mkdir(exist_ok=True)
atlas=np.array(Image.open(R/'look/game-17de0.png').convert('RGBA'))
yy0,xx0=np.mgrid[:64,:32]
delta=np.max(np.abs(atlas[:64,:,:3].astype(float)-atlas[50,16,:3]),axis=2)
mask=np.clip((delta-5)/25,0,1)
mask[(xx0-15.5)**2+(yy0-15.5)**2<13.5**2]=1
for state,dy in [('open',0),('half',64),('closed',192)]:
    xx,yy=np.meshgrid(np.arange(-16,48),np.arange(-16,48))
    tile=atlas[np.clip(yy+dy,dy,dy+63),np.clip(xx,0,31)]
    tile[:,:,3]=(255*mask[np.clip(yy,0,63),np.clip(xx,0,31)]).astype(np.uint8)
    Image.fromarray(tile).save(B/'eyes'/f'{state}.png')
eyeim=bpy.data.images.load(str(B/'eyes/open.png')); eyeim.pack(); eyeim.name='eyes_open'
mat=bpy.data.materials.new('eyes'); mat.use_nodes=True
node=mat.node_tree.nodes.new('ShaderNodeTexImage'); node.image=eyeim; node.extension='EXTEND'
mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
mat.node_tree.links.new(node.outputs['Alpha'],mat.node_tree.nodes.get('Principled BSDF').inputs['Alpha'])
mat.surface_render_method='DITHERED'
objects=[]
for name,dx,side in [('purin_mesh_09',0,'left'),('purin_mesh_10',.0096,'right')]:
    ob=bpy.data.objects[name]
    for uv in ob.data.uv_layers.active.data:
        u,v=uv.uv
        uv.uv=((32*(u+dx)+16)/64,1-((1-v-.43658447265625)*256+16)/64)
    ob.data.materials.clear(); ob.data.materials.append(mat)
    objects.append(dict(name=name,side=side))
mouth=bpy.data.objects['purin_mesh_11']
mouthmat=mouth.data.materials[0]
mouthpx=np.array(Image.open(R/'look/game-13de0.png').convert('RGBA'))
delta=np.max(np.abs(mouthpx[:,:,:3].astype(float)-mouthpx[50,16,:3]),axis=2)
mouthpx[:,:,3]=(255*np.clip((delta-8)/25,0,1)).astype(np.uint8)
Image.fromarray(mouthpx).save(B/'eyes/mouth.png')
for node in mouthmat.node_tree.nodes:
    if node.type=='TEX_IMAGE':
        mouthim=bpy.data.images.load(str(B/'eyes/mouth.png')); mouthim.pack(); node.image=mouthim
        for link in list(node.inputs['Vector'].links): mouthmat.node_tree.links.remove(link)
        node.extension='EXTEND'
        mouthmat.node_tree.links.new(node.outputs['Alpha'],mouthmat.node_tree.nodes.get('Principled BSDF').inputs['Alpha'])
mouthmat.surface_render_method='DITHERED'
for uv in mouth.data.uv_layers.active.data: uv.uv.y+=.4375
record=dict(objects=objects,frames={s:f'eyes/{s}.png' for s in ('open','half','closed')},eye_texture_size=[64,64],made={s:f'Colosseum purin CI8 eye tile {n}; clamped UV transform applied' for s,n in [('open',0),('half',1),('closed',3)]},notes=['No chained texture is missing. Source Mapping node was ignored; rigid arm/ear/curl assignments replaced with vanilla anatomical weights.'])
(B/'eyes.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
