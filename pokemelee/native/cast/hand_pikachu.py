"""Colosseum Pikachu fitted anatomically to Melee Pikachu; preserve rip topology and normals.

Surfboard PObjs 02..07 are a source-only prop. 15/16 are retained expression surfaces.
No generated shading or manual subdivision: round_out.py is the final geometry step.
"""

from cast_paths import WORK, TARGETS
import json
import ast
from pathlib import Path
import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image

ROOT = Path(str(WORK / 'hand/pikachu-Pikachu'))
BUILD = ROOT / '3-build'
D = json.loads((ROOT/'inspection.json').read_text(encoding='utf-8'))
S = D['source']['meshes']
SB = {n: np.array(b['head']) for n,b in D['source']['bones'].items()}
TB = {n: np.array(b['head']) for n,b in D['vanilla']['bones'].items()}
helper=ROOT.parents[1]/'tools/hand_view.py'
tree=ast.parse(helper.read_text(encoding='utf-8'));tree.body=tree.body[:-1]
ns={};exec(compile(tree,str(helper),'exec'),ns)
rest,pose,C=ns['rests']('Pikachu'),ns['frame']('Pikachu','Wait1-1'),ns['C']
MOVES={f'JOBJ_{j}':C@pose[j]@np.linalg.inv(rest[j])@np.linalg.inv(C) for j in rest}
REST_TB=TB.copy()
TB={f'JOBJ_{j}':(C@pose[j])[:3,3] for j in pose}

def rot(a,b):
    return np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())

def segment(a,b,c,d,width):
    a,b,c,d = np.array(a),np.array(b),np.array(c),np.array(d)
    axis=b-a; length=np.linalg.norm(axis); axis/=length
    r=rot(axis,(d-c)/np.linalg.norm(d-c))
    linear=r @ (width*np.eye(3)+(np.linalg.norm(d-c)/length-width)*np.outer(axis,axis))
    return linear,c-linear@a

def apply(p,t): return t[0]@p+t[1]
headlinear=MOVES['JOBJ_14'][:3,:3]@np.diag([31.7,29.,26.])
HEAD = (headlinear, TB['JOBJ_14']-headlinear@SB['Bone_19'])
yaw=np.arctan2(MOVES['JOBJ_4'][1,0],MOVES['JOBJ_4'][0,0])
rz=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1]])
BODY = (rz@np.diag([28.,28.,29.]),np.array([-.15,0,.12]))
transforms = {'Bone_01':BODY,'Bone_18':BODY,'Bone_19':HEAD}
jointmap = {'Bone_01':'JOBJ_4','Bone_18':'JOBJ_5','Bone_19':'JOBJ_14'}

for src, dst in [([32,33,35,37],[8,9,10,11]),([38,39,41,43],[24,25,26,27])]:
    a,b,c,end = [SB[f'Bone_{i:02d}'] if i not in (37,43) else SB['Bone_37_HandLeft' if i==37 else 'Bone_43_HandRight'] for i in src]
    ta,tb,tc,td = [TB[f'JOBJ_{i}'] for i in dst]
    for sn,tn,t in zip(src[:3],dst[:3],[segment(a,b,ta,tb,25),segment(b,c,tb,tc,23),segment(c,end,tc,td,23)]):
        transforms[f'Bone_{sn:02d}']=t; jointmap[f'Bone_{sn:02d}']=f'JOBJ_{tn}'

for src,dst in [([2,3,4,5],[32,33,35,36]),([9,10,11,12],[40,41,43,44])]:
    a,b,c,d = [SB[f'Bone_{i:02d}'] for i in src]
    ta,tb,tc,td = [TB[f'JOBJ_{i}'] for i in dst]
    foot = segment(c,d,tc,td,30)
    for sn,tn,t in zip(src,dst,[segment(a,b,ta,tb,28),segment(b,c,tb,tc,28),foot,foot]):
        transforms[f'Bone_{sn:02d}']=t; jointmap[f'Bone_{sn:02d}']=f'JOBJ_{tn}'
# The rendered thigh and lower leg use Melee's muscle-control branch.
jointmap.update(Bone_02='JOBJ_37',Bone_03='JOBJ_38',Bone_09='JOBJ_45',Bone_10='JOBJ_46')

