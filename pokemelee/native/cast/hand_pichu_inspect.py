
from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np
from PIL import Image, ImageDraw

OUT = Path(str(WORK / 'hand/pichu-Pichu'))
FILES = {
    'source': str(WORK / "mons" / 'pichu/1-load/models/1-172_Pichu.blend'),
    'raw': str(OUT / '3-build/base.blend'),
    'vanilla': str(TARGETS / 'Pichu.glb'),
}
result = {}
for label, path in FILES.items():
    if path.endswith('.glb'):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=path)
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'vanilla.blend'))
    else:
        bpy.ops.wm.open_mainfile(filepath=path)
    data = {'meshes': {}, 'bones': {}}
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            data['bones'] = {b.name: {'parent': b.parent.name if b.parent else None,
                'head': list(ob.matrix_world @ b.head_local), 'tail': list(ob.matrix_world @ b.tail_local)} for b in ob.data.bones}
        if ob.type != 'MESH':
            continue
        pts = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        names = {g.index: g.name for g in ob.vertex_groups}
        weights = [{names[g.group]: g.weight for g in v.groups if g.weight > 0} for v in ob.data.vertices]
        total = {}
        for w in weights:
            for n, a in w.items(): total[n] = total.get(n, 0) + a
        mats = []
        for mat in ob.data.materials:
            nodes = mat.node_tree.nodes if mat.use_nodes else []
            mats.append({'name': mat.name, 'images': [n.image.name for n in nodes if n.type == 'TEX_IMAGE'],
                'mapping': [{i.name: list(i.default_value) if hasattr(i.default_value, '__len__') else i.default_value for i in n.inputs} for n in nodes if n.type == 'MAPPING']})
        data['meshes'][ob.name] = {'verts': len(pts), 'faces': len(ob.data.polygons), 'min': pts.min(0).tolist(), 'max': pts.max(0).tolist(),
            'weights': sorted(total.items(), key=lambda a: -a[1]), 'materials': mats, 'points': pts.tolist(), 'vw': weights}
    result[label] = data
    if label == 'source':
        tiles=[]
        for im in bpy.data.images:
            w,h=im.size
            if not w or not h: continue
            arr=(np.array(im.pixels[:]).reshape(h,w,4)[::-1]*255).round().clip(0,255).astype('uint8')
            pic=Image.fromarray(arr)
            pic.save(OUT / f'{im.name}.png')
            tile=Image.new('RGB',(540,390),(180,180,180))
            ImageDraw.Draw(tile).text((4,2),f'{im.name} {w}x{h}',fill='black')
            pic.thumbnail((528,360))
            tile.paste(pic,(4,25),pic)
            tiles.append(tile)
        sheet=Image.new('RGB',(540*3,390*((len(tiles)+2)//3)),(220,220,220))
        for i,t in enumerate(tiles): sheet.paste(t,(i%3*540,i//3*390))
        sheet.save(OUT/'source-textures.png')
(OUT/'inspection.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
for label, data in result.items():
    print('\n',label)
    for n,m in data['meshes'].items(): print(n,m['verts'],np.round(m['min'],3),np.round(m['max'],3),m['weights'][:5],m['materials'])
    for n,b in data['bones'].items(): print(n,b['parent'],np.round(b['head'],3))
