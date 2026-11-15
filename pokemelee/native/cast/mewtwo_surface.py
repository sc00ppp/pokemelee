"""Re-seat the Colosseum body appearance on the matching vanilla anatomy.

The original sparse chest, fingers and hocks folded into panels in game. Keep
the Colosseum head and face; use the same creature's native articulated surface
for the body. Copy stored normals from the donor without generating normals.
"""

from cast_paths import WORK, TARGETS, target_image
import json
from pathlib import Path
import bpy,bmesh
import numpy as np
from PIL import Image
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree

ROOT=Path(str(WORK / 'hand/mewtwo-Mewtwo'));B=ROOT/'3-build'
D=json.loads((ROOT/'inspection.json').read_text(encoding='utf-8'));S=D['source']['meshes']
regions={'body':{18,44,74},'arms':{20,21,32,33},'hands':{23,25,26,27,35,37,38,39},
         'legs':{5,6,10,11,61,62,66,67},'tail':set(range(74,81)),'tube':{56,57,58}}
ids={'body':[0,5],'arms':[8],'hands':[3,9,10],'legs':[15,16,17,18,38,39,40,41],'tail':[11],'tube':[6]}

# The edited fit supplies correspondence for the Colosseum texture palette.
bpy.ops.wm.open_mainfile(filepath=str(B/'edited.blend'))
materials={m.name:m for m in bpy.data.materials if m.name.startswith('mewtwo_')}
for m in materials.values():m.use_fake_user=True
refs={}
for region,bones in regions.items():
    pts=[];faces=[];uvs=[];mats=[]
    for name,src in S.items():
        ob=bpy.data.objects.get(name)
        if ob is None:continue
        if region=='tail' and name not in ['mewtwo_mesh_10','mewtwo_mesh_11','mewtwo_mesh_22']:continue
        if region=='body' and name in ['mewtwo_mesh_10','mewtwo_mesh_11','mewtwo_mesh_22']:continue
        for face in ob.data.polygons:
            bs=[int(max(src['vw'][i],key=src['vw'][i].get).split('_')[1]) for i in face.vertices]
            if sum(b in bones for b in bs)<2:continue
            start=len(pts);pts += [list(ob.data.vertices[i].co) for i in face.vertices]
            faces.append(list(range(start,start+len(face.vertices))))
            uvs.append(np.array([ob.data.uv_layers.active.data[i].uv[:] for i in face.loop_indices]))
            mats.append(ob.data.materials[face.material_index].name)
    refs[region]=(np.array(pts),faces,uvs,mats,BVHTree.FromPolygons(pts,faces))

# Keep only source head surfaces and its two eye meshes, removing no head detail.
head=bpy.data.objects['mewtwo_mesh_07'];bm=bmesh.new();bm.from_mesh(head.data);bm.faces.ensure_lookup_table()
src=S['mewtwo_mesh_07']
# Restore the whole source head as one rigid shape. The preliminary fit had
# pulled three attachment vertices down onto the donor conduit.
headmat=np.diag([9.6,9.,9.3]);headpivot=np.array(D['source']['bones']['Bone_47']['head'])
for v in bm.verts:
    v.co=headmat@(np.array(src['points'][v.index])-headpivot)+np.array([0,-.2554,16.2])
    if 'Bone_44' in src['vw'][v.index]:v.co.z-=.6
gone=[]
for f in bm.faces:
    bs=[int(max(src['vw'][v.index],key=src['vw'][v.index].get).split('_')[1]) for v in f.verts]
    if not all(b in [44,47,59] for b in bs):gone.append(f)
bmesh.ops.delete(bm,geom=gone,context='FACES');bm.to_mesh(head.data);bm.free();head.data.update()
for g in head.vertex_groups:g.remove(list(range(len(head.data.vertices))))
head.vertex_groups['JOBJ_43'].add(list(range(len(head.data.vertices))),1.,'REPLACE')
keep={'mewtwo_mesh_07','mewtwo_mesh_16','mewtwo_mesh_17','mewtwo_mesh_18','mewtwo_mesh_19','eyes_left','eyes_right'}
for ob in list(bpy.data.objects):
    if ob.type=='MESH' and ob.name not in keep:bpy.data.objects.remove(ob,do_unlink=True)
arm=bpy.data.objects['Armature']
# Variants discarded the real skin around the eyes. It is a border surface,
# not an alternate expression: its outside vertices meet the skull/muzzle and
# its inside vertices meet mesh_21. Restore the original piece and material.
with bpy.data.libraries.load(str(WORK / "mons" / 'mewtwo/1-load/models/1-150_Mewtwo.blend'),link=False) as (src,dst):
    dst.objects=['mewtwo_mesh_20']
