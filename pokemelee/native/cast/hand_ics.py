"""Build Jynx/Popo or Smoochum/Nana by hand from the Colosseum source.

The source sets the silhouette. One scale for head and body; only arms/legs
reach the fighter's joints. Original corner normals are transported, not rebuilt.
Usage: python hand_ics.py jynx|smoochum
"""

from cast_paths import WORK, TARGETS
import json
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Vector
from ics_runtime import enable, helpers, ROOT, TARGETS
enable()
from rigswap.core import eyes

mon = sys.argv[1]
fighter = {'jynx': 'Popo', 'smoochum': 'Nana'}[mon]
home = ROOT / 'hand' / f'{mon}-{fighter}'
build = home / '3-build'
build.mkdir(parents=True, exist_ok=True)
source = next((ROOT / 'mons' / mon / '1-load/models').glob('*.blend'))
v = helpers('hand_view.py')
C = v['C']
rest, frame = v['rests'](fighter), v['frame'](fighter, 'Wait1-1')
M = {j: C @ frame[j] @ np.linalg.inv(rest[j]) @ np.linalg.inv(C) for j in rest}
TB = {j: (C @ m)[:3, 3] for j, m in frame.items()}
SCALE = 7.7 if mon == 'jynx' else 21.0
yaw = np.arctan2(M[4][1, 0], M[4][0, 0])
R = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1.]])

bpy.ops.wm.open_mainfile(filepath=str(source))
source_arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
SB = {int(b.name.split('_')[1]): np.array(source_arm.matrix_world @ b.head_local) for b in source_arm.data.bones}
offset = np.array([TB[4][0], TB[4][1], .04])

if mon == 'jynx':
    for name in ('rougela_mesh_10', 'rougela_mesh_21'):
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

# The complete eye-bearing source surface, with real CLAMP atlas frames.
ename, texture, pitch, half, shut = (('rougela_mesh_14', 'tex_3B08', 24, 24, 48)
    if mon == 'jynx' else ('muchul_mesh_02', 'tex_2F10', 48, 96, 192))
eye = bpy.data.objects[ename]
surf = eyes.Surface(1, eye, 0, list(range(len(eye.data.polygons))), texture)
rec = eyes.make_fixed(build, [surf], {texture: eyes._pixels(bpy.data.images[texture])},
                      {'band': pitch, 'half': [0, half], 'closed': [0, shut]})
(build / 'eyes.json').write_text(json.dumps(rec, indent=1), encoding='utf-8')


def body(p):
    return offset + R @ (p * SCALE)


def segment(p, a, b, c, d, stretch=True):
    axis = (b - a) / np.linalg.norm(b - a)
    rot = np.array(Vector(axis).rotation_difference(Vector(d - c)).to_matrix())
    length = np.linalg.norm(d - c) / np.linalg.norm(b - a) if stretch else SCALE
    A = rot @ (SCALE * np.eye(3) + (length - SCALE) * np.outer(axis, axis))
    return c + A @ (p - a), A


def weights(w):
    w = {j: float(a) for j, a in w.items() if a > 1e-6}
    total = sum(w.values())
    return {j: a / total for j, a in w.items()}


def mapped(p, b):
    A = R * SCALE
    if mon == 'jynx':
        for arm, target in (([4, 6, 10, 12, 13], [9, 10, 11, 14]), ([14, 16, 20, 22, 23], [24, 25, 26, 29])):
            s, e, wrist, tip, sleeve = arm
            upper, lower, hand, have = target
            if b in (s, s+1, sleeve):
                q, lin = segment(p, SB[s], SB[e], body(SB[s]), TB[lower])
                return q, {upper: 1}, lin
            if b in (e, e+1, e+2, e+3):
                q, lin = segment(p, SB[e], SB[wrist], TB[lower], TB[hand])
                return q, {lower: 1}, lin
            if b in (wrist, wrist+1, tip):
                q, lin = segment(p, SB[wrist], SB[tip], TB[hand], TB[have], False)
                return q, {hand: 1}, lin
        if 25 <= b <= 96:
            # Head, lips, crown and all hair keep one shared transform.
            return body(p), {19: 1}, A
        if b >= 97 or p[2] < .55:
            # Original skirt: waist on hips, lower hem on the rotation root.
            # Keeping its own hem off the floor avoids artificial trouser legs.
            waist = float(np.clip((p[2] - .06) / .49, 0, 1))
            return body(p), weights({3: 1-waist, 4: waist}), A
        spine = float(np.clip((p[2] - .50) / .17, 0, 1))
        return body(p), weights({4:1-spine, 5:spine}), A
    for src, target in (([42, 43, 44, 45], [9, 10, 11, 14]), ([46, 47, 48, 49], [24, 25, 26, 29])):
        s, e, wrist, tip = src
        upper, lower, hand, have = target
        if b not in src:
            continue
        axis = SB[tip] - SB[s]
        t = float((p - SB[s]) @ axis / (axis @ axis))
        cross = p - SB[s] - t*axis
        palm = TB[hand] + (TB[have]-TB[hand]) / np.linalg.norm(TB[have]-TB[hand]) * .55
        path = [body(SB[s]), TB[lower], TB[hand], palm]
        knots = [0., .42, .78, 1.]
        k = min(max(np.searchsorted(knots, t, side='right')-1, 0), 2)
        u = (t-knots[k])/(knots[k+1]-knots[k])
        tangent = path[k+1]-path[k]
        rot = np.array(Vector(axis).rotation_difference(Vector(tangent)).to_matrix())
        q = path[k]*(1-u)+path[k+1]*u + rot @ (cross*SCALE)
        # Soft transitions on the actual surface, not independent scraps.
        if t < .42:
            blend = float(np.clip((t-.23)/.30,0,1))
            w = {upper:1-blend,lower:blend}
        else:
            blend = float(np.clip((t-.61)/.30,0,1))
            w = {lower:1-blend,hand:blend}
        return q, weights(w), rot*SCALE
    if 5 <= b <= 41:
        return body(p), {19: 1}, A
    for src, dst in (([55, 57], [36, 37, 39]), ([50, 52], [42, 43, 45])):
        thigh, ankle = src
        a, k, foot = dst
        if thigh <= b <= ankle+2:
            return body(p), {foot: 1}, A
    return body(p), ({4:1} if b==2 else {5:1}), A


