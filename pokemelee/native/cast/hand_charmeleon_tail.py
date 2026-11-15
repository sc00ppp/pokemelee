"""Lower the existing Charmeleon-Roy tail about its root; keep its skin weights.

The previous hand port is the input, saved separately before prep can overwrite it.
Only the tail and its flame move. The attachment fades to zero at the body seam.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import shutil

import bpy
import numpy as np

import hand_charmeleon as original

B = original.B
BASE = B / 'tail-base.blend'
ANGLE = -55.0


def main():
    if not BASE.exists():
        shutil.copy2(B / 'edited.blend', BASE)
    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    angle = np.deg2rad(ANGLE)
    turn = np.array([[1, 0, 0], [0, np.cos(angle), -np.sin(angle)],
                     [0, np.sin(angle), np.cos(angle)]])
    root = original.tail_at
    selected = {}
    for name, source in original.S['objects'].items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        for i, (point, weights) in enumerate(zip(source['co'], source['weights'])):
            if int(max(weights, key=weights.get)[5:]) in (15, 16, 17, 18, 19):
                amount = original.smooth(.18, .31, point[1])
                if amount:
                    selected[tuple(np.round(ob.data.vertices[i].co, 4))] = amount

    changed = {}
    before = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        before[ob.name] = [tuple(v.co) for v in ob.data.vertices]
        ids = []
        for v in ob.data.vertices:
            amount = 1.0 if ob.name.startswith('charmeleon_flame_') else selected.get(tuple(np.round(v.co, 4)), 0.0)
            if amount:
                p = np.array(v.co)
                v.co = p + amount * (root + turn @ (p - root) - p)
                ids.append(v.index)
        if ids:
            changed[ob.name] = ids
            ob.data.update()

    # Rebuild the changed surfaces' shared corner normals using the same rule as
    # the previous hand port. Untouched objects keep their existing normals.
    normals = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        for poly in ob.data.polygons:
            pts = np.array([ob.data.vertices[v].co for v in poly.vertices])
            area = np.cross(pts[1] - pts[0], pts[2] - pts[0])
            for p in pts:
                key = tuple(np.round(p, 4))
                normals[key] = normals.get(key, np.zeros(3)) + area
    for name in changed:
        me = bpy.data.objects[name].data
        custom = []
        for loop in me.loops:
            n = normals[tuple(np.round(me.vertices[loop.vertex_index].co, 4))]
            length = np.linalg.norm(n)
            custom.append((n / length if length > 1e-8 else np.array([0., 0., 1.])).tolist())
        me.normals_split_custom_set(custom)
        me.update()

    for name, coordinates in before.items():
        changed_ids = set(changed.get(name, []))
        for i, v in enumerate(bpy.data.objects[name].data.vertices):
            if i not in changed_ids:
                assert tuple(v.co) == coordinates[i], (name, i)
    report = {'input': str(BASE), 'root': root.tolist(), 'rotation_x_degrees': ANGLE,
              'changed_vertices': {name: len(ids) for name, ids in changed.items()},
              'other_vertex_positions_unchanged': True, 'weights_unchanged': True,
              'materials_uvs_skeleton_unchanged': True}
    (original.H / 'tail-edit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(B / 'build.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(B / 'edited.blend'))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
