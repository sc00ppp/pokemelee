"""stand_feet.py <build dir> <Fighter> [flat]: each foot rigged and placed as the fighter's own foot is, in edited.blend.
`flat` is for a blocky foot with a real flat sole (see flat_sole).

Three things the fit leaves wrong, each of which tips a foot off the floor in idle:
- A foot can ride the knee joint, or skip the foot joint for the toe joint (Machoke, Blaziken, Breloom), so it has no ankle
  and follows the shin. Below the ankle a point belongs to the foot, and its weight on anything else moves there.
- The sole is laid flat on y = 0 at rest, but rest isn't a stand: Ganondorf's rest foot is rolled 20 degrees and Yoshi's
  sole sits .86 under the floor. The foot turns about the ankle and slides until its sole has the plane and the depth
  under the ankle that the vanilla foot's has, and nothing of it hangs below that. A point shared with the shin moves by
  its share.
- Melee's back foot lifts its heel in idle and bends at the toe joint, so a foot that's stiff to the tip stands in the air.
  The toe joint takes the same share of the foot's length as on the vanilla foot.

The foot keeps the mon's shape and length: it is placed, never stretched to the fighter's (owner, 10-31).

Run after the edit, before round_out. No AI asks. Prints what each foot needed."""
import json
import struct
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np

import os
from rigswap.plugins.melee.targets.bones import JOINT_NAMES    # noqa: E402

T = Path(os.environ['RIGSWAP_MELEE_TARGETS'])
C = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)     # game (y up, +z front) to Blender
UP = np.array([0, 1, 0.])
LOW = .3            # the underside's low points lie in this share of the foot's height
SAME = 10           # hull faces within these degrees of each other are one patch
QUARTER = 25        # the sole's height is this percentile of the low points: one stray point mustn't set it
TWIN = np.array([1, -1, -1.])   # a rotation vector seen in the mirror across the fighter's midline
BAND = .12         # the ankle's blend into the shin, as a share of the shin's length above the ankle
TOE_BAND = .1       # the toe joint's blend, as a share of the foot's length
MOST = 4            # joints a point keeps


def local(node):
    if 'matrix' in node:
        return np.array(node['matrix'], float).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0, 0, 0, 1])
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    m[:3, :3] = m[:3, :3] @ np.diag(node.get('scale', [1, 1, 1]))
    m[:3, 3] = node.get('translation', [0, 0, 0])
    return m


def skeleton(fighter):
    """({joint: rest world}, {joint: it and the joints below it})"""
    b = (T / f'{fighter}.glb').read_bytes()
    n = struct.unpack('<I', b[12:16])[0]
    nodes = json.loads(b[20:20 + n])['nodes']
    rest, below = {}, {}

    def walk(i, parent, chain):
        world = parent @ local(nodes[i])
        name = nodes[i].get('name', '')
        if name.startswith('JOBJ_'):
            j = int(name[5:])
            rest[j], below[j] = world, {j}
            for k in chain:
                below[k].add(j)
            chain = chain + [j]
        for c in nodes[i].get('children', []):
            walk(c, world, chain)
    children = {c for nd in nodes for c in nd.get('children', [])}
    for i in range(len(nodes)):
        if i not in children:
            walk(i, np.eye(4), [])
    return rest, below


def meshes():
    return [o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.vertices)]


def weights(ob):
    """Vertex by vertex, {joint: weight}."""
    names = {g.index: g.name for g in ob.vertex_groups}
    return [{int(names[g.group][5:]): g.weight for g in v.groups if names.get(g.group, '').startswith('JOBJ_')
             and g.weight > 0} for v in ob.data.vertices]


def game_points(ob):
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get('co', co)
    mw = np.array(ob.matrix_world)
    return (co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]) @ C     # Blender to game: x' = C.T x, as rows x @ C


def foot_points(joints):
    """The rest points mostly on `joints`."""
    out = []
    for ob in meshes():
        for p, held in zip(game_points(ob), weights(ob)):
            total = sum(held.values())
            if total and sum(w for j, w in held.items() if j in joints) / total >= .5:
                out.append(p)
    return np.array(out).reshape(-1, 3)


def set_weights(ob, i, held):
    """Vertex i's joints from a {joint: weight}: its strongest MOST, summing to 1."""
    keep = sorted(held.items(), key=lambda item: -item[1])[:MOST]
    total = sum(w for _, w in keep)
    for g in [g for g in ob.vertex_groups if g.name.startswith('JOBJ_')]:
        g.remove([i])
    for j, w in keep:
        group = ob.vertex_groups.get(f'JOBJ_{j}') or ob.vertex_groups.new(name=f'JOBJ_{j}')
        group.add([i], w / total, 'REPLACE')


