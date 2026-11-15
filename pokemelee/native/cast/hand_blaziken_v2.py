"""Blaziken v2: the source's bell-shaped legs are its feet.

The source hem, underside and three small claws keep their topology, UVs and
width relative to the retained head. Only their pose and joint ownership change.
No invented instep, normal repair, subdivision or vanilla geometry is used.
Run edit, round_out.py, inspect the rounded build, then hand_finish.py.
"""

from cast_paths import WORK, TARGETS
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

R = Path(str(WORK / ''))
OLD = R / 'hand/blaziken-CaptainFalcon'
W = OLD / 'v2'
B = W / '3-build'
T = Path(str(TARGETS / ''))


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def unit(v):
    return v / np.linalg.norm(v)


def set_weight(ob, i, weights):
    for g in ob.vertex_groups:
        g.remove([i])
    total = sum(weights.values())
    for name, value in weights.items():
        if value > 1e-7:
            group = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
            group.add([i], float(value / total), 'REPLACE')


def edit():
    import bpy
    from mathutils import Vector
    import shutil

    B.mkdir(parents=True, exist_ok=True)
    # Copy only the needed inputs, never old export products or prepped geometry.
    for name in ('base.blend', 'eyes.json', 'target.json'):
        shutil.copy2(OLD / '3-build' / name, B / name)
    shutil.copytree(OLD / '3-build/eyes', B / 'eyes', dirs_exist_ok=True)
    src = read(OLD / 'reference/source-geometry.json')
    base = read(OLD / 'reference/base-geometry.json')
    feet = read(OLD / 'reference/vanilla-feet.json')

    def point(data, name):
        return np.array(data['bones'][name]['head'], float)

    def rotation(a, b):
        return np.array(Vector(unit(a)).rotation_difference(Vector(unit(b))).to_matrix())

    head_source = np.array(src['meshes']['bursyamo_mesh_26']['co'])
    head_base = np.array(base['meshes']['bursyamo_mesh_26']['co'])
    scale = float(np.ptp(head_base[:, 0]) / np.ptp(head_source[:, 0]))
    bpy.ops.wm.open_mainfile(filepath=str(B / 'base.blend'))
    plans = [dict(side='R', hip='Bone_017', knee='Bone_018', ankle='Bone_019', hem='Bone_020',
                  extra='Bone_027', clawbone='Bone_023', thigh=13, shin=14, foot=16, toe=17, claw='00'),
             dict(side='L', hip='Bone_030', knee='Bone_031', ankle='Bone_032', hem='Bone_033',
                  extra='Bone_040_Additional3', clawbone='Bone_036', thigh=7, shin=8, foot=10, toe=11, claw='03')]
    evidence = {'head_scale': scale, 'legs': {}, 'finish_order': ['edit', 'round_out', 'hand_finish']}
    for plan in plans:
        side = plan['side']
        sh, sk, sa = [point(src, plan[k]) for k in ('hip', 'knee', 'ankle')]
        th, tk, ta = [point(base, 'JOBJ_' + str(plan[k])) for k in ('thigh', 'shin', 'foot')]
        normal = np.array(feet[side][0])[[0, 2, 1]] * [1, -1, 1]
        forward = np.array(feet[side][4])[[0, 2, 1]] * [1, -1, 1]
        across = unit(np.cross(normal, forward))
        # A source foot is a radial flare. Keep its authored orientation around
        # the leg, and place its plane in the fighter's contact plane.
        basis = np.column_stack((across, -forward, normal))
        claw_co = np.array(src['meshes']['bursyamo_mesh_' + plan['claw']]['co'])
        source_floor = float(claw_co[:, 2].min())
        floor = ta + normal * feet[side][2] + forward * .65

        def foot(p):
            d = p - sa
            d[2] = p[2] - source_floor
            # All vertices of the bottom ring share one support level. The
            # original alpha-cut feather edge keeps its torn silhouette.
            if p[2] < .015:
                d[2] = -.014 - source_floor
            return floor + basis @ (d * scale)

        ankle_center = foot(sa.copy())
        thigh_turn = rotation(sk - sh, tk - th)
        shin_turn = rotation(sa - sk, ankle_center - tk)

        def thigh(p):
            axis = unit(sk - sh)
            along = (p - sh) @ axis
            return th + unit(tk - th) * along * np.linalg.norm(tk - th) / np.linalg.norm(sk - sh) + thigh_turn @ ((p - sh) - along * axis) * 9.3

        def shin(p):
            axis = unit(sa - sk)
            along = (p - sk) @ axis
            return tk + unit(ankle_center - tk) * along * np.linalg.norm(ankle_center - tk) / np.linalg.norm(sa - sk) + shin_turn @ ((p - sk) - along * axis) * scale

        def foot_weights(q):
            toe_at = point(base, 'JOBJ_' + str(plan['toe']))
            toe = float(np.clip((q - toe_at) @ forward / 1.0 + .5, 0, 1))
            return {'JOBJ_' + str(plan['foot']): 1 - toe, 'JOBJ_' + str(plan['toe']): toe}

        keys = [plan[k] for k in ('hip', 'knee', 'ankle', 'hem', 'extra', 'clawbone')]
        count = 0
        for name, data in src['meshes'].items():
            ob = bpy.data.objects.get(name)
            if ob is None or len(ob.data.vertices) != len(data['co']):
                continue
            for i, (xyz, weights) in enumerate(zip(data['co'], data['weights'])):
                share = sum(weights.get(k, 0) for k in keys)
                if not share:
                    continue
                p = np.array(xyz, float)
                old = np.array(base['meshes'][name]['co'][i])
                new = old * (1 - share)
                held = {k: v * (1 - share) for k, v in base['meshes'][name]['weights'][i].items()}
                for key in keys:
                    amount = weights.get(key, 0)
                    if not amount:
                        continue
                    if key in (plan['ankle'], plan['hem'], plan['clawbone']):
                        q = foot(p.copy())
                        if key == plan['clawbone']:
                            # Retain each seven-vertex source claw's shape, with
                            # its contact tip fixed. Smaller hidden roots cannot
                            # poke through a flare when the ankle bends sideways.
                            claw = claw_co[(i // 7) * 7:(i // 7 + 1) * 7]
                            tip = claw[np.argmin(claw[:, 2])]
                            claw_point = tip + (p - tip) * .70
                            d = claw_point - sa
                            d[2] = claw_point[2] - source_floor
                            q = floor + basis @ (d * scale)
                        ww = foot_weights(q)
                        if key == plan['ankle']:
                            # This is the upper feather ring, above the joint;
                            # making it rigid to the foot folds the long calf
                            # through itself in Falcon's neutral-air ankle bend.
                            # The lower hem and claws remain wholly foot/toe skin.
                            shin_share = float(np.clip((p[2] - .06) / .04, 0, 1)) * .45
                            ww = {joint: value * (1 - shin_share) for joint, value in ww.items()}
                            ww['JOBJ_' + str(plan['shin'])] = shin_share
                    elif key == plan['hip']:
                        blend = np.clip(np.linalg.norm(p - sh) / .25, 0, 1)
                        q = old * (1 - blend) + thigh(p) * blend
                        ww = {'JOBJ_' + str(plan['thigh']): 1}
                    else:
                        q = shin(p)
                        ww = {'JOBJ_' + str(plan['shin']): 1}
                    new += amount * q
                    for joint, value in ww.items():
                        held[joint] = held.get(joint, 0) + amount * value
                ob.data.vertices[i].co = new
                set_weight(ob, i, held)
                count += 1
            ob.data.update()
        hem = np.array([foot(np.array(p)) for data in src['meshes'].values()
                        for p, w in zip(data['co'], data['weights']) if w.get(plan['hem'], 0) > .99])
        evidence['legs'][side] = {'vertices': count, 'hem_height_over_sole': (hem @ normal - floor @ normal).tolist(),
                                  'source_claw_min_z': source_floor, 'foot': plan['foot'], 'toe': plan['toe']}
        print(side, 'source leg vertices', count, 'hem plane', np.round(hem @ normal, 4))

    # Preserve the first port's exact accepted plume edit. The rest of the head,
    # beak and eyes are already unchanged in base.blend.
    ob = bpy.data.objects['bursyamo_mesh_21']
    data = src['meshes'][ob.name]
    for bone, sign in [('Bone_088', 1), ('Bone_091', -1)]:
        ids = [i for i, w in enumerate(data['weights']) if w.get(bone, 0) > .99]
        root = point(src, bone)
        delta = np.array([data['co'][i] for i in ids]) - root
        axis = unit(delta.mean(0))
        u = delta @ axis
        root_target = point(base, 'JOBJ_39') + np.array([sign * .91, .68, 1.18])
        direction = np.array([sign * 1.8, 9.5, -2.1])
        turn = rotation(axis, direction)
        for i, p, arc in zip(ids, delta, u):
            ob.data.vertices[i].co = root_target + direction * (arc / u.max()) + turn @ (p - axis * arc) * 12.0
            set_weight(ob, i, {'JOBJ_39': 1.0})
    ob.data.update()
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and 'rigswap_loose' in ob.data.attributes:
            ob.data.attributes.remove(ob.data.attributes['rigswap_loose'])
    (B / 'loose.json').write_text(json.dumps({'attribute': 'rigswap_loose', 'chains': [],
        'notes': ['Accepted v1 head-bound plumes retained.']}, indent=2), encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(B / 'edited.blend'))
    (W / 'geometry-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print('Saved', B / 'edited.blend', 'head/flare scale', scale)


def audit():
    """Read the actual rounded skin in the target's saved animation frames."""
    import bpy
    from mathutils import Matrix, Quaternion, Vector
    from mathutils.bvhtree import BVHTree

    blob = (T / 'CaptainFalcon.glb').read_bytes()
    nodes = json.loads(blob[20:20 + int.from_bytes(blob[12:16], 'little')])['nodes']
    rest = {}

    def walk(i, parent):
        node = nodes[i]
        if 'matrix' in node:
            local = np.array(node['matrix']).reshape(4, 4).T
        else:
            x, y, z, w = node.get('rotation', [0, 0, 0, 1])
            local = np.array(Matrix.LocRotScale(Vector(node.get('translation', [0, 0, 0])),
                Quaternion((w, x, y, z)), Vector(node.get('scale', [1, 1, 1]))))
        world = parent @ local
        if node.get('name', '').startswith('JOBJ_'):
            rest[int(node['name'][5:])] = world
        for child in node.get('children', []):
            walk(child, world)

    children = {c for node in nodes for c in node.get('children', [])}
    for i in range(len(nodes)):
        if i not in children:
            walk(i, np.eye(4))
    C = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
    bpy.ops.wm.open_mainfile(filepath=str(B / 'build.blend'))
    tables = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        points = np.array([list(ob.matrix_world @ v.co) + [1] for v in ob.data.vertices])
        names = {g.index: int(g.name[5:]) for g in ob.vertex_groups if g.name.startswith('JOBJ_')}
        held = [{names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0}
                for v in ob.data.vertices]
        tables[ob.name] = points, held, [list(p.vertices) for p in ob.data.polygons]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(T / 'CaptainFalcon.glb'))
    vanilla = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        names = {g.index: int(g.name[5:]) for g in ob.vertex_groups if g.name.startswith('JOBJ_')}
        for v in ob.data.vertices:
            weights = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0}
            for side, chain in [('L', {10, 11}), ('R', {16, 17})]:
                if sum(weights.get(j, 0) for j in chain) > .99:
                    vanilla.append((side, np.array(list(ob.matrix_world @ v.co) + [1]), weights))
    result = {}

    def crossings(points, faces, hp, hf):
        # Segment/triangle intersection identifies actual penetration, unlike
        # two nearby vertices or a projected overlap in a side view.
        count = 0
        for face in faces:
            for a, b in zip(face, face[1:] + face[:1]):
                origin, direction = points[a], points[b] - points[a]
                for tri in hf:
                    p, q, r = np.array(hp)[tri[:3]]
                    edge1, edge2 = q - p, r - p
                    h = np.cross(direction, edge2)
                    det = edge1 @ h
                    if abs(det) < 1e-9:
                        continue
                    s = origin - p
                    u = (s @ h) / det
                    v = (direction @ np.cross(s, edge1)) / det
                    t = (edge2 @ np.cross(s, edge1)) / det
                    if 1e-5 < t < 1 - 1e-5 and u > 1e-5 and v > 1e-5 and u + v < 1 - 1e-5:
                        count += 1
        return count

    for pose in ['Wait1-1', 'Run-6', 'Dash-4', 'AttackAirLw-10', 'AttackAirN-4']:
        frame = read(T / 'frames/CaptainFalcon' / (pose + '.json'))
        moves = {b['index']: C @ np.array(b['matrix']).reshape(4, 4).T @ np.linalg.inv(rest[b['index']]) @ C.T
                 for b in frame['bones'] if b['index'] in rest}
        posed = {}
        soles = {'L': [], 'R': []}
        hems = {'L': [], 'R': []}
        vanilla_soles = {'L': [], 'R': []}
        for side, p, weights in vanilla:
            q = sum((w * (moves.get(j, np.eye(4)) @ p) for j, w in weights.items()), np.zeros(4)) / sum(weights.values())
            vanilla_soles[side].append(q[2])
        for name, (points, held, faces) in tables.items():
            out = np.array([sum((w * (moves.get(j, np.eye(4)) @ p) for j, w in weights.items()), np.zeros(4)) / sum(weights.values())
                            for p, weights in zip(points, held)])[:, :3]
            posed[name] = out
            if name in ['bursyamo_mesh_00', 'bursyamo_mesh_03', 'bursyamo_mesh_19', 'bursyamo_mesh_20']:
                for p, weights in zip(out, held):
                    for side, chain in [('L', {10, 11}), ('R', {16, 17})]:
                        if sum(weights.get(j, 0) for j in chain) > .99:
                            soles[side].append(p[2])
                            if name in ['bursyamo_mesh_19', 'bursyamo_mesh_20']:
                                hems[side].append(p[2])
        head = ['bursyamo_mesh_23', 'bursyamo_mesh_24', 'bursyamo_mesh_26', 'bursyamo_mesh_27']
        hp, hf = [], []
        for name in head:
            offset = len(hp)
            hp.extend(posed[name].tolist())
            hf.extend([[offset + i for i in f] for f in tables[name][2]])
        tree = BVHTree.FromPolygons(hp, hf)
        spikes = {}
        intersections = {}
        for name in ['bursyamo_mesh_02', 'bursyamo_mesh_05']:
            spikes[name] = round(min(tree.find_nearest(Vector(p))[3] for p in posed[name]), 5)
            intersections[name] = crossings(posed[name], tables[name][2], hp, hf)
        result[pose] = {'lowest_hem_or_claw': {s: round(min(v), 5) for s, v in soles.items()},
                        'lowest_hem': {s: round(min(v), 5) for s, v in hems.items()},
                        'vanilla_sole': {s: round(min(v), 5) for s, v in vanilla_soles.items()},
                        'spur_to_face_nearest_vertex': spikes, 'spur_face_intersections': intersections}
        if pose == 'AttackAirN-4':
            all_points = np.concatenate(list(posed.values()))
            lo, hi = all_points.min(0), all_points.max(0)
            mid = (lo + hi) / 2
            size = max(hi[2] - lo[2], np.linalg.norm(hi[:2] - lo[:2])) * 1.08
            hit = []
            for name, points in posed.items():
                xy = np.column_stack((.5 - (points[:, 1] - mid[1]) / size,
                                      .5 - (points[:, 2] - mid[2]) / size)) * 460
                for k, face in enumerate(tables[name][2]):
                    a, b, c = xy[face[:3]]
                    try:
                        u, v = np.linalg.solve(np.column_stack((b-a, c-a)), np.array([181, 339]) - a)
                    except np.linalg.LinAlgError:
                        continue
                    if u >= 0 and v >= 0 and u+v <= 1:
                        depth = points[face[0], 0]*(1-u-v) + points[face[1], 0]*u + points[face[2], 0]*v
                        hit.append((float(depth), name, k, face))
            result[pose]['visible_patch_faces'] = sorted(hit)[:8]
    (W / 'pose-audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))



if __name__ == "__main__":
    edit()
