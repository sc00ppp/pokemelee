"""Quilava on Fox, rebuilt from the source anatomy, then stand_feet/round_out.

The raw fit mistook the rump effect rig for the skull. Retain the source pear,
thick neck, broad low head and paws. A single scale covers head and body; Fox
supplies the limb joints and native eyelid drive, not the anatomy. The pear's
haunches stay on the hips; legs() adds short closed hind legs on Fox's chain.
No normal edits or subdivision: round_out owns that step.
"""

from cast_paths import WORK, TARGETS
import json
import sys
from collections import defaultdict
from pathlib import Path
import bpy
import bmesh
import numpy as np
from mathutils import Vector, Euler
from mathutils.bvhtree import BVHTree
from PIL import Image

R=Path(str(WORK / ''))
H=R/'hand/quilava-Fox'
B=H/'3-build'
SOURCE=R/'mons/quilava/1-load/models/1-156_Quilava.blend'
SCALE=18.0
ORIGIN=np.array([0.,-5.31,.9])

def read_source():
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    arm=next(o for o in bpy.data.objects if o.type=='ARMATURE')
    bones={int(b.name.split('_')[1]):np.array(arm.matrix_world@b.head_local) for b in arm.data.bones}
    objects={}
    for o in bpy.data.objects:
        if o.type!='MESH': continue
        groups={g.index:g.name for g in o.vertex_groups}
        objects[o.name]=dict(co=[list(o.matrix_world@v.co) for v in o.data.vertices],
            weights=[{int(groups[g.group].split('_')[1]):g.weight for g in v.groups if g.weight>0} for v in o.data.vertices],
            faces=[list(f.vertices) for f in o.data.polygons],
            uv=[list(v.uv) for v in o.data.uv_layers.active.data])
    im=bpy.data.images['tex_2D60']
    atlas=np.uint8(np.clip(np.array(im.pixels[:]).reshape(im.size[1],im.size[0],4)[::-1]*255,0,255))
    return bones,objects,atlas

def unit(v): return v/np.linalg.norm(v)
def rot(a,b): return np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())
def body(p): return np.asarray(p)*SCALE+ORIGIN

def trunk(p):
    z=body(p)[2]
    if z<9.5:
        t=float(np.clip((z-7.0)/2.5,0,1))
        return {4:1-t,22:t}
    t=float(np.clip((z-10.3)/1.7,0,1))
    return {22:1-t,41:t}

def map_point(p,b):
    if b in (5,7,29,30,32,50): return body(p),trunk(p)
    if 51<=b<=65: return body(p),{41:1}
    for shoulder,upper,elbow,wrist,ju,je,jw in [(42,43,44,46,25,26,27),(35,36,37,39,55,56,57)]:
        # The geometric elbow and wrist rings precede the source joint names.
        # Fit the rings themselves, so the lower arm cannot cross the upper arm.
        e=RINGS[upper]; w=RINGS[elbow]
        turn=rot(unit(w-e),unit(T[jw]-T[je]))
        if b==upper:
            return T[je]+turn@(p-e)*SCALE,{ju:.5,je:.5}
        if b==elbow:
            return T[jw]+turn@(p-w)*17.5,{je:.35,jw:.65}
        if b==wrist:
            return T[jw]+turn@(p-w)*SCALE,{jw:1}
    for hip,upper,heel,toe,jh,jk,ja in [(8,9,11,14,6,7,9),(18,19,21,24,12,13,15)]:
        if b==upper:
            # These points are the pear's haunch: its lower corner, not a leg.
            # Stretched from the hips to Fox's ankle they became kneeless tubes
            # in run and kicks and folded the belly open in crouch, so they stay
            # on the pear; legs() gives Quilava a leg on Fox's chain instead.
            return body(p),trunk(p)
        if b in (heel,toe):
            return T[ja]+(p-S[heel])*SCALE,{ja:1}
    if 66<=b<=73: return body(p),{4:1}
    raise ValueError((b,p))

def transform(p,row):
    q=np.zeros(3); w=defaultdict(float)
    for b,s in row.items():
        at,held=map_point(np.array(p),b); q+=at*s
        for j,v in held.items(): w[j]+=v*s
    return q,dict(w)

