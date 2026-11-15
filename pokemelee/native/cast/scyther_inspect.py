"""Inventory source and copied pre-prep mesh geometry for the Scyther hand port."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np

R = Path(str(WORK / ''))
out = {}
for label, path in [('source', R/'mons/scyther/1-load/models/1-123_Scyther.blend'),
                    ('base', R/'hand/scyther-Link/3-build/base.blend')]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    data = {'meshes': {}, 'bones': {}}
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            for b in ob.data.bones:
                data['bones'][b.name] = {'head': list(ob.matrix_world @ b.head_local),
                    'tail': list(ob.matrix_world @ b.tail_local), 'parent': b.parent.name if b.parent else None}
        if ob.type != 'MESH':
            continue
        pts = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        names = {g.index:g.name for g in ob.vertex_groups}
        weights = [{names[g.group]:g.weight for g in v.groups if g.weight > 0} for v in ob.data.vertices]
        totals = {}
        for row in weights:
            for k,v in row.items(): totals[k] = totals.get(k,0)+v
        data['meshes'][ob.name] = {'points':pts.tolist(), 'weights':weights,
            'faces':[list(p.vertices) for p in ob.data.polygons],
            'uv': {u.name:[list(d.uv) for d in u.data] for u in ob.data.uv_layers},
            'materials':[m.name for m in ob.data.materials]}
        print(label, ob.name, len(pts), 'lo', pts.min(0).round(3), 'hi', pts.max(0).round(3),
              'weights', {k:round(v,1) for k,v in totals.items()}, 'mats', data['meshes'][ob.name]['materials'])
    out[label] = data
(R/'hand/scyther-Link/review/inventory.json').write_text(json.dumps(out),encoding='utf-8')
for label in out:
    print(label, 'BONES')
    for name, b in out[label]['bones'].items():
        print(name, np.round(b['head'],3), b['parent'])
