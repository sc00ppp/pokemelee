"""Record source and copied-build geometry for the Charmeleon hand port."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np

R = Path(str(WORK / ''))
out = R / 'hand/charmeleon-Roy/look'
out.mkdir(parents=True, exist_ok=True)
for label, file in [('source', R / 'mons/charmeleon/1-load/models/1-005_Charmeleon.blend'),
                    ('base', R / 'hand/charmeleon-Roy/3-build/base.blend')]:
    bpy.ops.wm.open_mainfile(filepath=str(file))
    record = {'objects': {}, 'bones': {}}
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            for b in ob.data.bones:
                record['bones'][b.name] = {'head': list(ob.matrix_world @ b.head_local),
                                          'tail': list(ob.matrix_world @ b.tail_local),
                                          'parent': b.parent.name if b.parent else None}
        if ob.type != 'MESH':
            continue
        co = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        weights = [{ob.vertex_groups[g.group].name: g.weight for g in v.groups if g.weight > 0}
                   for v in ob.data.vertices]
        group_counts = {}
        for row in weights:
            for k, w in row.items():
                group_counts[k] = group_counts.get(k, 0) + w
        record['objects'][ob.name] = dict(co=co.tolist(), weights=weights,
            faces=[list(f.vertices) for f in ob.data.polygons],
            edges=[list(e.vertices) for e in ob.data.edges],
            uv={u.name:[list(d.uv) for d in u.data] for u in ob.data.uv_layers},
            loops=[l.vertex_index for l in ob.data.loops],
            mats=[m.name for m in ob.data.materials],
            bounds=[co.min(0).tolist(),co.max(0).tolist()])
        print(label, ob.name, len(co), np.round(co.min(0),3), np.round(co.max(0),3),
              {k:round(v,1) for k,v in group_counts.items()})
    for im in bpy.data.images:
        if im.size[0] and im.type != 'RENDER_RESULT':
            im.save_render(str(out / f'{label}-{im.name.replace("/", "_")}.png'))
    (out / f'{label}-geometry.json').write_text(json.dumps(record), encoding='utf-8')
    print(label, 'BONES', json.dumps(record['bones']))