def rig(o,rows):
    o.vertex_groups.clear()
    for i,row in enumerate(rows):
        total=sum(row.values())
        for j,w in row.items():
            if w>1e-6:
                name=f'JOBJ_{j}'
                (o.vertex_groups.get(name) or o.vertex_groups.new(name=name)).add([i],float(w/total),'REPLACE')

def material(name,png):
    im=bpy.data.images.load(str(png)); im.name=name; im.pack()
    mat=bpy.data.materials.new(name); mat.use_nodes=True
    bs=mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Roughness'].default_value=.8
    tex=mat.node_tree.nodes.new('ShaderNodeTexImage'); tex.image=im; tex.extension='EXTEND'
    mat.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color'])
    return mat

def mesh(name,points,faces,uv,mat,rows):
    me=bpy.data.meshes.new(name); me.from_pydata([list(p) for p in points],[],faces); me.update()
    me.materials.append(mat); layer=me.uv_layers.new(name='UVMap')
    for loop in me.loops: layer.data[loop.index].uv=uv[loop.vertex_index]
    ob=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(ob)
    ob.modifiers.new('Armature','ARMATURE').object=bpy.data.objects['Armature']
    rig(ob,rows)
    return ob

def convex_hull(points):
    p=sorted(set(tuple(v) for v in points))
    def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[]; hi=[]
    for v in p:
        while len(lo)>1 and cross(lo[-2],lo[-1],v)<=0: lo.pop()
        lo.append(v)
    for v in p[::-1]:
        while len(hi)>1 and cross(hi[-2],hi[-1],v)<=0: hi.pop()
        hi.append(v)
    return np.array(lo[:-1]+hi[:-1],float)

def separate_arms():
    """Keep the original arm surfaces, with their roots tucked into the torso.

    The front-facing source sockets cannot swing outward as one welded chest
    patch without turning it inside out. Close those small openings with the
    same source rim and attach the original tubes at the sides of the chest.
    """
    data=src['magmarashi_mesh_02']; co=np.array(data['co']); uv=np.array(data['uv']).reshape(-1,3,2)
    bone=[max(w,key=w.get) for w in data['weights']]
    armfaces=[i for i,f in enumerate(data['faces']) if any(bone[v] in (36,37,43,44) for v in f)]
    points=[]; faces=[]; uvs=[]; rows=[]
    for i in armfaces:
        face=data['faces'][i]; sign=1 if co[face,0].mean()>0 else -1
        upper=43 if sign>0 else 36; je=26 if sign>0 else 56
        centre=ROOTS[upper].mean(0); at=np.array([sign*1.65,-.35,10.65])
        turn=rot(unit(RINGS[upper]-centre),unit(T[je]-at))
        start=len(points)
        for v,tex in zip(face,uv[i]):
            if bone[v]==32: q=at+turn@(co[v]-centre)*SCALE; held={22:1}
            else: q,held=map_point(co[v],bone[v])
            points.append(q); rows.append(held); uvs.append(tex)
        faces.append((start,start+1,start+2))
    ob=bpy.data.objects['magmarashi_mesh_02']
    arms=mesh('quilava_arms',points,faces,uvs,ob.data.materials[0],rows)
    # Reuse positions across source triangles; UVs remain per corner. Separate
    # per-triangle vertices would make a round tube appear as flat strips.
    welded=bmesh.new(); welded.from_mesh(arms.data)
    bmesh.ops.remove_doubles(welded,verts=list(welded.verts),dist=1e-5)
    welded.to_mesh(arms.data); welded.free(); arms.data.update()
    for face in arms.data.polygons: face.use_smooth=True
    bm=bmesh.new(); bm.from_mesh(ob.data); bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm,geom=[bm.faces[i] for i in armfaces],context='FACES_ONLY')
    layer=bm.loops.layers.uv.active; deform=bm.verts.layers.deform.verify()
    groups={g.name:g.index for g in ob.vertex_groups}
    for upper in (43,36):
        bm.verts.ensure_lookup_table()
        root=ROOTS[upper]; centre=root.mean(0)
        normal=unit(np.linalg.svd(root-centre)[2][-1]); normal*=1 if normal[1]<0 else -1
        axis=unit(root[0]-centre); across=np.cross(normal,axis)
        order=np.argsort(np.arctan2((root-centre)@across,(root-centre)@axis))
        verts=[]; tex=[]
        for p in root[order]:
            ids=np.where(np.linalg.norm(co-p,axis=1)<1e-4)[0]
            idx=next((j for j in ids if bm.verts[int(j)].link_faces),int(ids[0]))
            v=bm.verts[int(idx)]; verts.append(v)
            tex.append(np.mean([list(l[layer].uv) for l in v.link_loops],axis=0))
        c=bm.verts.new(body(centre)); held=trunk(centre)
        for j,w in held.items():
            if w>1e-6:
                name=f'JOBJ_{j}'
                if name not in groups: groups[name]=ob.vertex_groups.new(name=name).index
                c[deform][groups[name]]=w
        middle=np.mean(tex,axis=0)
        for k in range(len(verts)):
            nxt=(k+1)%len(verts)
            f=bm.faces.new((verts[k],verts[nxt],c))
            f.smooth=True
            for l,t in zip(f.loops,(tex[k],tex[nxt],middle)): l[layer].uv=t
    bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS')
    bm.to_mesh(ob.data); bm.free(); ob.data.update()

