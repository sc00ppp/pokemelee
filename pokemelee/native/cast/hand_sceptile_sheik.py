"""Hand-fit Sceptile's authored surface to Sheik's unchanged joints.

The source inspections are reused read-only from sceptile-Marth. The raw Sheik
build supplies materials and blink crops; base.blend remains the preserved input.
Shoulders, elbows, wrists and the leg rings use the source's anatomical chains.
The tail uses a restrained hips/waist/chest gradient: Sheik's 58-joint target has
no hair/braid chain. Needles, chain, vanish and Zelda files are not edited.
"""

from cast_paths import WORK, TARGETS
import json
from pathlib import Path
import bpy
import numpy as np

R = Path(str(WORK / ''))
H = R / 'hand/sceptile-Sheik'
B = H / '3-build'
SOURCE = json.loads((R/'hand/sceptile-Marth/source.json').read_text(encoding='utf-8'))
RAW = json.loads((H/'base.json').read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
S = {n:np.array(b['head']) for n,b in SOURCE['bones'].items()}
T = {n:np.array(b['head']) for n,b in RAW['bones'].items()}
def sb(i): return S[f'Bone_{i:02d}']
def tb(i): return T[f'JOBJ_{i}']
def unit(p): return p/np.linalg.norm(p)
def frame(a,b,ref):
    y=unit(b-a)
    x=unit(np.array(ref)-y*np.dot(ref,y))
    return np.column_stack((x,y,np.cross(x,y)))
def segment(p,a,b,c,d,k,ref=(1,0,0),newref=(1,0,0)):
    f,g=frame(a,b,ref),frame(c,d,newref)
    v=f.T@(p-a)
    v*= [k,np.linalg.norm(d-c)/np.linalg.norm(b-a),k]
    return c+g@v

maps={}
spine=[19,57,58,85,86]
spine_to=[tb(i) for i in (4,17,18,35,36)]
for a,b,c,d,j in zip(spine[:-1],spine[1:],spine_to[:-1],spine_to[1:],(4,17,18,35)):
    maps[a]=(sb(a),sb(b),c,d,7.2,(1,0,0),(1,0,0),j)

for a,b,c,joints,sign in ((60,61,64,(21,22,23),1),(73,74,77,(41,42,43),-1)):
    source=[sb(a),sb(b),sb(c)]
    target=[tb(j) for j in joints]
    for bone,n in ((a,0),(b,1)):
        maps[bone]=(source[n],source[n+1],target[n],target[n+1],7.0,(0,0,1),(0,0,1),joints[n])
    fingers=(66,67,68) if sign==1 else (79,80,81)
    end=np.mean([sb(i) for i in fingers],axis=0)
    handend=target[-1]+np.array([sign*.85,0,-.12])
    maps[c]=(source[-1],end,target[-1],handend,6.0,(0,0,1),(0,0,1),joints[-1])
    for bone in fingers: maps[bone]=maps[c]
    for blade in ((70,71) if sign==1 else (83,84)): maps[blade]=maps[b]

LEG=(4.5,4.2,4.2,4.8)   # thickness down the leg: Sheik's legs are long, so the body's scale made a haunch into a slab
for chain,joints in (((20,22,24,26,28),(6,7,9,10)),((35,37,39,41,43),(12,13,15,16))):
    a,b,c,d,e=chain
    thigh,knee,heel,toe=[tb(i) for i in joints]
    hock=knee*.37+heel*.63
    target=[thigh,knee,hock,heel,toe]
    for n,bone in enumerate(chain[:-1]):
        carrier=joints[0] if n==0 else joints[1] if n<3 else joints[2]
        maps[bone]=(sb(bone),sb(chain[n+1]),target[n],target[n+1],LEG[n],(1,0,0),(1,0,0),carrier)
    footend=S['Bone_29_FootLeft' if a==20 else 'Bone_44_FootRight']
    maps[e]=(sb(e),footend,toe,toe+np.array([0,-.95,-.22]),5.8,(1,0,0),(1,0,0),joints[3])
    maps[a+1]=maps[a]
    maps[d-1]=maps[d]

eye_axis=unit(S['Bone_90_EyeLeft']-S['Bone_92_EyeRight'])
forward=S['Bone_91_Mouth']-sb(86)
forward=unit(forward-eye_axis*np.dot(forward,eye_axis))
headframe=np.column_stack((eye_axis,-forward,np.cross(eye_axis,-forward)))
def head(p): return tb(36)+6.8*(headframe.T@(p-sb(86)))

tail_src=np.array([sb(i) for i in (19,51,52,53,54,55)]+[S['Bone_56_Tail']])
tail_dst=np.array([tb(4),[0,1.0,8.3],[0,2.15,8.38],[0,3.6,8.48],[0,5.05,8.58],[0,6.5,8.68],[0,8.4,8.8]])
def tail(p):
    choices=[]
    for i,(a,b) in enumerate(zip(tail_src[:-1],tail_src[1:])):
        u=np.clip(np.dot(p-a,b-a)/np.dot(b-a,b-a),0,1)
        choices.append((np.linalg.norm(p-a-u*(b-a)),i,u))
    _,i,u=min(choices)
    q=segment(p,tail_src[i],tail_src[i+1],tail_dst[i],tail_dst[i+1],6.2)
    t=(i+u)/(len(tail_src)-1)
    t=t*t*(3-2*t)
    return q,{4:1-.22*t,17:.17*t,18:.05*t}

def mapped(p,bone):
    i=int(bone.split('_')[1])
    if i in (86,93): return head(p),{36:1.}
    if i in range(94,100): i={94:85,95:85,96:58,97:58,98:19,99:19}[i]
    a,b,c,d,k,r,s,j=maps[i]
    return segment(p,a,b,c,d,k,r,s),{j:1.}

records=[]
for name,m in SOURCE['meshes'].items():
    if name=='jukain_mesh_08': continue
    ob=bpy.data.objects.get(name)
    assert ob is not None and len(ob.data.vertices)==len(m['points']),name
    for v,p,w in zip(ob.data.vertices,np.array(m['points']),m['weights']):
        if name in ('jukain_mesh_14','jukain_mesh_17','jukain_mesh_18','jukain_mesh_19'):
            q,weights=tail(p)
        else:
            q=np.zeros(3); weights={}
            for b,share in w.items():
                pos,ww=mapped(p,b)
                q+=share*pos
                for j,x in ww.items(): weights[j]=weights.get(j,0)+share*x
        records.append([ob,v.index,p,q,weights])

# Exact source seam positions must stay identical across material boundaries.
weld={}
for rec in records: weld.setdefault(tuple(np.round(rec[2],5)),[]).append(rec)
for group in weld.values():
    pos=np.mean([r[3] for r in group],axis=0)
    weights={}
    for r in group:
        for j,w in r[4].items(): weights[j]=weights.get(j,0)+w/len(group)
    for r in group: r[3]=pos.copy(); r[4]=weights.copy()

# Recover split-eye source points through the raw head's affine deformation.
src=SOURCE['meshes']['jukain_mesh_01']; raw=RAW['meshes']['jukain_mesh_01']
ids=[i for i,w in enumerate(src['weights']) if w.get('Bone_86',0)>.999]
a=np.column_stack((np.array(src['points'])[ids],np.ones(len(ids))))
b=np.array(raw['points'])[ids]
aff=np.linalg.lstsq(a,b,rcond=None)[0]
assert np.max(np.abs(a@aff-b))<1e-4
for name in ('eyes_left','eyes_right'):
    ob=bpy.data.objects[name]
    for v in ob.data.vertices:
        p=(np.array(v.co)-aff[3])@np.linalg.inv(aff[:3])
        records.append([ob,v.index,p,head(p),{36:1.}])

for ob in {r[0] for r in records}: ob.vertex_groups.clear()
for ob,i,p,q,weights in records:
    if max(weights,key=weights.get) in (9,10,15,16): q[2]=max(q[2],.04)
    ob.data.vertices[i].co=q
    for j,w in weights.items():
        if w>1e-6:
            name=f'JOBJ_{j}'
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i],float(w),'REPLACE')
for ob in {r[0] for r in records}:
    if 'custom_normal' in ob.data.attributes: ob.data.attributes.remove(ob.data.attributes['custom_normal'])
    ob.data.update()

(H/'hand-changes.json').write_text(json.dumps({
    'raw_run':'saved Sceptile/Sheik base recipe',
    'script':'tools/hand_sceptile_sheik.py','head_scale':6.8,'tail_scale':6.2,
    'tail_tip_weights':{'JOBJ_4':.78,'JOBJ_17':.17,'JOBJ_18':.05},
    'arm_chains':[[60,61,64],[73,74,77]],'forearm_blades':['JOBJ_22','JOBJ_42'],
    'art_index':279,'notes':['No hair/braid chain in the 58 target joints.',
    'Vanilla Sheik special effects and kept prop preserved; no Zelda files touched.']
},indent=1),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(B/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
print('Saved Sceptile on Sheik with authored limb chains and restrained tail gradient.')
