"""hand_machoke_neck.py <3-build>: Machoke's head back against his back, as the source has it, in build.blend, at idle. Run after
hand_machoke.py --round.

The source has no neck: its head touches a hump of shoulder. The port kept the source's head on an upright Ganondorf with a
chest as deep as the source's whole sloped back, so the head's skin ran back as a long tube into a lip on the back, weighted
to the hips, with the far collar standing up as a fin. The fit also narrowed the shoulders to Ganondorf's, about .7 of the
source's at the head's scale, so the head hung out from them as half their span where the source's is a third. So: the head
moves back and comes down to size against those shoulders, the upper back comes in, the band between takes the surface of
least bend, with weights spread evenly across it so the head pulls the neck and the hips no longer do, and a hump rises
right behind the head. The arms, belt and feet don't move, and the belt and shoulders
keep their own weights: only the neck takes new ones. No AI asks."""

from cast_paths import WORK, TARGETS
import heapq
import sys
from pathlib import Path

import bpy
import numpy as np

CENTRE, REACH = np.array([2.2, .3, 17.4]), 5.8      # idle: the band and the back's top, about the lip
TORSO = {2, 3, 4, 17, 18, 19, 20, 22, 52, 53, 64, 66}
HEAD, HIPS, SPINE = 53, 4, 18
BELT = 'goriky_mesh_07', 'goriky_mesh_19', 'goriky_mesh_27'
SHIFT = 2.3                                         # the head moves back this far along its own axis, whole, so it swings less too
SMALL, REAR = .8, 2.                                # the head's size, about this far behind its centre: the fit narrowed the shoulders
BACK, DEPTH = (2.6, 0.), .62                        # behind this x the upper back keeps this share of its depth:
RISE = 13., 15.5                                    # the belt's rear below the first height, the spine above the second
HUMP, WIDE, HIGH = np.array([1.5, .3, 18.]), 3.8, .5  # the hump behind the head
SHOULDERS, PIN = {20, 22, 64, 66}, .25               # a point this much on its shoulder keeps its weights, unless it's in the neck
GIRTH = 2.5                                         # the neck: this far along the skin from the head's own points
STEP = 16                                           # weights in sixteenths, three joints a point
WELD = 3                                            # decimals: points this close at idle are one point


def helpers():
    ns = {'__name__': 'machoke_neck', '__file__': str(Path(__file__).parent / 'round_out.py')}
    code = Path(ns['__file__']).read_text(encoding='utf-8')
    exec(compile(code.rsplit('\nmain()', 1)[0], ns['__file__'], 'exec'), ns)
    return ns


def weights(ob):
    names = {g.index: int(g.name[5:]) for g in ob.vertex_groups if g.name.startswith('JOBJ_')}
    return [{names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 1e-7} for v in ob.data.vertices]


def set_weights(ob, index, held):
    for group in ob.vertex_groups:
        group.remove([index])
    for j, w in held.items():
        (ob.vertex_groups.get(f'JOBJ_{j}') or ob.vertex_groups.new(name=f'JOBJ_{j}')).add([index], w, 'REPLACE')


