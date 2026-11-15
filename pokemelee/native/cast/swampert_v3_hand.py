"""Swampert v3 (2026-11-12): the joints. Writes hand/swampert-DonkeyKong/v3/3-build/edited.blend.

The body, head, arms, hands, tail and eyes are v2's, unchanged in shape. What changes is how pieces meet DK's joints.

Every point is now defined where it stands in DK's idle (Wait1-1) and bound back through its own idle skin, so idle
is exact for every point, blended or not. v2 did that for the legs only; shoulder, neck and elbow seam points kept an
average of two rest places and stood wrong in every pose.

Legs. Swampert's own leg is one rigid haunch (source bone 61) and a foot (81); his knee and ankle bones carry no
skin. v2 hung the haunch where his leg hangs, from the hip straight down to the foot, and bound it to DK's thigh
joint, whose bone points forward at idle. So the haunch lay across the bone it followed, DK's shin carried nothing,
and the haunch was tied to the foot by faces that stretched: any pose but idle swung it off like a door.
Here a leg is three closed rigid pieces on DK's own chain, meeting inside each other as the rip's own pieces do:
- the haunch along DK's thigh (hip to knee on his bone, the patch still facing out), closed at both ends;
- a shin from his knee to his ankle, which Swampert's model lacks (a stand-in: a plain blue tapered tube);
- the foot on his foot joint, as before.
No point is shared between two of them, so nothing can stretch or tear, whatever the knee does.

Shoulders. Three things. Swampert's own shoulder sockets stand 2 units ahead of and inside DK's shoulder joints
in the fitted chest, so each arm root floated behind its socket and the faces between tore. The chest was one block
on the chest joint and nothing followed DK's collar bones, which carry his shoulder joint up to 4.3 units off the
chest. And the arm met the chest through eight faces between two rigid rings, which a shoulder that turns 4 to 175
degrees folds over. Now the chest's shoulder bumps are moved onto DK's joints, the chest around each follows the
collar, and the arm leaves the chest: its root is closed with a ball about the joint and the chest is closed under it.

Elbows and wrists. The same eight-to-ten faces between two rigid rings, on joints that turn 0 to 139 and 15 to 146
degrees: bent hard they folded over and showed their backs as a dark slit. Each piece now ends closed, inside a ball
about DK's joint that rides the piece below it (the forearm at the elbow, the hand at the wrist).

Run: swampert_v3_hand.py, stand_feet.py <3-build> DonkeyKong, round_out.py <3-build> --idle DonkeyKong, hand_finish.
soft_legs.py is NOT run: its pelvis step is done here, and its hip ring would blend the haunch back into the hips."""

from cast_paths import WORK, TARGETS
import json
import sys
from pathlib import Path

import bpy
import bmesh        # after bpy: the module only exists once bpy is loaded
import numpy as np
from mathutils import Matrix, Vector
from PIL import Image

R = Path(str(WORK / ''))
B = R / 'hand/swampert-DonkeyKong/v3/3-build'
SOURCE = R / 'hand/swampert-DonkeyKong/v2/source-idle.blend'
ns = {'__name__': 'view_helpers'}
exec(compile((R / 'tools/hand_view.py').read_text(encoding='utf-8').rsplit('\nmain()', 1)[0], 'hand_view.py', 'exec'), ns)
C = ns['C']
rest = ns['rests']('DonkeyKong')
idle_frame = ns['frame']('DonkeyKong', 'Wait1-1')
idle = {j: C @ m @ np.linalg.inv(rest[j]) @ np.linalg.inv(C) for j, m in idle_frame.items() if j in rest}
T = {j: (C @ m)[:3, 3] for j, m in rest.items()}                      # joints in the bind
I = {j: (idle[j] @ np.r_[T[j], 1])[:3] for j in idle}                  # joints in idle

HAUNCH = 17.0       # the haunch across its axis: the body's own scale
WIDE = 1.5          # the haunch sits this far outside DK's thigh bone: Swampert's hips are wider than DK's
SHIN = (2.3, 1.9)   # the shin's radius at the knee and at the ankle
HIP_END = .4        # the haunch's point toward the body, drawn in to this share: at idle it faces back, out of the rump
BALL = 1.6          # the shoulder ball's radius: the upper arm's own root ring is 1.4 to 1.65 across the bone
SOCKET = (1.5, 4.2) # the chest within SOCKET[0] of its own shoulder socket moves whole onto DK's joint; none beyond SOCKET[1]
SIDES = 8
CAP = (2.2, 5.0)    # the chest within CAP[0] of a collar bone follows it, by how far along the bone; none beyond CAP[1]
HINGE = {'elbow': 1.55, 'wrist': 1.3}   # each ball's radius: the thinner piece's own thickness there, so it fills a bend and never bulges
KNEE_END = .5       # the haunch's end past the knee, drawn back to this share: it tapered to a point
STEP, MOST = 8, 3   # weights in eighths, three joints a point (soft_legs' limits, for the export)


