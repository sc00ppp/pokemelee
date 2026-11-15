"""Record source/rest geometry once for the Combusken hand port; no edits."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np
from PIL import Image

R=Path(str(WORK / ''))
H=R/'hand/combusken-Falco'
for label,path in [('source',R/'mons/combusken/1-load/models/1-g3_wakasyamo.blend'),('base',H/'3-build/base.blend')]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    data={'bones':{},'objects':{}}
    print('\n',label)
    for ob in bpy.data.objects:
        if ob.type=='ARMATURE':
            for b in ob.data.bones:
                data['bones'][b.name]={'head':list(ob.matrix_world@b.head_local),'parent':b.parent.name if b.parent else None}
                print(b.name, np.round(data['bones'][b.name]['head'],4).tolist(),data['bones'][b.name]['parent'])
        if ob.type!='MESH': continue
        co=np.array([ob.matrix_world@v.co for v in ob.data.vertices])
        names={g.index:g.name for g in ob.vertex_groups}
        weights=[{names[g.group]:g.weight for g in v.groups if g.weight>1e-5} for v in ob.data.vertices]
        d={'co':co.tolist(),'weights':weights,'faces':[list(p.vertices) for p in ob.data.polygons],
           'uv':{l.name:[list(v.uv) for v in l.data] for l in ob.data.uv_layers},
           'materials':[m.name for m in ob.data.materials]}
        data['objects'][ob.name]=d
        dominant=sorted(set(max(w,key=w.get) for w in weights if w))
        print(ob.name,len(co),len(d['faces']),np.round(co.min(0),3).tolist(),np.round(co.max(0),3).tolist(),dominant,d['materials'])
    (H/f'{label}-geometry.json').write_text(json.dumps(data),encoding='utf-8')
    if label=='source':
        for im in bpy.data.images:
            if not im.has_data: continue
            w,h=im.size
            px=np.array(im.pixels[:]).reshape(h,w,4)
            Image.fromarray(np.uint8(np.clip(px[::-1]*255,0,255))).save(H/f'source-{im.name}.png')
        for m in bpy.data.materials:
            if not m.use_nodes:continue
            print('MAT',m.name,[(n.type,n.image.name if n.type=='TEX_IMAGE' and n.image else '',[(i.name,list(i.default_value) if hasattr(i.default_value,'__len__') else i.default_value) for i in n.inputs if n.type=='MAPPING' and i.name in ('Location','Rotation','Scale')]) for n in m.node_tree.nodes])