def ease(value, low, high):
    t = np.clip((value - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def tidy(held):
    """The three strongest joints, in sixteenths, summing to one."""
    top = sorted(held.items(), key=lambda kv: -kv[1])[:3]
    total = sum(w for _, w in top)
    cut = [(j, round(w / total * STEP)) for j, w in top]
    cut[0] = cut[0][0], cut[0][1] + STEP - sum(n for _, n in cut)
    return {j: n / STEP for j, n in cut if n}


def main():
    build = Path(sys.argv[1])
    bpy.ops.wm.open_mainfile(filepath=str(build / 'build.blend'))
    ns = helpers()
    meshes = ns['mesh_objects']()
    skin = ns['idle_skin']('Ganondorf')

    # one graph of the whole body at idle, across its meshes
    ids, spots, held, parts = {}, [], [], {}
    for ob in meshes:
        me = ob.data
        mats = ns['vertex_skins'](ob, skin)
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        idle = np.einsum('nij,nj->ni', mats[:, :3, :3], co) + mats[:, :3, 3]
        ws = weights(ob)
        place = np.empty(len(idle), int)
        for i, p in enumerate(idle):
            key = tuple(p.round(WELD))
            if key not in ids:
                ids[key] = len(spots)
                spots.append(p)
                held.append(ws[i])
            place[i] = ids[key]
        index = np.empty(len(me.loops), int)
        me.loops.foreach_get('vertex_index', index)
        normals = np.einsum('nij,nj->ni', np.linalg.inv(mats[index, :3, :3]).transpose(0, 2, 1), ns['stored_normals'](me))
        parts[ob.name] = dict(idle=idle, place=place, index=index, normals=normals)
    spots = np.array(spots)
    n = len(spots)
    edges = set()
    for ob in meshes:
        place = parts[ob.name]['place']
        for face in ob.data.polygons:
            ring = place[list(face.vertices)]
            edges.update((min(a, b), max(a, b)) for a, b in zip(ring.tolist(), np.roll(ring, -1).tolist()) if a != b)
    near = [[] for _ in range(n)]
    for a, b in edges:
        near[a].append(b)
        near[b].append(a)

    def free(i):
        w = held[i]
        total = sum(w.values())
        return np.linalg.norm(spots[i] - CENTRE) < REACH and w.get(HEAD, 0) / total < .999 and \
            sum(v for j, v in w.items() if j not in TORSO) / total < .2 and near[i]

    # the head and the back, moved; the band between follows below
    back = skin[HEAD][:3, :3] @ np.array([0, SHIFT, 0])
    print('head moves', back.round(2))
    goal = spots.copy()
    belt = {int(i) for name in BELT for i in parts[name]['place']}
    heads = {i for i in range(n) if held[i].get(HEAD, 0) / sum(held[i].values()) > .999}
    rear = spots[list(heads)].mean(0) + back + skin[HEAD][:3, :3] @ np.array([0, REAR, 0])
    for i in range(n):
        total = sum(held[i].values())
        if i in heads:
            goal[i] = rear + SMALL * (spots[i] + back - rear)
        elif i not in belt:
            arm = sum(v for j, v in held[i].items() if j not in TORSO) / total
            rise = ease(spots[i, 2], *RISE)
            goal[i, 0] -= (1 - DEPTH) * max(spots[i, 0] - (BACK[0] + rise * (BACK[1] - BACK[0])), 0) * (1 - arm)

    inside = [i for i in range(n) if free(i)]
    inner = set(inside)
    rows = sorted(inner | {j for i in inside for j in near[i]})
    columns = sorted(set(rows) | {j for i in rows for j in near[i]})
    at = {i: k for k, i in enumerate(columns)}
    lap = np.zeros((len(rows), len(columns)))
    for r, i in enumerate(rows):
        lap[r, at[i]] = 1
        for j in near[i]:
            lap[r, at[j]] -= 1 / len(near[i])
    mine = [at[i] for i in inside]
    rest = [at[i] for i in columns if i not in inner]
    fixed = goal[[i for i in columns if i not in inner]]

    # least bend, held a little to the old surface toward the edge of the reach
    t = np.linalg.norm(spots[inside] - CENTRE, axis=1) / REACH
    hold = np.diag(.6 * t ** 4)
    a = lap[:, mine]
    moved = np.linalg.solve(a.T @ a + hold, hold @ goal[inside] - a.T @ lap[:, rest] @ fixed)
    r = np.clip(1 - np.sum((moved - HUMP) ** 2, axis=1) / WIDE ** 2, 0, 1)
    moved[:, 2] += HIGH * r * r
    print('faired', len(inside), 'points, moved up to', np.linalg.norm(moved - spots[inside], axis=1).max().round(2))

    # the same band's weights, spread evenly; the upper back's share of the hips goes to the spine
    now = goal.copy()
    now[inside] = moved
    along = dict.fromkeys(heads, 0.)
    heap = [(0., i) for i in along]
    while heap:
        walked, i = heapq.heappop(heap)
        if walked > along[i]:
            continue
        for j in near[i]:
            step = walked + np.linalg.norm(now[i] - now[j])
            if j not in belt and step < GIRTH and step < along.get(j, GIRTH):
                along[j] = step
                heapq.heappush(heap, (step, j))

    def pinned(i):
        return i in belt or (i not in along and sum(held[i].get(j, 0) for j in SHOULDERS) / sum(held[i].values()) >= PIN)

    loose = [i for i in inside if not pinned(i)]
    row = {i: k for k, i in enumerate(loose)}
    outside = sorted({j for i in loose for j in near[i]} - set(loose))
    out = {i: k for k, i in enumerate(outside)}
    joints = sorted({j for i in loose + outside for j in held[i]} | {SPINE})
    plain = np.zeros((len(loose), len(loose)))
    side = np.zeros((len(loose), len(outside)))
    for i in loose:
        plain[row[i], row[i]] = 1
        for j in near[i]:
            if j in row:
                plain[row[i], row[j]] -= 1 / len(near[i])
            else:
                side[row[i], out[j]] += 1 / len(near[i])
    known = np.zeros((len(outside), len(joints)))
    for k, i in enumerate(outside):
        total = sum(held[i].values())
        rise = 0 if i in belt else ease(spots[i, 2], *RISE)
        for j, w in held[i].items():
            known[k, joints.index(j)] += w / total * (1 - rise if j == HIPS else 1)
        known[k, joints.index(SPINE)] += held[i].get(HIPS, 0) / total * rise
    spread = np.clip(np.linalg.solve(plain, side @ known), 0, None)
    print('new weights on', len(loose), 'of', len(inside), 'points')

    new_held = {i: tidy({j: float(w) for j, w in zip(joints, line) if w > 1e-3}) for i, line in zip(loose, spread)}

    # normals of the new surface, on what moved and the ring around it
    shade = np.zeros((n, 3))
    for ob in meshes:
        place = parts[ob.name]['place']
        for face in ob.data.polygons:
            ring = place[list(face.vertices)]
            shade[ring] += np.cross(now[ring[1]] - now[ring[0]], now[ring[2]] - now[ring[0]])
    shade /= np.maximum(np.linalg.norm(shade, axis=1, keepdims=True), 1e-9)
    bent = {int(i) for i in np.flatnonzero(np.linalg.norm(now - spots, axis=1) > 1e-3)} - belt - heads
    ring = list(bent | {j for i in bent for j in near[i]})

    for ob in meshes:
        me = ob.data
        part = parts[ob.name]
        place = part['place']
        for i in np.flatnonzero(np.isin(place, loose)):
            set_weights(ob, int(i), new_held[place[i]])
        mats = ns['vertex_skins'](ob, skin)
        inv = np.linalg.inv(mats)
        idle = part['idle'] + (now - spots)[place]
        co = np.einsum('nij,nj->ni', inv[:, :3, :3], idle) + inv[:, :3, 3]
        me.vertices.foreach_set('co', co.ravel())
        me.update()
        normals = part['normals']
        fresh = np.isin(place[part['index']], ring)
        normals[fresh] = shade[place[part['index'][fresh]]]
        normals = np.einsum('nji,nj->ni', mats[part['index'], :3, :3], normals)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        me.normals_split_custom_set(normals.tolist())
        me.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(build / 'build.blend'))


main()