def unit(v):
    return np.array(v, float) / np.linalg.norm(v)


def basis(direction, up):
    x = unit(direction)
    z = unit(np.array(up) - x * np.dot(x, up))
    y = np.cross(z, x)
    return np.column_stack((x, y, z))


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def stored_normals(me):
    values = np.empty(len(me.loops) * 3)
    me.corner_normals.foreach_get('vector', values)
    return values.reshape(-1, 3)


# ---------------------------------------------------------------- the source, in its own Idle
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
srcarm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
H = {int(b.name.split('_')[1]): np.array(srcarm.matrix_world @ b.head_local) for b in srcarm.data.bones}
seams, records = {}, {}
for ob in bpy.data.objects:
    if ob.type != 'MESH':
        continue
    assert ob.data.has_custom_normals, ob.name
    names = {g.index: int(g.name.split('_')[1]) for g in ob.vertex_groups}
    mw = np.array(ob.matrix_world)
    pts = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
    ws = [{names[g.group]: g.weight for g in v.groups if g.weight > 0} for v in ob.data.vertices]
    for p, w in zip(pts, ws):
        seams.setdefault(tuple(p.round(5)), []).append(w)
    normals = stored_normals(ob.data) @ np.linalg.inv(mw[:3, :3])        # rows: n' = inv(M).T n
    records[ob.name] = (pts, ws, normals)
for k, rows in list(seams.items()):
    w = {}
    for row in rows:
        for j, v in row.items():
            w[j] = w.get(j, 0) + v / len(rows)
    seams[k] = w

# ---------------------------------------------------------------- the target skeleton, eyes and the source surfaces
bpy.ops.wm.open_mainfile(filepath=str(B / 'base.blend'))
arm = bpy.data.objects['Armature']
eyes = {o.name: o for o in bpy.data.objects if o.name in ('eyes_left', 'eyes_right')}
for ob in list(bpy.data.objects):
    if ob.type == 'MESH' and ob.name not in eyes:
        bpy.data.objects.remove(ob, do_unlink=True)
with bpy.data.libraries.load(str(SOURCE), link=False) as (data, loaded):
    loaded.objects = [name for name in data.objects if name in records and name != 'laglarge_mesh_05']
for ob in loaded.objects:
    bpy.context.scene.collection.objects.link(ob)

# ---------------------------------------------------------------- v2's maps for body, head, arms and tail, unchanged
maps = {}


def affine(a, b, c, d, radial, joint, up=None, target_up=None):
    u, v = b - a, d - c
    if up is None:
        rot = np.array(Vector(u).rotation_difference(Vector(v)).to_matrix())
        axis = unit(u)
        m = rot @ (np.eye(3) * radial + np.outer(axis, axis) * (np.linalg.norm(v) / np.linalg.norm(u) - radial))
    else:
        m = basis(v, target_up) @ np.diag([np.linalg.norm(v) / np.linalg.norm(u), radial, radial]) @ basis(u, up).T
    return m, c - m @ a, joint


torso = basis(H[9] - H[23], (0, 0, 1))
head_basis = basis(H[44] - H[45], (H[55] + H[59] - H[52] - H[56]) / 2)
head_idle = np.array([-.1, -3.3, 15.3])
head_at = (np.linalg.inv(idle[44]) @ np.r_[head_idle, 1])[:3]
yaw = np.radians(-18)
face_turn = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
head_m = np.linalg.inv(idle[44][:3, :3]) @ face_turn @ (15.0 * head_basis.T)
head_map = (head_m, head_at - head_m @ H[40], 44)
shoulder = (T[29] + T[51]) / 2
body_map = affine(H[5], (H[10] + H[24]) / 2, T[4], shoulder, 17.0, 26, H[9] - H[23], T[29] - T[51])
for j in range(89):
    maps[j] = body_map
for j in range(40, 60):
    maps[j] = head_map
for shoulder_j, elbow, wrist, tip, last, start, stop, tshoulder, telbow, twrist, sign in (
        (10, 11, 15, 20, 22, 9, 23, 29, 30, 31, 1), (24, 25, 29, 34, 36, 23, 37, 51, 52, 53, -1)):
    spread = H[last] - H[17 if sign == 1 else 31]
    target_up = np.array([0, sign, 0])
    a = affine(H[shoulder_j], H[elbow], T[tshoulder], T[telbow], 18.5, tshoulder, spread, target_up)
    b = affine(H[elbow], H[wrist], T[telbow], T[twrist], 18.5, telbow, spread, target_up)
    hm = basis(T[twrist] - T[telbow], target_up) @ (15.8 * np.eye(3)) @ basis(H[tip] - H[wrist], spread).T
    hand = (hm, T[twrist] - hm @ H[wrist], twrist)
    for j in range(start, stop):
        maps[j] = a if j <= shoulder_j else b if j < wrist else hand
    maps[13 if sign == 1 else 27] = hand
