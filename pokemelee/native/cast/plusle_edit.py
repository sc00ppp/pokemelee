"""plusle_edit.py <base.blend> <out.blend> <ends.npz> <vanilla-Pichu.blend>: the hand fix of Plusle-Pichu and Minun-Pichu.

Pichu is a ball that never bends at the legs: no vertex of it is on the thigh or knee, and its feet are separate rigid
pieces on JOBJ_35/36 and 41/42 that swing clear of the body. The mons are one skin with two stubs, and rigswap's fit
pulls the stubs along Pichu's leg joints into cones, which shred, and folds the belly in any move that tucks the legs.
So the port is built as Pichu is:
- the mon's own trunk goes back, at the fit's scale, and what lies below PRESS, the stubs and the creases between them,
  is projected from a centre onto a half ellipsoid, which has no folds in it, as low as Pichu's body ends (BOTTOM);
- every trunk vertex loses its leg weights. The hip share takes vanilla Pichu's split between JOBJ_4, 5 and 6, read from
  the nearest vanilla body vertices, because the fit gives the chest to the hips and nothing sits on the spine;
- Pichu's own feet are added on their own joints, in a plain texel of the mon's body picture;
- the tail, which the fit leaves riding the hips, goes wholly on JOBJ_43.

Works on both mons: the objects' names differ only by prefix and by which meshes are the tail."""

from cast_paths import WORK, TARGETS
import sys
from pathlib import Path

import bpy
import numpy as np

src, dest, ends, vanilla = sys.argv[1:5]
ALL_LEG = {'JOBJ_32', 'JOBJ_33', 'JOBJ_34', 'JOBJ_35', 'JOBJ_36', 'JOBJ_38', 'JOBJ_39', 'JOBJ_40', 'JOBJ_41', 'JOBJ_42'}
TRUNK = ('JOBJ_4', 'JOBJ_5', 'JOBJ_6')
FEET = ('Joint_0_Object_12', 'Joint_0_Object_13', 'Joint_0_Object_14',
        'Joint_0_Object_33', 'Joint_0_Object_34', 'Joint_0_Object_35')
RESTORE = (4.0, 5.5)        # below the first height the mon's own shape, above the second the fit's
PRESS = 3.4                 # below this height the trunk becomes a bowl...
BOTTOM = 1.0                # ...whose lowest point is here: where Pichu's body ends over its feet
SEAM = 0.9                  # the height over which the bowl gives way to the mon's own surface


