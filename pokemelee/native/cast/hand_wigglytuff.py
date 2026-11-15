"""Restore Wigglytuff's continuous body and source eye UVs; atlas the body for Kirby's one static DObj.

The source's abdomen was spread over Kirby's independent feet. It belongs to his squashable ball joint instead.
Ears and curl follow that same joint. Keep one animated face object at Kirby's eye texture slot, with original
Colosseum open/half/closed tiles. The mouth remains the original smile on the body atlas.
"""

from cast_paths import WORK, TARGETS
import json
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image

R = Path(str(WORK / ''))
H = R / 'hand/wigglytuff-Kirby'
B = H / '3-build'
from rigswap.plugins.melee.prep.textures import read_pixels


def coordinates(ob):
    return np.array([ob.matrix_world @ v.co for v in ob.data.vertices])


def rigid(ob, joint):
    ob.vertex_groups.clear()
    ob.vertex_groups.new(name=joint).add(list(range(len(ob.data.vertices))), 1, 'REPLACE')


def material(name, pixels, path):
    Image.fromarray(pixels, 'RGBA').save(path)
    im = bpy.data.images.load(str(path), check_existing=False)
    im.name = name
    im.pack()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = True
    shader = m.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Roughness'].default_value = 1
    tex = m.node_tree.nodes.new('ShaderNodeTexImage')
    tex.image = im
    tex.extension = 'EXTEND'
    m.node_tree.links.new(tex.outputs['Color'], shader.inputs['Base Color'])
    m.node_tree.nodes.active = tex
    return m