def sole(points, up):
    """The unit normal of the plane a foot's underside lies in, starting from a guess at up."""
    n = up / np.linalg.norm(up)
    for _ in range(6):
        h = points @ n
        _, _, axes = np.linalg.svd(points - points.mean(0) - np.outer(h - h.mean(), n))
        u, v = points @ axes[0], points @ axes[1]
        a = (u - u.min()) / max(np.ptp(u), 1e-9) * 4.99
        b = (v - v.min()) / max(np.ptp(v), 1e-9) * 2.99
        cell = {}
        for i in range(len(points)):
            key = int(a[i]), int(b[i])
            if key not in cell or h[i] < h[cell[key]]:
                cell[key] = i
        low = [i for i in cell.values() if h[i] <= h.min() + LOW * np.ptp(h)]
        if len(low) < 3:
            break
        at = points[low]
        spread = np.linalg.svd(at - at.mean(0))
        if spread[1][1] < 1e-6:     # the low points lie on a line, which gives no plane
            break
        normal = spread[2][2]
        n = normal if normal @ n > 0 else -normal
    return n


def flat_sole(points, up):
    """The same for a blocky foot with a real flat sole and toes curled up (Machoke), which the plane above reads short: the
    biggest patch of its convex hull looking down. A hull bridges claw tips, so this is wrong for claws (Scizor, Combusken)."""
    bm = bmesh.new()
    hull = bmesh.ops.convex_hull(bm, input=[bm.verts.new(p) for p in points])['geom']
    middle = points.mean(0)
    normals, area = [], []
    for face in hull:
        if isinstance(face, bmesh.types.BMFace):
            face.normal_update()
            n = np.array(face.normal)
            normals.append(n if n @ (np.array(face.calc_center_median()) - middle) < 0 else -n)
            area.append(face.calc_area())
    bm.free()
    normals, area = np.array(normals), np.array(area)
    down = normals @ up > .5
    if not down.any():
        return up
    normals, area = normals[down], area[down]
    near = normals @ normals.T > np.cos(np.radians(SAME))
    best = near[(near * area).sum(1).argmax()]
    n = normals[best].T @ area[best]
    return n / np.linalg.norm(n)


def underside(points, n):
    """The heights along n of the foot's low points, one per patch of the sole."""
    h = points @ n
    _, _, axes = np.linalg.svd(points - points.mean(0) - np.outer(h - h.mean(), n))
    u, v = points @ axes[0], points @ axes[1]
    a = (u - u.min()) / max(np.ptp(u), 1e-9) * 4.99
    b = (v - v.min()) / max(np.ptp(v), 1e-9) * 2.99
    cell = {}
    for i in range(len(points)):
        key = int(a[i]), int(b[i])
        cell[key] = min(cell.get(key, h[i]), h[i])
    return [x for x in cell.values() if x <= h.min() + LOW * np.ptp(h)]


def arc(a, b):
    """The rotation vector of the shortest turn from unit a to unit b."""
    axis = np.cross(a, b)
    size = np.linalg.norm(axis)
    return axis / size * np.arctan2(size, a @ b) if size > 1e-9 else np.zeros(3)


def turned(points, vector):
    """Points turned by a rotation vector (Rodrigues), row by row."""
    angle = np.linalg.norm(vector, axis=-1, keepdims=True)
    k = vector / np.maximum(angle, 1e-12)
    return points * np.cos(angle) + np.cross(k, points) * np.sin(angle) + \
        k * (k * points).sum(-1, keepdims=True) * (1 - np.cos(angle))


