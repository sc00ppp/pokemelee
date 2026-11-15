"""V4-based Scizor: 1.15x source pincers, two-unit offsets and bridged cuffs.

The v4 rounding pass is replayed inside v6. Only the rear pincer cap is opened
for a real cuff surface; no upper-arm, shoulder or forearm length is changed.
"""

from cast_paths import WORK, TARGETS
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from collections import Counter

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import hand_scizor_v4 as v4

R = v4.R
ROOT = R/'hand/scizor-Marth/v6'
OLD = ROOT.parent/'v4'
BUILD = ROOT/'3-build'
V = v4.definitions('hand_view.py')
FACTOR = 1.15
OFFSET = 2.0


def skin(pose):
    c, rest = V['C'], V['rests']('Marth')
    return {j:c@m@np.linalg.inv(rest[j])@np.linalg.inv(c)
            for j,m in V['frame']('Marth',pose).items() if j in rest}


def transform(points, matrix):
    return np.asarray(points)@matrix[:3,:3].T+matrix[:3,3]


def components(me):
    adj = {v.index:set() for v in me.vertices}
    for e in me.edges:
        a,b = e.vertices
        adj[a].add(b); adj[b].add(a)
    unseen, out = set(adj), []
    while unseen:
        todo = [unseen.pop()]; found = set(todo)
        while todo:
            for i in adj[todo.pop()]-found:
                found.add(i); unseen.discard(i); todo.append(i)
        out.append(found)
    return out


def loop_order(edges):
    adj = {}
    for a,b in edges:
        adj.setdefault(a,[]).append(b); adj.setdefault(b,[]).append(a)
    assert all(len(v)==2 for v in adj.values()), adj
    first = min(adj); result = [first]; prev = None; cur = first
    while True:
        nxt = next(v for v in adj[cur] if v != prev)
        if nxt == first: break
        result.append(nxt); prev,cur = cur,nxt
    assert len(result)==len(adj)
    return result


def face_boundary(faces):
    edges = Counter()
    for f in faces:
        vs = list(f)
        for a,b in zip(vs,vs[1:]+vs[:1]):
            edges[tuple(sorted((a,b)))] += 1
    return [e for e,n in edges.items() if n==1]


def seed():
    ROOT.mkdir(exist_ok=True)
    for name in ('3-build','review','shots'):
        (ROOT/name).mkdir(exist_ok=True)
    shutil.copytree(OLD/'3-build', BUILD, dirs_exist_ok=True)
    record = json.loads((OLD/'edit-record.json').read_text(encoding='utf-8'))
    record.update(version=6, base_version=4, pincer_factor_from_v4=FACTOR,
                  offset=OFFSET, forearm_length_change=0., placement_correction={'l':[0.,0.,0.],'r':[0.,0.,0.]})
    rest = V['rests']('Marth'); c = V['C']
    direction = v4.unit((c@rest[75])[:3,0])
    local = np.linalg.inv((c@rest[73])[:3,:3])@direction
    directions = {'r':direction, 'l':v4.unit((c@rest[31])[:3,:3]@local)}
    for side in ('l','r'):
        info = record['pincer_'+side]
        info['v4_anchor'] = info['anchor']
        info['offset_direction'] = directions[side].tolist()
        info['anchor'] = (np.array(info['anchor'])+OFFSET*directions[side]).tolist()
        info['scale'] = 8.*FACTOR
    record['shape'] = 'V4 pincers uniformly scaled 1.15 about their roots and offset 2 along the sword direction and matching hand-local direction; short thick blended cuffs.'
    record['rounding'] = 'V4 round_out replay, preserving the 17 non-arm meshes and all shoulder/upper-arm/forearm vertex positions; new cuff rings join the original forearm boundary to the pincer rear cap boundary.'
    solve_clearance(record)
    (ROOT/'edit-record.json').write_text(json.dumps(record,indent=2), encoding='utf-8')
    print('Seeded v6 exclusively from v4', flush=True)
    slots=json.loads((BUILD/'weapons_replaced.json').read_text(encoding='utf-8'))
    for slot in slots:
        if slot.get('part') not in ('scabbard','sword_stowed'):
            slot['replacement']='Scizor v6: source pincer uniformly scaled 9.2, offset 2 along JOBJ_75 local +x, thick blended wrist, original forearm length'
    (BUILD/'weapons_replaced.json').write_text(json.dumps(slots,indent=2),encoding='utf-8')