rows, saved = [], {}
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.polygons)]
for ob in meshes:
    mw = ob.matrix_world.copy()
    # Blender transforms custom normals with the mesh transform.
    ob.data.transform(mw)
    ob.parent = None
    ob.matrix_world = Matrix.Identity(4)
    normals = np.array([n.vector[:] for n in ob.data.corner_normals])
    saved[ob.name] = normals
    for vertex in ob.data.vertices:
        p = np.array(vertex.co)
        own = max(vertex.groups, key=lambda g:g.weight)
        b = int(ob.vertex_groups[own.group].name.split('_')[1])
        q, w, lin = mapped(p, b)
        rows.append((ob, vertex.index, p, q, w, lin))
    for mod in list(ob.modifiers):
        ob.modifiers.remove(mod)

# Common source seams receive exactly one position and envelope.
seams = {}
for index, row in enumerate(rows):
    seams.setdefault(tuple(np.round(row[2], 6)), []).append(index)
normal_xform = {}
for members in seams.values():
    q = np.mean([rows[i][3] for i in members], axis=0)
    A = np.mean([rows[i][5] for i in members], axis=0)
    w = {}
    for i in members:
        for j, share in rows[i][4].items():
            w[j] = w.get(j, 0) + share/len(members)
    w = weights(dict(sorted(w.items(), key=lambda x:-x[1])[:4]))
    skin = sum(share*M[j] for j, share in w.items())
    bound = np.linalg.solve(skin, np.r_[q, 1])[:3]
    linear = np.linalg.inv(skin[:3,:3]) @ A
    for i in members:
        ob, vi = rows[i][:2]
        ob.data.vertices[vi].co = bound
        normal_xform[ob.name, vi] = np.linalg.inv(linear).T
        for group in ob.vertex_groups:
            group.remove([vi])
        for j, share in w.items():
            name = f'JOBJ_{j}'
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([vi], share, 'REPLACE')

bpy.data.objects.remove(source_arm, do_unlink=True)
with bpy.data.libraries.load(str(TARGETS/f'{fighter}.blend'), link=False) as (data_from, data_to):
    data_to.objects = ['Armature']
arm = data_to.objects[0]
bpy.context.scene.collection.objects.link(arm)
arm.name = 'Armature'
bpy.context.view_layer.update()
for ob in meshes:
    values = np.array([normal_xform[ob.name, l.vertex_index] @ saved[ob.name][l.index] for l in ob.data.loops])
    values /= np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-9)
    ob.data.normals_split_custom_set(values.tolist())
    ob.data.update()
    for g in list(ob.vertex_groups):
        if not g.name.startswith('JOBJ_'):
            ob.vertex_groups.remove(g)
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()
    ob.matrix_world = Matrix.Identity(4)
    # Export's normal and UV paths use UVMap.
    if ob.data.uv_layers:
        ob.data.uv_layers.active.name = 'UVMap'
for im in bpy.data.images:
    if im.size[0] and not im.packed_file:
        im.pack()
(build/'target.json').write_text(json.dumps({'name':fighter, 'skeleton':str(TARGETS/f'{fighter}.glb')}), encoding='utf-8')
(home/'design.json').write_text(json.dumps({'source':str(source), 'scale':SCALE,
    'head_scale':SCALE, 'body_scale':SCALE, 'target':str(TARGETS), 'idle':'Wait1-1',
    'dropped':['rougela_mesh_10','rougela_mesh_21'] if mon=='jynx' else [],
    'normals':'source corner normals transported through binding; never recomputed'}, indent=1), encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(build/'base.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(build/'edited.blend'))
print(mon, 'saved', len(rows), 'vertices; scale', SCALE, flush=True)
