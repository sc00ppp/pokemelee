"""hand_eyes.py <in.blend> <out.blend> <build dir> <eye atlas> <mouth atlas> <glb>: Gardevoir's real eyes on a build.

Her face material has two layers. Layer 0, drawn through UV0, is a 64x768 atlas of eye frames 96 rows apart; layer 1,
through UV1, is the mouth atlas, its alpha masking it over layer 0. The rip kept layer 1 alone (hsd_cmpr.py reads layer 0
out of the pkx). Both eyes share their UV0 as mirror images, so one eye tile serves both: the picture here is 128x64, the
eye at source size on the left, the mouth's rest frame on the right, and the eye faces get new UVs into it."""

from cast_paths import WORK, TARGETS
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import bpy

src, dest, build, eye_png, mouth_png, glb_path = sys.argv[1:7]
build = Path(build)
FRAMES = {'open': 0, 'half': 1, 'closed': 3}
PITCH, TOP, SIDE = 96, 8, 64        # eye frames' rows apart, the rows above a tile, a tile's side
MESH = 'sirnight_mesh_25'
BOX = (-51, -60, 168, 137)          # the old picture: UV1's box in pixels (eyes.json 'crop')

blob = Path(glb_path).read_bytes()
n = int.from_bytes(blob[12:16], 'little')
g = json.loads(blob[20:20 + n])
start = 20 + n + 8


def accessor(i):
    a = g['accessors'][i]
    v = g['bufferViews'][a['bufferView']]
    at = start + v.get('byteOffset', 0) + a.get('byteOffset', 0)
    kind, size = {5123: ('<u2', 1), 5125: ('<u4', 1), 5126: ('<f4', 2)}[a['componentType']]
    return np.frombuffer(blob, kind, a['count'] * size, at)


p = next(m for m in g['meshes'] if m['name'] == MESH)['primitives'][0]
uv0 = accessor(p['attributes']['TEXCOORD_0']).reshape(-1, 2) * [SIDE, 768]
uv1 = accessor(p['attributes']['TEXCOORD_1']).reshape(-1, 2) * [SIDE, 384]
tris = accessor(p['indices']).astype(int).reshape(-1, 3)
is_mouth = [np.ptp(uv0[t], axis=0).max() < 1e-3 for t in tris]
print(len(tris), 'triangles;', sum(is_mouth), 'mouth')


def eye_at(q):
    return np.clip(q - [0, TOP], 0, SIDE)


def mouth_at(q):
    return np.clip(q - [0, 16], 0, SIDE) + [SIDE, 0]


eye = np.array(Image.open(eye_png).convert('RGBA')).astype(float)
mouth = np.array(Image.open(mouth_png).convert('RGBA')).astype(float)
skin = eye[PITCH * 6 + 40, 32, :3]      # a blank frame's colour: what UV0 gives the mouth's faces
pictures = {}
for state, k in FRAMES.items():
    pic = np.zeros((SIDE, SIDE * 2, 4))
    pic[..., 3] = 255
    pic[:, :SIDE, :3] = eye[k * PITCH + TOP:k * PITCH + TOP + SIDE, :SIDE, :3]
    rest = mouth[16:16 + SIDE, :SIDE]
    pic[:, SIDE:, :3] = rest[..., :3] * rest[..., 3:] / 255 + skin * (1 - rest[..., 3:] / 255)
    # the mouth's alpha over the eye layer on the left side's strips, which reach it
    for t, m in zip(tris, is_mouth):
        if m or uv1[t, 0].mean() > 32:
            continue
        a, b, c = eye_at(uv0[t])
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-6:
            continue
        xx, yy = np.meshgrid(np.arange(SIDE) + .5, np.arange(SIDE) + .5)
        w0 = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / d
        w1 = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / d
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        q = (w0[..., None] * uv1[t[0]] + w1[..., None] * uv1[t[1]] + w2[..., None] * uv1[t[2]])
        px = np.clip(q[..., 0].astype(int), 0, SIDE - 1)
        py = np.clip(q[..., 1].astype(int), 0, PITCH - 1)
        over = mouth[py, px]
        al = over[..., 3:] / 255 * inside[..., None]
        pic[:, :SIDE, :3] = over[..., :3] * al + pic[:, :SIDE, :3] * (1 - al)
    pictures[state] = pic.round().astype(np.uint8)
    Image.fromarray(pictures[state], 'RGBA').save(build / 'eyes' / f'{state}.png')

bpy.ops.wm.open_mainfile(filepath=str(Path(src).resolve()))
x0, y0, w, h = BOX
for name in ('eyes_left', 'eyes_right'):
    ob = bpy.data.objects[name]
    m = ob.data
    layer = m.uv_layers.active
    for poly in m.polygons:
        old = np.array([[layer.data[i].uv[0] * w + x0, (1 - layer.data[i].uv[1]) * h + y0] for i in poly.loop_indices])
        best, order = None, None
        for k, t in enumerate(tris):
            for perm in ((0, 1, 2), (1, 2, 0), (2, 0, 1), (0, 2, 1), (2, 1, 0), (1, 0, 2)):
                miss = np.abs(uv1[t[list(perm)]] - old).max()
                if best is None or miss < best[0]:
                    best, order = (miss, k), [t[j] for j in perm]
        assert best[0] < 1.0, (name, poly.index, best)
        for loop, v in zip(poly.loop_indices, order):
            xy = mouth_at(uv1[v]) if is_mouth[best[1]] else eye_at(uv0[v])
            layer.data[loop].uv = (xy[0] / (SIDE * 2), 1 - xy[1] / SIDE)
old = bpy.data.images['eyes_open']
new = bpy.data.images.load(str((build / 'eyes' / 'open.png').resolve()))
new.pack()
for node in bpy.data.materials['eyes'].node_tree.nodes:
    if node.type == 'TEX_IMAGE':
        node.image = new
bpy.data.images.remove(old)
new.name = 'eyes_open'
bpy.ops.wm.save_as_mainfile(filepath=str(Path(dest).resolve()))
record = json.loads((build / 'eyes.json').read_text(encoding='utf-8'))
record['eye_texture_size'] = [SIDE * 2, SIDE]
record['made'] = {s: f'hand_eyes.py: frame {k} of the pkx eye atlas, the mouth at rest beside it' for s, k in FRAMES.items()}
record['notes'] = ['Layer 0 of the face material, dropped by the rip, read out of the pkx: tools/hand_eyes.py']
(build / 'eyes.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
print('saved', dest)