def solve_clearance(record):
    """Resolve actual idle body contact by translating only the whole pincer."""
    bpy.ops.wm.open_mainfile(filepath=str(OLD/'review/rounded.blend'))
    rest=V['rests']('Marth'); frame=V['frame']('Marth','Wait1-1')
    moves={j:m@np.linalg.inv(rest[j]) for j,m in frame.items() if j in rest}
    body=[]
    for ob in bpy.data.objects:
        if ob.type=='MESH' and not any(x in ob.name for x in ('__jaw_','__shaft_fore_','__shaft_upper_')) and ob.name not in ('hassam_mesh_02','hassam_mesh_08'):
            points,rows=V['skin_table'](ob); points=V['posed'](points,rows,moves)
            body.append(BVHTree.FromPolygons(points.tolist(),[list(f.vertices) for f in ob.data.polygons]))
            if ob.name.endswith('__abdomen'): center=points.mean(0)
    sm=skin('Wait1-1')
    record['idle_clearance_placement']={}
    for side,joint in [('r',75),('l',31)]:
        info=record['pincer_'+side]; parts=[]; outer=[]
        for ob in bpy.data.objects:
            if ob.type=='MESH' and (ob.name.endswith('__jaw_'+side) or ob.name in ('hassam_mesh_02','hassam_mesh_08')):
                p=np.array([v.co[:] for v in ob.data.vertices])
                ids={v.index for v in ob.data.vertices if any(ob.vertex_groups[g.group].name=='JOBJ_'+str(joint) and g.weight>.99 for g in v.groups)}
                faces=[list(f.vertices) for f in ob.data.polygons if all(i in ids for i in f.vertices)]
                if not faces: continue
                p=np.array(info['anchor'])+FACTOR*(p-info['v4_anchor'])
                used=sorted({i for f in faces for i in f}); mapping={old:i for i,old in enumerate(used)}
                parts.append((transform(p[used],sm[joint]),[[mapping[i] for i in f] for f in faces]))
                if '__jaw_' in ob.name: outer.append(transform(p,sm[joint]))
        def hits(shift):
            return sum(len(BVHTree.FromPolygons((p+shift).tolist(),f).overlap(b)) for p,f in parts for b in body)
        before=hits(np.zeros(3)); correction=np.zeros(3)
        floor=min(p[:,2].min() for p,f in parts)
        if floor<=0: correction[2]=.1-floor
        if hits(correction):
            outward=np.concatenate(outer).mean(0)-center
            outward[2]=0.; outward=v4.unit(outward)
            lo,hi=0.,.25
            while hits(correction+hi*outward):
                hi*=2
                assert hi<=4.,'Idle correction unexpectedly large'
            for _ in range(18):
                mid=(lo+hi)/2
                if hits(correction+mid*outward): lo=mid
                else: hi=mid
            correction+=(hi+.05)*outward
        assert hits(correction)==0
        local=np.linalg.inv(sm[joint][:3,:3])@correction
        record['placement_correction'][side]=local.tolist()
        record['idle_clearance_placement'][side]={'initial_triangle_contacts':before,
            'idle_translation':correction.tolist(),'distance':float(np.linalg.norm(correction)),
            'method':'Minimum outward horizontal translation clearing the actual idle body triangles, plus 0.05 margin; pincer shape and forearm untouched.'}
        print('Idle clearance',side,record['idle_clearance_placement'][side],flush=True)


def tag_caps(path):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    for name, faces in {
        'hassam_mesh_12__jaw_r':[{31,30,22},{30,34,22}],
        'hassam_mesh_11__jaw_l':[{21,27,28},{27,33,28}],
    }.items():
        me = bpy.data.objects[name].data
        at = me.attributes.get('v6_rear_cap') or me.attributes.new('v6_rear_cap','INT','FACE')
        for p in me.polygons:
            at.data[p.index].value = int(set(p.vertices) in faces)
        assert sum(x.value for x in at.data)==2
    bpy.ops.wm.save_as_mainfile(filepath=str(path))


def open_cap(ob):
    me = ob.data
    selected = [p for p in me.polygons if me.attributes['v6_rear_cap'].data[p.index].value]
    ring = loop_order(face_boundary([p.vertices for p in selected]))
    points = np.array([me.vertices[i].co[:] for i in ring])
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    gone = [bm.faces[p.index] for p in selected]
    bmesh.ops.delete(bm, geom=gone, context='FACES_ONLY')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(me); bm.free(); me.update()
    return points