def clip(poly,hull):
    # Each point carries UV pixel coordinates and the source surface position.
    for a,b in zip(hull,np.roll(hull,-1,axis=0)):
        out=[]
        def distance(v):
            d,e=b-a,v[:2]-a
            return d[0]*e[1]-d[1]*e[0]
        for p,q in zip(poly,poly[1:]+poly[:1]):
            dp,dq=distance(p),distance(q)
            if dp>=-1e-8: out.append(p)
            if (dp>=0)!=(dq>=0): out.append(p+(q-p)*(dp/(dp-dq)))
        poly=out
        if not poly: break
    return poly

def lids(src,atlas):
    eyes=B/'eyes'; eyes.mkdir(exist_ok=True)
    for state,k in [('open',0),('half',1),('closed',3)]: Image.fromarray(atlas[k*64:(k+1)*64]).save(eyes/f'{state}.png')
    mat=material('quilava_closed_lid',eyes/'closed.png')
    eye=src['magmarashi_mesh_00']; p=np.array(eye['co']); uv=np.array(eye['uv']).reshape(-1,3,2)
    hull=convex_hull([(9,26),(10,17),(17,9),(28,3),(43,3),(47,13),(45,28),(35,31),(18,31)])
    (H/'reference/lid-outline.json').write_text(json.dumps(hull.tolist()),encoding='utf-8')
    ns={}; exec(compile((R/'tools/hand_view.py').read_text(encoding='utf-8').rsplit('\nmain()',1)[0],'hand_view.py','exec'),ns)
    rests=ns['rests']('Fox'); cg=ns['C'][:3,:3]
    locals_=json.loads((H/'reference/fox-rest-local.json').read_text(encoding='utf-8-sig'))
    rounded=json.loads((H/'reference/rounded-eye-surface.json').read_text(encoding='utf-8'))
    eye_surface=BVHTree.FromPolygons(rounded['points'],rounded['faces'])
    for sign,joint,parent,rx in [(1,45,42,.6981201),(-1,49,46,-.6981201)]:
        points=[]; faces=[]; uvs=[]
        for f,coords in zip(eye['faces'],uv):
            if np.mean(p[f,0])*sign<0: continue
            pix=coords*[64,-256]+[0,256]
            poly=clip([np.r_[u,v] for u,v in zip(pix,p[f])],hull)
            if len(poly)<3: continue
            start=len(points)
            for v in poly:
                # Position the lid on round_out's curved face, not on the flat
                # source triangle underneath it. This is surface placement;
                # shading and subdivision remain exclusively round_out's.
                at,normal,_,_=eye_surface.find_nearest(Vector(body(v[2:])))
                points.append(np.array(at+normal*.095))
                uvs.append((v[0]/64,1-v[1]/64))
            for i in range(1,len(poly)-1): faces.append((start,start+i,start+i+1))
        angles=list(locals_[joint]['rotation']); resting=np.array(Euler(angles,'XYZ').to_matrix())
        angles[0]=rx; closure=np.array(Euler(angles,'XYZ').to_matrix())
        axes=cg@rests[parent][:3,:3]; turn=axes@closure@resting.T@axes.T; pivot=cg@rests[joint][:3,3]
        share=1.0
        bind=np.linalg.inv(turn*share+np.eye(3)*(1-share))
        points=[pivot+bind@(p-pivot) for p in points]
        mesh(f'quilava_lid_{joint}',points,faces,uvs,mat,[{joint:share,41:1-share}]*len(points))
    (B/'eyes.json').write_text(json.dumps(dict(
        objects=[dict(name='magmarashi_mesh_00',side='both'),dict(name='quilava_lid_45',side='left'),dict(name='quilava_lid_49',side='right')],
        source='hand_quilava.py', frames={s:f'eyes/{s}.png' for s in ('open','half','closed')},
        notes=['Native skeletal blink on Fox joints 45/49; Wait1 drive states 1,0,1,2.',
               'Source mesh_00 is the flush face surface; lids are clipped to the eye silhouette.',
               'PKX eye material has one CLAMP layer; source atlas stride 64, closed band 3.']
    ),indent=2),encoding='utf-8')

