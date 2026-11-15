"""Rebuild Alakazam's fit from the source anatomy; keep the rip's surfaces/normals.

hand_alakazam_lean.py is the first pass, which the owner found too close to Zelda. The owner then asked for a bigger head and
a smaller neck, which is the source's too.

Chest and shoulder armour have independent scales, anatomical bends meet Zelda's
joints, hands keep their grip, and the removed spoons return on their wrists.
Run round_out.py after this script, then inspect before hand_finish.py.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
from collections import defaultdict
import bpy
import numpy as np
from mathutils import Vector
from PIL import Image

R = Path(str(WORK / ''))
H = R / 'hand/alakazam-Zelda'
B = H / '3-build'
SOURCE = R / 'mons/alakazam/1-load/models/1-065_Alakazam.blend'
src = json.loads((H / 'source-geometry.json').read_text(encoding='utf-8'))
old = json.loads((H / 'base-geometry.json').read_text(encoding='utf-8'))
S = {int(k.split('_')[1]): np.array(v['head']) for k, v in src['bones'].items()}
T = {int(k.split('_')[1]): np.array(v['head']) for k, v in old['bones'].items()}


def unit(v):
    return v / np.linalg.norm(v)


def rotation(a, b):
    return np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())


def segment(p, a, b, c, d, width):
    axis = unit(b - a)
    v = p - a
    along = v @ axis
    rot = rotation(axis, unit(d - c))
    return c + rot @ ((v - along * axis) * width + along * axis * np.linalg.norm(d - c) / np.linalg.norm(b - a))


def rigid(p, pivot, at, rot, scale):
    return at + rot @ ((p - pivot) * scale)


# The source's head is as big as its torso and has no neck: it sits level with the shoulders, in front of the chest, with
# its back flush with the chest's. Its top stays where it was, so it grows down over the neck.
HEAD_AT = T[89] + [0, -1.15, -.8]
HEAD_SCALE = 8.0
# Widths from the source against the head: an upper arm 12% of its width, a forearm 34%, heavy armour and big hands and feet.
# Zelda's arm is only about 6.5 of these long, so an arm near the head's scale is a little stubbier than the source's, never thin.
CHEST, SHOULDER, UPPER, FOREARM, HAND = 7.0, 6.0, 7.5, 7.5, 7.5
HIPS, THIGH, SHIN, FOOT = [6.4, 5.6, 5.5], 6.5, 5.6, [5.6, 6.4, 6.5]


def head(p):
    return HEAD_AT + (p - S[40]) * HEAD_SCALE


def moustache(p):
    sign = 1 if p[0] > 0 else -1
    root = S[47 if sign > 0 else 51]
    angle = np.radians(-50 * sign)
    c, s = np.cos(angle), np.sin(angle)
    rot = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    q = head(root) + rot @ (p - root) * HEAD_SCALE * .85
    # The source sweeps back toward the chest. Put that arc in front of the
    # snout so the broad ends read as a moustache from Melee's side camera.
    q[1] = head(root)[1] - (p[1] - root[1]) * 3.0
    return q


arm_specs = [(7, 8, 9, 11, 20, 72, 73, 76), (23, 24, 25, 27, 36, 100, 101, 104)]
arms = {}
for shoulder, upper, elbow, wrist, spoon, jupper, jelbow, jwrist in arm_specs:
    ru = rotation(unit(S[elbow] - S[upper]), unit(T[jelbow] - T[jupper]))
    # Forearm roll retains upright spoons and a closed grip in Zelda's T pose.
    a, b = unit(S[wrist] - S[elbow]), unit(T[jwrist] - T[jelbow])
    upa, upb = unit(np.array([0, 0, 1]) - a * a[2]), unit(np.array([0, 0, 1]) - b * b[2])
    rh = np.column_stack([b, np.cross(upb, b), upb]) @ np.column_stack([a, np.cross(upa, a), upa]).T
    arms[upper] = dict(shoulder=shoulder, upper=upper, elbow=elbow, wrist=wrist, spoon=spoon,
                       ju=jupper, je=jelbow, jw=jwrist, ru=ru, rh=rh)


def body_map(p, bone):
    if bone == 4:
        return T[4] + [0, .2, .2] + (p - S[4]) * HIPS, {4: 1}
    if bone == 5:
        q = np.array([p[0] * CHEST, (p[1] + .02) * CHEST * .86 - .2, 8.65 + (p[2] - .585) * 9.1])
        z = q[2]
        if z < 9.5:
            t = np.clip((z - 8.4) / 1.1, 0, 1)
            weights = {4: 1 - t, 66: t}
        else:
            t = np.clip((z - 9.5) / 1.2, 0, 1)
            weights = {66: 1 - t, 67: t}
        return q, weights
    if bone == 39:
        # The neck's lower ring is inside the chest now and stays with it. The
        # upper ring still shares the facial panels' transform.
        t = np.clip((.965 - p[2]) / .14, 0, 1)
        return head(p), {89: 1 - t, 67: t}
    if bone == 40:
        return head(p), {89: 1}
    if 47 <= bone <= 54:
        return moustache(p), {89: 1}
    for a in arms.values():
        if bone == a['shoulder']:
            at = T[a['ju']] + unit(T[a['je']] - T[a['ju']]) * .65
            return rigid(p, S[a['upper']], at, a['ru'], SHOULDER), {a['ju']: 1}
        if bone == a['upper']:
            # The source's shoulder cap covered an open arm root. Once the
            # cap is smaller, anchor that ring in the chest instead of letting
            # it swing free with the upper arm.
            axis = S[a['elbow']] - S[a['upper']]
            u = np.clip((p - S[a['upper']]) @ axis / (axis @ axis), 0, 1)
            start = T[a['ju']] + [-np.sign(T[a['ju']][0]) * .45, -.05, -.3]
            q = segment(p, S[a['upper']], S[a['elbow']], start, T[a['je']], UPPER)
            t = float(np.clip(u / .23, 0, 1))
            return q, {67: 1 - t, a['ju']: t}
        if bone == a['elbow']:
            # Same roll as the grip at its wrist end.
            axis = unit(S[a['wrist']] - S[a['elbow']])
            v = p - S[a['elbow']]
            along = v @ axis
            q = T[a['je']] + a['rh'] @ ((v - along * axis) * FOREARM + along * axis * np.linalg.norm(T[a['jw']] - T[a['je']]) / np.linalg.norm(S[a['wrist']] - S[a['elbow']]))
            return q, {a['je']: 1}
        if a['wrist'] <= bone <= a['spoon'] + 2:
            return rigid(p, S[a['wrist']], T[a['jw']], a['rh'], HAND), {a['jw']: 1}
    for hip, knee, ankle, jhip, jknee, jankle in [(55, 56, 58, 6, 7, 9), (64, 65, 67, 12, 13, 15)]:
        # The ankle ring meets the foot at the real ankle, not at a toe bone.
        if bone == hip:
            return segment(p, S[hip], S[knee], T[jhip], T[jknee], THIGH), {jhip: 1}
        if bone == knee:
            return segment(p, S[knee], S[ankle], T[jknee], T[jankle], SHIN), {jknee: 1}
        if ankle <= bone <= (63 if ankle == 58 else 72):
            q = T[jankle] + (p - S[ankle]) * FOOT
            return q, {jankle: 1}
    raise ValueError((bone, p))


def transform(p, weights):
    out, wout = np.zeros(3), defaultdict(float)
    for b, share in weights.items():
        q, w = body_map(p, int(b.split('_')[1]))
        out += q * share
        for j, v in w.items():
            wout[j] += share * v
    return out, dict(wout)


def rig(ob, weights):
    ob.vertex_groups.clear()
    for i, row in enumerate(weights):
        total = sum(row.values())
        for j, w in row.items():
            if w > 1e-6:
                name = f'JOBJ_{j}'
                (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i], float(w / total), 'REPLACE')


bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
im = bpy.data.images['tex_3ED4']
w, h = im.size
eye_atlas = np.uint8(np.clip(np.array(im.pixels[:]).reshape(h, w, 4)[::-1] * 255, 0, 255))
bpy.ops.wm.open_mainfile(filepath=str(B / 'base.blend'))
# Source and raw meshes have matching topology. Exact shared positions receive
# one result, so separate pieces remain joined at anatomical rings.
shared = defaultdict(list)
for name, ob in src['objects'].items():
    if name in ('foodin_mesh_09', 'foodin_mesh_23', 'foodin_mesh_24'):
        continue
    for p, weights in zip(ob['co'], ob['weights']):
        shared[tuple(np.round(p, 5))].append(transform(np.array(p), weights))
joined = {}
for key, entries in shared.items():
    weights = defaultdict(float)
    for _, ws in entries:
        for j, w in ws.items():
            weights[j] += w / len(entries)
    joined[key] = np.mean([q for q, _ in entries], axis=0), dict(weights)
for name, data in src['objects'].items():
    ob = bpy.data.objects.get(name)
    if ob is None:
        continue
    assert len(ob.data.vertices) == len(data['co']), name
    points, weights = zip(*(joined[tuple(np.round(p, 5))] for p in data['co']))
    ob.data.vertices.foreach_set('co', np.array(points).ravel())
    ob.data.update()
    rig(ob, weights)

# Recover source-space positions of the eye triangles from the raw head's
# affine fit; both eyes receive exactly the head's transform.
head_src = np.array(src['objects']['foodin_mesh_08']['co'])
head_old = np.array(old['objects']['foodin_mesh_08']['co'])
fit = np.linalg.lstsq(np.column_stack([head_src, np.ones(len(head_src))]), head_old, rcond=None)[0]
for name in ('eyes_left', 'eyes_right'):
    ob = bpy.data.objects[name]
    p = (np.array([v.co for v in ob.data.vertices]) - fit[3]) @ np.linalg.inv(fit[:3])
    # Rounding the head buried the pupil region 0.01--0.02 units under its
    # forehead while leaving the white corner visible. The UV crop is right;
    # offset the whole eye overlay just outside the curved head instead.
    sign = 1 if p[:, 0].mean() > 0 else -1
    eye_clearance = np.array([sign * .055, -.055, .008]) * HEAD_SCALE / 6
    ob.data.vertices.foreach_set('co', np.array([head(v) + eye_clearance for v in p]).ravel())
    ob.data.update()
    rig(ob, [{89: 1}] * len(p))

# Restore the source's real closed tile (64 pixels right of open), keeping the
# already correct open UV crop. No colour-managed texture render is involved.
Image.fromarray(eye_atlas[13:51, 70:120]).save(B / 'eyes/closed.png')
record = json.loads((B / 'eyes.json').read_text(encoding='utf-8'))
record['made']['closed'] = 'source tex_3ED4: real closed eye, open crop translated +64 pixels in X'
record['notes'] = ['Alakazam hand port restores the real closed eye tile; the open crop is preserved.']
(B / 'eyes.json').write_text(json.dumps(record, indent=2), encoding='utf-8')

# Bring back both real spoons, with their original mesh, UVs and normals.
with bpy.data.libraries.load(str(SOURCE), link=False) as (available, loaded):
    loaded.objects = ['foodin_mesh_23', 'foodin_mesh_24']
for ob in loaded.objects:
    bpy.context.scene.collection.objects.link(ob)
    data = src['objects'][ob.name]
    a = arms[24 if ob.name.endswith('23') else 8]
    # Shrink the long bind-pose spoon about its grip, not about its wrist.
    p = np.array(data['co'])
    pivot = S[a['spoon']]
    p = pivot + (p - pivot) * .72
    moved = np.array([rigid(v, S[a['wrist']], T[a['jw']], a['rh'], HAND) for v in p])
    ob.parent = None
    ob.matrix_world = np.eye(4).tolist()
    ob.data.vertices.foreach_set('co', moved.ravel())
    ob.data.update()
    ob.modifiers.clear()
    ob.modifiers.new('Armature', 'ARMATURE').object = bpy.data.objects['Armature']
    rig(ob, [{a['jw']: 1}] * len(p))

# The knee-tip decals carry glTF texture transforms that prep does not read.
for name, offset, sx in [('foodin_mesh_19', .552, -1), ('foodin_mesh_20', -.448, 1)]:
    ob = bpy.data.objects[name]
    for uv in ob.data.uv_layers.active.data:
        uv.uv = (uv.uv.x * sx + offset, uv.uv.y - .141667)
    for mat in ob.data.materials:
        for node in mat.node_tree.nodes:
            if node.type == 'MAPPING':
                node.inputs['Location'].default_value = (0, 0, 0)
                node.inputs['Scale'].default_value = (1, 1, 1)

bpy.ops.wm.save_as_mainfile(filepath=str(B / 'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B / 'edited.blend'))
print('Alakazam: big head on no neck, armour and hands at the source proportions, swept moustache, closed grips and two spoons.')
