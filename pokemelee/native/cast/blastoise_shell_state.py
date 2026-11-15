"""Replace Bowser's kept tucked-body state with rounded Blastoise geometry.

Per-costume post step after round_out and hand_finish, no rigswap changes.
Static GX geometry is written in the real shell joint's local coordinates;
it has no envelopes, avoiding the double transform of envelopes under a JObj.
"""

from cast_paths import WORK, TARGETS, FILES
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
import bpy
import numpy as np
from mathutils import Matrix
from rigswap.plugins.melee.dat import Dat,joints,joint_dobjs,dat_joints
from rigswap.plugins.melee.export.eyes import dae_dobjs
from rigswap.plugins.melee.export.dobjs import layout,layout_differs,fighter_tables
from rigswap.plugins.melee.facts.memory import _triangles

H=Path(str(WORK / 'hand/blastoise-Bowser'));B=H/'3-build'
OUT=H/'4-export/Bowser.dat';SYM='PlyKoopa5K_Share_joint'
NS='{http://www.collada.org/2005/11/COLLADASchema}'
back=json.loads((B/'export/readback.json').read_text(encoding='utf-8'))
dae=next((Path(back['export_directory'])/'dae').glob('*.dae'))
names={m.get('id'):m.get('name') for m in ET.parse(dae).getroot().iter(NS+'material')}
source=dae_dobjs(dae)
material_place={names[mat]:back['dobjs']['places'][i] for i,(_,mat) in enumerate(source)}
aliases=back['joins']['material_aliases']
def resolve(n):
    seen=set()
    while n in aliases and n not in seen:seen.add(n);n=aliases[n]
    if n not in material_place:
        n=next(m for m in material_place if m.split('.')[0]==n.split('.')[0])
    return n

d=Dat.read(OUT);before=layout(d,SYM)
joint_list=joints(d,SYM);places=[p for j in joint_list for p in joint_dobjs(d,j)]
slots=list(range(78,100));assert len({before[p].joint for p in slots})==1
shell_joint=before[slots[0]].joint
rest=dat_joints(OUT,SYM)[f'JOBJ_{shell_joint}'];inv=np.linalg.inv(rest)
C=np.array([[1,0,0],[0,0,1],[0,-1,0]],float) # build to game

bpy.ops.wm.open_mainfile(filepath=str(B/'rounded.blend'))
by_material=defaultdict(list)
for ob in list(bpy.data.objects):
    if ob.type!='MESH':continue
    me=ob.data;group={g.index:g.name for g in ob.vertex_groups}
    is_head=ob.name.startswith('eyes') or ob.name in [f'kamex_mesh_{i:02}' for i in (0,1,3,4,5,17,18)]
    for v in me.vertices:
        p=np.array(v.co);side=1 if p[0]>=0 else -1
        if is_head:p=np.array([0,-3.2,28.5])+.53*(p-np.array([0,-5.55,29.53]))
        elif ob.name in ('kamex_mesh_14','kamex_mesh_15','kamex_mesh_16'):
            g=max(v.groups,key=lambda x:x.weight);j=int(group[g.group][5:])
            if j in (24,25,26,27,28) or (abs(p[0])<6 and p[1]>6):pass
            elif p[2]>21:p=np.array([side*7.5,-2.7,25])+.3*(p-np.array([side*14,-2,28]))
            else:p=np.array([side*5,0,14])+.28*(p-np.array([side*8,0,8]))
        v.co=p
    me.update();me.calc_loop_triangles()
    for tri in me.loop_triangles:
        mat=resolve(me.materials[tri.material_index].name)
        for li in tri.loops:
            v=me.vertices[me.loops[li].vertex_index]
            game=C@np.array(v.co);local=(inv@np.r_[game,1])[:3]
            normal=rest[:3,:3].T@(C@np.array(me.corner_normals[li].vector));normal/=np.linalg.norm(normal)
            uv=np.array(me.uv_layers.active.data[li].uv);uv[1]=1-uv[1]
            by_material[mat].append((local,normal,uv))
    ob.vertex_groups.clear();ob.vertex_groups.new(name=f'JOBJ_{shell_joint}').add(list(range(len(me.vertices))),1.,'REPLACE')
bpy.ops.wm.save_as_mainfile(filepath=str(B/'shell-state.blend'))
assert len(by_material)<=len(slots),(len(by_material),len(slots))
for slot in slots:d.point(places[slot]+12,None)
records=[]
for slot,(mat,verts) in zip(slots,by_material.items()):
    a=np.array([v[0] for v in verts]);n=np.array([v[1] for v in verts]);uv=np.array([v[2] for v in verts])
    assert len(a)<65536 and len(a)%3==0
    arrays=[d.add(x.astype('>f4').tobytes(),align=32) for x in (a,n,uv)]
    desc=bytearray()
    for attr,cnt,stride in ((9,1,12),(10,0,12),(13,1,8)):
        desc+=struct.pack('>4IBxHI',attr,3,cnt,4,0,stride,0)
    desc+=struct.pack('>I',255)+bytes(20)
    vd=d.add(desc)
    for i,p in enumerate(arrays):d.point(vd+24*i+20,p)
    dl=b'\x90'+struct.pack('>H',len(a))+b''.join(struct.pack('>3H',i,i,i) for i in range(len(a)))
    dl+=bytes(-len(dl)%32);display=d.add(dl,align=32)
    po=d.add(bytes(24));d.point(po+8,vd);d.point(po+16,display)
    struct.pack_into('>HH',d.data,po+12,0,len(dl)//32)
    d.point(places[slot]+8,d.ptr(places[material_place[mat]]+8));d.point(places[slot]+12,po)
    assert _triangles(d,po)==len(a)//3
    records.append({'place':slot,'material':mat,'triangles':len(a)//3})
d.save(OUT)
tables=fighter_tables(FILES / 'PlKp.dat')
assert layout_differs(before,layout(OUT,SYM),tables.animated) is None
(H/'shell-state.json').write_text(json.dumps({'joint':shell_joint,'replaced_places':slots,'geometry':records,
    'triangles':sum(r['triangles'] for r in records),'bytes':OUT.stat().st_size,
    'checks':['DObj order and animated texture destinations unchanged','Static local geometry: no double envelope transform',
              'All GX triangle counts read back exactly','No Bowser tucked-body geometry remains in the replacement slots']},indent=2),encoding='utf-8')
print('Replaced shell state on joint',shell_joint,'with',len(records),'materials;',OUT.stat().st_size,'bytes')
