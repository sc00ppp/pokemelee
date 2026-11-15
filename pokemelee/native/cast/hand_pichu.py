"""Colosseum Pichu on Melee Pichu, retaining the source's anatomy and atlas.

Run with the rigswap bpy Python. Output is edited.blend; round_out and
hand_finish are separate, unmodified final steps. No source/run edits.
"""

from cast_paths import WORK, TARGETS
import ast
import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from PIL import Image

ROOT = Path(str(WORK / 'hand/pichu-Pichu'))
BUILD = ROOT / '3-build'
SOURCE = str(WORK / "mons" / 'pichu/1-load/models/1-172_Pichu.blend')
D = json.loads((ROOT / 'inspection.json').read_text(encoding='utf-8'))
S = D['source']['meshes']
SB = {n: np.array(b['head']) for n, b in D['source']['bones'].items()}
helper = ROOT.parents[1] / 'tools/hand_view.py'
tree = ast.parse(helper.read_text(encoding='utf-8'))
tree.body = tree.body[:-1]
ns = {}
exec(compile(tree, str(helper), 'exec'), ns)
C = ns['C']
rest, frame = ns['rests']('Pichu'), ns['frame']('Pichu', 'Wait1-1')
M = {j: C @ frame[j] @ np.linalg.inv(rest[j]) @ np.linalg.inv(C) for j in rest}
TB = {j: (C @ frame[j])[:3, 3] for j in frame}
SCALE = 74.0
yaw = np.arctan2(M[5][1, 0], M[5][0, 0])
R = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])


def body(p):
    return TB[4] + R @ ((p - SB['Bone_01']) * SCALE)


def head(p):
    return TB[15] + M[15][:3, :3] @ ((p - SB['Bone_16']) * SCALE)


def segment(a, b, c, d, stretch=True):
    axis = b - a
    length = np.linalg.norm(axis)
    axis /= length
    rotation = np.array(Vector(axis).rotation_difference(Vector(d - c)).to_matrix())
    longitudinal = np.linalg.norm(d - c) / length if stretch else SCALE
    linear = rotation @ (SCALE * np.eye(3) + (longitudinal - SCALE) * np.outer(axis, axis))
    return lambda p: c + linear @ (p - a)


arms = {}
for src, dst, end in [([4, 5, 6, 7], [9, 10, 11, 12, 13], 'Bone_09_HandLeft'),
                      ([10, 11, 12, 13], [25, 26, 27, 28, 29], 'Bone_15_HandRight')]:
    a, b, c, d = [SB[f'Bone_{i:02d}'] for i in src]
    upper = segment(a, c, TB[dst[0]], TB[dst[1]])
    lower = segment(c, d, TB[dst[1]], TB[dst[2]])
    palm = segment(d, SB[end], TB[dst[2]], (TB[dst[3]] + TB[dst[4]]) / 2, False)
    arms[src[0]] = (upper, {dst[0]: 1})
    arms[src[1]] = (upper, {dst[0]: .65, dst[1]: .35})
    arms[src[2]] = (lower, {dst[1]: 1})
    arms[src[3]] = (palm, {dst[2]: 1})


def mapped(p, owner):
    b = int(owner.split('_')[1])
    if b in arms:
        transform, w = arms[b]
        return transform(p), w
    if b in (16, 23, 24, 25, 26):
        w = {15: 1}
        # The skin at each ear base stays on the head; both real ear joints
        # progressively take the outer ear. Same rule on every shared seam.
        if b in (25, 26) and p[2] > .199 and abs(p[0]) > .070:
            root, tip = (18, 19) if p[0] > 0 else (21, 22)
            ear = float(np.clip((abs(p[0]) - .070) / .055, 0, 1))
            outer = float(np.clip((abs(p[0]) - .125) / .055, 0, 1))
            w = {15: 1 - ear, root: ear * (1 - outer), tip: ear * outer}
        return head(p), w
    if b in (41, 42):
        return TB[43] + R @ ((p - SB['Bone_41']) * SCALE), {43: 1}
    if b in (27, 28, 29, 30, 34, 35, 36, 37):
        foot, ankle = (35, SB['Bone_29']) if p[0] > 0 else (41, SB['Bone_36'])
        # Whole source foot, with its sideways splay and tiny toes, translated
        # to the ankle. The hidden stub above it blends into the pear body.
        qfoot = TB[foot] + R @ ((p - ankle) * SCALE)
        if b in (27, 34):
            upper = float(np.clip((p[2] - .016) / .025, 0, 1))
            return upper * body(p) + (1 - upper) * qfoot, {4: upper, foot: 1 - upper}
        toe = 36 if foot == 35 else 42
        return qfoot, ({foot: .45, toe: .55} if b in (30, 37) else {foot: 1})
    chest = float(np.clip((p[2] - .055) / .045, 0, 1))
    neck = float(np.clip((p[2] - .095) / .028, 0, 1))
    return body(p), {4: (1 - chest) * (1 - neck), 5: chest * (1 - neck), 15: neck}


# Record the source eye faces before loading the immutable pre-prep state.
bpy.ops.wm.open_mainfile(filepath=SOURCE)
eye = bpy.data.objects['pichu_mesh_13']
eye_points = np.array(S['pichu_mesh_13']['points'])
eye_faces = []
for f in eye.data.polygons:
    eye_faces.append((eye_points[list(f.vertices)], np.array([eye.data.uv_layers.active.data[i].uv for i in f.loop_indices])))
