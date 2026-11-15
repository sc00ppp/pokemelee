"""Rebuild Blastoise's rigid shell assembly and source anatomy on Bowser.
Stored normals are retained. round_out.py is the sole rounding/shading step.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
from collections import defaultdict
import bpy
import numpy as np
from mathutils import Vector, Matrix
from PIL import Image

R=Path(str(WORK / ''))
H=R/'hand/blastoise-Bowser';B=H/'3-build'
S=json.loads((H/'source-geometry.json').read_text(encoding='utf-8'))
T=json.loads((H/'base-geometry.json').read_text(encoding='utf-8'))
def sj(i):return np.array(next(v['head'] for n,v in S['bones'].items() if n==f'Bone_{i:02}' or n.startswith(f'Bone_{i:02}_')))
def tj(i):return np.array(T['bones'][f'JOBJ_{i}']['head'])
def unit(p):return p/np.linalg.norm(p)
def mix(a,b,t):return a*(1-t)+b*t
def smooth(a,b,x):
    t=float(np.clip((x-a)/(b-a),0,1));return t*t*(3-2*t)
def wt(j):return {f'JOBJ_{j}':1.}
TORSO={'JOBJ_29':1.}
def blendw(a,b,t):
    w=defaultdict(float)
    for n,v in a.items():w[n]+=v*(1-t)
    for n,v in b.items():w[n]+=v*t
    return dict(w)
def rot(a,b):return np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())

BODY_SCALE=np.array([20.,20.,18.5])
BODY_OFFSET=np.array([0.,2.,8.5])
def body(p):return p*BODY_SCALE+BODY_OFFSET
def head(p):return np.array([0.,-5.546,29.533])+24.*(p-sj(26))

def tube(p,src,dst,width):
    # Closest centreline segment; cross-sections rotate together, no independently turned end rings.
    opts=[]
    for i in range(len(src)-1):
        v=src[i+1]-src[i];u=float(np.clip((p-src[i])@v/(v@v),0,1))
        opts.append((np.linalg.norm(p-mix(src[i],src[i+1],u)),i,u))
    _,i,u=min(opts)
    q=mix(dst[i],dst[i+1],u)+width*(rot(src[i+1]-src[i],dst[i+1]-dst[i])@(p-mix(src[i],src[i+1],u)))
    return q,i,u

ARMS={}
ac=np.array(S['objects']['kamex_mesh_14']['co'])
for side,rings,jj in [(1,([0,1,2,3,95,96,97,98,99],[4,8,12,16,20,24,28,32],[6,10,14,18,22,26,30,34]),(33,34,35)),
                      (-1,(list(range(68,77)),[38,42,46,50,54,58,62,66],[36,40,44,48,52,56,60,64]),(60,61,62))]:
    src=np.array([ac[r].mean(0) for r in rings]);dst=np.array([body(src[0]),tj(jj[1]),tj(jj[2])])
    rotations=[]
    for i,ring in enumerate(rings):
        normal=np.linalg.svd(ac[ring]-src[i])[2][-1]
        along=src[min(i+1,2)]-src[max(0,i-1)]
        if normal@along<0:normal=-normal
        direction=dst[min(i+1,2)]-dst[max(0,i-1)]
        rotations.append(rot(normal,direction))
    ARMS[side]=(src,dst,rings,jj,rotations)

def arm(p,side,hand=False):
    src,dst,rings,jj,rr=ARMS[side]
    if hand:return dst[2]+20.*(rr[2]@(p-src[2])),wt(jj[2])
    for i,ring in enumerate(rings):
        if np.linalg.norm(ac[ring]-p,axis=1).min()<1e-5:
            if i==0:return body(p),blendw(TORSO,wt(jj[0]),.15)
            w=blendw(wt(jj[i-1]),wt(jj[i]),.5)
            return dst[i]+20.*(rr[i]@(p-src[i])),w
    raise ValueError(('arm point not in anatomical ring',p))

def leg(p,side,foot=False):
    ss,kk,aa,jj=(4,5,6,(6,7,9)) if side==1 else (10,11,12,(15,16,18))
    src=np.array([sj(ss),sj(kk),sj(aa)])
    dst=np.array([body(src[0]),tj(jj[1]),tj(jj[2])])
    # Foot stays level and attached to the ankle. Actual source sole is z=-.004.
    footq=dst[2]+(p-src[2])*np.array([21.,23.,dst[2,2]/(src[2,2]+.004)])
    if foot:return footq,wt(jj[2])
    q,i,u=tube(p,src,dst,20.)
    if i==0:
        w=blendw(wt(jj[0]),wt(jj[1]),.5*smooth(.7,1,u))
        b=smooth(0,.3,u);q=mix(body(p),q,b);w=blendw(TORSO,w,b)
    else:
        w=blendw(wt(jj[0]),wt(jj[1]),.5+.5*smooth(0,.25,u))
        b=smooth(.5,.95,u);q=mix(q,footq,b);w=blendw(w,wt(jj[2]),b)
    return q,w

def tail(p):
    return body(p),TORSO

def mapped(p,w,name):
    n=int(max(w,key=w.get)[5:7])
    if name not in ('kamex_mesh_14','kamex_mesh_15','kamex_mesh_16'):
        return (head(p),wt(48)) if n in (26,32) else (body(p),TORSO)
    if n in (37,38,39):return arm(p,1,n==39)
    if n in (42,43,44):return arm(p,-1,n==44)
    if n in (4,5,6):return leg(p,1,n==6)
    if n in (10,11,12):return leg(p,-1,n==12)
    if n in (34,35):return tail(p)
    raise ValueError((name,n))

def main():
    bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
    armature=bpy.data.objects['Armature']
    with bpy.data.libraries.load(str(R/'mons/blastoise/1-load/models/1-009_Blastoise.blend'),link=False) as (src,dst):
        dst.objects=['kamex_mesh_21','kamex_mesh_23']
    for ob in dst.objects:
        bpy.context.scene.collection.objects.link(ob);ob.parent=None
        for m in ob.modifiers:
            if m.type=='ARMATURE':m.object=armature
    seams=defaultdict(list);records={}
    for name,o in S['objects'].items():
        records[name]=[]
        for p,w in zip(o['co'],o['weights']):
            key=tuple(np.round(p,5));seams[key].append(mapped(np.array(p),w,name));records[name].append(key)
    shared={}
    for key,vals in seams.items():
        w=defaultdict(float)
        for _,ww in vals:
            for j,v in ww.items():w[j]+=v/len(vals)
        shared[key]=(np.mean([v[0] for v in vals],axis=0),dict(w))
    eye_source=np.array(S['objects']['kamex_mesh_02']['co'])
    # Split eye meshes retain raw coordinates: invert the exact raw head fit to identify source points.
    raw_head=np.array(T['objects']['kamex_mesh_18']['co'])
    source_head=np.array(S['objects']['kamex_mesh_18']['co'])
    fit=np.linalg.lstsq(np.column_stack([source_head,np.ones(len(source_head))]),raw_head,rcond=None)[0]
    for name in ('eyes_left','eyes_right'):
        raw=np.array(T['objects'][name]['co']);src=(raw-fit[3])@np.linalg.inv(fit[:3])
        records[name]=[]
        for p in src:
            k=int(np.argmin(np.linalg.norm(eye_source-p,axis=1)));assert np.linalg.norm(eye_source[k]-p)<1e-4
            records[name].append(tuple(np.round(eye_source[k],5)))
    del records['kamex_mesh_02']
    for name,keys in records.items():
        ob=bpy.data.objects[name];ob.matrix_world=Matrix.Identity(4);ob.vertex_groups.clear()
        assert len(keys)==len(ob.data.vertices)
        for v,key in zip(ob.data.vertices,keys):
            co,w=shared[key];v.co=co
            for j,weight in w.items():
                if weight>1e-6:(ob.vertex_groups.get(j) or ob.vertex_groups.new(name=j)).add([v.index],float(weight),'REPLACE')
        ob.data.update()
    # HSD marks these maps as specular-only. The GLB incorrectly makes them dark diffuse paint.
    silver=bpy.data.images.new('blastoise_silver',width=8,height=8)
    silver.pixels=[.70,.72,.74,1.]*64;silver.pack()
    for name in ('kamex_mesh_13','kamex_mesh_21','kamex_mesh_23'):
        for mat in bpy.data.objects[name].data.materials:
            for node in mat.node_tree.nodes:
                if node.type=='TEX_IMAGE':node.image=silver
    # Painted black source sockets were hidden by the short source limbs. Bowser's
    # wider poses expose them as holes. Continue the actual rim/belly colour there.
    for number in (8,9,10):
        ob=bpy.data.objects[f'kamex_mesh_{number:02}']
        for mat in ob.data.materials:
            for node in mat.node_tree.nodes:
                if node.type!='TEX_IMAGE':continue
                old=node.image;w,h=old.size;px=np.array(old.pixels[:]).reshape(h,w,4)
                mask=px[:,:,:3].max(2)<.55
                if not mask.any():continue
                good=np.argwhere(~mask)
                for y,x in np.argwhere(mask):
                    near=good[np.argmin(((good-[y,x])**2).sum(1))]
                    px[y,x]=px[tuple(near)]
                # Rim sockets are entirely white; belly/tail retain their two-colour boundaries.
                if number in (8,10):px[:,:,:3]=[.94,.97,.96]
                if number==12:
                    for y,x in np.argwhere(mask):px[y,x,:3]=[.94,.97,.96] if y>h*.56 else [.51,.39,.25]
                if number==9:
                    for y,x in np.argwhere(mask):px[y,x,:3]=px[y,w//2,:3] if px[y,w//2,:3].max()>.55 else [.72,.56,.35]
                im=bpy.data.images.new(f'blastoise_socket_{number}',width=w,height=h)
                im.pixels=px.ravel().tolist();im.pack();node.image=im
    # Real source eye states are 24 rows apart; keep the existing 25px UV box and clamp its last row.
    atlas=Image.open(H/'review/source-tex_6668.png').convert('RGBA')
    for state,row in [('open',0),('half',24),('closed',48)]:
        px=np.array(atlas)[row:row+24];px=np.concatenate([px,px[-1:]],axis=0)
        Image.fromarray(px).save(B/'eyes'/f'{state}.png')
    new=bpy.data.images.load(str(B/'eyes/open.png'));new.pack()
    for node in bpy.data.materials['eyes'].node_tree.nodes:
        if node.type=='TEX_IMAGE':node.image=new
    e=json.loads((B/'eyes.json').read_text(encoding='utf-8'))
    e.pop('drawn',None)
    e['eye_texture_size']=[56,25];e['made']={s:f'source atlas rows {row}..{row+23}, clamped' for s,row in [('open',0),('half',24),('closed',48)]}
    (B/'eyes.json').write_text(json.dumps(e,indent=2),encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
    (H/'edit-notes.json').write_text(json.dumps({'body_scale':BODY_SCALE.tolist(),'body_offset':BODY_OFFSET.tolist(),
        'shell_joint':29,'restored':['kamex_mesh_21','kamex_mesh_23'],
        'notes':['Rigid source shell, rim, belly and cannon assembly restored as one piece.',
                 'Specular-only cannon texture replaced by source silver diffuse colour.',
                 'Stored normals retained for round_out. Real eye tiles restored.']},indent=2),encoding='utf-8')

if __name__=='__main__':main()