def flames():
    # A small opaque texture with a yellow heart and orange/red tips and edges.
    yy,xx=np.mgrid[0:128,0:64]; t=1-yy/127.; edge=abs(xx/63.*2-1)
    hot=np.clip((.78-t)*2.5,0,1)*np.clip((1-edge)*1.8,0,1)
    orange=np.array([245,77,20]); yellow=np.array([255,228,62])
    rgb=orange+(yellow-orange)*hot[:,:,None]
    texture=np.dstack([rgb,np.full((128,64),255)]).astype(np.uint8)
    path=B/'quilava-flame.png'; Image.fromarray(texture).save(path)
    mat=material('quilava_flame',path)
    # Tongues rise from the head vent ridge and the broad rear vent region.
    specs=[
        ('crown',41,[(0,.105,.807,.026,.023,-.01,.03,.17),(-.032,.14,.82,.028,.035,-.025,.025,.22),
                     (.035,.16,.827,.029,.032,.025,.03,.18),(0,.20,.835,.035,.04,0,.035,.26),
                     (-.04,.235,.826,.025,.028,-.025,.04,.16),(.035,.25,.82,.026,.028,.025,.055,.20)]),
        ('rump',4,[(-.09,.393,.18,.035,.026,-.045,.15,.16),(.09,.393,.18,.035,.026,.045,.15,.16),
                    (-.045,.416,.18,.04,.027,-.035,.20,.22),(.045,.416,.18,.04,.027,.035,.19,.24),
                    (0,.424,.19,.045,.03,0,.16,.29)])]
    for name,joint,tongues in specs:
        points=[]; faces=[]; uv=[]
        for index,(x,y,z,rx,ry,dx,dy,dz) in enumerate(tongues):
            if name=='crown':
                dz*=.78; dx+=(-1 if index%2 else 1)*.025; dy+=.04
            start=len(points)
            # Uneven, bent tongues: a broad hot root and narrow orange lick.
            for t,wide in [(0,1),(.43,.76),(.74,.34)]:
                for u,(ax,ay) in enumerate([(-1,0),(0,-1),(1,0),(0,1)]):
                    bend=(1 if index%2 else -1)*.018*np.sin(t*np.pi)
                    points.append(body([x+dx*t+ax*rx*wide+bend,y+dy*t+ay*ry*wide,z+dz*t]))
                    uv.append(([0,.5,1,.5][u],t))
            points.append(body([x+dx,y+dy,z+dz])); uv.append((.5,1))
            for j in range(4):
                k=(j+1)%4
                for ring in (0,4):
                    a=start+ring
                    faces.extend([(a+j,a+k,a+4+k),(a+j,a+4+k,a+4+j)])
                faces.append((start+8+j,start+8+k,start+12))
            faces.extend([(start,start+2,start+1),(start,start+3,start+2)])
        mesh('quilava_flame_'+name,points,faces,uv,mat,[{joint:1}]*len(points))


