"""Read the source, raw port and target once; preserve all mesh data."""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(str(WORK / 'hand/mewtwo-Mewtwo'))
def inspect():
    out={'bones':{},'meshes':{}}
    for ob in bpy.data.objects:
        if ob.type=='ARMATURE':
            for b in ob.data.bones:
                out['bones'][b.name]={'head':list(ob.matrix_world@b.head_local),'tail':list(ob.matrix_world@b.tail_local),'parent':b.parent.name if b.parent else None}
        if ob.type!='MESH': continue
        names={g.index:g.name for g in ob.vertex_groups}
        pts=[list(ob.matrix_world@v.co) for v in ob.data.vertices]
        weights=[{names[g.group]:g.weight for g in v.groups if g.weight>0} for v in ob.data.vertices]
        out['meshes'][ob.name]={'points':pts,'vw':weights,'faces':[list(p.vertices) for p in ob.data.polygons],
            'uv':[[list(d.uv) for d in uv.data] for uv in ob.data.uv_layers],
            'mats':[m.name for m in ob.data.materials]}
        p=np.array(pts); usage={}
        for w in weights:
            for k,v in w.items():usage[k]=usage.get(k,0)+v
        print(ob.name,len(pts),len(ob.data.polygons),'bounds',p.min(0).round(3),p.max(0).round(3),'groups',sorted(usage.items(),key=lambda x:-x[1])[:12],flush=True)
    print('BONES',json.dumps(out['bones']),flush=True)
    return out

data={}
for label,path in [('source',str(WORK / "mons" / 'mewtwo/1-load/models/1-150_Mewtwo.blend')),('raw',str(ROOT/'3-build/base.blend'))]:
    bpy.ops.wm.open_mainfile(filepath=path)
    print(label,flush=True);data[label]=inspect()
    if label=='source':
        tiles=[]
        for im in bpy.data.images:
            w,h=im.size
            if not w or not h:continue
            arr=np.array(im.pixels[:]).reshape(h,w,4)[::-1]
            pic=Image.fromarray(np.clip(arr*255,0,255).astype('uint8'))
            pic.save(ROOT/f'{im.name}.png')
            tile=Image.new('RGB',(180,360),(60,60,60));p=pic.copy();p.thumbnail((160,325));tile.paste(p,(10,30));ImageDraw.Draw(tile).text((5,5),f'{im.name} {w}x{h}');tiles.append(tile)
        sheet=Image.new('RGB',(180*7,360*((len(tiles)+6)//7)))
        for i,t in enumerate(tiles):sheet.paste(t,((i%7)*180,(i//7)*360))
        sheet.save(ROOT/'source-textures.png')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(TARGETS / 'Mewtwo.glb'))
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'vanilla.blend'))
print('vanilla',flush=True);data['vanilla']=inspect()
(ROOT/'inspection.json').write_text(json.dumps(data),encoding='utf-8')
