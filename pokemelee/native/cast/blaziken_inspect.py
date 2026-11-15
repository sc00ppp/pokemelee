"""Read source and fitted geometry once; preserve coordinate/weight evidence."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np

R = Path(str(WORK / ''))
OUT = R / 'hand/blaziken-CaptainFalcon/reference'
for label, path in [('source', R/'mons/blaziken/1-load/models/1-g3_bursyamo.blend'),
                    ('base', OUT.parent/'3-build/base.blend')]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    data = {'meshes': {}, 'bones': {}}
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            for b in ob.data.bones:
                data['bones'][b.name] = {'head': list(ob.matrix_world @ b.head_local),
                                          'tail': list(ob.matrix_world @ b.tail_local),
                                          'parent': b.parent.name if b.parent else None}
        if ob.type != 'MESH':
            continue
        co = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        names = {g.index:g.name for g in ob.vertex_groups}
        weights = [{names[g.group]:round(g.weight,5) for g in v.groups if g.weight>1e-5} for v in ob.data.vertices]
        totals = {}
        for w in weights:
            for k, v in w.items(): totals[k] = totals.get(k,0)+v
        row = {'co':co.tolist(),'weights':weights,'faces':[list(p.vertices) for p in ob.data.polygons],
               'materials':[m.name for m in ob.data.materials], 'attributes':list(ob.data.attributes.keys())}
        data['meshes'][ob.name] = row
        print(label, ob.name, len(co), len(row['faces']),
              'bounds',co.min(0).round(2).tolist(),co.max(0).round(2).tolist(),
              'weights',sorted([(k,round(v,1)) for k,v in totals.items()],key=lambda t:-t[1])[:6])
    (OUT/f'{label}-geometry.json').write_text(json.dumps(data,indent=1),encoding='utf-8')
    print(label,'BONES',json.dumps(data['bones']))