pitch = np.radians(-12)
rot = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
tail_m = np.linalg.inv(idle[4][:3, :3]) @ rot @ (11.8 * torso.T)
tail_origin = (np.linalg.inv(idle[4]) @ np.r_[np.array([-.21, 6.0, 8.2]), 1])[:3]
tail_map = (tail_m, tail_origin - tail_m @ H[74], 4)
for j in range(74, 79):
    maps[j] = tail_map
BODY_AT, BODY_SCALE = np.array([-.21, 3.0, 9.5]), np.array([17.0, 13.0, 12.0])
BODY_M = np.diag(BODY_SCALE) @ torso.T                                   # the trunk, fitted upright in DK's idle


def fit_plain(p):
    return BODY_AT + BODY_M @ (p - H[5])


ARMS = {'L': dict(up=10, joint=29, collar=27, elbow=30), 'R': dict(up=24, joint=51, collar=49, elbow=52)}
for side in ARMS.values():      # (name, source bone above, source bone below, DK joint): the hinges down the arm
    side['hinges'] = (('elbow', side['up'], side['up'] + 1, side['elbow']), ('wrist', side['up'] + 1, side['up'] + 5, side['elbow'] + 1))
for side in ARMS.values():
    side['socket'] = fit_plain(H[side['up']])                  # his own shoulder, in the fitted chest
    side['shift'] = I[side['joint']] - side['socket']
    print('shoulder socket', side['socket'].round(2), 'to DK joint by', side['shift'].round(2), flush=True)


def fit_body(p):
    """The trunk in DK's idle, its shoulder bumps carried onto his shoulder joints."""
    at = fit_plain(p)
    return at + sum(a['shift'] * float(smooth((SOCKET[1] - np.linalg.norm(at - a['socket'])) / (SOCKET[1] - SOCKET[0])))
                    for a in ARMS.values())


# ---------------------------------------------------------------- the legs: rigid pieces on DK's chain
X = np.array([1., 0, 0])
legs = []
for hip, knee, ankle, foot, toe, th, tk, tf, sign in ((61, 62, 63, 81, 82, 6, 7, 9, 1), (68, 69, 70, 84, 85, 16, 17, 19, -1)):
    # The foot: v2's, the mon's own foot flat on the floor under DK's ankle (stand_feet sets its plane after).
    forward = H[toe] - H[foot]
    forward[2] = 0
    fb = basis(forward, (0, 0, 1))
    fm = basis((0, -1, 0), (0, 0, 1)) @ np.diag([13.5, 12.8, 9.0]) @ fb.T
    sole = [(fm @ (p - H[foot]))[2] for pts, ws, _ in records.values() for p, w in zip(pts, ws) if w.get(foot, 0) > .99]
    foot_at = T[tf].copy()
    foot_at[2] = -min(sole) + .04
    foot_map = (idle[tf][:3, :3] @ fm, (idle[tf] @ np.r_[foot_at - fm @ H[foot], 1])[:3], tf)   # source to idle
    # The haunch: his own hip-to-knee line laid on DK's idle thigh, turned about that line so what faced out still does.
    us = unit(H[knee] - H[hip])
    fs = np.column_stack((us, unit(X - (X @ us) * us), np.cross(us, unit(X - (X @ us) * us))))
    ui = unit(I[tk] - I[th])
    fi = np.column_stack((ui, unit(X - (X @ ui) * ui), np.cross(ui, unit(X - (X @ ui) * ui))))
    along = np.linalg.norm(T[tk] - T[th]) / np.linalg.norm(H[knee] - H[hip])
    hm = fi @ np.diag([along, HAUNCH, HAUNCH]) @ fs.T
    haunch_map = (hm, I[th] + sign * WIDE * X - hm @ H[hip], th)                                # source to idle
    legs.append(dict(hip=hip, foot=foot, th=th, tk=tk, tf=tf, sign=sign, haunch=haunch_map, footmap=foot_map,
                     name='L' if sign == 1 else 'R'))
    print('leg', legs[-1]['name'], 'thigh %.2f of his %.2f along the bone; knee at' % (along * np.linalg.norm(H[knee] - H[hip]),
          17 * np.linalg.norm(H[knee] - H[hip])), (hm @ H[knee] + haunch_map[1]).round(2), 'DK knee', I[tk].round(2), flush=True)
LEG_OF = {l['hip']: l for l in legs}
FOOT_OF = {l['foot']: l for l in legs}


