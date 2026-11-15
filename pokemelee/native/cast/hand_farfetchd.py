"""Hand port from the preserved raw base: wing arms, proper ankles and a sword-bone leek.

The source is asymmetrically posed. Its wing roots 21/35 were never paired, so the
raw run left both on the chest; its foot joints 49/62 were mistaken for knees.
Keep the fighter skeleton unchanged and move the author's actual skin into it.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

R = Path(str(WORK / ''))
H = R / 'hand/farfetchd-YoungLink'
B = H / '3-build'
SOURCE = R / 'mons/farfetchd/1-load/models/1-083_Farfetchd.blend'
slots = json.loads((Path(str(TARGETS / '')) / 'YoungLink.weapons.json').read_text(encoding='utf-8'))


def points(ob):
    return np.array([ob.matrix_world @ v.co for v in ob.data.vertices])


def bone_weights(ob):
    names = {g.index: g.name for g in ob.vertex_groups}
    return [{names[g.group]: g.weight for g in v.groups if g.weight > 0} for v in ob.data.vertices]


def rotate(a, b):
    return np.array(Vector(a).normalized().rotation_difference(Vector(b).normalized()).to_matrix())


def unit(v):
    return v / np.linalg.norm(v)


def segment(a, b, c, d, width):
    """One affine move whose two joint positions match and whose cross section keeps its size."""
    direction = (b - a) / np.linalg.norm(b - a)
    along = np.linalg.norm(d - c) / np.linalg.norm(b - a)
    linear = rotate(b - a, d - c) @ (np.eye(3) * width + np.outer(direction, direction) * (along - width))
    # The little source joints sit inside much larger skin pieces. Extrapolating
    # their axial stretch past either joint makes spikes out of that extra skin.
    return linear, c - linear @ a, (a, direction, np.linalg.norm(b-a), along, width, (d-c)/np.linalg.norm(d-c))


def rigid(a, c, scale, rotation=None):
    linear = (np.eye(3) if rotation is None else rotation) * scale
    return linear, c - linear @ a


def apply(p, transform):
    linear, shift = transform[:2]
    result = linear @ p + shift
    if len(transform) == 3:
        a, direction, length, along, width, out = transform[2]
        axial = np.dot(p-a, direction)
        excess = axial - np.clip(axial, 0, length)
        result += out * excess * (width-along)
    return result


def write_skin(ob, p, weights):
    assert len(ob.data.vertices) == len(p), ob.name
    ob.data.vertices.foreach_set('co', np.asarray(p).ravel())
    ob.vertex_groups.clear()
    for i, shares in enumerate(weights):
        for name, w in shares.items():
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i], w, 'REPLACE')
    ob.data.update()


bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
sj = {b.name: np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
skin = {o.name: (points(o), bone_weights(o)) for o in bpy.context.scene.objects if o.type == 'MESH'}
bpy.ops.wm.open_mainfile(filepath=str(B / 'base.blend'))
arm = bpy.data.objects['Armature']
tj = {b.name: np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
S = lambda n: sj[f'Bone_{n:02d}']
T = lambda n: tj[f'JOBJ_{n}']
transforms, owners = {}, {}


def assign(source, target, transform):
    transforms[f'Bone_{source:02d}'] = transform
    owners[f'Bone_{source:02d}'] = f'JOBJ_{target}'


# Recover the split eye geometry's original coordinates from the raw head's exact
# affine move, using only its vertices that have not been seam blended.
original, sw = skin['kamonegi_mesh_00']
raw = bpy.data.objects['kamonegi_mesh_00']
rp, rw = points(raw), bone_weights(raw)
head = [i for i, w in enumerate(sw) if w.get('Bone_06') == 1 and rw[i].get('JOBJ_42', 0) > .99999]
fit = np.linalg.lstsq(np.column_stack([original[head], np.ones(len(head))]), rp[head], rcond=None)[0]
assert np.max(np.abs(np.column_stack([original[head], np.ones(len(head))]) @ fit - rp[head])) < 1e-4
eye_source = {n: (points(bpy.data.objects[n]) - fit[3]) @ np.linalg.inv(fit[:3]) for n in ('eyes_left', 'eyes_right')}

# The compact body keeps Farfetch'd's round breast. Head and beak are one rigid
# unit; the source's joints inside the beak are expression bones, not a neck.
hips, middle = T(4) + [0, 0, -2.5], T(17) + [0, 0, -1]
chest = T(18) + [0, 0, 1.2]
head_at = T(42) + [0, 0, -.7]
assign(3, 4, segment(S(3), S(4), hips, middle, 22))
assign(4, 17, segment(S(4), S(5), middle, chest, 22))
assign(5, 18, segment(S(5), S(6), chest, head_at, 22))
head_transform = rigid(S(6), head_at, 16)
for n in (6, 13, 14, 15, 16, 17, 18, 19):
    assign(n, 42, head_transform)
assign(45, 4, rigid(S(3), hips, 22))

# Four authored wing joints are shoulder attachment, upper arm, forearm, palm.
# Feather digits retain their silhouette as a single hand rather than becoming
# thin human fingers. Their shared seam vertices are blended below.
for source, target in [([21, 22, 23, 24], [19, 21, 22, 25]),
                       ([35, 36, 37, 38], [53, 55, 56, 59])]:
    destination = [T(n).copy() for n in target]
    destination[0] += [0, 0, -.65]
    palm = source[-1]
    fingers = [26, 27, 28, 29, 31, 32, 33, 34] if palm == 24 else [40, 41, 42, 44]
    # The palm's long axis, from the wrist into its feather fan.
    direction = np.mean([S(n) for n in fingers], axis=0) - S(palm)
    out = T(target[-1]) - T(target[-2])
    hand_transform = rigid(S(palm), T(target[-1]), 12, rotate(direction, out))
    for k in range(3):
        assign(source[k], target[k], segment(S(source[k]), S(source[k+1]),
            destination[k], destination[k+1], 14))
    for n in [palm] + fingers:
        assign(n, target[-1], hand_transform)

# Proper foot joints: 49/62 are ankles, 51/64 are toes. Rotate the asymmetric
# source feet to face forward; keep their broad webbing and put each sole at z=0.
legp, legw = skin['kamonegi_mesh_05']
for source, target, tip in [([47, 48, 49, 51], [6, 7, 9, 10], 'Bone_53_FootLeft'),
                             ([60, 61, 62, 64], [12, 13, 15, 16], 'Bone_66_FootRight')]:
    ankle = S(source[2])
    forward = sj[tip] - ankle
    forward[2] = 0
    rotation = rotate(forward, np.array([0, -1, 0]))
    foot = rigid(ankle, T(target[2]), 18, rotation)
    ids = [i for i, w in enumerate(legw) if any(f'Bone_{n:02d}' in w for n in source[2:])]
    sole = min(apply(legp[i], foot)[2] for i in ids)
    foot = foot[0], foot[1] - [0, 0, sole]
    ankle_at = apply(ankle, foot)
    assign(source[0], target[0], segment(S(source[0]), S(source[1]), T(target[0]), T(target[1]), 16))
    assign(source[1], target[1], segment(S(source[1]), ankle, T(target[1]), ankle_at, 16))
    for n in source[2:]:
        assign(n, target[2], foot)

# Hold the white stem near its end, leaving the leaves along the blade's axis.
# The whole prop rides JOBJ_27; no hip weights and no second vanilla sword.
axis = S(56) - S(55)
axis /= np.linalg.norm(axis)
grip = S(55) - axis * .12
weapon = rigid(grip, T(27), 17, rotate(axis, T(28)-T(27)))
for n in (54, 55, 56, 57, 59):
    assign(n, 27, weapon)

# Average the source's coincident seams before deforming. This includes the
# reversed inner wing surfaces, keeping both sides on exactly the same skin.
places = {}
for name, (p, ws) in skin.items():
    if name == 'kamonegi_mesh_09':
        continue
    for i, (pos, w) in enumerate(zip(p, ws)):
        key = tuple(pos.round(5))
        places.setdefault(key, []).append((name, i, w))
blended = {}
for key, rows in places.items():
    total = {}
    for _, _, ws in rows:
        for n, w in ws.items():
            total[n] = total.get(n, 0) + w / len(rows)
    for name, i, _ in rows:
        blended[name, i] = total

for name, (p, _) in skin.items():
    if name == 'kamonegi_mesh_09':
        continue
    q, weights = [], []
    for i, pos in enumerate(p):
        w = blended[name, i]
        q.append(sum(share * apply(pos, transforms[n]) for n, share in w.items()))
        renamed = {}
        for n, share in w.items():
            renamed[owners[n]] = renamed.get(owners[n], 0) + share
        weights.append(renamed)
    write_skin(bpy.data.objects[name], q, weights)
for name, p in eye_source.items():
    write_skin(bpy.data.objects[name], [apply(pos, head_transform) for pos in p], [{'JOBJ_42': 1}] * len(p))

(B / 'weapons_replaced.json').write_text(json.dumps([slots['weapons'][0], slots['weapons'][1]], indent=1), encoding='utf-8')
(H / 'hand-changes.json').write_text(json.dumps(dict(source=str(SOURCE), owners=owners,
    head_scale=16, torso_width=22, wing_width=14, foot_scale=18, leek_scale=17,
    notes=['Original source wing chains mapped to arms.', 'Ankles 49/62 corrected; soles grounded.',
           'One rigid head/beak with smaller scale.', 'Leek on sword bone JOBJ_27.',
           'Both wings are plain arms (owner, 10-31: the wing as a shield did not work).',
           'Both vanilla sword and shield slots replaced, so the shield is gone.']), indent=1), encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(B / 'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B / 'edited.blend'))
print('Saved Farfetchd hand port')