def ramp(v, a, b):
    t = np.clip((v - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def world(ob):
    mw = np.array(ob.matrix_world)
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get('co', co)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def groups_of(ob):
    names = [g.name for g in ob.vertex_groups]
    return [{names[e.group]: e.weight for e in v.groups if e.weight > 0} for v in ob.data.vertices]


def vanilla_parts():
    """Vanilla Pichu in build space: main body points and trunk shares, and the feet as (points, faces, weights)."""
    bpy.ops.wm.open_mainfile(filepath=str(Path(vanilla).resolve()))
    body = bpy.data.objects['Joint_0_Object_0']
    co = world(body)
    w = np.array([[row.get(j, 0) for j in TRUNK] for row in groups_of(body)])
    keep = w.sum(1) > .99
    parts = []
    for name in FEET:
        ob = bpy.data.objects[name]
        parts.append((name, world(ob), [list(p.vertices) for p in ob.data.polygons], groups_of(ob)))
    return co[keep], w[keep], parts


vanilla_co, vanilla_w, feet = vanilla_parts()
print('vanilla foot height', min(f[1][:, 2].min() for f in feet), max(f[1][:, 2].max() for f in feet))
print('vanilla foot y', min(f[1][:, 1].min() for f in feet), max(f[1][:, 1].max() for f in feet))
bpy.ops.wm.open_mainfile(filepath=str(Path(src).resolve()))
d = np.load(ends, allow_pickle=True)
S, P, W = d['source'], d['placed'], d['weights']
bones = [str(b) for b in d['bones']]

obs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.name.startswith('eyes_')]
prefix = obs[0].name.split('_mesh_')[0]
mesh = lambda n: bpy.data.objects[f'{prefix}_mesh_{n:02d}']
tail = [mesh(n) for n in ({'prasle': (11, 12), 'minun': (14, 15)}[prefix])]
trunk = [mesh(n) for n in (1, 2, 3, 4, 5, 6)]
armature = bpy.data.objects['Armature']

# the fit's hips: its map from the mon's shape to the placed one, on vertices wholly on JOBJ_4 above the legs
hips = (W[:, bones.index('JOBJ_4')] > .99) & (S[:, 2] > 3)
A = np.linalg.lstsq(np.c_[S, np.ones(len(S))][hips], P[hips], rcond=None)[0]
fit = np.c_[S, np.ones(len(S))] @ A
band = fit[(np.abs(fit[:, 2] - PRESS) < .6) & (np.abs(fit[:, 1]) < 3.9) & (np.abs(fit[:, 0]) < 3.9)]
bowl = (np.abs(band[:, 0]).max(), np.ptp(band[:, 1]) / 2, (band[:, 1].max() + band[:, 1].min()) / 2)
print('hips fit from', hips.sum(), 'vertices; bowl', np.round(bowl, 2))


def source_of(co):
    dist = ((co[:, None] - P[None]) ** 2).sum(2)
    assert dist.min(1).max() < 1e-6
    return S[dist.argmin(1)]


def set_groups(ob, table):
    for g in list(ob.vertex_groups):
        ob.vertex_groups.remove(g)
    for name in sorted({n for row in table for n in row}, key=lambda s: int(s[5:])):
        g = ob.vertex_groups.new(name=name)
        for i, row in enumerate(table):
            if name in row:
                g.add([i], row[name], 'REPLACE')


def trim(row, most=4):
    top = sorted(row.items(), key=lambda kv: -kv[1])[:most]
    total = sum(v for _, v in top)
    return {k: v / total for k, v in top if v / total > .01}


plain = None        # the uv of the belly: a plain texel of the body picture
for ob in trunk:
    n = len(ob.data.vertices)
    co = np.array([v.co[:] for v in ob.data.vertices])
    s = source_of(co)
    own = np.c_[s, np.ones(n)] @ A
    low = own[:, 2] < PRESS
    centre = np.array([0, bowl[2], PRESS])
    radii = np.array([bowl[0], bowl[1], PRESS - BOTTOM])
    d = (own[low] - centre) / radii
    on = centre + d / np.linalg.norm(d, axis=1, keepdims=True) * radii
    b = 1 - ramp(own[low, 2], PRESS - SEAM, PRESS)[:, None]
    own[low] = own[low] * (1 - b) + on * b
    t = ramp(s[:, 2], *RESTORE)[:, None]
    new = own * (1 - t) + co * t
    ob.data.vertices.foreach_set('co', new.ravel())
    ob.data.update()

    near = ((new[:, None] - vanilla_co[None]) ** 2).sum(2).argsort(1)[:, :6]
    dist = (((new[:, None] - vanilla_co[near]) ** 2).sum(2)) ** .5 + .05
    share = (vanilla_w[near] / dist[..., None]).sum(1) / (1 / dist).sum(1)[:, None]
    table = groups_of(ob)
    for i, row in enumerate(table):
        hip = row.pop('JOBJ_4', 0) + sum(row.pop(j, 0) for j in ALL_LEG)
        for j, f in zip(TRUNK, share[i]):
            if hip * f > 0:
                row[j] = row.get(j, 0) + hip * f
        table[i] = trim(row)
    set_groups(ob, table)
    uv = ob.data.uv_layers.active.data
    for loop in ob.data.loops:
        v = new[loop.vertex_index]
        score = abs(v[0]) + abs(v[2] - 3.5)
        if v[1] < -2 and (plain is None or score < plain[0]):
            plain = (score, tuple(uv[loop.index].uv))
print('plain uv', plain)

for ob in tail:
    set_groups(ob, [{'JOBJ_43': 1.0} for _ in ob.data.vertices])

for name, points, faces, weights in feet:
    me = bpy.data.meshes.new(f'{prefix}_foot_{name[-2:]}')
    me.from_pydata(points.tolist(), [], faces)
    me.update()
    me.materials.append(trunk[0].data.materials[0])
    layer = me.uv_layers.new(name='UVMap')
    for loop in me.loops:
        layer.data[loop.index].uv = plain[1]
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = armature
    set_groups(ob, [trim(row) for row in weights])

bpy.ops.wm.save_as_mainfile(filepath=str(Path(dest).resolve()))
print('saved', dest)
