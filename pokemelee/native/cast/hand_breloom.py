"""hand_breloom.py <3-build dir> <source .blend> <replay dir>: Breloom's arms and claws on Luigi, in edited.blend.

What the fit left (owner, 2026-11-17: "brelooms arms are a jumbled mess"):
- Each red claw is one closed cone on the source's wrist, with a groove down it. The fit gave its base to Luigi's hand
  joint and its two halves to his thumb and a finger joint, each point wholly on one of them. Luigi's hand opens and
  closes in nearly every move, so the cone tore into three pieces that turn apart: shards, slivers, green poking through.
- The source arm is a stub a few millimetres long (a four-point ring and a six-point ring on the body's side). The fit
  stretched that stub over Luigi's whole arm: the body's side faces made the upper arm and the stub the forearm, with
  its wrist ring spread over the hand, thumb and finger joints and no ring at the elbow. Bent, it folds into flaps, and
  the stub's open end shows its dark inside.

What this does, for each arm (nothing else in the costume moves):
- The claw is the source's own cone at the body's scale, rigid on the hand joint, its base at the wrist and its point
  along the forearm, with the source's front kept to the front.
- The arm is a closed green tube with rings at the shoulder, either side of the elbow and at the wrist, each ring on
  one joint or a blend of two, so it bends at the elbow and twists along the forearm. It starts inside the body where
  the source's arm left it and ends inside the claw's base, with the stub's own texture.
- The stub stays, folded into a small funnel inside the body under the tube's root, so the body keeps its surface; the
  ring where it meets the body follows the body and the upper arm only (its forearm share goes to the upper arm).

Run after stand_feet, before round_out. No AI asks."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import bpy
import bmesh
import numpy as np

BUILD, SOURCE, REPLAY = (Path(a) for a in sys.argv[1:4])
K = json.loads((REPLAY / 'replay.json').read_text(encoding='utf-8'))['scale']    # the body's uniform scale
FRONT = np.array([0., -1., 0.])     # Blender: up +Z, front -Y, in the source and in the build alike
BODY = 5                            # Luigi's WaistN: the torso
SIDES = {
    'L': dict(root='Bone_60', wrist='Bone_61', tip='Bone_63_HandLeft', digits={'Bone_61', 'Bone_64', 'Bone_65'},
              joints=(8, 9, 10)),
    'R': dict(root='Bone_66', wrist='Bone_67', tip='Bone_69_HandRight', digits={'Bone_67', 'Bone_70', 'Bone_71'},
              joints=(31, 32, 33)),
}
ISLANDS = ('kinogassa_mesh_05', 'kinogassa_mesh_07')    # the stub's faces (the right one is split between the two)
CLAWS = 'kinogassa_mesh_10'                             # hand and foot claws: only the hand claws move
SIDES_N = 6             # points round the tube; round_out doubles them
# the tube along the arm: (where, radius, weights). Radii from the source: stub rings .037-.053, claw base .055 (x K)
ROOT_DEPTH, ROOT_OUT = .45, .08     # the root ring inside the body and the ring just outside it, along the hole's normal
ROOT_R, SHOULDER_R, UPPER_R, ELBOW_R, WRIST_R = .55, .55, .5, .48, .46
HOLE_COVER = 1.3                    # the ring outside the body follows the hole's outline, this much bigger, so it hides it
ELBOW_SPAN = .3                     # rings either side of the elbow, this far along the bones
WRIST_IN, END_IN = .1, .3           # the wrist ring and the closed end, this far into the claw past the hand joint


def unit(v):
    return v / np.linalg.norm(v)


def basis(axis, ref):
    a = unit(axis)
    r = unit(ref - (ref @ a) * a)
    return np.column_stack([a, r, np.cross(a, r)])


def top_bone(ob):
    names = {g.index: g.name for g in ob.vertex_groups}
    return [names[max(v.groups, key=lambda g: g.weight).group] if len(v.groups) else None for v in ob.data.vertices]


def world(ob):
    mw = np.array(ob.matrix_world)
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get('co', co)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def read_source():
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    bones = {b.name: np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
    return bones, {n: (world(bpy.data.objects[n]), top_bone(bpy.data.objects[n])) for n in (*ISLANDS, CLAWS)}


def weights(ob, i):
    names = {g.index: g.name for g in ob.vertex_groups}
    return {int(names[g.group][5:]): g.weight for g in ob.data.vertices[i].groups
            if names[g.group].startswith('JOBJ_') and g.weight > 0}


def set_weights(ob, i, held):
    total = sum(held.values())
    for g in [g for g in ob.vertex_groups if g.name.startswith('JOBJ_')]:
        g.remove([i])
    for j, w in held.items():
        if w > 1e-6:
            (ob.vertex_groups.get(f'JOBJ_{j}') or ob.vertex_groups.new(name=f'JOBJ_{j}')).add([i], w / total, 'REPLACE')


def put(ob, moves):
    """Vertex coordinates from {index: world point} (the build's meshes sit at the identity)."""
    assert ob.matrix_world.is_identity, ob.name
    for i, p in moves.items():
        ob.data.vertices[i].co = p.tolist()
    ob.data.update()


def key(p):
    return tuple(np.round(p, 4))


def main():
    S, src = read_source()
    bpy.ops.wm.open_mainfile(filepath=str(BUILD / 'edited.blend'))
    armature = bpy.data.objects['Armature']

    def J(j):
        return np.array(armature.matrix_world @ armature.data.bones[f'JOBJ_{j}'].head_local)

    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.vertices)]
    for name, (co, _) in src.items():
        assert len(bpy.data.objects[name].data.vertices) == len(co), name
    notes = {'scale': K, 'arms': {}}
    rings_all = {}
    for side, s in SIDES.items():
        shoulder, elbow, hand = s['joints']
        js, je, jh = J(shoulder), J(elbow), J(hand)
        upper, fore = unit(je - js), unit(jh - je)

        # the claw: the source's cone, rigid on the hand
        turn = basis(fore, FRONT) @ basis(S[s['tip']] - S[s['wrist']], FRONT).T
        ob = bpy.data.objects[CLAWS]
        co, top = src[CLAWS]
        claw = [i for i, b in enumerate(top) if b in s['digits']]
        put(ob, {i: jh + turn @ (K * (co[i] - S[s['wrist']])) for i in claw})
        for i in claw:
            set_weights(ob, i, {hand: 1.0})

        # the stub: its faces, the ring where it meets the body, and that ring's twin on the body
        stub, ring, faces = {}, defaultdict(list), {}
        for name in ISLANDS:
            ob = bpy.data.objects[name]
            co, top = src[name]
            mine = {i for i, b in enumerate(top) if b == s['root'] or b in s['digits']}
            stub[name] = mine
            faces[name] = [list(p.vertices) for p in ob.data.polygons if set(p.vertices) & mine]
            for f in faces[name]:
                for v in f:
                    if v not in mine:
                        ring[key(np.array(ob.data.vertices[v].co))].append((name, v))
        places = {k: np.array(k) for k in ring}
        for ob in meshes:      # the body's own points at those places: the hole the stub came out of
            for v in ob.data.vertices:
                k = key(np.array(v.co))
                if k in ring and (ob.name, v.index) not in ring[k]:
                    ring[k].append((ob.name, v.index))
        hole = np.array(list(places.values()))
        middle = hole.mean(0)
        normal = unit(np.cross(hole[1] - hole[0], hole[2] - hole[0])) if len(hole) == 3 else unit(middle * [1, 1, 0])
        outward = middle - np.array([0, 0, middle[2]])
        normal = normal if normal @ outward > 0 else -normal

        # the ring follows the torso, neck and upper arm: its forearm share goes to the upper arm
        shared = defaultdict(float)
        count = 0
        for k, users in ring.items():
            for name, v in users:
                ob = bpy.data.objects[name]
                held = weights(ob, v)
                held[shoulder] = held.get(shoulder, 0) + sum(w for j, w in held.items() if j not in (BODY, 22, shoulder))
                held = {j: w for j, w in held.items() if j in (BODY, 22, shoulder)}
                set_weights(ob, v, held)
                for j, w in held.items():
                    shared[j] += w / sum(held.values())
                count += 1
        shared = {j: w / count for j, w in shared.items()}

        # the stub folded into a funnel inside the body, under the tube's root
        for name, mine in stub.items():
            ob = bpy.data.objects[name]
            co, top = src[name]
            pts = world(ob)
            for group, depth, radius in ((s['root'], .25, .25), (None, .4, .12)):
                idx = [i for i in mine if (top[i] == s['root']) == (group is not None)]
                if not idx:
                    continue
                c = co[idx].mean(0)
                moves = {}
                for i in idx:
                    off = co[i] - c
                    off -= (off @ normal) * normal
                    moves[i] = middle - depth * normal + radius * unit(off)
                put(ob, moves)
                for i in idx:
                    set_weights(ob, i, shared)

        # the tube
        e1, e2 = je - ELBOW_SPAN * upper, je + ELBOW_SPAN * fore
        rings = [(middle - ROOT_DEPTH * normal, ROOT_R, {BODY: 1.0}),
                 (middle + ROOT_OUT * normal, (SHOULDER_R, normal, hole), shared),
                 (e1, UPPER_R, {shoulder: .8, elbow: .2}),
                 (je, ELBOW_R, {shoulder: .5, elbow: .5}),
                 (e2, ELBOW_R, {shoulder: .2, elbow: .8}),
                 (jh + WRIST_IN * fore, WRIST_R, {elbow: .3, hand: .7})]
        ends = [(middle - (ROOT_DEPTH + .1) * normal, {BODY: 1.0}), (jh + END_IN * fore, {hand: 1.0})]
        rings_all[side] = (rings, ends, stub)
        notes['arms'][side] = {'hole': middle.round(3).tolist(), 'claw_points': len(claw),
                               'ring_weights': {str(j): round(w, 3) for j, w in shared.items()},
                               'shoulder_elbow_hand': [js.round(3).tolist(), je.round(3).tolist(), jh.round(3).tolist()]}

    make_tube(rings_all, src)
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD / 'edited.blend'))
    (BUILD / 'breloom-arms.json').write_text(json.dumps(notes, indent=2), encoding='utf-8')
    print('Breloom arms:', json.dumps(notes))