# The legs share the pear's skin material, so the export cuts them into PObjs
# with it. At 8, 10 and 14 sides that cut left a small neck PObj which
# anime_cast's inside-out vote (winding judged in mixed stored spaces) turned
# inside out: black patches on the AniMelee neck. At 12 no PObj is turned.
LEG_SIDES=12
# Ring radii along the leg, in Fox units: Quilava's short, thick hind leg. The
# pear is about 6.9 wide; Fox's chain only says where the hip, knee and ankle are.
THIGH,KNEE,SHIN,ANKLE=1.45,1.15,1.0,.85
TOP=1.0     # the thigh's capped top, at Fox's hip joint, stays inside the pear as the thigh swings
BACK=.9     # the tube runs this far behind Fox's knee
# Fox stands side-on: at idle his back (right) foot points about 69 degrees
# outward, so the paw on it was seen end-on beside a full-length front paw.
# Quilava stands with both paws forward, so the right paw is turned by that
# angle about its heel in Fox's idle frame; other poses keep the same turn.
PAW_TURN={'right':1.0}

def loft(rings,sides=LEG_SIDES):
    """A closed tube through (centre, radius, weights) rings, capped at both ends."""
    pts=[];rows=[];faces=[];u=None
    centres=[np.array(c,float) for c,_,_ in rings]
    for i,(c,r,row) in enumerate(rings):
        axis=unit(centres[min(i+1,len(rings)-1)]-centres[max(i-1,0)])
        u=np.array([1.,0,0]) if u is None else u
        u=unit(u-(u@axis)*axis); v=np.cross(axis,u)
        for k in range(sides):
            a=2*np.pi*k/sides
            pts.append(centres[i]+(u*np.cos(a)+v*np.sin(a))*r); rows.append(row)
    for r in range(len(rings)-1):
        for k in range(sides):
            a=r*sides+k; b=r*sides+(k+1)%sides
            faces.extend([(a,b,b+sides),(a,b+sides,a+sides)])
    for r,flip in ((0,True),(len(rings)-1,False)):
        centre=len(pts); pts.append(centres[r]); rows.append(rings[r][2])
        for k in range(sides):
            f=(r*sides+k,r*sides+(k+1)%sides,centre)
            faces.append(f[::-1] if flip else f)
    return pts,rows,faces

