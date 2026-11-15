"""Blaziken: source feather rings above distinct feet, with controlled head plumes.

Run from the untouched pre-prep base. No stored normals or existing topology are
changed. stand_feet, round_out, then hand_finish complete this hand port.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

R = Path(str(WORK / ''))
W = R/'hand/blaziken-CaptainFalcon'
B = W/'3-build'
src = json.loads((W/'reference/source-geometry.json').read_text(encoding='utf-8'))
base = json.loads((W/'reference/base-geometry.json').read_text(encoding='utf-8'))
feet = json.loads((W/'reference/vanilla-feet.json').read_text(encoding='utf-8'))

def point(data, name):
    return np.array(data['bones'][name]['head'], float)

def unit(v):
    return v/np.linalg.norm(v)

def rot(a, b):
    return np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())

def weight(ob, i, w):
    for g in ob.vertex_groups:
        g.remove([i])
    for name, value in w.items():
        if value > 1e-5:
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i], float(value), 'REPLACE')

bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
arm = bpy.data.objects['Armature']
plans = [dict(side='R', hip='Bone_017', knee='Bone_018', ankle='Bone_019', hem='Bone_020',
              extra='Bone_027', thigh=13, shin=14, foot=16, claw='00'),
         dict(side='L', hip='Bone_030', knee='Bone_031', ankle='Bone_032', hem='Bone_033',
              extra='Bone_040_Additional3', thigh=7, shin=8, foot=10, claw='03')]
for plan in plans:
    sh, sk, sa = [point(src, plan[k]) for k in ('hip','knee','ankle')]
    th, tk, ta = [point(base, 'JOBJ_'+str(plan[k])) for k in ('thigh','shin','foot')]
    rth, rsh = rot(unit(sk-sh), unit(tk-th)), rot(unit(sa-sk), unit(ta-tk))
    # The feather ends above the ankle blend band used by stand_feet.
    hem_center = ta + [0, 0, 2.05]
    def thigh(p):
        u = (p-sh)@unit(sk-sh)
        return th + unit(tk-th)*u*np.linalg.norm(tk-th)/np.linalg.norm(sk-sh) + rth@((p-sh)-u*unit(sk-sh))*9.3
    def knee(p):
        u = (p-sk)@unit(sa-sk)
        return tk + unit(hem_center-tk)*u*np.linalg.norm(hem_center-tk)/np.linalg.norm(sa-sk) + rsh@((p-sk)-u*unit(sa-sk))*9.3
    def ankle(p):
        return hem_center + (p-sa)*[6.6,6.6,8.0]
    moved = 0
    for name, data in src['meshes'].items():
        ob = bpy.data.objects.get(name)
        if ob is None or len(ob.data.vertices)!=len(data['co']):
            continue
        for i,(xyz,w) in enumerate(zip(data['co'],data['weights'])):
            keys = (plan['hip'],plan['knee'],plan['ankle'],plan['hem'],plan['extra'])
            share = sum(w.get(k,0) for k in keys)
            if not share:
                continue
            p = np.array(xyz)
            old = np.array(base['meshes'][name]['co'][i])
            # Hip attachments stay continuous with the retained waist.
            blend = np.clip(np.linalg.norm(p-sh)/.25,0,1)
            new = old*(1-share)
            for key in keys:
                fn = thigh if key==plan['hip'] else ankle if key in (plan['ankle'],plan['hem']) else knee
                q = fn(p)
                if key==plan['hip']:
                    q = old*(1-blend)+q*blend
                new += w.get(key,0)*q
            ob.data.vertices[i].co = new
            # Feather hem belongs to the shin, not the ankle/toes.
            held = dict(base['meshes'][name]['weights'][i])
            if w.get(plan['ankle'],0)+w.get(plan['hem'],0)>.99:
                held = {'JOBJ_'+str(plan['shin']):1.0}
            weight(ob,i,held)
            moved += 1
        ob.data.update()
    print(plan['side'],'source leg vertices rebuilt',moved)

    # The source has three separate seven-point talons. Turn each lengthwise,
    # preserving its original faces, UVs and split normals, and spread the toes.
    ob = bpy.data.objects['bursyamo_mesh_'+plan['claw']]
    co = np.array(src['meshes'][ob.name]['co'])
    forward = np.array(feet[plan['side']][4])[[0,2,1]]*[1,-1,1]
    forward[2]=0
    forward=unit(forward)
    across=np.array([-forward[1],forward[0],0])
    normal=np.array(feet[plan['side']][0])[[0,2,1]]*[1,-1,1]
    depth=feet[plan['side']][2]
    floor = ta+normal*depth
    for c, spread in enumerate((-.85,0,.85)):
        ids=np.arange(c*7,c*7+7)
        pts=co[ids]
        # Source tip is lowest; source crest is its furthest radial point.
        tip=int(np.argmin(pts[:,2]))
        xy=pts[:,:2]-pts[:,:2].mean(0)
        crest=unit(xy[np.argmax(np.linalg.norm(xy,axis=1))])
        width_axis=np.array([-crest[1],crest[0]])
        xx=xy@width_axis
        zz=xy@crest
        xx=(xx-(xx.min()+xx.max())/2)/np.ptp(xx)*.66
        zz=(zz-zz.min())/np.ptp(zz)*.85+.06
        zz[tip]=.025
        along=.85+(pts[:,2].max()-pts[:,2])/np.ptp(pts[:,2])*(3.572-.85)
        along-=abs(spread)*.12
        for k,i in enumerate(ids):
            ob.data.vertices[int(i)].co=floor+across*(spread+xx[k])+forward*along[k]+normal*zz[k]
            weight(ob,int(i),{'JOBJ_'+str(plan['foot']):1.0})
    ob.data.update()

    # A small continuous grey instep connects the three talons to the ankle.
    points=[]
    profiles=[(-.75,.52,1.15),(.05,.70,3.45),(.95,1.03,1.28),(1.62,1.10,.72)]
    for along,width,top in profiles:
        for dx,z in [(-.65,.03),(.65,.03),(1,.20),(1,.65),(.52,1),(-.52,1),(-1,.65),(-1,.20)]:
            points.append(tuple(floor+forward*along+across*(width*dx)+normal*(.03+(top-.03)*z)))
    faces=[]
    for r in range(len(profiles)-1):
        for j in range(8):
            a=r*8+j; b=r*8+(j+1)%8; c=(r+1)*8+(j+1)%8; d=(r+1)*8+j
            faces.extend([(a,b,c),(a,c,d)])
    faces.extend([(0,j+1,j) for j in range(1,7)])
    k=(len(profiles)-1)*8
    faces.extend([(k,k+j,k+j+1) for j in range(1,7)])
    # Winding above follows clockwise profiles viewed along the toe direction.
    me=bpy.data.meshes.new('blaziken_instep_'+plan['side'])
    me.from_pydata(points,[],faces)
    me.materials.append(bpy.data.materials['bursyamo_mat_30'])
    layer=me.uv_layers.new(name='UVMap')
    for uv in layer.data: uv.uv=(.52,.72)
    instep=bpy.data.objects.new(me.name,me)
    bpy.context.scene.collection.objects.link(instep)
    mod=instep.modifiers.new('Armature','ARMATURE');mod.object=arm
    for i,p in enumerate(points):
        h=(np.array(p)-floor)@normal
        shin=float(np.clip((h-1.7)/1.1,0,1))
        weight(instep,i,{'JOBJ_'+str(plan['foot']):1-shin,'JOBJ_'+str(plan['shin']):shin})
    # This is a new continuous surface, with no rip normals to preserve.
    for p in me.polygons: p.use_smooth=True
    me.update()

# Keep the two pointed plumes behind the shoulders. Their roots retain the head
# surface; each plume follows the head instead of an unconstrained spring.
ob=bpy.data.objects['bursyamo_mesh_21']
data=src['meshes'][ob.name]
for bone,sign in [('Bone_088',1),('Bone_091',-1)]:
    ids=[i for i,w in enumerate(data['weights']) if w.get(bone,0)>.99]
    root=point(src,bone)
    pts=np.array([data['co'][i] for i in ids])
    delta=pts-root
    axis=unit(delta.mean(0))
    u=delta@axis
    root_target=point(base,'JOBJ_39')+np.array([sign*.91,.68,1.18])
    direction=np.array([sign*1.8,9.5,-2.1])
    turn=rot(axis,unit(direction))
    for i,p,arc in zip(ids,delta,u):
        t=arc/u.max()
        ob.data.vertices[i].co=root_target+direction*t+turn@(p-axis*arc)*12.0
        weight(ob,i,{'JOBJ_39':1.0})
ob.data.update()
for ob in bpy.data.objects:
    if ob.type=='MESH' and 'rigswap_loose' in ob.data.attributes:
        ob.data.attributes.remove(ob.data.attributes['rigswap_loose'])
(B/'loose.json').write_text(json.dumps({'attribute':'rigswap_loose','chains':[],
    'notes':['Plumes have a clear rearward path on the head joint; no springs can sweep them through the torso.']},indent=1),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
print('Saved hand edit; next: stand_feet, round_out, hand_finish.')