names = ['pichu_mesh_14', 'pichu_mesh_15', 'pichu_mesh_16']
src = np.concatenate([S[n]['points'] for n in names])
raw = np.concatenate([D['raw']['meshes'][n]['points'] for n in names])
aff = np.linalg.lstsq(np.c_[src, np.ones(len(src))], raw, rcond=None)[0]
assert abs(np.c_[src, np.ones(len(src))] @ aff - raw).max() < 1e-5

bpy.ops.wm.open_mainfile(filepath=str(BUILD / 'base.blend'))
rows = []
for ob in bpy.data.objects:
    if ob.type != 'MESH':
        continue
    if ob.name.startswith('eyes_'):
        points = np.array([np.linalg.solve(aff[:3].T, np.array(v.co) - aff[3]) for v in ob.data.vertices])
        for face in ob.data.polygons:
            pts = points[list(face.vertices)]
            best = None
            for source_pts, uv in eye_faces:
                distances = np.linalg.norm(pts[:, None, :] - source_pts[None, :, :], axis=2)
                order = distances.argmin(1)
                error = distances[np.arange(3), order].max()
                if len(set(order)) == 3 and (best is None or error < best[0]):
                    best = error, uv[order]
            assert best[0] < 1e-6, (ob.name, face.index, best[0])
            for loop, uv in zip(face.loop_indices, best[1]):
                # Unshifted source UV, padded with the CLAMP edge texels.
                xy = np.array([uv[0] * 64, (1 - uv[1]) * 432])
                ob.data.uv_layers.active.data[loop].uv = ((xy[0] + 32) / 146, 1 - (xy[1] + 18) / 55)
        for i, p in enumerate(points):
            rows.append((ob, i, p, head(p), {15: 1}))
    else:
        data = S[ob.name]
        assert len(ob.data.vertices) == len(data['points'])
        for i, (p, held) in enumerate(zip(np.array(data['points']), data['vw'])):
            assert len(held) == 1
            q, w = mapped(p, next(iter(held)))
            rows.append((ob, i, p, q, w))

# The rigid source PObjs share anatomical seam points. Average only those
# identical source points so each side gets the same placement and skin.
# This changes neither topology nor stored normals.
groups = {}
for k, row in enumerate(rows):
    groups.setdefault(tuple(np.round(row[2], 6)), []).append(k)
for members in groups.values():
    q = np.mean([rows[k][3] for k in members], axis=0)
    weights = {}
    for k in members:
        for j, w in rows[k][4].items():
            weights[j] = weights.get(j, 0) + w / len(members)
    weights = dict(sorted(((j, w) for j, w in weights.items() if w > 1e-6), key=lambda x: -x[1])[:4])
    total = sum(weights.values())
    weights = {j: w / total for j, w in weights.items()}
    skin = sum(w * M[j] for j, w in weights.items())
    bound = (np.linalg.inv(skin) @ np.r_[q, 1])[:3]
    for k in members:
        ob, i = rows[k][:2]
        ob.data.vertices[i].co = bound
        for group in ob.vertex_groups:
            group.remove([i])
        for j, w in weights.items():
            name = f'JOBJ_{j}'
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i], float(w), 'REPLACE')

# PKX mobj 0x3620 has exactly one TObj, CLAMP/CLAMP, 64x432 CI8.
# The rip's texture is complete; the atlas has nine 48-row frames.
atlas = np.array(Image.open(ROOT / 'tex_3598.png').convert('RGBA'))
states = {'open': 0, 'half': 48, 'closed': 96}
xx = np.clip(np.arange(-32, 114), 0, 63)
yy = np.clip(np.arange(-18, 37), 0, 47)
for state, offset in states.items():
    Image.fromarray(atlas[(yy + offset)[:, None], xx[None, :]]).save(BUILD / 'eyes' / f'{state}.png')
old = bpy.data.images.get('eyes_open')
new = bpy.data.images.load(str(BUILD / 'eyes/open.png'))
new.pack()
for node in bpy.data.materials['eyes'].node_tree.nodes:
    if node.type == 'TEX_IMAGE':
        node.image = new
        node.extension = 'EXTEND'
if old:
    bpy.data.images.remove(old)
new.name = 'eyes_open'
record = json.loads((BUILD / 'eyes.json').read_text(encoding='utf-8'))
record.update(crop=[-32, -18, 146, 55], eye_texture_size=[64, 432], parts=[{'box': [0, 0, 146, 55], 'up': 'top'}],
              made={s: f'Colosseum pichu tex_3598 actual 48-row atlas frame {r // 48}, padded CLAMP footprint' for s, r in states.items()},
              notes=['PKX confirms a single texture layer; restore unshifted source UVs and real blink frames.'])
record.pop('drawn', None)
(BUILD / 'eyes.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
for ob in bpy.data.objects:
    if ob.type == 'MESH':
        ob.data.update()
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD / 'edited.blend'))
print('Source scale:', SCALE, 'head/body width ratio:', .2004 / .1182)
print('Real blink atlas rows:', states, 'CLAMP footprint:', record['crop'])
