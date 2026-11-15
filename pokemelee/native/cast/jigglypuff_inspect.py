"""Record Jigglypuff source, raw port, vanilla skin, and original game textures."""

from cast_paths import WORK, TARGETS
import json
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image, ImageDraw

R = Path(str(WORK / ''))
OUT = R / 'hand/jigglypuff-Jigglypuff/look'
sys.path.insert(0, str(R / 'tools'))
from hsd_scene import Scene, pkx
from rigswap.plugins.melee.export.eyes import decode, colours_of, _unblocks

s = Scene(pkx('purin'))
js = s.joints(s.u32(s.u32(s.u32(s.roots['scene_data']))))
textures = {}
for j in js:
    for dob in j['dobjs']:
        for t in dob['mobj']['tobjs']:
            if t['image'] in textures:
                continue
            w, h = t['size']
            if t['fmt'] == 4:
                a = _unblocks(colours_of(np.frombuffer(s.data[t['image']:t['image']+w*h*2], '>u2'), 1), w,h,4,4)
            else:
                lut=t['tlut']; at=s.u32(lut); fmt=s.u32(lut+4)
                count=struct.unpack_from('>H', s.data, lut+12)[0]
                a=decode(s.data[t['image']:],w,h,t['fmt'],s.data[at:at+count*2],fmt)
            im=Image.fromarray(a)
            im.save(OUT / f"game-{t['image']:x}.png")
            textures[t['image']]=im
sheet=Image.new('RGB',(700,1100),(70,70,70)); draw=ImageDraw.Draw(sheet)
x=10
for at,im in textures.items():
    scale=4
    sheet.paste(im.resize((im.width*scale, im.height*scale)),(x,35))
    draw.text((x,10),hex(at),fill='white'); x+=max(80,im.width*scale+20)
sheet.save(OUT/'game-textures.png')

def inspect(label):
    report={'meshes':{},'bones':{}}
    for ob in bpy.data.objects:
        if ob.type=='ARMATURE':
            report['bones']={b.name:dict(head=list(ob.matrix_world@b.head_local),tail=list(ob.matrix_world@b.tail_local),parent=b.parent.name if b.parent else None) for b in ob.data.bones}
        if ob.type!='MESH': continue
        co=np.array([ob.matrix_world@v.co for v in ob.data.vertices]); groups={g.index:g.name for g in ob.vertex_groups}
        mats=[]
        for mat in ob.data.materials:
            nodes=[]
            if mat and mat.use_nodes:
                for n in mat.node_tree.nodes:
                    if n.type=='TEX_IMAGE': nodes.append(dict(type=n.type,image=n.image.name,size=list(n.image.size)))
                    if n.type=='MAPPING': nodes.append(dict(type=n.type,inputs={v.name:list(v.default_value) for v in n.inputs if hasattr(v.default_value,'__len__')}))
            mats.append(dict(name=mat.name,nodes=nodes))
        report['meshes'][ob.name]=dict(verts=len(co),faces=len(ob.data.polygons),lo=co.min(0).tolist(),hi=co.max(0).tolist(),materials=mats,uv={uv.name:dict(lo=np.array([v.uv for v in uv.data]).min(0).tolist(),hi=np.array([v.uv for v in uv.data]).max(0).tolist()) for uv in ob.data.uv_layers},weights={name:sum(w.weight for v in ob.data.vertices for w in v.groups if w.group==i) for i,name in groups.items() if any(w.group==i and w.weight>0 for v in ob.data.vertices for w in v.groups)})
    (OUT/f'{label}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(label,[(n,m['verts'],m['lo'],m['hi'],m['weights']) for n,m in report['meshes'].items()])

bpy.ops.wm.open_mainfile(filepath=str(WORK / "mons" / 'jigglypuff/1-load/models/1-039_Jigglypuff.blend'))
inspect('source')
bpy.ops.wm.open_mainfile(filepath=str(R/'hand/jigglypuff-Jigglypuff/3-build/base.blend'))
inspect('raw')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(TARGETS / 'Jigglypuff.glb'))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'vanilla.blend'))
inspect('vanilla')
