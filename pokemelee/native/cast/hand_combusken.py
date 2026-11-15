"""Restore Combusken's source anatomy on Falco, starting from the raw pre-prep copy.

Source normals are left intact. Run round_out.py after this, before hand_finish.
The six discarded meshes are real hand claws, not alternate hand appearances.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
from collections import defaultdict
import bpy
import numpy as np
from mathutils import Vector, Matrix

R=Path(str(WORK / ''))
H=R/'hand/combusken-Falco'
B=H/'3-build'
SRC=R/'mons/combusken/1-load/models/1-g3_wakasyamo.blend'
S=json.loads((H/'source-geometry.json').read_text(encoding='utf-8'))
T=json.loads((H/'base-geometry.json').read_text(encoding='utf-8'))
def sj(i): return np.array(S['bones'][f'Bone_{i:03}']['head'])
def tj(i): return np.array(T['bones'][f'JOBJ_{i}']['head'])
def unit(v): return v/np.linalg.norm(v)
def mix(a,b,t): return a*(1-t)+b*t
def smooth(a,b,x):
    t=float(np.clip((x-a)/(b-a),0,1));return t*t*(3-2*t)
def rot(a,b): return np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())
def yaw(a): return np.array(Matrix.Rotation(float(a),3,'Z'))
def wt(j): return {f'JOBJ_{j}':1.}
def blendw(a,b,t):
    out=defaultdict(float)
    for n,w in a.items():out[n]+=w*(1-t)
    for n,w in b.items():out[n]+=w*t
    return dict(out)
def levels(z,heights,joints):
    if z<=heights[0]:return wt(joints[0])
    if z>=heights[-1]:return wt(joints[-1])
    i=int(np.searchsorted(heights,z)-1)
    return blendw(wt(joints[i]),wt(joints[i+1]),(z-heights[i])/(heights[i+1]-heights[i]))

HEAD_SCALE=19.
HEAD_TO=np.array([0.,-.2,14.15])
HEAD_ROT=yaw(-np.arctan2(.0213,.1197))
def head(p):return HEAD_TO+HEAD_SCALE*(HEAD_ROT@(p-sj(36)))

def trunk(p):
    z=p[2]
    angle=np.interp(z,[.32,.49,.55],[.88,.70,.176])
    center=np.array([np.interp(z,[.38,.522,.6514],[-.0175,-.017,-.0165]),
                     np.interp(z,[.38,.522,.6514],[.0095,.0091,-.036]),z])
    q=yaw(-angle)@(p-center)
    out=np.array([q[0]*17.,q[1]*17.-.05,np.interp(z,[.20,.3815,.4913,.522,.55],[4.7,8.3,10.55,11.69,12.22])])
    t=smooth(.49,.55,z)
    out=mix(out,head(p),t)
    w=levels(out[2],[8.3,9.43,10.8,12.],[4,19,38,39])
    return out,w

ARMS={}
for side,ss,ee,hh,tip,across,jj in [
    (1,6,8,12,[14,16,19],(13,18),(23,24,26)),
    (-1,20,22,26,[28,30,33],(27,32),(49,50,52))]:
    src=np.array([sj(ss),sj(ee),sj(hh)])
    dst=np.array([tj(j) for j in jj])
    along=unit(np.mean([sj(i) for i in tip],axis=0)-src[-1])
    acrossv=sj(across[0])-sj(across[1]);acrossv=unit(acrossv-along*(acrossv@along))
    normal=np.cross(along,acrossv)
    source_basis=np.column_stack([along,acrossv,normal])
    dest_basis=np.column_stack([[side,0,0],[0,-1,0],[0,0,-side]])
    handrot=dest_basis@source_basis.T
    # Keep the forearm's roll continuous with the hand. Independent shortest-arc
    # rotations align the limb axes but leave an arbitrary twist between them;
    # blending those positions pinches the wrist into a candy-wrapper shape.
    forearmrot=rot(handrot@unit(src[2]-src[1]),unit(dst[2]-dst[1]))@handrot
    upperrot=rot(forearmrot@unit(src[1]-src[0]),unit(dst[1]-dst[0]))@forearmrot
    ARMS[side]=(src,dst,jj,handrot,(upperrot,forearmrot))

def arm(p,side,is_hand=False):
    src,dst,jj,handrot,segmentrots=ARMS[side]
    armvec=src[2]-src[1]
    t=float((p-src[1])@armvec/(armvec@armvec))
    if is_hand or t>.65:
        hand=dst[2]+11.5*(handrot@(p-src[2]))
        if is_hand or t>=.9:return hand,wt(jj[2])
    # Select the segment by distance, respecting the asymmetric posed source.
    options=[]
    for i in (0,1):
        v=src[i+1]-src[i];u=float(np.clip((p-src[i])@v/(v@v),0,1))
        options.append((np.linalg.norm(p-(src[i]+u*v)),i,u))
    _,i,u=min(options)
    v=src[i+1]-src[i]
    off=p-src[i]-u*v
    q=mix(dst[i],dst[i+1],u)+11.5*(segmentrots[i]@off)
    if i==0:
        w=blendw(wt(jj[0]),wt(jj[1]),smooth(.75,1.,u)*.5)
        tr,tw=trunk(p);b=smooth(0,.38,u)
        q=mix(tr,q,b);w=blendw(tw,w,b)
    else:
        w=blendw(wt(jj[0]),wt(jj[1]),.5+.5*smooth(0,.2,u))
        b=smooth(.65,.9,t)
        if b:q=mix(q,hand,b);w=blendw(w,wt(jj[2]),b)
    return q,w

LEGS={}
grey=np.array(S['objects']['wakasyamo_mesh_30']['co'])
for side,hip,ank,roots,tips,ring,jj in [
    (1,58,61,(65,70),(66,68,71),(0,2,3,16),(6,7,9)),
    (-1,77,80,(89,84),(85,87,90),(5,7,9,13),(12,13,15))]:
    toe_roots=(65,67,70) if side==1 else (84,86,89)
    forward=unit(np.mean([sj(i) for i in tips],axis=0)-np.mean([sj(i) for i in toe_roots],axis=0))
    right=sj(roots[0])-sj(roots[1]);right=unit(right-forward*(right@forward))
    up=unit(np.cross(forward,right))
    if up[2]<0:right=-right;up=-up
    footrot=np.stack([right,-forward,up])
    footpoints=[]
    for name,o in S['objects'].items():
        for p,w in zip(o['co'],o['weights']):
            n=int(max(w,key=w.get)[5:8])
            if (side==1 and 62<=n<=72) or (side==-1 and 81<=n<=91):
                footpoints.append(footrot@(np.array(p)-sj(ank)))
    footpoints=np.array(footpoints)
    scale=np.array([17.,19.,tj(jj[2])[2]/-footpoints[:,2].min()])
    src=np.array([sj(hip),grey[list(ring)].mean(0),sj(ank)])
    dst=np.array([tj(j) for j in jj])
    LEGS[side]=(src,dst,jj,footrot,scale)

def leg(p,side,is_foot=False):
    src,dst,jj,fr,fs=LEGS[side]
    foot=dst[2]+(fr@(p-src[2]))*fs
    if is_foot:return foot,wt(jj[2])
    # Knee ring sits exactly on Falco's knee; every ring shares one cross-section plane.
    vec=src[2]-src[0];axis=unit(vec)
    d=float((p-src[1])@axis)
    if d<=0:
        u=float(np.clip((p-src[0])@axis/((src[1]-src[0])@axis),0,1))
        at=mix(src[0],src[1],u)
        off=p-at;off-=axis*(off@axis)
        q=mix(dst[0],dst[1],u)+13.2*(rot(axis,unit(dst[1]-dst[0]))@off)
        w=blendw(wt(jj[0]),wt(jj[1]),smooth(.8,1.,u)*.5)
        # Blend the thigh roots into the pelvis, using original source memberships later.
        return q,w
    axis2=axis;u=float(np.clip((p-src[1])@axis2/((src[2]-src[1])@axis2),0,1))
    at=mix(src[1],src[2],u);off=p-at;off-=axis2*(off@axis2)
    width=mix(13.2,17.,u)
    q=mix(dst[1],dst[2],u)+width*(rot(axis2,unit(dst[2]-dst[1]))@off)
    b=smooth(.55,.9,u)
    q=mix(q,foot,b)
    w=blendw(wt(jj[0]),wt(jj[1]),.5+.5*smooth(0,.2,u))
    return q,blendw(w,wt(jj[2]),b)

def by_bone(p,n):
    if 6<=n<=19:return arm(p,1,n>=12)
    if 20<=n<=33:return arm(p,-1,n>=26)
    if 58<=n<=72:return leg(p,1,n>=62)
    if 77<=n<=91:return leg(p,-1,n>=81)
    if 35<=n<=53:return head(p),wt(39)
    if n==55:
        q=trunk(sj(54))[0]+14.*(yaw(-.88)@(p-sj(54)))
        return q,wt(4)
    return trunk(p)

def mapped(p,w,name):
    # The yellow feather bib belongs to the torso, including its long lower points.
    # Giving those tips to thighs pulls the bib across the face during a high kick.
    if name in ('wakasyamo_mesh_23','wakasyamo_mesh_40','wakasyamo_mesh_41'):
        w={('Bone_005' if 58<=int(n[5:8])<=91 else n):v for n,v in w.items()}
    # Torso/head transition must be identical for both sides of the eye/face seam.
    if p[2]>=.515 and all(35<=int(n[5:8])<=53 or n=='Bone_005' for n in w):
        return trunk(p) if p[2]<.55 else (head(p),wt(39))
    q=np.zeros(3);out=defaultdict(float);total=sum(w.values())
    for n,weight in w.items():
        at,weights=by_bone(p,int(n[5:8]));share=weight/total
        q+=at*share
        for j,v in weights.items():out[j]+=v*share
    return q,dict(out)

def main():
    bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
    armature=bpy.data.objects['Armature']
    missing=[n for n in S['objects'] if n not in bpy.data.objects and n!='wakasyamo_mesh_26']
    with bpy.data.libraries.load(str(SRC),link=False) as (src,dst):dst.objects=list(missing)
    for ob in dst.objects:
        bpy.context.scene.collection.objects.link(ob)
        for mod in ob.modifiers:
            if mod.type=='ARMATURE':mod.object=armature
        ob.parent=None
    # Source coordinates identify seams globally; use one result at each coincident position.
    seam=defaultdict(list)
    records={}
    for name,o in S['objects'].items():
        dest='eyes_right' if name=='wakasyamo_mesh_26' else name
        records[dest]=[]
        for p,w in zip(o['co'],o['weights']):
            result=mapped(np.array(p),w,name)
            key=tuple(np.round(p,5));seam[key].append(result);records[dest].append(key)
    shared={}
    for key,values in seam.items():
        q=np.mean([v[0] for v in values],axis=0);w=defaultdict(float)
        for _,weights in values:
            for n,v in weights.items():w[n]+=v/len(values)
        shared[key]=(q,dict(w))
    for name,keys in records.items():
        ob=bpy.data.objects[name]
        assert len(ob.data.vertices)==len(keys),(name,len(ob.data.vertices),len(keys))
        ob.matrix_world=Matrix.Identity(4)
        ob.vertex_groups.clear()
        for v,key in zip(ob.data.vertices,keys):
            co,w=shared[key];v.co=co
            for j,weight in w.items():
                if weight>1e-6:(ob.vertex_groups.get(j) or ob.vertex_groups.new(name=j)).add([v.index],float(weight),'REPLACE')
        ob.data.update()
    # Source textures stay untouched. Existing clamp-correct open/half/closed eye tiles stay packed.
    bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
    # The reconstructed crest is one upright crown on the skull. Old raw-run
    # hair springs retain sideways attachment points and would override that rig.
    (B/'loose.json').write_text(json.dumps({'attribute':'rigswap_loose','chains':[]},indent=2),encoding='utf-8')
    (H/'edit-notes.json').write_text(json.dumps({'restored_claws':missing,'head_scale':HEAD_SCALE,
        'head_anchor':HEAD_TO.tolist(),'thigh_width_scale':13.2,'hand_scale':11.5,
        'notes':['Preserved all stored normals; round_out is the sole rounding/shading step.',
                 'Source facial forward is -Y; raw front reading +X rotated face and toes sideways.',
                 'Anatomical grey/orange knee rings mapped to Falco knees; feet assigned ankle joints.',
                 'Source six discarded meshes are real claw digits.']},indent=2),encoding='utf-8')
    print('Restored claws',missing)
    print('Saved',B/'edited.blend')

if __name__=='__main__':main()