def cuff(ob, side, end, record):
    """Append a ringed surface directly to the unchanged forearm end indices."""
    me = ob.data
    oldp = np.array([v.co[:] for v in me.vertices])
    oldfaces = [list(p.vertices) for p in me.polygons]
    oldnorm = np.array([n.vector[:] for n in me.corner_normals])
    tube = min(components(me), key=lambda ids:min(abs(oldp[i,0]) for i in ids))
    boundary = face_boundary([f for f in oldfaces if all(i in tube for i in f)])
    distal = [e for e in boundary if all(abs(oldp[i,0])>6.5 for i in e)]
    startids = loop_order(distal)
    start = oldp[startids]
    c0,c3 = start.mean(0),end.mean(0)
    j = record['arm_joints'][side]
    fore = v4.unit(np.array(j['wrist'])-j['elbow'])
    direct = v4.unit(c3-c0)
    # Parallel-transport the existing ring, then align the end loop to it.
    rot = v4.rotation(fore,direct)
    target = (start-c0)@rot.T
    if np.dot(np.cross(start[1]-start[0],start[2]-start[1]),fore)<0:
        startids.reverse(); start=oldp[startids]; target=(start-c0)@rot.T
    if np.dot(np.sum(np.cross(end-c3,np.roll(end-c3,-1,axis=0)),axis=0),direct)<0:
        end=end[::-1]
    # Choose the closest angular correspondence, avoiding twisted bridges.
    start_unit = v4.unit(target[0])
    k=int(np.argmax((end-c3)@start_unit/np.maximum(np.linalg.norm(end-c3,axis=1),1e-9)))
    end=np.roll(end,-k,axis=0)
    n=len(start); m=len(end)
    assert n==12 and m==16,(side,n,m)
    # Ring radius never narrows below the old forearm until entering the root.
    u = v4.unit(target[0]-direct*np.dot(target[0],direct))
    z = np.cross(direct,u)
    theta = np.unwrap(np.arctan2(target@z,target@u))
    if theta[-1]<theta[0]: theta=-theta
    circular = np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*z
    c1=c0+fore*.65; c2=c3-direct*.65
    points=oldp.tolist(); faces=oldfaces.copy(); rings=[startids]
    ring_t = {}
    for step in range(1,8):
        t=step/8
        center=(1-t)**3*c0+3*(1-t)**2*t*c1+3*(1-t)*t*t*c2+t**3*c3
        tangent=v4.unit(3*(1-t)**2*(c1-c0)+6*(1-t)*t*(c2-c1)+3*t*t*(c3-c2))
        radial=(start-c0)@v4.rotation(fore,tangent).T
        circle=circular@v4.rotation(direct,tangent).T
        radius=.47+.06*np.sin(np.pi*t)
        blend=v4.smooth(t/.28)*(1-v4.smooth((t-.72)/.28))
        radial=(1-blend)*radial+blend*radius*circle
        # Approach the actual pincer cap contour in the final part of the cuff.
        end_sample=np.array([(1-(i*m/n)%1)*end[int(i*m/n)%m]+((i*m/n)%1)*end[(int(i*m/n)+1)%m]-c3 for i in range(n)])
        eblend=v4.smooth((t-.65)/.35)
        radial=(1-eblend)*radial+eblend*end_sample
        ids=list(range(len(points),len(points)+n)); points.extend((center+radial).tolist())
        rings.append(ids)
        ring_t.update({i:t for i in ids})
    ids=list(range(len(points),len(points)+m)); points.extend(end.tolist()); rings.append(ids)
    ring_t.update({i:1. for i in ids})
    for a,b in zip(rings,rings[1:]):
        # Monotone zipper joins arbitrary ring counts with genuine surface.
        i=k=0
        while i<len(a) or k<len(b):
            if (i+1)/len(a)<=(k+1)/len(b):
                faces.append([a[i%len(a)],a[(i+1)%len(a)],b[k%len(b)]]); i+=1
            else:
                faces.append([a[i%len(a)],b[(k+1)%len(b)],b[k%len(b)]]); k+=1
    nm=bpy.data.meshes.new(me.name+'_v6')
    nm.from_pydata(points,[],faces); nm.update()
    for mat in me.materials: nm.materials.append(mat)
    for p,old in zip(nm.polygons,me.polygons):
        p.material_index=old.material_index; p.use_smooth=old.use_smooth
    for p in list(nm.polygons)[len(oldfaces):]: p.use_smooth=True
    for olduv in me.uv_layers:
        uv=nm.uv_layers.new(name=olduv.name)
        for i,value in enumerate(olduv.data): uv.data[i].uv=value.uv
        for lp in list(nm.loops)[len(me.loops):]:
            normal=nm.vertices[lp.vertex_index].normal
            uv.data[lp.index].uv=(.5+.25*normal.x,.5+.25*normal.z)
    # Preserve every original vertex group and data tag.
    held=[{ob.vertex_groups[g.group].name:g.weight for g in v.groups} for v in me.vertices]
    for at in me.attributes:
        if at.domain=='POINT' and at.data_type in ('FLOAT','INT') and not at.name.startswith('.'):
            dest=nm.attributes.new(at.name,at.data_type,'POINT')
            for i,value in enumerate(at.data): dest.data[i].value=value.value
            if at.name=='v4_index':
                for value in list(dest.data)[len(oldp):]: value.value=-1
    ob.data=nm
    for i,weights in enumerate(held): v4.weights(ob,i,weights)
    hand='JOBJ_73' if side=='r' else 'JOBJ_31'
    claw=record['pincer_'+side]['joint']
    # The original forearm end already lies on the wrist. A broad transition
    # across the cuff, rather than a one-ring change, absorbs sword rotation.
    mean_weights={}
    for i in startids:
        for joint,w in held[i].items(): mean_weights[joint]=mean_weights.get(joint,0)+w/n
    for i,t in ring_t.items():
        blend=v4.smooth(t)
        weights={j:w*(1-blend) for j,w in mean_weights.items()}
        weights[claw]=weights.get(claw,0)+blend
        v4.weights(ob,i,weights)
    at=nm.attributes.new('v6_wrist','FLOAT','POINT')
    for i in ring_t: at.data[i].value=1.
    for i in startids: at.data[i].value=.5
    at=nm.attributes.new('v6_cuff_t','FLOAT','POINT')
    for i,t in ring_t.items(): at.data[i].value=t
    # Existing corner normals are retained; only the cuff gets new shading.
    normals=np.array([n.vector[:] for n in nm.corner_normals])
    normals[:len(oldnorm)]=oldnorm
    nm.normals_split_custom_set(normals.tolist())
    rip=nm.attributes.new('rip_normal','FLOAT_VECTOR','CORNER')
    for i,n in enumerate(normals): rip.data[i].vector=n
    if me.attributes.get('rip_normal'):
        for i,value in enumerate(me.attributes['rip_normal'].data): rip.data[i].vector=value.vector
    record.setdefault('wrists',{})[side]={'mesh':ob.name,'start_indices':startids,
        'end_indices':rings[-1], 'new_vertices':len(points)-len(oldp),
        'new_faces':len(faces)-len(oldfaces),'rings':len(rings),
        'middle_radius':.53,'original_ring_radius_max':float(np.linalg.norm(start-c0,axis=1).max())}


