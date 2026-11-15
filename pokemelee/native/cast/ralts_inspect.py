"""Record Ralts source and hand-copy geometry, materials and joints."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np

R = Path(str(WORK / ''))
out = {}
for label, path in [('source', R/'mons/ralts/1-load/models/1-g3_ralts.blend'),
                    ('base', R/'hand/ralts-Ness/3-build/base.blend')]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    rec = {'meshes': {}, 'bones': {}, 'materials': {}}
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            p = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
            groups = {g.index:g.name for g in ob.vertex_groups}
            weights = [{groups[g.group]:round(g.weight,5) for g in v.groups if g.weight>0} for v in ob.data.vertices]
            rec['meshes'][ob.name] = dict(vertices=len(p), bounds=[p.min(0).tolist(),p.max(0).tolist()],
                materials=[m.name for m in ob.data.materials], groups=sorted({g for w in weights for g in w}),
                points=p.round(6).tolist(),weights=weights,faces=[list(p.vertices) for p in ob.data.polygons])
        elif ob.type == 'ARMATURE':
            for b in ob.data.bones:
                rec['bones'][b.name] = dict(parent=b.parent.name if b.parent else None,
                    head=list(ob.matrix_world @ b.head_local),tail=list(ob.matrix_world @ b.tail_local))
    for m in bpy.data.materials:
        rec['materials'][m.name] = [(n.type,n.name,list(n.image.size) if n.type=='TEX_IMAGE' and n.image else None) for n in m.node_tree.nodes] if m.use_nodes else []
    out[label] = rec
(R/'hand/ralts-Ness/inspect.json').write_text(json.dumps(out,indent=1),encoding='utf-8')
for label, rec in out.items():
    print(label)
    for name,m in rec['meshes'].items():
        print(name,m['vertices'],np.round(m['bounds'],3).tolist(),m['groups'],m['materials'])
    print('BONES')
    for name,b in rec['bones'].items():
        print(name,b['parent'],np.round(b['head'],4).tolist())