def legs():
    """Quilava's hind legs: closed tubes on Fox's leg chain, run after stand_feet.

    The source has no leg to stretch: each haunch is the pear's lower corner
    and the paw sits under it. So the pear stays whole on the hips, the paw stays
    the source paw on the ankle where stand_feet placed it, and a short tapered
    leg rides Fox's thigh, knee and ankle with blended knee weights. Its top is
    inside the pear and its foot end inside the paw's heel, so standing shows
    the source silhouette with a stub of leg, and motion shows a thick leg that
    bends at a knee. Rest space: Fox's rest legs hang straight down.
    """
    if bpy.context.scene.get('quilava_legs'): return
    ns={}; exec(compile((R/'tools/hand_view.py').read_text(encoding='utf-8').rsplit('\nmain()',1)[0],'hand_view.py','exec'),ns)
    rest=ns['rests']('Fox'); cg=ns['C']
    def at(j): return (cg@rest[j])[:3,3]
    idle={j:cg@m@np.linalg.inv(rest[j])@np.linalg.inv(cg) for j,m in ns['frame']('Fox','Wait1-1').items() if j in rest}
    pear=bpy.data.objects['magmarashi_mesh_02']; skin=pear.data.materials[0]
    # One cream texel of the pear's own texture: the haunch's corner nearest
    # the belly colour, so the leg reads as the haunch carried down.
    im=next(n.image for n in skin.node_tree.nodes if n.type=='TEX_IMAGE')
    px=np.array(im.pixels[:]).reshape(im.size[1],im.size[0],4)
    def texel(uv):
        x=int(np.clip(uv[0],0,1)*(im.size[0]-1)); y=int(np.clip(uv[1],0,1)*(im.size[1]-1))
        return px[max(y-1,0):y+2,max(x-1,0):x+2,:3].reshape(-1,3)
    cream=np.array([246,217,120])/255.
    source=json.loads((H/'source-geometry.json').read_text(encoding='utf-8'))['objects'][pear.name]
    src_id=np.empty(len(pear.data.vertices),int); pear.data.attributes['quilava_source_index'].data.foreach_get('value',src_id)
    haunch={i for i,w in enumerate(source['weights']) if {int(b) for b in w}&{9,19}}
    choices=[tuple(l.uv) for poly in pear.data.polygons for li in poly.loop_indices
             for l in [pear.data.uv_layers.active.data[li]] if src_id[pear.data.loops[li].vertex_index] in haunch]
    skin_uv=min(choices,key=lambda uv:float(np.abs(texel(uv)-cream).sum(1).max()))
    made=[]
    for side,(jh,jk,ja,toe) in (('left',(6,7,9,10)),('right',(12,13,15,16))):
        paw=[]
        for ob in bpy.data.objects:
            if ob.type!='MESH': continue
            names={g.index:g.name for g in ob.vertex_groups}
            for v in ob.data.vertices:
                held={int(names[g.group][5:]):g.weight for g in v.groups if g.weight>1e-6}
                if sum(w for j,w in held.items() if j in (ja,toe))>=.5*sum(held.values()): paw.append(np.array(v.co))
        paw=np.array(paw)
        ahead=at(toe)-at(ja); ahead[2]=0; ahead=unit(ahead)
        along=paw@ahead; heel=paw[along<=along.min()+.4*np.ptp(along)]
        top=heel[:,2].max(); width=np.ptp(heel@np.cross([0,0,1.],ahead))
        foot=np.r_[heel[:,:2].mean(0),top-.35]
        if PAW_TURN.get(side):
            m=idle[ja][:3,:3]; d=m@(at(toe)-at(ja))
            turn=-np.arctan2(d[0],-d[1])*PAW_TURN[side]
            rz=np.array([[np.cos(turn),-np.sin(turn),0],[np.sin(turn),np.cos(turn),0],[0,0,1]])
            rb=np.linalg.inv(m)@rz@m
            for ob in bpy.data.objects:
                if ob.type!='MESH' or ob.name.startswith('quilava_leg'): continue
                names={g.index:g.name for g in ob.vertex_groups}
                for v in ob.data.vertices:
                    held={int(names[g.group][5:]):g.weight for g in v.groups if g.weight>1e-6}
                    if sum(w for j,w in held.items() if j in (ja,toe))>=.5*sum(held.values()):
                        v.co=Vector(foot+rb@(np.array(v.co)-foot))
                ob.data.update()
            print('Paw',side,'turned',round(float(np.degrees(turn)),1))
        # The tube runs behind Fox's knee, as a leg's flesh lies behind its
        # kneecap, so Fox's idle knee bend stays inside the belly.
        hip,knee=at(jh),at(jk)+[0,BACK,0]
        line=[(hip,TOP,{jh:1}),(hip*.55+knee*.45,THIGH,{jh:1}),(hip*.18+knee*.82,(THIGH+KNEE)/2,{jh:.8,jk:.2}),
              (knee,KNEE,{jh:.5,jk:.5}),(knee*.75+foot*.25,(KNEE+SHIN)/2,{jh:.15,jk:.85}),
              (knee*.4+foot*.6,SHIN,{jk:1}),(knee*.15+foot*.85,(SHIN+ANKLE)/2,{jk:.5,ja:.5}),
              (foot,min(ANKLE,width*.45),{ja:1})]
        pts,rows,faces=loft(line)
        ob=mesh(f'quilava_leg_{side}',pts,faces,[skin_uv]*len(pts),skin,rows)
        ob.data.polygons.foreach_set('use_smooth',[True]*len(ob.data.polygons)); ob.data.update()
        made.append(dict(side=side,joints=[jh,jk,ja],rings=len(line),paw_points=len(paw),
                         paw_top=round(float(top),3),paw_heel_width=round(float(width),3)))
    bpy.context.scene['quilava_legs']=True
    (H/'legs.json').write_text(json.dumps(dict(skin_uv=skin_uv,legs=made),indent=2),encoding='utf-8')
    print('Legs:',json.dumps(made))


