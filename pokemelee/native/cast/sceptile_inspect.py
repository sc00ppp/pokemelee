"""Inspect Sceptile's source and hand-port geometry without changing either."""

from cast_paths import WORK, TARGETS
import json
import sys
from pathlib import Path
import bpy
import numpy as np

src, out = sys.argv[1:3]
bpy.ops.wm.open_mainfile(filepath=str(Path(src).resolve()))
data = {'bones': {}, 'meshes': {}}
for ob in bpy.data.objects:
    if ob.type == 'ARMATURE':
        for b in ob.data.bones:
            data['bones'][b.name] = {'parent': b.parent.name if b.parent else None,
                'head': list(ob.matrix_world @ b.head_local), 'tail': list(ob.matrix_world @ b.tail_local)}
    elif ob.type == 'MESH':
        pts = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        groups = {g.index:g.name for g in ob.vertex_groups}
        weights = [{groups[g.group]:g.weight for g in v.groups if g.weight > .0001} for v in ob.data.vertices]
        totals = {}
        for w in weights:
            for g,v in w.items(): totals[g] = totals.get(g, 0) + v
        data['meshes'][ob.name] = {'bounds':[pts.min(0).tolist(),pts.max(0).tolist()],
            'points':pts.tolist(),'faces':[list(p.vertices) for p in ob.data.polygons],
            'weights':weights,'totals':totals,'materials':[m.name for m in ob.data.materials],
            'uvs':[uv.name for uv in ob.data.uv_layers]}
Path(out).write_text(json.dumps(data, indent=1), encoding='utf-8')
for name, m in data['meshes'].items():
    print(name, len(m['points']), np.round(m['bounds'],2).tolist(), sorted(m['totals'].items(),key=lambda x:-x[1])[:8])
for name,b in data['bones'].items():
    print(name, b['parent'], np.round(b['head'],3))