# ---------------------------------------------------------------- one point: where it stands in idle, and on what
def map_point(p, ws):
    """(idle place, {joint: weight}, the matrix its normal turns by) of a body, head, arm or tail point."""
    at, weights, turn = np.zeros(3), {}, np.zeros((3, 3))
    if len(ws) > 1 and any(a['up'] in ws for a in ARMS.values()):
        ws = {j: 1.0 for j in ws if j in (5, 6, 7, 8)}             # a chest point the rip shared with the arm: the chest's
    for j, w in ws.items():
        assert j not in LEG_OF and j not in FOOT_OF, j
        if j in (5, 6, 7, 8):
            place, dst, m = fit_body(p), 26, BODY_M
        else:
            m, off, dst = maps[j]
            place = (idle[dst] @ np.r_[m @ p + off, 1])[:3]
            m = idle[dst][:3, :3] @ m
        at += w * place
        turn += w * np.linalg.inv(m).T
        weights[dst] = weights.get(dst, 0) + w
    return at, {j: w for j, w in weights.items() if w > 1e-6}, turn


def piece_of(bones):
    """The piece a face belongs to, by the source bones of its corners."""
    for leg in legs:
        if leg['hip'] in bones:
            return 'haunch' + leg['name']             # the haunch, its skirt to the body and its sock to the foot
    for leg in legs:
        if bones == {leg['foot']}:
            return 'foot' + leg['name']
    return 'body'


points = {}        # (object name, vertex) -> dict(at, w, turn)
caps = {'body' + l['name']: {} for l in legs} | {'haunch' + l['name'] + 'top': {} for l in legs} \
    | {'haunch' + l['name'] + 'end': {} for l in legs} | {'foot' + l['name']: {} for l in legs} \
    | {'chest' + n: {} for n in ARMS} | {'arm' + n: {} for n in ARMS} \
    | {h + end + n: {} for n in ARMS for h in HINGE for end in 'AB'}
uv_at = {}        # (cap, source place) -> a UV its piece draws there
dropped = 0
for ob in loaded.objects:
    pts, original, normals = records[ob.name]
    ob.parent = None
    ob.matrix_world = Matrix.Identity(4)
    for mod in list(ob.modifiers):
        ob.modifiers.remove(mod)
    me = ob.data
    dom = [max(w, key=w.get) for w in original]
    # Each haunch's faces leave the body and the foot: the points they shared are doubled, one for each side.
    bm = bmesh.new()
    bm.from_mesh(me)
    src = bm.verts.layers.int.new('src')
    corner = bm.loops.layers.int.new('src_corner')      # a split moves its faces to the end: corners keep their number
    for v in bm.verts:
        v[src] = v.index
    for f in bm.faces:
        for n, loop in enumerate(f.loops):
            loop[corner] = me.polygons[f.index].loop_start + n
    for leg in legs:
        faces = [f for f in bm.faces if leg['hip'] in {dom[v[src]] for v in f.verts}]
        if faces:
            bmesh.ops.split(bm, geom=faces)
    # The faces from the chest to each upper arm's root ring go: the ball closes the arm, a cap the chest.
    uv_layer = bm.loops.layers.uv.active
    for n, side in ARMS.items():
        up = side['up']
        bridge = [f for f in bm.faces if any(original[v[src]].get(up, 0) > .99 for v in f.verts)
                  and any(up not in original[v[src]] or len(original[v[src]]) > 1 for v in f.verts)
                  and not any(up + 1 in original[v[src]] for v in f.verts)]
        for f in bridge:
            for loop in f.loops:
                which = ('arm' if original[loop.vert[src]].get(up, 0) > .99 else 'chest') + n
                uv_at[which, tuple(pts[loop.vert[src]].round(5))] = tuple(loop[uv_layer].uv)
        dropped += len(bridge)
        if bridge:
            bmesh.ops.delete(bm, geom=bridge, context='FACES_ONLY')
        # And at the elbow and the wrist the faces from one piece's end ring to the next piece's root ring.
        pure = lambda v, bone: original[v[src]].get(bone, 0) > .99
        for hinge, above, below, _ in side['hinges']:
            bridge = [f for f in bm.faces if any(pure(v, above) for v in f.verts) and any(pure(v, below) for v in f.verts)]
            for f in bridge:
                for loop in f.loops:
                    which = hinge + ('A' if pure(loop.vert, above) else 'B') + n
                    uv_at[which, tuple(pts[loop.vert[src]].round(5))] = tuple(loop[uv_layer].uv)
            dropped += len(bridge)
            if bridge:
                bmesh.ops.delete(bm, geom=bridge, context='FACES_ONLY')
    bm.to_mesh(me)
    bm.free()
    me.update()
    source_of = [d.value for d in me.attributes['src'].data]
    piece = {}
    for poly in me.polygons:
        kind = piece_of({dom[source_of[v]] for v in poly.vertices})
        for v in poly.vertices:
            assert piece.setdefault(v, kind) == kind, (ob.name, v, kind, piece[v])
    ob.vertex_groups.clear()
    for v in me.vertices:
        s = source_of[v.index]
        p, kind = pts[s], piece.get(v.index, 'body')
        if kind.startswith('haunch'):
            leg = next(l for l in legs if kind == 'haunch' + l['name'])
            m, off, dst = leg['haunch']
            entry = dict(at=m @ p + off, w={dst: 1.0}, turn=np.linalg.inv(m).T)
            if dom[s] not in LEG_OF:               # a doubled point: the haunch's open edge, to be closed
                if dom[s] not in FOOT_OF:
                    pivot = m @ H[leg['hip']] + off
                    entry['at'] = pivot + HIP_END * (entry['at'] - pivot)
                else:
                    entry['at'] = entry['at'] + KNEE_END * (m @ (H[leg['hip'] + 1] - H[leg['foot']]))
                caps[kind + ('end' if dom[s] in FOOT_OF else 'top')][tuple(p.round(5))] = entry
            # Its skirt met the body in a crease and its sock met the foot in another. Closed, it is one round
            # blob, so each place carries one normal and round_out shades it whole.
            entry['tag'] = unit(entry['at'] - (m @ ((H[leg['hip']] + H[leg['hip'] + 1]) / 2) + off))
        elif kind.startswith('foot'):
            leg = next(l for l in legs if kind == 'foot' + l['name'])
            m, off, dst = leg['footmap']
            entry = dict(at=m @ p + off, w={dst: 1.0}, turn=np.linalg.inv(m).T)
        else:
            at, w, turn = map_point(p, seams[tuple(p.round(5))])
            if ob.name == 'laglarge_mesh_00':          # the whole black fan is tail, its base too (v2)
                m, off, dst = tail_map
                at, w, turn = (idle[4] @ np.r_[m @ p + off, 1])[:3], {4: 1.0}, np.linalg.inv(idle[4][:3, :3] @ m).T
            entry = dict(at=at, w=w, turn=turn)
        entry['src'] = s
        points[ob.name, v.index] = entry
        for which in caps:
            if (which, tuple(p.round(5))) in uv_at:
                caps[which][tuple(p.round(5))] = dict(at=entry['at'], w=dict(entry['w']), uv=uv_at[which, tuple(p.round(5))])
    # The edges the split opened, by the source places on them: the body's hole and the foot's top.
    uvs = me.uv_layers.active.data
    for poly in me.polygons:
        bones = [dom[source_of[v]] for v in poly.vertices]
        kind = piece_of(set(bones))
        if kind.startswith('haunch'):
            leg = next(l for l in legs if kind == 'haunch' + l['name'])
            for v, bone, li in zip(poly.vertices, bones, poly.loop_indices):
                key = tuple(pts[source_of[v]].round(5))
                if bone in FOOT_OF:
                    m, off, dst = leg['footmap']
                    caps['foot' + leg['name']][key] = dict(at=m @ pts[source_of[v]] + off, w={dst: 1.0}, uv=tuple(uvs[li].uv))
                    caps[kind + 'end'][key]['uv'] = tuple(uvs[li].uv)
                elif bone not in LEG_OF:
                    at, w, _ = map_point(pts[source_of[v]], seams[key])
                    caps['body' + leg['name']][key] = dict(at=at, w=w, uv=tuple(uvs[li].uv), like=True)
                    caps[kind + 'top'][key]['uv'] = tuple(uvs[li].uv)