# Run after stand_feet, before round_out. Existing sole clearance is retained;
# the legs are built after it, so the paws' placement is unchanged.
if '--sole-clearance' in sys.argv:
    bpy.ops.wm.open_mainfile(filepath=str(B/'edited.blend'))
    if not bpy.context.scene.get('quilava_sole_clearance'):
        for ob in bpy.data.objects:
            if ob.type!='MESH': continue
            groups={g.index:g.name for g in ob.vertex_groups}
            for v in ob.data.vertices:
                share=sum(g.weight for g in v.groups if groups[g.group] in ('JOBJ_9','JOBJ_10','JOBJ_15','JOBJ_16'))
                v.co.z+=.15*share
            ob.data.update()
        bpy.context.scene['quilava_sole_clearance']=.15
    legs()
    bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
    sys.exit(0)

S,src,atlas=read_source()
(H/'source-geometry.json').write_text(json.dumps({'objects':src}),encoding='utf-8')
RINGS={}
for bone in (43,44,36,37):
    pts=[p for data in src.values() for p,w in zip(data['co'],data['weights']) if w.get(bone,0)>.99]
    RINGS[bone]=np.unique(np.round(pts,5),axis=0).mean(0)
ROOTS={}
data=src['magmarashi_mesh_02']
for bone in (43,36):
    ids={i for f in data['faces'] if any(data['weights'][j].get(bone,0)>.99 for j in f)
           for i in f if data['weights'][i].get(32,0)>.99}
    ROOTS[bone]=np.unique(np.round([data['co'][i] for i in ids],5),axis=0)
bpy.ops.wm.open_mainfile(filepath=str(B/'base.blend'))
arm=bpy.data.objects['Armature']; T={int(b.name[5:]):np.array(arm.matrix_world@b.head_local) for b in arm.data.bones}
shared=defaultdict(list)
for name,data in src.items():
    if name in ('magmarashi_mesh_07','magmarashi_mesh_08'): continue
    for p,w in zip(data['co'],data['weights']): shared[tuple(np.round(p,5))].append(transform(p,w))
joined={}
for key,entries in shared.items():
    w=defaultdict(float)
    for _,row in entries:
        for j,v in row.items(): w[j]+=v/len(entries)
    joined[key]=np.mean([p for p,_ in entries],axis=0),dict(w)
for name,data in src.items():
    ob=bpy.data.objects[name]
    if name in ('magmarashi_mesh_07','magmarashi_mesh_08'):
        bpy.data.objects.remove(ob,do_unlink=True); continue
    points,rows=zip(*(joined[tuple(np.round(p,5))] for p in data['co']))
    ob.data.vertices.foreach_set('co',np.array(points).ravel()); ob.data.update(); rig(ob,rows)
    source_index=ob.data.attributes.new('quilava_source_index','INT','POINT')
    source_index.data.foreach_set('value',list(range(len(ob.data.vertices))))
    for mat in ob.data.materials:
        for node in mat.node_tree.nodes:
            if node.type=='TEX_IMAGE': node.extension='EXTEND'
separate_arms()
if '--prepare-eye-surface' not in sys.argv:
    lids(src,atlas)
flames()
(B/'loose.json').write_text(json.dumps({'attribute':'rigswap_loose','chains':[]}),encoding='utf-8')
for ob in bpy.data.objects:
    if ob.type=='MESH' and 'rigswap_loose' in ob.data.attributes: ob.data.attributes.remove(ob.data.attributes['rigswap_loose'])
bpy.ops.wm.save_as_mainfile(filepath=str(B/'edited.blend'))
print('Quilava: uniform source scale',SCALE,'native Fox eyelids, opaque head and hip flames.')
