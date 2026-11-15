"""One source/rest inventory for the Blastoise hand port; preserves inputs."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
from collections import Counter
import bpy
import numpy as np
from PIL import Image, ImageDraw

R=Path(str(WORK / ''))
H=R/'hand/blastoise-Bowser'
for label,path in [('source',R/'mons/blastoise/1-load/models/1-009_Blastoise.blend'),
                   ('base',H/'3-build/base.blend')]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    data={'bones':{},'objects':{}}
    print('\n',label)
    for ob in bpy.data.objects:
        if ob.type=='ARMATURE':
            for b in ob.data.bones:
                data['bones'][b.name]={'head':list(ob.matrix_world@b.head_local),'parent':b.parent.name if b.parent else None}
                print(b.name,np.round(data['bones'][b.name]['head'],4).tolist(),data['bones'][b.name]['parent'])
        if ob.type!='MESH':continue
        co=np.array([ob.matrix_world@v.co for v in ob.data.vertices])
        names={g.index:g.name for g in ob.vertex_groups}
        weights=[{names[g.group]:g.weight for g in v.groups if g.weight>1e-5} for v in ob.data.vertices]
        data['objects'][ob.name]={'co':co.tolist(),'weights':weights,'faces':[list(p.vertices) for p in ob.data.polygons],
            'uv':{l.name:[list(v.uv) for v in l.data] for l in ob.data.uv_layers},'materials':[m.name for m in ob.data.materials]}
        print(ob.name,len(co),len(ob.data.polygons),np.round(co.min(0),3).tolist(),np.round(co.max(0),3).tolist(),dict(Counter(max(w,key=w.get) for w in weights if w)))
    (H/f'{label}-geometry.json').write_text(json.dumps(data),encoding='utf-8')
    if label=='source':
        ims=[]
        for im in bpy.data.images:
            w,h=im.size
            if not w or not h:continue
            px=np.array(im.pixels[:]).reshape(h,w,4)
            img=Image.fromarray(np.uint8(np.clip(px[::-1]*255,0,255)))
            img.save(H/'review'/f'source-{im.name}.png')
            tile=Image.new('RGB',(220,240),'#777777');tile.paste(img.resize((192,192)),(0,25));ImageDraw.Draw(tile).text((0,0),im.name,fill='white');ims.append(tile)
        sheet=Image.new('RGB',(220*5,240*((len(ims)+4)//5)))
        for i,im in enumerate(ims):sheet.paste(im,(220*(i%5),240*(i//5)))
        sheet.save(H/'review/source-textures.png')