surround=dst.objects[0];bpy.context.scene.collection.objects.link(surround)
local=np.array([v.co[:] for v in surround.data.vertices])
goal=(np.array(S['mewtwo_mesh_20']['points'])-headpivot)@headmat.T+np.array([0,-.2554,16.2])
fit=np.linalg.lstsq(np.column_stack([local,np.ones(len(local))]),goal,rcond=None)[0]
mat=np.eye(4);mat[:3,:]=fit.T
assert np.max(np.abs(np.column_stack([local,np.ones(len(local))])@fit-goal))<1e-4
surround.data.transform(Matrix(mat.tolist()));surround.parent=None;surround.matrix_world=Matrix.Identity(4)
surround.vertex_groups.clear();surround.vertex_groups.new(name='JOBJ_43').add(list(range(len(local))),1.,'REPLACE')
for mod in surround.modifiers:
    if mod.type=='ARMATURE':mod.object=arm
surround.data.uv_layers.active.name='UVMap'
print('Restored eye surround:',surround.name,len(surround.data.polygons),'stored normals:',surround.data.has_custom_normals)
# Retain the source neck's connecting strip. Its upper ring is the head's own
# boundary; omitting this strip leaves a visible gap beneath the jaw in game.
neck=bpy.data.objects['mewtwo_mesh_16'];source_neck=S['mewtwo_mesh_16']
native_neck=D['vanilla']['meshes']['Joint_0_Object_5']
neckfaces=[f for f in native_neck['faces'] if all(
    any(j in native_neck['vw'][i] for j in ['JOBJ_42','JOBJ_43']) for i in f)]
necktree=BVHTree.FromPolygons(native_neck['points'],neckfaces)
for v in neck.data.vertices:
    p=np.array(source_neck['points'][v.index]);upper='Bone_44' in source_neck['vw'][v.index]
    q=headmat@(p-headpivot)+np.array([0,-.2554,16.2])
    if upper:q[2]-=.6
    if not upper:
        at,_,fi,_=necktree.find_nearest(Vector(q));q=np.array(at)
        f=neckfaces[fi];tri=np.array(native_neck['points'])[f[:3]]
        bary=np.linalg.lstsq(np.vstack([tri.T,np.ones(3)]),np.r_[q,1],rcond=None)[0]
        bary=np.maximum(bary,0);bary/=bary.sum();weights={}
        for i,share in zip(f[:3],bary):
            for name,w in native_neck['vw'][i].items():weights[name]=weights.get(name,0)+share*w
    else:weights={'JOBJ_43':1.}
    v.co=q
    for g in neck.vertex_groups:g.remove([v.index])
    for joint,w in weights.items():
        (neck.vertex_groups.get(joint) or neck.vertex_groups.new(name=joint)).add([v.index],w,'REPLACE')
neck.data.materials.clear();neck.data.materials.append(materials['mewtwo_mat_7'])
for uv in neck.data.uv_layers.active.data:uv.uv=(.5,.9)
neck.data.update()
# Preserve the donor belly boundary, painted in the Colosseum palette. Its
# original shaded mask is a surface-layout guide, not a new design.
atlas=np.array(target_image('Mewtwo', 'Texture_0_CMP')).astype(float)
mask=np.clip((atlas[:,:,0]-atlas[:,:,1]+3)/38,0,1)
white=np.array([224.,224.,247.]);purple=np.array([137.,111.,155.])
atlas[:,:,:3]=white[None,None,:]*(1-mask[:,:,None])+purple[None,None,:]*mask[:,:,None]
Image.fromarray(atlas.round().astype('uint8')).save(ROOT/'body-palette.png')
bodymat=materials['mewtwo_mat_7'].copy();bodymat.name='mewtwo_body_palette'
bodyimage=bpy.data.images.load(str(ROOT/'body-palette.png'));bodyimage.pack()
for n in bodymat.node_tree.nodes:
    if n.type=='TEX_IMAGE':n.image=bodyimage
Image.new('RGBA',(8,8),(137,111,155,255)).save(ROOT/'tail-palette.png')
tailmat=materials['mewtwo_mat_11'].copy();tailmat.name='mewtwo_tail_palette'
tailimage=bpy.data.images.load(str(ROOT/'tail-palette.png'));tailimage.pack()
for n in tailmat.node_tree.nodes:
    if n.type=='TEX_IMAGE':n.image=tailimage