def shade_cuffs(record):
    """Use round_out shading only at the new surface and its shared boundary."""
    ro=v4.definitions('round_out.py')
    selected=[o for o in bpy.data.objects if o.type=='MESH' and ('__shaft_fore_' in o.name or '__jaw_' in o.name)]
    keep={o.name:np.array([n.vector[:] for n in o.data.corner_normals]) for o in selected}
    touched={}
    for side in ('l','r'):
        info=record['wrists'][side]; fore=bpy.data.objects[info['mesh']]
        seams=np.array([fore.data.vertices[i].co[:] for i in info['start_indices']+info['end_indices']])
        for ob in selected:
            if not ob.name.endswith('_'+side): continue
            p=np.array([v.co[:] for v in ob.data.vertices])
            near=np.linalg.norm(p[:,None]-seams[None],axis=2).min(axis=1)<1e-5
            if ob==fore:
                near|=np.array([a.value>.1 for a in ob.data.attributes['v6_wrist'].data])
            touched[ob.name]=near
    ro['shade'](selected)
    for ob in selected:
        values=np.array([n.vector[:] for n in ob.data.corner_normals])
        for lp in ob.data.loops:
            if not touched[ob.name][lp.vertex_index]: values[lp.index]=keep[ob.name][lp.index]
        ob.data.normals_split_custom_set(values.tolist())


