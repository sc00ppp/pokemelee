"""Anatomical Colosseum Mewtwo fit. Source topology/UVs/normals are retained.

Vanilla supplies surface placement and skin envelopes; round_out owns smoothing.
Tail rings are remapped by their actual skin centres, not the upstream pivots.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image

ROOT=Path(str(WORK / 'hand/mewtwo-Mewtwo'))
B=ROOT/'3-build'
D=json.loads((ROOT/'inspection.json').read_text(encoding='utf-8'))
S=D['source']['meshes']; V=D['vanilla']['meshes']
SB={n:np.array(v['head']) for n,v in D['source']['bones'].items()}
TB={n:np.array(v['head']) for n,v in D['vanilla']['bones'].items()}
def sb(i):return SB[f'Bone_{i:02d}']
def tb(i):return TB[f'JOBJ_{i}']
def unit(v):return v/max(np.linalg.norm(v),1e-12)
def segment(a,b,c,d,width):
    axis=unit(b-a);r=np.array(Vector(axis).rotation_difference(Vector(unit(d-c))).to_matrix())
    mat=r@(width*np.eye(3)+(np.linalg.norm(d-c)/np.linalg.norm(b-a)-width)*np.outer(axis,axis))
    return mat,c-mat@a
def apply(p,t):return t[0]@p+t[1]
def reference(ids,side=0):
    pts=[];faces=[];weights=[]
    for i in ids:
        m=V[f'Joint_0_Object_{i}'];start=len(pts);pts+=m['points'];weights+=m['vw']
        faces += [[start+j for j in f] for f in m['faces'] if not side or all(np.sign(m['points'][j][0])==side for j in f)]
    return np.array(pts),faces,weights,BVHTree.FromPolygons(pts,faces)
refs={'body':reference([0,5]),'tail':reference([11]),'tube':reference([6]),
      'legL':reference([15,16,17,18]),'legR':reference([38,39,40,41]),
      'armL':reference([8],1),'armR':reference([8],-1),
      'handL':reference([9,10,3],1),'handR':reference([9,10,3],-1)}
def near(p,key,amount=1.):
    pts,faces,weights,tree=refs[key]
    at,normal,fi,dist=tree.find_nearest(Vector(p));at=np.array(at)
    f=faces[fi];tri=pts[f[:3]]
    bary=np.linalg.lstsq(np.vstack([tri.T,np.ones(3)]),np.r_[at,1],rcond=None)[0]
    bary=np.clip(bary,0,1);bary/=bary.sum();w={}
    for i,share in zip(f[:3],bary):
        for k,v in weights[i].items():w[k]=w.get(k,0)+share*v
    w=dict(sorted(w.items(),key=lambda x:-x[1])[:4]);total=sum(w.values())
    return p+(at-p)*amount,{k:v/total for k,v in w.items() if v>1e-6}

# Untwist the torso by its shoulder direction, then fit its actual chest surface.
x=unit(sb(31)-sb(19));z=unit(sb(45)-sb(74));y=unit(np.cross(z,x));x=unit(np.cross(y,z))
bodymat=np.diag([8.5,8.8,10.0])@np.array([x,y,z])
BODY=(bodymat,tb(5)-bodymat@sb(74))
HEAD=(np.diag([9.6,9.0,9.3]),np.array([0,-.2554,16.20])-np.diag([9.6,9.0,9.3])@sb(47))
trans={}
for src,dst,side in [([4,6,7,11],[8,9,11,12],'L'),([60,62,63,67],[14,15,17,18],'R')]:
    a,b,c,d=[sb(i) for i in src];ta,tb_,tc,td=[tb(i) for i in dst]
    for sn,t in zip([src[0]+1,src[1],src[2]+3],[segment(a,b,ta,tb_,8.2),segment(b,c,tb_,tc,8.2),segment(c,d,tc,td,8.2)]):trans[sn]=(t,'leg'+side)
    # Align the toe direction in the floor plane, preserving its spherical toes.
    end=SB['Bone_13_FootLeft' if side=='L' else 'Bone_69_FootRight']
    fwd=unit(np.array([end[0]-d[0],end[1]-d[1],0]))
    up=np.array([0,0,1.]);across=np.cross(fwd,up)
    mat=8.2*np.column_stack([[-1,0,0],[0,-1,0],[0,0,1]])@np.array([across,fwd,up])
    trans[src[3]]=((mat,td-mat@d),'leg'+side)
for src,dst,side in [([31,33,35],[31,32,35],'L'),([19,21,23],[54,55,58],'R')]:
    a,b,c=[sb(i) for i in src];ta,tb_,tc=[tb(i) for i in dst]
    trans[src[0]+1]=(segment(a,b,ta,tb_,7.2),'arm'+side)
    trans[src[1]]=(segment(b,c,tb_,tc,7.2),'arm'+side)

# Recover the source fingertips, fit a shared palm transform, then keep each
# finger in the part of vanilla that it actually animates with.
def source_points(bone):
    return np.unique(np.array([p for m in S.values() for p,w in zip(m['points'],m['vw']) if f'Bone_{bone:02d}' in w]).round(5),axis=0)
for wrist,fingers,tw,ends,side in [(35,[37,38,39],35,[41,39,37],'L'),(23,[25,26,27],58,[64,62,60],'R')]:
    sp=np.array([source_points(i).mean(0) for i in fingers])
    tp=np.array([tb(i)+np.array([.4 if side=='L' else -.4,0,0]) for i in ends])
    sx=unit(sp[1]-sb(wrist));sy=unit(sp[2]-sp[0]-sx*np.dot(sp[2]-sp[0],sx));sz=unit(np.cross(sx,sy))
    tx=unit(tp[1]-tb(tw));ty=unit(tp[2]-tp[0]-tx*np.dot(tp[2]-tp[0],tx));tz=unit(np.cross(tx,ty))
    rot=np.column_stack([tx,ty,tz])@np.array([sx,sy,sz])
    mat=rot@np.column_stack([sx,sy,sz])@np.diag([8.,6.4,7.])@np.array([sx,sy,sz])
    trans[wrist]=((mat,tb(tw)-mat@sb(wrist)),'hand'+side)
    for i,c,d in zip(fingers,sp,tp):trans[i]=((rot*7.,d-rot@c*7.),'hand'+side)

# Actual tail rings; the seam on mesh_22 shares these exact same coordinates.
tailcentres={i:source_points(i).mean(0) for i in range(75,80)}
tailcentres[74]=np.unique(np.array([p for name in ['mewtwo_mesh_10','mewtwo_mesh_22'] for p,w in zip(S[name]['points'],S[name]['vw']) if 'Bone_74' in w]).round(5),axis=0).mean(0)
tailcentres[80]=SB['Bone_81_Tail']
tailY={74:2.65,75:6.74,76:9.86,77:12.97,78:16.26,79:19.73,80:22.6}
def tail(p,i):
    c=tailcentres[i]
    tangent=unit(tailcentres[min(80,i+1)]-tailcentres[max(74,i-1)])
    # Carry the same right axis down the curl, so the two material shells meet.
    right=unit(np.cross([0,0,1],tangent));up=unit(np.cross(tangent,right))
    delta=p-c
    y=tailY[i]+np.dot(delta,tangent)*9.2
    z=np.interp(y,[2.1,3.828,6.74,9.86,12.97,16.26,19.73,23],[7.849,7.586,7.659,7.713,7.749,7.78,7.828,7.867])
    q=np.array([-np.dot(delta,right)*9.2,y,z+np.dot(delta,up)*9.2])
    return near(q,'tail',1.)

# The source's conduit is a three-ring chain. Its visible rings correspond to
# the following vanilla stations; envelopes come from vanilla's animated tube.
tubepoints={56:tb(51),57:tb(50),58:tb(48)}
def tube(p,i):
    c=source_points(i).mean(0)
    prev=sb(56) if i==56 else source_points(i-1).mean(0)
    nxt=c if i==58 else source_points(i+1).mean(0)
    axis=unit(nxt-prev) if i<58 else unit(c-prev)
    delta=p-c;dest=tubepoints[i]
    before=tb(45) if i==56 else tubepoints[i-1]
    after=tb(28) if i==58 else tubepoints[i+1]
    rot=np.array(Vector(axis).rotation_difference(Vector(unit(after-before))).to_matrix())
    q=dest+rot@delta*7.
    return near(q,'tube',1.)

bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
rawhead=np.array(D['raw']['meshes']['mewtwo_mesh_18']['points'])
srchead=np.array(S['mewtwo_mesh_18']['points'])
# Head raw mapping is exactly the build's uniform scale/translation; a second
# surface gives full rank instead of relying on its five coplanar points.
rawhead=np.concatenate([rawhead,D['raw']['meshes']['mewtwo_mesh_17']['points']])
srchead=np.concatenate([srchead,S['mewtwo_mesh_17']['points']])
aff=np.linalg.lstsq(np.column_stack([srchead,np.ones(len(srchead))]),rawhead,rcond=None)[0]
records=[]
for ob in bpy.data.objects:
    if ob.type!='MESH':continue
    for v in ob.data.vertices:
        if ob.name.startswith('eyes_'):
            p=np.linalg.solve(aff[:3].T,np.array(v.co)-aff[3]);w={'Bone_47':1.}
        else:p=np.array(S[ob.name]['points'][v.index]);w=S[ob.name]['vw'][v.index]
        bone=int(max(w,key=w.get).split('_')[1])
        if bone==47 and ob.name=='mewtwo_mesh_07' and np.linalg.norm(p-sb(56))<.12:
            q=tb(45)+(p-sb(56))*7.;q,nw=near(q,'tube',1.)
        elif bone in [47,59]:q=apply(p,HEAD);nw={'JOBJ_43':1.}
        elif bone in [56,57,58]:q,nw=tube(p,bone)
        elif bone>=75 or (bone==74 and ob.name in ['mewtwo_mesh_10','mewtwo_mesh_22']):q,nw=tail(p,bone)
        elif bone in trans:q,nw=near(apply(p,trans[bone][0]),trans[bone][1],.4 if trans[bone][1].startswith('hand') else .85)
        elif bone==44:
            q=apply(p,HEAD);q,nw=near(q,'body',.75)
        else:q,nw=near(apply(p,BODY),'body',.95)
        records.append((ob,v.index,p,q,nw))

# Join coincident source seam points geometrically and give each the same skin
# envelope. Stored normals are untouched; round_out reads them from base.blend.
seams={}
for row in records:seams.setdefault(tuple(np.round(row[2],4)),[]).append(row)
for members in seams.values():
    q=np.mean([r[3] for r in members],axis=0);w={}
    for r in members:
        for k,v in r[4].items():w[k]=w.get(k,0)+v/len(members)
    w=dict(sorted(w.items(),key=lambda kv:-kv[1])[:4]);total=sum(w.values())
    for ob,i,_,_,_ in members:
        ob.data.vertices[i].co=q
        for g in ob.vertex_groups:g.remove([i])
        for n,v in w.items():(ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n)).add([i],v/total,'REPLACE')
for ob in bpy.data.objects:
    if ob.type=='MESH':ob.data.update()

# The real eye atlas has 48-row open/half/closed tiles. Keep raw eye UV crop,
# replacing only the image contents; no triangle wrapping is needed here.
atlas=np.array(Image.open(ROOT/'tex_34A0.png').convert('RGBA'))
for state,offset in [('open',0),('half',48),('closed',96)]:
    Image.fromarray(atlas[7+offset:52+offset]).save(B/'eyes'/f'{state}.png')
old=bpy.data.images.get('eyes_open');new=bpy.data.images.load(str(B/'eyes/open.png'));new.pack()
for node in bpy.data.materials['eyes'].node_tree.nodes:
    if node.type=='TEX_IMAGE':node.image=new
if old:bpy.data.images.remove(old)
new.name='eyes_open'
eye=json.loads((B/'eyes.json').read_text(encoding='utf-8'))
eye['made']={s:f'Source atlas, 48-row tile {i}' for i,s in enumerate(['open','half','closed'])}
eye.pop('drawn',None);eye['notes']=['Real closed tile restored; raw UV footprint retained.']
(B/'eyes.json').write_text(json.dumps(eye,indent=2),encoding='utf-8')
# The forehead's stress-mark atlas uses a +1 V mapping to the blank rest tile.
for ob in [bpy.data.objects['mewtwo_mesh_18']]:
    for uv in ob.data.uv_layers.active.data:uv.uv=(.5,.99)
    for mat in ob.data.materials:
        for n in mat.node_tree.nodes:
            if n.type=='MAPPING':n.inputs['Location'].default_value=(0,0,0)
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
print('Saved anatomical Mewtwo; source topology and stored normals preserved.')