print({k: len(v) for k, v in caps.items()}, flush=True)

# ---------------------------------------------------------------- new surface: the caps and the shins
blue_ob = next(o for o in loaded.objects if o.name == 'laglarge_mesh_02')
image = next(n.image for n in blue_ob.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
px = np.array(image.pixels[:]).reshape(image.size[1], image.size[0], -1)
uvs = np.array([d.uv[:] for d in blue_ob.data.uv_layers.active.data])
source_of = [d.value for d in blue_ob.data.attributes['src'].data]
on_haunch = np.array([max(records[blue_ob.name][1][source_of[l.vertex_index]], key=records[blue_ob.name][1][source_of[l.vertex_index]].get)
                      in LEG_OF for l in blue_ob.data.loops])
colours = np.array([px[int(np.clip(v % 1, 0, .999) * image.size[1]), int(np.clip(u % 1, 0, .999) * image.size[0]), :3] for u, v in uvs])
middle = np.median(colours[on_haunch], axis=0)
BLUE = uvs[on_haunch][np.argmin(np.linalg.norm(colours[on_haunch] - middle, axis=1))]
print('leg blue', middle.round(3), 'at uv', BLUE.round(4), 'in', image.name, tuple(image.size), flush=True)

new_points, new_faces, new_rows, new_uvs, new_tags = [], [], [], [], []


def add(entries, faces, outward=None):
    """Points (dicts with at, w and maybe uv) and faces over them, wound to face away from the point `outward`."""
    base = len(new_points)
    for e in entries:
        new_points.append(e['at'])
        new_rows.append(e['w'])
        new_uvs.append(e.get('uv', tuple(BLUE)))
        new_tags.append(e.get('tag', 'body' if e.get('like') else None))
    for f in faces:
        a, b, c = [np.array(entries[i]['at']) for i in f[:3]]
        mid = np.mean([entries[i]['at'] for i in f], axis=0)
        if outward is not None and np.cross(b - a, c - a) @ (mid - outward) < 0:
            f = f[::-1]
        new_faces.append([base + i for i in f])


def fan(entries, away):
    """A loop of points closed with triangles about its middle, facing `away` from that point."""
    ring = [e for e in entries]
    centre = np.mean([e['at'] for e in ring], axis=0)
    normal = np.linalg.svd(np.array([e['at'] for e in ring]) - centre)[2][-1]
    u = unit(ring[0]['at'] - centre)
    v = np.cross(normal, u)
    ring.sort(key=lambda e: np.arctan2((e['at'] - centre) @ v, (e['at'] - centre) @ u))
    if len(ring) == 3:
        add(ring, [[0, 1, 2]], away)
    else:
        add(ring, [[0, i, i + 1] for i in range(1, len(ring) - 1)], away)


for leg in legs:
    n = leg['name']
    m, off, _ = leg['haunch']
    middle_of = m @ ((H[leg['hip']] + H[leg['hip'] + 1]) / 2) + off          # inside the haunch
    fan(list(caps['body' + n].values()), I[4])                               # the body's hole, facing out of the body
    fan(list(caps['haunch' + n + 'top'].values()), middle_of)
    fan(list(caps['haunch' + n + 'end'].values()), middle_of)
    fan(list(caps['foot' + n].values()), I[leg['tf']] - np.array([0, 0, 1.]))  # the foot's top, facing up
    # The shin: a closed tube on DK's shin joint from his knee to his ankle, a ball at the knee so it turns in place.
    a, b = T[leg['tk']], T[leg['tf']]
    axis = unit(b - a)
    u = unit(np.cross(axis, (0, 1, 0)))
    v = np.cross(axis, u)
    long = np.linalg.norm(b - a)
    rings = [(-SHIN[0] * .98, .2), (-SHIN[0] * .7, .72), (0, 1), (.35 * long, 1), (.7 * long, 1), (long, 1), (long + .3, .5)]
    skin = idle[leg['tk']]
    rows = []
    for s, share in rings:
        radius = (SHIN[0] + (SHIN[1] - SHIN[0]) * np.clip(s / long, 0, 1)) * share
        centre = a + axis * s
        rows.append([dict(at=(skin @ np.r_[centre + radius * (np.cos(t) * u + np.sin(t) * v), 1])[:3], w={leg['tk']: 1.0})
                     for t in np.arange(SIDES) * 2 * np.pi / SIDES])
    entries = [e for row in rows for e in row]
    inside = (skin @ np.r_[(a + b) / 2, 1])[:3]
    quads = [[r * SIDES + i, r * SIDES + (i + 1) % SIDES, (r + 1) * SIDES + (i + 1) % SIDES, (r + 1) * SIDES + i]
             for r in range(len(rows) - 1) for i in range(SIDES)]
    add(entries, [t for q in quads for t in ([q[0], q[1], q[2]], [q[0], q[2], q[3]])], inside)
    fan(rows[0], inside)
    fan(rows[-1], inside)
for n, side in ARMS.items():
    joint, axis = I[side['joint']], unit(I[side['elbow']] - I[side['joint']])
    fan(list(caps['chest' + n].values()), I[26])                             # the chest closed where the arm left
    # The arm's root ring, then a ball about DK's shoulder joint: it looks the same however the arm turns.
    ring = list(caps['arm' + n].values())
    assert len(ring) == 4 and len(caps['chest' + n]) == 4, (n, len(ring), len(caps['chest' + n]))
    out = [unit((e['at'] - joint) - ((e['at'] - joint) @ axis) * axis) for e in ring]
    order = np.argsort([np.arctan2(o @ np.cross(axis, out[0]), o @ out[0]) for o in out])
    ring, out = [ring[i] for i in order], [out[i] for i in order]
    rows = [ring]
    for along, across in ((0, 1), (-.62, .78), (-.92, .38)):
        rows.append([dict(at=joint + BALL * (along * axis + across * o), w={side['joint']: 1.0}, uv=e['uv'])
                     for e, o in zip(ring, out)])
    entries = [e for row in rows for e in row]
    quads = [[r * 4 + i, r * 4 + (i + 1) % 4, (r + 1) * 4 + (i + 1) % 4, (r + 1) * 4 + i] for r in range(3) for i in range(4)]
    add(entries, [t for q in quads for t in ([q[0], q[1], q[2]], [q[0], q[2], q[3]])], joint + .4 * axis)
    fan(rows[-1], joint)
    # The elbow and the wrist: both pieces closed, and a ball about DK's joint on the piece below it.
    for hinge, _, _, dk in side['hinges']:
        at, before = I[dk], I[dk - 1]
        above, below = list(caps[hinge + 'A' + n].values()), list(caps[hinge + 'B' + n].values())
        fan(above, (before + at) / 2)
        fan(below, at + (at - before) / 2)
        reach = [np.linalg.norm(e['at'] - at) for e in above + below]
        radius = min(HINGE[hinge], max(reach) + .05)
        print(hinge, n, 'ball %.2f; %d and %d ring points, %.2f to %.2f from the joint' % (
            radius, len(above), len(below), min(reach), max(reach)), flush=True)
        axis = unit(at - before)
        u = unit(np.cross(axis, (0, 0, 1)))
        v = np.cross(axis, u)
        rows = [[dict(at=at + radius * (np.cos(lat) * axis + np.sin(lat) * (np.cos(t) * u + np.sin(t) * v)),
                      w={dk: 1.0}, uv=below[0]['uv']) for t in np.arange(6) * np.pi / 3]
                for lat in np.radians((30, 65, 100, 135, 160))]
        entries = [e for row in rows for e in row]
        quads = [[r * 6 + i, r * 6 + (i + 1) % 6, (r + 1) * 6 + (i + 1) % 6, (r + 1) * 6 + i] for r in range(len(rows) - 1) for i in range(6)]
        add(entries, [t for q in quads for t in ([q[0], q[1], q[2]], [q[0], q[2], q[3]])], at)
        fan(rows[0], at)
        fan(rows[-1], at)
parts = bpy.data.meshes.new('swampert_v3_parts')
parts.from_pydata([list(map(float, p)) for p in new_points], [], new_faces)
parts.update()
parts.materials.append(blue_ob.data.materials[0])
layer = parts.uv_layers.new(name=blue_ob.data.uv_layers.active.name)
for loop, d in zip(parts.loops, layer.data):
    d.uv = new_uvs[loop.vertex_index]
parts.polygons.foreach_set('use_smooth', [True] * len(parts.polygons))
parts_ob = bpy.data.objects.new('swampert_v3_parts', parts)
bpy.context.scene.collection.objects.link(parts_ob)
for i, (p, w, tag) in enumerate(zip(new_points, new_rows, new_tags)):
    points[parts_ob.name, i] = dict(at=np.array(p), w=dict(w), turn=None, src=None, tag=tag)
print('new surface: %d points, %d faces' % (len(new_points), len(new_faces)), flush=True)

# ---------------------------------------------------------------- weights that follow DK's joints
span = T[26] - T[4]
to_chest = np.linalg.inv(idle[26])
pelvis = collar = 0
print('idle collars against the chest joint:', [float(np.abs(idle[j] - idle[26]).max().round(4)) for j in (27, 49)], flush=True)
for key, e in points.items():
    w = e['w']
    share = w.get(26, 0)
    if share < 1e-6:
        continue
    # The collar: the chest beside a collar bone goes with it, by how far along the bone it sits. At the neck end
    # nothing moves, at the shoulder joint and past it everything does.
    for joint, bone in ((29, 27), (51, 49)):
        along = (e['at'] - I[bone]) @ (I[joint] - I[bone]) / ((I[joint] - I[bone]) @ (I[joint] - I[bone]))
        off = np.linalg.norm(e['at'] - (I[bone] + np.clip(along, 0, 1) * (I[joint] - I[bone])))
        near = float(smooth(along) * smooth((CAP[1] - off) / (CAP[1] - CAP[0])))
        if near > 0:
            w[bone] = w.get(bone, 0) + share * near
            w[26] = share = share * (1 - near)
            collar += 1
    # The pelvis: up the trunk from the hips to the chest joint, as soft_legs did after rounding.
    if share >= .5 * sum(w.values()):
        up = float(smooth(((to_chest @ np.r_[e['at'], 1])[:3] - T[4]) @ span / (span @ span)))
        if up < 1:
            w[4] = w.get(4, 0) + share * (1 - up)
            w[26] = share * up
            pelvis += 1
    e['w'] = {j: v for j, v in w.items() if v > 1e-6}
print('collar %d points, pelvis %d points' % (collar, pelvis), flush=True)


def tidy(w):
    top = sorted(w.items(), key=lambda kv: -kv[1])[:MOST]
    total = sum(v for _, v in top)
    eighths = {j: round(v / total * STEP) for j, v in top}
    eighths = {j: n for j, n in eighths.items() if n}
    largest = max(eighths, key=eighths.get)
    eighths[largest] += STEP - sum(eighths.values())
    return {j: n / STEP for j, n in eighths.items()}


# ---------------------------------------------------------------- bind every point back through its own idle skin
mixes, body_normals = {}, {}
for ob in [*loaded.objects, parts_ob]:
    me = ob.data
    skins = np.empty((len(me.vertices), 3, 3))
    for v in me.vertices:
        e = points[ob.name, v.index]
        w = e['w'] = tidy(e['w'])
        m = sum(share * idle[j] for j, share in w.items())
        v.co = (np.linalg.inv(m) @ np.r_[e['at'], 1])[:3]
        skins[v.index] = m[:3, :3]
        for j, share in w.items():
            (ob.vertex_groups.get(f'JOBJ_{j}') or ob.vertex_groups.new(name=f'JOBJ_{j}')).add([v.index], share, 'REPLACE')
        mixes[tuple(sorted(w))] = mixes.get(tuple(sorted(w)), 0) + 1
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
    me.update()
    index = np.empty(len(me.loops), int)
    me.loops.foreach_get('vertex_index', index)
    if ob is parts_ob:
        # New surface shades itself, but a cap over a hole takes the normals of the surface around the hole.
        in_idle = []
        for i, n in zip(index, stored_normals(me)):
            tag = points[ob.name, i]['tag']
            if isinstance(tag, str):
                near = body_normals[tuple(points[ob.name, i]['at'].round(3))]
                tag = unit(np.sum(near, axis=0))
            in_idle.append(np.linalg.inv(skins[i]).T @ n if tag is None else tag)
    else:
        # Shading: the source's own corner normals, turned as their point was into idle.
        kept = records[ob.name][2][[d.value for d in me.attributes['src_corner'].data]]
        assert len(kept) == len(me.loops), ob.name
        me.attributes.remove(me.attributes['src_corner'])
        me.attributes.remove(me.attributes['src'])
        in_idle = []
        for i, n in zip(index, kept):
            e = points[ob.name, i]
            in_idle.append(e['tag'] if 'tag' in e else unit(e['turn'] @ n))
            if 'tag' not in e:
                body_normals.setdefault(tuple(e['at'].round(3)), []).append(in_idle[-1])
    turned = np.array([skins[i].T @ n for i, n in zip(index, in_idle)])       # and back to the bind with their point
    turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-9)
    me.normals_split_custom_set(turned.tolist())
    me.update()