# Both ear roots share the head transform. Orient their whole length to the
# vanilla silhouette, then sample the vanilla ear's own joint blend.
for s,ids,dst in [(1,[27,28],[17,18]),(-1,[29,30],[20,21])]:
    a=SB[f'Bone_{ids[0]:02d}']; tip=np.array([s*.177,.073,.446])
    c=apply(a,HEAD); d=TB[f'JOBJ_{dst[1]}']+(TB[f'JOBJ_{dst[1]}']-TB[f'JOBJ_{dst[0]}'])*2.05
    t=segment(a,tip,c,d,29)
    for sn,tn in zip(ids,dst): transforms[f'Bone_{sn:02d}']=t; jointmap[f'Bone_{sn:02d}']=f'JOBJ_{tn}'

# Vanilla's standing surface guides the body shape and ear weighting. The
# actual muscle/foot-control branch was read from its skin, not joint order.
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'vanilla.blend'))
def reference(names):
    pts=[]; faces=[]; weights=[]
    for name in names:
        ob=bpy.data.objects[name]; base=len(pts)
        gn={g.index:g.name for g in ob.vertex_groups}
        for v in ob.data.vertices:
            w={gn[g.group]:g.weight for g in v.groups if g.weight>0}
            p=np.r_[np.array(ob.matrix_world@v.co),1.]
            pts.append(sum(share*(MOVES[k]@p)[:3] for k,share in w.items())/sum(w.values()))
            weights.append(w)
        faces.extend([base+i for i in p.vertices] for p in ob.data.polygons)
    return np.array(pts),faces,weights,BVHTree.FromPolygons(pts,faces)
refs={'body':reference(['Joint_0_Object_0']), 'tail':reference(['Joint_0_Object_1']),
      'ears':reference(['Joint_0_Object_2','Joint_0_Object_11'])}

bpy.ops.wm.open_mainfile(filepath=str(WORK / "mons" / 'pikachu/1-load/models/1-025_Pikachu.blend'))
eye_source=bpy.data.objects['pikachu_mesh_25']
eye_uv={l.vertex_index:np.array(eye_source.data.uv_layers.active.data[l.index].uv) for l in eye_source.data.loops}
eye_pts=np.array(S['pikachu_mesh_25']['points'])

def nearby(p,ref):
    pts,faces,weights,tree=ref
    at,normal,fi,distance=tree.find_nearest(Vector(p))
    f=faces[fi]; tri=pts[f[:3]]
    bary=np.linalg.lstsq(np.vstack([tri.T,np.ones(3)]),np.r_[np.array(at),1.],rcond=None)[0]
    bary=np.clip(bary,0,1); bary/=bary.sum()
    w={}
    for i,share in zip(f[:3],bary):
        for k,v in weights[i].items():w[k]=w.get(k,0)+share*v
    w=dict(sorted(w.items(),key=lambda kv:-kv[1])[:4]); total=sum(w.values())
    return np.array(at),{k:float(v/total) for k,v in w.items() if v>1e-7}

bpy.ops.wm.open_mainfile(filepath=str(BUILD/'base.blend'))
def weight(ob,i,w):
    for g in ob.vertex_groups: g.remove([i])
    for n,v in w.items():
        if v>1e-7: (ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n)).add([i],float(v),'REPLACE')

