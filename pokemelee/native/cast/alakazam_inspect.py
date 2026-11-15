"""One geometry/texture inventory for the Alakazam hand port, without edits."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np
from PIL import Image

R = Path(str(WORK / ''))
H = R / 'hand/alakazam-Zelda'
for label, path in [('source', R / 'mons/alakazam/1-load/models/1-065_Alakazam.blend'),
                    ('base', H / '3-build/base.blend')]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    data = {'bones': {}, 'objects': {}}
    print('\n', label)
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            for b in ob.data.bones:
                data['bones'][b.name] = {'head': list(ob.matrix_world @ b.head_local),
                                        'matrix': [list(r) for r in ob.matrix_world @ b.matrix_local],
                                        'parent': b.parent.name if b.parent else None}
                print(b.name, np.round(data['bones'][b.name]['head'], 4).tolist(), data['bones'][b.name]['parent'])
        if ob.type != 'MESH' or not ob.data.vertices:
            continue
        co = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        names = {g.index: g.name for g in ob.vertex_groups}
        weights = [{names[g.group]: g.weight for g in v.groups if g.weight > 1e-5} for v in ob.data.vertices]
        d = {'co': co.tolist(), 'weights': weights, 'faces': [list(p.vertices) for p in ob.data.polygons],
             'uv': {l.name: [list(v.uv) for v in l.data] for l in ob.data.uv_layers},
             'materials': [m.name for m in ob.data.materials]}
        data['objects'][ob.name] = d
        dominant = sorted(set(max(w, key=w.get) for w in weights if w))
        print(ob.name, len(co), len(d['faces']), np.round(co.min(0), 3).tolist(), np.round(co.max(0), 3).tolist(), dominant)
    (H / f'{label}-geometry.json').write_text(json.dumps(data), encoding='utf-8')
    if label == 'source':
        for im in bpy.data.images:
            w, h = im.size
            if not w or not h:
                continue
            px = np.array(im.pixels[:]).reshape(h, w, 4)
            Image.fromarray(np.uint8(np.clip(px[::-1] * 255, 0, 255))).save(H / 'look' / f'source-{im.name}.png')
        for m in bpy.data.materials:
            if m.use_nodes:
                print('MAT', m.name, [(n.type, n.image.name if n.type == 'TEX_IMAGE' and n.image else '') for n in m.node_tree.nodes])