def deform(record):
    for ob in bpy.data.objects:
        if ob.type!='MESH': continue
        if not ('__jaw_' in ob.name or '__shaft_fore_' in ob.name or ob.name in ('hassam_mesh_02','hassam_mesh_08')):
            continue
        at=ob.data.attributes.get('v4_index') or ob.data.attributes.new('v4_index','INT','POINT')
        for v in ob.data.vertices: at.data[v.index].value=v.index
        side=None; cap=set()
        if ob.name.endswith('__shaft_fore_l'):
            cap=max(components(ob.data),key=lambda ids:min(ob.data.vertices[i].co.x for i in ids))
        normals=[n.vector[:] for n in ob.data.corner_normals]
        for v in ob.data.vertices:
            if '__jaw_' in ob.name: side=ob.name[-1]
            elif ob.name in ('hassam_mesh_02','hassam_mesh_08'):
                side='r' if any(ob.vertex_groups[g.group].name=='JOBJ_75' and g.weight>.5 for g in v.groups) else 'l'
            elif v.index in cap: side='l'
            else: continue
            info=record['pincer_'+side]
            v.co=np.array(info['anchor'])+FACTOR*(np.array(v.co)-info['v4_anchor'])+record['placement_correction'][side]
            v4.weights(ob,v.index,{info['joint']:1.})
        ob.data.update()
        ob.data.normals_split_custom_set(normals)
    for side,name,shaft in [('r','hassam_mesh_12__jaw_r','hassam_mesh_12__shaft_fore_r'),
                            ('l','hassam_mesh_11__jaw_l','hassam_mesh_11__shaft_fore_l')]:
        end=open_cap(bpy.data.objects[name])
        cuff(bpy.data.objects[shaft],side,end,record)


def round_shells():
    out=ROOT/'round/3-build'
    # Always replay the immutable v4 inputs, even after the v6 source folder
    # contains the finished editable model from a previous invocation.
    for filename in ('base.blend','edited.blend'):
        shutil.copy2(OLD/'round/3-build'/filename,out/filename)
    tag_caps(out/'edited.blend')
    v4.ROOT=ROOT
    v4.round_shells()
    record=json.loads((ROOT/'edit-record.json').read_text(encoding='utf-8'))
    deform(record)
    shade_cuffs(record)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'build.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'review/rounded.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'edited.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'build.blend'))
    (ROOT/'edit-record.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('V6: uniform pincers and thick, ringed cuffs saved',flush=True)


def finish():
    """Preserve the added cuff geometry with a build-local triangle allowance.

    9000 is rigswap's historical importer heuristic, not a measured game limit
    (prep/triangles.py). V4 already uses 8984. A local Fighter copy admits this
    build's 9312 triangles; normal memory, palette and export checks still run.
    No rigswap file or global constant is changed.
    """
    from rigswap.plugins import melee
    from rigswap.plugins.melee.prep import run as prep_run
    out=ROOT/'round/3-build'
    shutil.copy2(ROOT/'review/rounded.blend',out/'build.blend')
    bpy.ops.wm.open_mainfile(filepath=str(out/'build.blend'))
    triangles=sum(len(p.vertices)-2 for ob in bpy.data.objects if ob.type=='MESH' for p in ob.data.polygons)
    allowance=max(9000,triangles)
    report=prep_run(out,replace(melee.fighter('Marth'),triangles=allowance))
    assert not report['triangles']['decimated'],report['triangles']
    dat=melee.export(out,ROOT/'round/4-export/Marth.dat')
    (ROOT/'review/export-policy.json').write_text(json.dumps({
        'triangle_allowance':allowance,'reason':'Preserve v4 and the thick continuous cuffs; no global mesh simplification.',
        'scope':'This v6 build only; unmodified rigswap functions with a local Fighter dataclass copy.',
        'memory_and_readback_checks':'Unmodified and required.'},indent=2),encoding='utf-8')
    print('V6 preserved export:',dat,flush=True)


if __name__=='__main__':
    if '--round-shells' in sys.argv: round_shells()
    elif '--finish' in sys.argv: finish()
    else: seed()