# Recover split-eye positions through the known raw head transform, without
# touching their loop topology or stored normals.
src=np.concatenate([S[f'pikachu_mesh_{n}']['points'] for n in [15,16]])
raw=np.concatenate([D['raw']['meshes'][f'pikachu_mesh_{n}']['points'] for n in [15,16]])
raw_aff=np.linalg.lstsq(np.column_stack([src,np.ones(len(src))]),raw,rcond=None)[0]
for ob in list(bpy.data.objects):
    if ob.type!='MESH':continue
    if ob.name in [f'pikachu_mesh_{i:02d}' for i in [2,3,4,5,6,7]]:
        bpy.data.objects.remove(ob,do_unlink=True);continue
    if ob.name.startswith('eyes_'):
        for v in ob.data.vertices:
            p=np.linalg.solve(raw_aff[:3].T,np.array(v.co)-raw_aff[3])
            q=apply(p,HEAD)
            v.co=(np.linalg.inv(MOVES['JOBJ_14'])@np.r_[q,1])[:3];weight(ob,v.index,{'JOBJ_14':1})
            uv=eye_uv[int(np.argmin(np.linalg.norm(eye_pts-p,axis=1)))]
            mapped=((uv[0]*32+20)/58,1-((1-uv[1])*352+9)/46)
            for loop in ob.data.loops:
                if loop.vertex_index==v.index:ob.data.uv_layers.active.data[loop.index].uv=mapped
        continue
    data=S[ob.name]
    for v,p,w in zip(ob.data.vertices,np.array(data['points']),data['vw']):
        if ob.name=='pikachu_mesh_24':
            # Keep the source's bolt outline broad. The source lies in YZ,
            # vanilla in XZ; thickness travels along vanilla's plane normal.
            q=np.array([(p[1]-.124)*24.2, 3.976+(p[2]-.055)*4.2-p[0]*29, 2.507+(p[2]-.055)*29.2])
            nw={f'JOBJ_{int(k[-2:])+3}':share for k,share in w.items()}
        else:
            q=sum(apply(p,transforms[k])*share for k,share in w.items())/sum(w.values())
            head=w.get('Bone_19',0)
            if ob.name=='pikachu_mesh_23':
                _,nw=nearby(q,refs['ears'])
                if head>.99:nw={'JOBJ_14':1}
            elif head>.99:
                nw={'JOBJ_14':1}
            else:
                at,_=nearby(q,refs['body'])
                nw={}
                for k,share in w.items():nw[jointmap[k]]=nw.get(jointmap[k],0)+share
                total=sum(nw.values());nw={k:v/total for k,v in nw.items()}
                # Fit low body and limb rings to the actual vanilla surface;
                # retain the source head and facial geometry verbatim in shape.
                q=q+(at-q)*(.25*(1-head))
            # Geometry was fitted in a standing pose. Bring it into the target
            # bind pose using the exact inverse of its blended skin matrix.
            matrix=sum(MOVES[k]*share for k,share in nw.items())
            q=(np.linalg.inv(matrix)@np.r_[q,1])[:3]
        v.co=q;weight(ob,v.index,nw)
    if ob.name in ('pikachu_mesh_15','pikachu_mesh_16'):
        # These are actual head surfaces carrying optional sweat/anger tiles.
        # Their source +1 V transform clamps to blank yellow in the rest state.
        for uv in ob.data.uv_layers.active.data:uv.uv=(.5,.01)
        for mat in ob.data.materials:
            for node in mat.node_tree.nodes:
                if node.type=='MAPPING':node.inputs['Location'].default_value=(0,0,0)
    ob.data.update()

# Real atlas states, preserving the raw crop's UV rectangle with edge clamping.
atlas=np.array(Image.open(ROOT/'tex_3170.png').convert('RGBA'))
for state,row in {'open':0,'half':80,'closed':40}.items():
    xx=np.clip(np.arange(-20,38),0,31); yy=np.clip(np.arange(-9,37),0,39)+row
    Image.fromarray(atlas[yy[:,None],xx[None,:]]).save(BUILD/'eyes'/f'{state}.png')
old=bpy.data.images.get('eyes_open')
new=bpy.data.images.load(str(BUILD/'eyes/open.png'));new.pack()
for n in bpy.data.materials['eyes'].node_tree.nodes:
    if n.type=='TEX_IMAGE':n.image=new
if old:bpy.data.images.remove(old)
new.name='eyes_open'
record=json.loads((BUILD/'eyes.json').read_text(encoding='utf-8'))
record['made']={s:f'Colosseum pikachu tex_3170, actual atlas row {r}' for s,r in {'open':0,'half':80,'closed':40}.items()}
record['crop']=[-20,-9,58,46]
record.pop('drawn',None);record['notes']=['Real CLAMP atlas blink states; no synthesized eyelid.']
(BUILD/'eyes.json').write_text(json.dumps(record,indent=1),encoding='utf-8')
# round_out.cut locates new edge points by position. Split-UV duplicate edges
# otherwise hit the same KD-tree entry twice, moving one twin and leaving the
# other at its midpoint. Weld only geometrically identical vertices with the
# same skin weights. UVs and custom_normal remain per-corner bmesh data; no
# normals are removed/replaced and no faces or subdivisions are added here.
for ob in bpy.data.objects:
    if ob.type!='MESH':continue
    me=ob.data;bm=bmesh.new();bm.from_mesh(me);bm.verts.ensure_lookup_table()
    layer=bm.verts.layers.deform.active;seen={};merge={}
    for v in bm.verts:
        key=(tuple(round(c,5) for c in v.co),tuple(sorted((g,round(w,6)) for g,w in v[layer].items() if w>1e-7)))
        if key in seen:merge[v]=seen[key]
        else:seen[key]=v
    if merge:
        loops=len(me.loops);normals='custom_normal' in me.attributes
        bmesh.ops.weld_verts(bm,targetmap=merge);bm.to_mesh(me)
        assert len(me.loops)==loops and ('custom_normal' in me.attributes)==normals
        print('welded UV-seam duplicates',ob.name,len(merge))
    bm.free()
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'build.blend'))
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'edited.blend'))
print('Source topology retained; surfboard removed, expression surfaces blank at rest; vanilla anatomical placement and skinning.')