bpy.ops.wm.open_mainfile(filepath=str(R / 'mons/wigglytuff/1-load/models/1-040_Wigglytuff.blend'))
source = {}
for ob in bpy.data.objects:
    if ob.type != 'MESH':
        continue
    image = next(n.image for n in ob.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE')
    source[ob.name] = dict(points=coordinates(ob), faces=[list(p.vertices) for p in ob.data.polygons],
                           uv=np.array([l.uv for l in ob.data.uv_layers.active.data]),
                           pixels=read_pixels(image), image=image.name)

bpy.ops.wm.open_mainfile(filepath=str(B / 'base.blend'))
# Curl is an unchanged rigid head piece: its correspondence gives exactly the head's source-to-build transform.
curl = source['pukurin_mesh_09']['points']
transform = np.linalg.lstsq(np.column_stack([curl, np.ones(len(curl))]),
                           coordinates(bpy.data.objects['pukurin_mesh_09']), rcond=None)[0]
assert np.max(np.abs(np.column_stack([curl,np.ones(len(curl))]) @ transform -
                     coordinates(bpy.data.objects['pukurin_mesh_09']))) < 1e-4
for ob in list(bpy.data.objects):
    if ob.name in ('eyes_left', 'eyes_right', 'pukurin_mesh_08'):
        bpy.data.objects.remove(ob, do_unlink=True)

src = source['pukurin_mesh_08']
me = bpy.data.meshes.new('wigglytuff_eyes')
me.from_pydata(src['points'].tolist(), [], src['faces'])
ob = bpy.data.objects.new('wigglytuff_eyes', me)
bpy.context.scene.collection.objects.link(ob)
mod = ob.modifiers.new('Armature', 'ARMATURE')
mod.object = bpy.data.objects['Armature']
uv = me.uv_layers.new(name='UVMap')
for l,q in zip(uv.data,src['uv']):
    l.uv = q

for ob in list(bpy.data.objects):
    if ob.type != 'MESH':
        continue
    name = 'pukurin_mesh_08' if ob.name == 'wigglytuff_eyes' else ob.name
    if name not in source:
        continue
    if name != 'pukurin_mesh_15':
        pts = source[name]['points']
        pts = np.column_stack([pts,np.ones(len(pts))]) @ transform
        ob.matrix_world = np.eye(4).tolist()
        ob.data.vertices.foreach_set('co', pts.ravel())
        rigid(ob, 'JOBJ_6')
    else:
        # Extend the arms' inner ends beneath the narrower Wigglytuff torso. Their tips and Kirby's rig stay put.
        groups = {g.index:g.name for g in ob.vertex_groups}
        for sign, names in [(1, {'JOBJ_24','JOBJ_25'}), (-1, {'JOBJ_29','JOBJ_30'})]:
            verts = [v for v in ob.data.vertices if any(groups[g.group] in names and g.weight > 0 for g in v.groups)]
            xs = [sign*v.co.x for v in verts]
            lo,hi = min(xs),max(xs)
            for v in verts:
                t = (sign*v.co.x-lo)/(hi-lo)
                v.co.x = sign*(2.85+t*(hi-2.85))
    if 'custom_normal' in ob.data.attributes:
        ob.data.attributes.remove(ob.data.attributes['custom_normal'])
    if 'rigswap_loose' in ob.data.attributes:
        ob.data.attributes.remove(ob.data.attributes['rigswap_loose'])
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.update()

# Eye UV box is sampled under the source's CLAMP, without moving triangles by whole tiles.
eye = bpy.data.objects['wigglytuff_eyes']
eye_src = source['pukurin_mesh_08']
eye_pixels = eye_src['pixels']
eye_origin = np.array([-40,-8])
eye_size = np.array([144,104])
for state,dy in [('open',0),('half',128),('closed',384)]:
    xs = np.clip(np.arange(eye_size[0])+eye_origin[0], 0,63)
    ys = np.clip(np.arange(eye_size[1])+eye_origin[1], 0,103)+dy
    pic = eye_pixels[np.clip(ys,0,511)[:,None],xs]
    path = B / 'eyes' / f'{state}.png'
    path.parent.mkdir(exist_ok=True)
    Image.fromarray(pic, 'RGBA').save(path)
    if state == 'open':
        eye_mat = material('wigglytuff_face', pic, path)
for l,q in zip(eye.data.uv_layers.active.data,eye_src['uv']):
    pixel = np.array([q[0]*64,(1-q[1])*512])
    qnew = (pixel-eye_origin)/eye_size
    l.uv = (qnew[0],1-qnew[1])
eye.data.materials.clear()
eye.data.materials.append(eye_mat)

# Pack finite sampled regions with four texels of clamped padding. Affine UV remapping retains original resolution.
body = [ob for ob in bpy.data.objects if ob.type == 'MESH' and ob != eye]
by_image = {}
for ob in body:
    rec = source[ob.name]
    by_image.setdefault(rec['image'], []).append(ob)
tiles = []
for key, objects in by_image.items():
    pix = source[objects[0].name]['pixels']
    h,w = pix.shape[:2]
    q = np.concatenate([source[ob.name]['uv'] for ob in objects])
    q = q * [w,-h] + [0,h]
    start = np.floor(q.min(0)).astype(int)-4
    end = np.ceil(q.max(0)).astype(int)+4
    xs = np.clip(np.arange(start[0],end[0]),0,w-1)
    ys = np.clip(np.arange(start[1],end[1]),0,h-1)
    tile = pix[ys[:,None],xs]
    tiles.append((key,objects,tile,start,np.array([w,h])))
tiles.sort(key=lambda r:-r[2].shape[0])
atlas = np.empty((256,512,4),np.uint8)
atlas[:] = source['pukurin_mesh_14']['pixels'][0,0]
x=y=row_h=0
record=[]
for key,objects,tile,start,size in tiles:
    h,w = tile.shape[:2]
    if x+w>512:
        x=0; y+=row_h; row_h=0
    assert y+h<=256, (key,w,h,x,y)
    atlas[y:y+h,x:x+w]=tile
    for ob in objects:
        for l,q in zip(ob.data.uv_layers.active.data,source[ob.name]['uv']):
            pixel = q*size*[1,-1]+[0,size[1]]
            new = (pixel-start+[x,y])/[512,256]
            l.uv=(new[0],1-new[1])
    record.append(dict(image=key,at=[x,y],size=[w,h],source_origin=start.tolist()))
    x+=w; row_h=max(row_h,h)
mat = material('wigglytuff_body_atlas',atlas,B/'wigglytuff-atlas.png')
for ob in body:
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.material_index=0
bpy.ops.object.select_all(action='DESELECT')
for ob in body:
    ob.select_set(True)
bpy.context.view_layer.objects.active=body[0]
bpy.ops.object.join()
bpy.context.object.name='wigglytuff_body'
# The rip splits one smooth surface at material boundaries. Share normals across those coincident boundaries.
meshes=[bpy.context.object,eye]
normal_sum={}
for ob in meshes:
    co=coordinates(ob)
    for p in ob.data.polygons:
        a,b,c=co[list(p.vertices)[:3]]
        n=np.cross(b-a,c-a)
        for v in p.vertices:
            key=tuple(np.round(co[v],4))
            normal_sum[key]=normal_sum.get(key,np.zeros(3))+n
for ob in meshes:
    co=coordinates(ob)
    normals=[]
    for l in ob.data.loops:
        n=normal_sum[tuple(np.round(co[l.vertex_index],4))]
        normals.append((n/max(np.linalg.norm(n),1e-10)).tolist())
    ob.data.normals_split_custom_set(normals)
eyes_record = dict(objects=[dict(name=eye.name,side=None,surfaces=['original pukurin_mesh_08'],triangles=34)],
                   material=eye_mat.name,image='wigglytuff_face',eye_texture_size=eye_size.tolist(),
                   frames={s:f'eyes/{s}.png' for s in ('open','half','closed')},
                   made={s:f'Colosseum eye atlas, row offset {dy}, clamped source UVs' for s,dy in [('open',0),('half',128),('closed',384)]},
                   notes=['Both eyes on the first animated eye slot (5); no left/right UV shifts. Mouth is the source smile.'])
(B/'eyes.json').write_text(json.dumps(eyes_record,indent=2),encoding='utf-8')
(B/'loose.json').write_text(json.dumps(dict(attribute='rigswap_loose',chains=[])),encoding='utf-8')
(B/'wigglytuff-hand.json').write_text(json.dumps(dict(atlas=record,head_transform=transform.tolist(),
    body_joint='JOBJ_6',mouth='static source smile',arm_roots=2.85),indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
shutil.copyfile(B/'build.blend',B/'edited.blend')
print('Saved hand edit: one static body atlas, original animated eye surface, continuous squashable body.')