def reach(c, d, outline, n):
    """How far from c along d (both in the plane of normal n) the hole's outline lies, the outline HOLE_COVER bigger."""
    middle = outline.mean(0)
    pts = [middle + HOLE_COVER * (p - middle) for p in outline]
    pts = [p - ((p - c) @ n) * n for p in pts]
    best = 0.
    for a, b in zip(pts, pts[1:] + pts[:1]):
        # c + s d = a + t (b - a): least squares in the plane
        m = np.column_stack([d, a - b])
        (s, t), *_ = np.linalg.lstsq(m, a - c, rcond=None)
        if s > 0 and -1e-6 <= t <= 1 + 1e-6:
            best = max(best, s)
    return best


def make_tube(rings_all, src):
    """One closed tube per arm, in one new object with the body's material and the stub's own texture."""
    body = bpy.data.objects['kinogassa_mesh_05']
    ob = body.copy()
    ob.data = body.data.copy()
    ob.name = ob.data.name = 'kinogassa_mesh_05_arms'
    for c in body.users_collection:
        c.objects.link(ob)
    ob.vertex_groups.clear()
    uv_of = {}
    for loop in body.data.loops:        # the stub's texture: the UV each stub point carries
        uv_of.setdefault(loop.vertex_index, tuple(body.data.uv_layers.active.data[loop.index].uv))
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new('UVMap')
    deform = bm.verts.layers.deform.verify()
    groups = {}

    def group(j):
        if j not in groups:
            groups[j] = ob.vertex_groups.new(name=f'JOBJ_{j}').index
        return groups[j]

    def vert(p, held):
        v = bm.verts.new(p.tolist())
        total = sum(held.values())
        for j, w in held.items():
            v[deform][group(j)] = w / total
        return v

    for side, (rings, ends, stub) in rings_all.items():
        # the stub's points all read one texel of the 32-pixel body texture: the tube reads it too
        stub_uv = tuple(np.mean([uv_of[i] for i in stub['kinogassa_mesh_05']], axis=0))
        centres = [c for c, _, _ in rings]
        tangents = [unit(centres[min(i + 1, len(centres) - 1)] - centres[max(i - 1, 0)]) for i in range(len(centres))]
        ref = unit(FRONT - (FRONT @ tangents[0]) * tangents[0])
        loops = []
        for (c, r, held), t in zip(rings, tangents):
            ref = unit(ref - (ref @ t) * t)                 # carried along the tube, so the strips don't twist
            side_v = np.cross(t, ref)
            angles = np.arange(SIDES_N) * 2 * np.pi / SIDES_N
            if isinstance(r, tuple):                        # the ring over the hole: in its plane, round its outline
                least, n, outline = r
                u = unit(ref - (ref @ n) * n)
                v = np.cross(n, u)
                points = [c + max(least, reach(c, d, outline, n)) * d
                          for d in (np.cos(a) * u + np.sin(a) * v for a in angles)]
            else:
                points = [c + r * (np.cos(a) * ref + np.sin(a) * side_v) for a in angles]
            loops.append([vert(p, held) for p in points])
        tips = [vert(p, held) for p, held in ends]
        made = []
        for a, b in zip(loops, loops[1:]):
            for k in range(SIDES_N):
                made.append(bm.faces.new((a[k], a[(k + 1) % SIDES_N], b[(k + 1) % SIDES_N], b[k])))
        for ring_, tip in ((loops[0], tips[0]), (loops[-1], tips[1])):
            for k in range(SIDES_N):
                made.append(bm.faces.new((ring_[k], ring_[(k + 1) % SIDES_N], tip)))
        for f in made:
            for loop in f.loops:
                loop[uv].uv = stub_uv
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='FIXED')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = True
        f.material_index = 0
    me = ob.data
    for name in [a.name for a in me.attributes if a.name == 'custom_normal']:
        me.attributes.remove(me.attributes[name])
    bm.to_mesh(me)
    bm.free()
    while len(me.materials) > 1:
        me.materials.pop()
    me.update()
    print('arms tube:', len(me.vertices), 'points', len(me.polygons), 'triangles')


main()