with bpy.data.libraries.load(str(ROOT/'vanilla.blend'),link=False) as (src,dst):
    dst.objects=[f'Joint_0_Object_{i}' for group in ids.values() for i in group]

def uv_at(point,ref):
    pts,faces,uvs,mats,tree=ref
    at,_,fi,_=tree.find_nearest(Vector(point));f=faces[fi]
    bary=np.linalg.lstsq(np.vstack([pts[f[:3]].T,np.ones(3)]),np.r_[np.array(at),1.],rcond=None)[0]
    bary=np.clip(bary,0,1);bary/=bary.sum()
    return bary@uvs[fi][:3],mats[fi]
for region,group in ids.items():
    for i in group:
        ob=bpy.data.objects[f'Joint_0_Object_{i}'];bpy.context.scene.collection.objects.link(ob)
        ob.name=f'mewtwo_surface_{region}_{i}'
        # Library-linked mesh dependencies are not evaluated in the scene yet.
        # Recover their exact original world transform from the recorded target,
        # then apply that transform to mesh data, including its stored normals.
        local=np.array([v.co[:] for v in ob.data.vertices]);world=np.array(D['vanilla']['meshes'][f'Joint_0_Object_{i}']['points'])
        fit=np.linalg.lstsq(np.column_stack([local,np.ones(len(local))]),world,rcond=None)[0]
        mat=np.eye(4);mat[:3,:]=fit.T
        assert np.max(np.abs(np.column_stack([local,np.ones(len(local))])@fit-world))<1e-4
        ob.data.transform(Matrix(mat.tolist()));ob.parent=None;ob.matrix_world=Matrix.Identity(4)
        for mod in ob.modifiers:
            if mod.type=='ARMATURE':mod.object=arm
        me=ob.data
        if region=='tube':
            names={g.index:g.name for g in ob.vertex_groups}
            for v in me.vertices:
                share=sum(g.weight for g in v.groups if names[g.group]=='JOBJ_43')
                v.co+=Vector((0,.25,.86))*share
        me.materials.clear();used={}
        uv=me.uv_layers.active
        for extra in list(me.uv_layers)[1:]:me.uv_layers.remove(extra)
        uv.name='UVMap'
        for p in me.polygons:
            mat='mewtwo_mat_11' if region=='tail' else 'mewtwo_mat_7'
            material=bodymat if i==0 else tailmat if region=='tail' else materials[mat]
            if mat not in used:used[mat]=len(me.materials);me.materials.append(material)
            p.material_index=used[mat]
            for li in p.loop_indices:
                if i!=0:uv.data[li].uv=(.5,.48) if region=='tail' else (.5,.9)
        me.update()
# Loading mesh dependencies also loads a second armature; it is not part of the
# output. Every surface modifier above now points to the original target rig.
for ob in list(bpy.data.objects):
    if ob.type=='ARMATURE' and ob!=arm:bpy.data.objects.remove(ob,do_unlink=True)
# Keep the rounded model within prep's 9,000-triangle limit. Automatic prep
# reduction collapsed every little facial/neck panel separately and opened
# seams. Reduce only the dense native body, with its seam vertices connected,
# before the prescribed round_out step. Source face topology remains intact.
donors=[ob for ob in bpy.context.scene.objects if ob.name.startswith('mewtwo_surface_')
        and not any(part in ob.name for part in ['_tail_','_tube_'])]
bpy.ops.object.select_all(action='DESELECT')
for ob in donors:ob.select_set(True)
bpy.context.view_layer.objects.active=donors[0]
bpy.ops.object.join()
body=bpy.context.view_layer.objects.active;body.name='mewtwo_surface_body'
bm=bmesh.new();bm.from_mesh(body.data)
bmesh.ops.remove_doubles(bm,verts=bm.verts[:],dist=0.0001)
bm.to_mesh(body.data);bm.free();body.data.update()
before=len(body.data.polygons)
reduce=body.modifiers.new('Mewtwo body surface budget','DECIMATE')
reduce.ratio=.48;reduce.use_collapse_triangulate=True
bpy.ops.object.modifier_move_to_index(modifier=reduce.name,index=0)
bpy.ops.object.modifier_apply(modifier=reduce.name)
print('Native body reduction before rounding:',before,'->',len(body.data.polygons),
      'stored normals:',body.data.has_custom_normals)
assert body.data.has_custom_normals,'Body reduction must carry its stored normals'
total=sum(len(o.data.polygons) for o in bpy.context.scene.objects if o.type=='MESH')
assert total*4<9000,total
print('After round_out expected triangles:',total*4)
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
print('Colosseum head retained; native anatomical body with Colosseum materials.')