print('weight mixes', dict(sorted(mixes.items(), key=lambda kv: -kv[1])), flush=True)

# ---------------------------------------------------------------- the eyes, as v2
src_eye_points = records['laglarge_mesh_05'][0]
with bpy.data.libraries.load(str(SOURCE), link=False) as (data, loaded_eye):
    loaded_eye.objects = ['laglarge_mesh_05']
src_eye = loaded_eye.objects[0]
for name, ob in eyes.items():
    start = 0 if name == 'eyes_left' else 7
    poly_start = 0 if name == 'eyes_left' else 5
    for poly in ob.data.polygons:
        original = src_eye.data.polygons[poly_start + poly.index]
        for li, source_li in zip(poly.loop_indices, original.loop_indices):
            u, v = src_eye.data.uv_layers.active.data[source_li].uv
            ob.data.uv_layers.active.data[li].uv = ((u * 64 - 2) / 62, v * 4 - 3)
    ob.vertex_groups.clear()
    vg = ob.vertex_groups.new(name='JOBJ_44')
    for v in ob.data.vertices:
        v.co = head_m @ src_eye_points[start + v.index] + head_map[1]
        vg.add([v.index], 1, 'REPLACE')
    ob.data.update()
bpy.data.objects.remove(src_eye, do_unlink=True)
atlas = next(im for im in bpy.data.images if im.name.startswith('tex_3C88') and im.size[1] == 256)
pixels = np.array(atlas.pixels[:]).reshape(256, 64, 4)[::-1]
rgba = np.clip(np.rint(pixels * 255), 0, 255).astype('uint8')
for state, row in (('open', 0), ('half', 64), ('closed', 128)):
    Image.fromarray(rgba[row:row + 64, 2:64]).save(B / 'eyes' / f'{state}.png')