def vanilla_feet(fighter, rest, below, names, read):
    """{side: (sole normal, sole's depth under the ankle, toe joint, the way along the foot, the part of its length before
    the toe joint)} of the fighter's own feet, at rest."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(T / f'{fighter}.glb'))
    out = {}
    for side in 'LR':
        j = names[f'{side}FootJ']
        foot, ankle = foot_points(below[j]), rest[j][:3, 3]
        n = read(foot, UP)
        held ={k: foot_points({k}) for k in below[j] - {j}}
        toe = max(held, key=lambda k: len(held[k]), default=None)
        along, part = None, None
        if toe is not None and len(held[toe]):
            along = rest[toe][:3, 3] - ankle
            along = along - along @ n * n
            along = along / np.linalg.norm(along)
            ends = foot @ along
            cut = ((foot_points({j}) @ along).max() + (held[toe] @ along).min()) / 2
            part = (cut - ends.min()) / np.ptp(ends)
        else:
            toe = None
        out[side] = n, np.percentile(underside(foot - ankle, n), QUARTER), toe, along, part
    return out


def give_foot(side, names, rest, below):
    """Below the ankle, weight on anything but the foot moves to the foot joint. Returns how many points changed."""
    other = 'R' if side == 'L' else 'L'
    leg, far = below[names[f'{side}LegJ']], below[names[f'{other}LegJ']]
    j, chain = names[f'{side}FootJ'], below[names[f'{side}FootJ']]
    ankle, knee = rest[j][:3, 3], rest[names[f'{side}KneeJ']][:3, 3]
    shin = np.linalg.norm(ankle - knee)
    down = (ankle - knee) / shin
    changed = 0
    for ob in meshes():
        for i, (p, held) in enumerate(zip(game_points(ob), weights(ob))):
            ours = sum(w for k, w in held.items() if k in leg)
            if not ours or sum(w for k, w in held.items() if k in far) > ours:
                continue
            share = np.clip(((p - ankle) @ down / shin + BAND) / BAND, 0, 1)
            loose = {k: w for k, w in held.items() if k not in chain}
            if not share or not loose:
                continue
            new = {k: w * (1 - share) for k, w in loose.items()}
            new.update({k: w for k, w in held.items() if k in chain})
            new[j] = new.get(j, 0) + share * sum(loose.values())
            set_weights(ob, i, {k: w for k, w in new.items() if w > 1e-3})
            changed += 1
    return changed


def tips(feet, own, read):
    """{side: the turn that lays its sole on the vanilla sole}. Rest mirrors left and right, so both feet need the same turn,
    and on a foot of a dozen points the larger reading is the bad one (Miltank 44 and 6, Scizor 33 and 3)."""
    turn = {side: arc(read(foot, UP), own[side][0]) for side, foot in feet.items()}
    least = min(turn, key=lambda side: np.linalg.norm(turn[side]))
    return {side: turn[least] if side == least else turn[least] * TWIN for side in turn}


def stand(side, fighter, own, tip, names, rest, below):
    """The foot turned about the ankle and slid along the sole to the vanilla foot's, and nothing of it under the sole."""
    j, joints = names[f'{side}FootJ'], below[names[f'{side}FootJ']]
    ankle = rest[j][:3, 3]
    foot = foot_points(joints)
    n_own, depth = own[:2]
    spun = turned(foot - ankle, tip)
    slide = depth - np.percentile(underside(spun, n_own), QUARTER)
    for ob in meshes():
        pts, held = game_points(ob), weights(ob)
        share = np.array([sum(w for k, w in h.items() if k in joints) / (sum(h.values()) or 1) for h in held])
        moved = share > 0
        out = turned(pts[moved] - ankle, tip * share[moved, None]) + np.outer(share[moved] * slide, n_own)
        out += np.outer(np.maximum(depth - out @ n_own, 0) * share[moved], n_own)
        pts[moved] = ankle + out
        mw = np.array(ob.matrix_world)
        ob.data.vertices.foreach_set('co', ((pts @ C.T - mw[:3, 3]) @ np.linalg.inv(mw[:3, :3]).T).ravel())
        ob.data.update()
    print('%s %s foot: %d points, tipped %.1f, slid %+.2f' % (
        fighter, side, len(foot), np.degrees(np.linalg.norm(tip)), slide))


def bend_toe(side, own, names, below):
    """The foot's far part onto the toe joint, cut at the vanilla foot's share of its length."""
    j, chain = names[f'{side}FootJ'], below[names[f'{side}FootJ']]
    toe, along, part = own[2:5]
    if toe is None:
        return
    ends = foot_points(chain) @ along
    length = np.ptp(ends)
    cut = ends.min() + part * length
    for ob in meshes():
        for i, (p, held) in enumerate(zip(game_points(ob), weights(ob))):
            on = sum(w for k, w in held.items() if k in chain)
            if not on:
                continue
            bit = np.clip((p @ along - cut) / (TOE_BAND * length) + .5, 0, 1)
            new = {k: w for k, w in held.items() if k not in chain}
            new[j], new[toe] = on * (1 - bit), on * bit
            set_weights(ob, i, {k: w for k, w in new.items() if w > 1e-3})


def main():
    build, fighter = Path(sys.argv[1]), sys.argv[2]
    if fighter == 'Ganondorf':
        bpy.ops.wm.open_mainfile(filepath=str(build / 'edited.blend'))
        if bpy.context.scene.get('machoke_idle_source_feet', False):
            print('Machoke: keeping source feet placed and bound through Wait1-1 by hand_machoke.py')
            return
    read = flat_sole if sys.argv[3:] == ['flat'] else sole
    names = {v: k for k, v in JOINT_NAMES[fighter].items()}
    rest, below = skeleton(fighter)
    own = vanilla_feet(fighter, rest, below, names, read)
    bpy.ops.wm.open_mainfile(filepath=str(build / 'edited.blend'))
    feet = {}
    for side in 'LR':
        print(fighter, side, 'foot took over', give_foot(side, names, rest, below), 'points')
        feet[side] = foot_points(below[names[f'{side}FootJ']])
        if len(feet[side]) < 4:
            print(fighter, side, 'has no foot to stand')
            del feet[side]
    if feet:
        turn = tips(feet, own, read)
        for side in feet:
            stand(side, fighter, own[side], turn[side], names, rest, below)
            bend_toe(side, own[side], names, below)
    bpy.ops.wm.save_as_mainfile(filepath=str(build / 'edited.blend'))


main()