eye_image = bpy.data.images.load(str(B / 'eyes/open.png'), check_existing=False)
eye_image.pack()
eye_image.name = 'eyes_open_v2'
for node in bpy.data.materials['eyes'].node_tree.nodes:
    if node.type == 'TEX_IMAGE':
        node.image = eye_image
record = json.loads((B / 'eyes.json').read_text(encoding='utf-8'))
record['made'] = {s: f'Original Swampert atlas at row {row}; swampert_v3_hand.py' for s, row in (('open', 0), ('half', 64), ('closed', 128))}
record['drawn'] = {}
(B / 'eyes.json').write_text(json.dumps(record, indent=1), encoding='utf-8')

# ---------------------------------------------------------------- weld the rip's exact copies (v2), keep its normals
for ob in loaded.objects:
    before = len(ob.data.polygons)
    normals = stored_normals(ob.data)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    assert len(ob.data.polygons) == before and len(ob.data.loops) == len(normals), ob.name
    ob.data.normals_split_custom_set(normals.tolist())
    ob.data.update()
    ob.name += '_v3'                       # not a name in base.blend: round_out reads these normals, not the raw fit's
source_faces = sum(len(o.data.polygons) for o in loaded.objects)
assert source_faces == 871 - 10 - dropped, (source_faces, dropped)   # all of the source but its eye quads (on eyes_*)
bpy.ops.wm.save_as_mainfile(filepath=str(B / 'edited.blend'))
print('%d source triangles kept (%d shoulder faces dropped), %d new; saved edited.blend' % (source_faces, dropped, len(new_faces)), flush=True)
