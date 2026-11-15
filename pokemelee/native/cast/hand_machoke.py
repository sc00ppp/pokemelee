"""hand_machoke.py <3-build>: Machoke's head back at the source's shape, from base.blend into edited.blend.

The fit squeezed the head to 4.6 wide, 6.8 tall and 3.1 deep where the source's is about as wide as it is tall and deep, and
that lost the round face and the wide mouth. Every point the source holds on the head goes to one uniform scale of its
source position, and a point shared with the neck goes by its share. The head sits where the source's does: level with the
shoulders and in front of the chest. The existing head placement is retained; the eye UV and foot fixes are below.

The eye panel's negative U coordinates must CLAMP to skin. The original eye split instead wrapped each triangle by
whole tiles, painting a second eye at the rear of each cheek. Restore the source UVs into an edge-padded crop.

The source feet are rigid, broad and low, with short toes. Place that source shape at uniform body scale in Wait1-1,
turning about each ankle and translating to the floor; bind back to the foot joint. Ganondorf's toe curl must not
reshape Machoke's rigid feet. A scene marker makes stand_feet leave this Machoke-only placement alone.

Run before stand_feet. `hand_machoke.py <3-build> --round` joins the overlapping shoulder shells, restores rigid
source fists, rounds joint seams in idle and applies soft_legs' shared arm/leg rings. Protected fix1 parts are restored;
rigid foot edges are excluded from PN bulges, so rounding cannot reshape the feet or lower their soles.
The reproducible full pipeline is hand/machoke-Ganondorf/fix2/rebuild.sh. No AI asks."""

from cast_paths import WORK, TARGETS
import json
import sys
from pathlib import Path

import bpy
import numpy as np
import bmesh
from PIL import Image
from mathutils import Vector

SOURCE = str(WORK / 'mons/machoke/1-load/models/1-067_Machoke.blend')
HEAD_BONES = 'Bone_60', 'Bone_61', 'Bone_62'
PIVOT = np.array([.016, -.39, .908])        # the source's head joint
HEAD_AT = np.array([0, -2.1, 17.6])         # Ganondorf's shoulders are at y .79, z 17.81; the source's head is .23 ahead of its
HEAD_SCALE = 14.                            # the body's scale at the shoulders, so the head keeps its size against them
EYES = 'eyes_left', 'eyes_right'            # the upper face's own panel (goriky_mesh_13), not an overlay, so it stays flush
FOOT_SCALE = 14.                           # same uniform scale as his source head
BELT = {'goriky_mesh_07', 'goriky_mesh_19', 'goriky_mesh_27'}
FEET = {'goriky_mesh_32', 'goriky_mesh_33'}


def head(p):
    return HEAD_AT + (p - PIVOT) * HEAD_SCALE


def points(ob):
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get('co', co)
    return co.reshape(-1, 3)


def view_helpers():
    ns = {'__name__': 'view_helpers'}
    code = (Path(__file__).parent / 'hand_view.py').read_text(encoding='utf-8')
    exec(compile(code.rsplit('\nmain()', 1)[0], 'hand_view.py', 'exec'), ns)
    return ns


def round_helpers():
    ns = {'__name__': 'machoke_round', '__file__': str(Path(__file__).parent / 'round_out.py')}
    code = Path(ns['__file__']).read_text(encoding='utf-8')
    exec(compile(code.rsplit('\nmain()', 1)[0], ns['__file__'], 'exec'), ns)
    original = ns['offsets']

    def offsets(meshes):
        numbers, bulges = original(meshes)
        foot_places = set()
        for ob, places in zip(meshes, numbers):
            foot_groups = {g.index for g in ob.vertex_groups if g.name in ('JOBJ_9', 'JOBJ_15')}
            rigid = {v.index for v in ob.data.vertices if sum(g.weight for g in v.groups if g.group in foot_groups) > .999}
            foot_places.update(int(place) for loop, place in zip(ob.data.loops, places) if loop.vertex_index in rigid)
        kept = {edge: delta for edge, delta in bulges.items() if not all(i in foot_places for i in edge)}
        print('Machoke: preserved source foot shape on', len(bulges)-len(kept), 'rounded edges')
        return numbers, kept

    ns['offsets'] = offsets
    return ns


def weights(ob):
    names = {g.index: int(g.name[5:]) for g in ob.vertex_groups if g.name.startswith('JOBJ_')}
    return [{names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 1e-7}
            for v in ob.data.vertices]


def set_weights(ob, index, held):
    for group in ob.vertex_groups:
        group.remove([index])
    for j, w in held.items():
        (ob.vertex_groups.get(f'JOBJ_{j}') or ob.vertex_groups.new(name=f'JOBJ_{j}')).add([index], w, 'REPLACE')


def frozen_parts(meshes, ns):
    """The first pass is exactly fix1; preserve its head, belt, eye and foot output."""
    frozen = {}
    for ob in meshes:
        w = weights(ob)
        lock = np.array([ob.name in BELT | FEET or ob.name.startswith('eyes_') or
                         ws.get(53,0)>1e-7 or any(ws.get(j, 0) > .999 for j in (9, 15)) for ws in w])
        if lock.any():
            frozen[ob.name] = (lock, points(ob), ns['stored_normals'](ob.data), w)
    return frozen


def restore_frozen(frozen):
    for name, (lock, co, normals, w) in frozen.items():
        ob = bpy.data.objects[name]
        assert len(ob.data.vertices) == len(co), name
        now = points(ob); now[lock] = co[lock]
        ob.data.vertices.foreach_set('co', now.ravel()); ob.data.update()
        for i in np.flatnonzero(lock):
            set_weights(ob, int(i), w[i])
        nn = np.array([n.vector for n in ob.data.corner_normals])
        ids = np.array([l.vertex_index for l in ob.data.loops])
        nn[lock[ids]] = normals[lock[ids]]
        ob.data.normals_split_custom_set(nn.tolist()); ob.data.update()


def join_shoulders(source):
    """Union the intersecting source shells, retaining every exterior triangle.

    A ring bridge between overlapping shells doubles back through the muscle.
    Instead, cut at their actual intersection in the source, interpolate UVs,
    and give each new shared point one idle position and one blended binding.
    Only the five meshes cut by the intersection are rebuilt; all other source
    faces and vertices, including the head, belt and feet, remain untouched.
    """
    from collections import defaultdict
    from mathutils.geometry import tessellate_polygon
    adjacency=defaultdict(set); source_positions={}; records=[]
    for name,mesh in source.items():
        keys=[tuple(p.round(5)) for p in mesh['p']]
        for i,k in enumerate(keys):source_positions[k]=mesh['p'][i]
        for fi,face in enumerate(mesh['f']):
            ff=[keys[i] for i in face]
            for a,b in zip(ff,ff[1:]+ff[:1]):adjacency[a].add(b);adjacency[b].add(a)
            records.append((name,fi,ff))
    todo=set(adjacency);components=[]
    while todo:
        stack=[todo.pop()];component=set(stack)
        while stack:
            for k in adjacency[stack.pop()]:
                if k in todo:todo.remove(k);component.add(k);stack.append(k)
        if len(component) in (84,45):components.append(component)
    components.sort(key=lambda c:(-len(c),min(c)))
    assert [len(c) for c in components]==[84,45,45]
    component_of={k:i for i,c in enumerate(components) for k in c}
    temporary_materials=[bpy.data.materials.new('Machoke union face '+str(i)) for i in range(len(records))]
    material_face={m.name:i for i,m in enumerate(temporary_materials)}
    shells=[]
    for comp in components:
        keys=sorted(comp);lookup={k:i for i,k in enumerate(keys)}
        chosen=[(ix,r) for ix,r in enumerate(records) if r[2][0] in comp]
        me=bpy.data.meshes.new('Machoke source shell')
        me.from_pydata([source_positions[k] for k in keys],[],[[lookup[k] for k in r[2]] for ix,r in chosen])
        for mat in temporary_materials:me.materials.append(mat)
        for p,(ix,r) in zip(me.polygons,chosen):p.material_index=ix
        bm=bmesh.new();bm.from_mesh(me);bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
        assert not any(not e.is_manifold for e in bm.edges)
        bm.to_mesh(me);bm.free();me.update()
        ob=bpy.data.objects.new(me.name,me);bpy.context.scene.collection.objects.link(ob);shells.append(ob)
    root=shells[0];bpy.context.view_layer.objects.active=root;root.select_set(True)
    for ob in shells[1:]:
        bpy.context.view_layer.update()
        mod=root.modifiers.new('Join actual shoulder intersection','BOOLEAN')
        mod.operation='UNION';mod.solver='MANIFOLD';mod.object=ob
        bpy.ops.object.modifier_apply(modifier=mod.name)
        print('Shoulder union shell result',len(root.data.vertices),len(root.data.polygons),flush=True)
        me=ob.data;bpy.data.objects.remove(ob,do_unlink=True);bpy.data.meshes.remove(me)
    union=defaultdict(list)
    for p in root.data.polygons:
        name,fi,_=records[material_face[root.data.materials[p.material_index].name]]
        union[name,fi].append(np.array([root.data.vertices[v].co for v in p.vertices]))
    changed=defaultdict(dict)
    for name,fi,ff in records:
        if ff[0] not in component_of:continue
        polygons=union[name,fi]
        same=len(polygons)==1 and len(polygons[0])==len(ff) and max(min(np.linalg.norm(p-np.array(q)) for q in ff) for p in polygons[0])<1.2e-5
        if not same:changed[name][fi]=polygons
    assert set(changed)<= {'goriky_mesh_08','goriky_mesh_11','goriky_mesh_21','goriky_mesh_22','goriky_mesh_23'}, {n:len(v) for n,v in changed.items()}
    me=root.data;bpy.data.objects.remove(root,do_unlink=True);bpy.data.meshes.remove(me)
    for mat in temporary_materials:
        if not mat.users:bpy.data.materials.remove(mat)
    ns=round_helpers();skin=ns['idle_skin']('Ganondorf')
    original={}
    for name in changed:
        ob=bpy.data.objects[name];p=points(ob);ws=weights(ob);mat=ns['vertex_skins'](ob,skin)
        original[name]=dict(p=p,w=ws,idle=np.einsum('nij,nj->ni',mat[:,:3,:3],p)+mat[:,:3,3],
            uv=np.array([l.uv for l in ob.data.uv_layers.active.data]),
            n=ns['stored_normals'](ob.data),f=[list(p.vertices) for p in ob.data.polygons],
            li=[list(p.loop_indices) for p in ob.data.polygons])
    triangles=[]
    for name,mesh in source.items():
        if name not in changed:continue
        for fi,f in enumerate(mesh['f']):
            p=mesh['p'][f];edge=np.column_stack([p[1]-p[0],p[2]-p[0]])
            triangles.append((name,fi,f,p,np.linalg.pinv(edge),component_of.get(tuple(p[0].round(5)))))
    def bary(p,tri):
        uv=tri[4]@(p-tri[3][0]);return np.array([1-uv.sum(),*uv])
    shared={}
    def binding(p):
        key=tuple(p.round(6))
        if key in shared:return shared[key]
        by_component=defaultdict(list)
        for tri in triangles:
            name,fi,f,q,inv,component=tri;b=bary(p,tri)
            if b.min() < -2e-5 or np.linalg.norm(b@q-p)>2e-6:continue
            ws=defaultdict(float)
            for i,v in zip(f,b):
                for j,w in original[name]['w'][i].items():ws[j]+=v*w
            by_component[component].append((b@original[name]['idle'][f],dict(ws)))
        assert by_component, p
        # Equal shell contribution at the cut, independent of triangle density.
        target=np.mean([np.mean([q for q,w in rows],axis=0) for rows in by_component.values()],axis=0)
        ws=defaultdict(float)
        for rows in by_component.values():
            for q,w in rows:
                for j,v in w.items():ws[j]+=v/len(rows)/len(by_component)
        ws={j:max(0.,v) for j,v in ws.items() if v>1e-6};total=sum(ws.values());ws={j:v/total for j,v in ws.items()}
        mat=sum(w*skin[j] for j,w in ws.items());bind=(np.linalg.inv(mat)@np.r_[target,1])[:3]
        shared[key]=(bind,ws,float(len(by_component)>1));return shared[key]
    count=0
    for name,changes in changed.items():
        ob=bpy.data.objects[name];old=original[name];src=source[name]
        co=list(old['p']);ww=list(old['w']);marked=[0.]*len(co)
        index={tuple(p.round(6)):i for i,p in enumerate(src['p'])}
        faces=[];uvs=[];normals=[]
        tri_by_face={tri[1]:tri for tri in triangles if tri[0]==name}
        for fi,f in enumerate(old['f']):
            loops=old['li'][fi]
            if fi not in changes:
                faces.append(f);uvs.extend(old['uv'][loops]);normals.extend(old['n'][loops]);continue
            tri=tri_by_face[fi]
            for polygon in changes[fi]:
                for triangle in tessellate_polygon([[Vector(p) for p in polygon]]):
                    ff=[]
                    for v in triangle:
                        p=np.array(polygon[int(v)] if np.isscalar(v) else v);key=tuple(p.round(6));b=bary(p,tri)
                        if key not in index:
                            at,w,mark=binding(p);index[key]=len(co);co.append(at);ww.append(w);marked.append(mark);count+=1
                        ff.append(index[key]);uvs.append(b@old['uv'][loops]);normals.append(b@old['n'][loops])
                    faces.append(ff)
        me=bpy.data.meshes.new(ob.data.name+'_union');me.from_pydata(co,[],faces)
        for mat in ob.data.materials:me.materials.append(mat)
        me.uv_layers.new(name='UVMap').data.foreach_set('uv',np.array(uvs).ravel())
        for p in me.polygons:p.use_smooth=True
        nn=np.array(normals);nn/=np.maximum(np.linalg.norm(nn,axis=1,keepdims=True),1e-12)
        ob.data=me
        for i,w in enumerate(ww):set_weights(ob,i,w)
        me.normals_split_custom_set(nn.tolist())
        me.attributes.new('machoke_join','FLOAT','POINT').data.foreach_set('value',marked);me.update()
    print('Machoke source shoulder union:',{n:len(v) for n,v in changed.items()},count,'new point copies',flush=True)


def fix_finger_weights(source_weights, source_points):
    """Restore each closed source fist as a rigid shape, including all wrist copies.

    Per-source-bone fitting stretched the finger strips independently. A rigid
    least-squares placement preserves the existing hand's position/orientation
    while restoring its source proportions and binding it to its actual wrist.
    """
    changed=0
    for side,joint in ((1,25),(-1,69)):
        chosen=[]
        for name,rows in source_weights.items():
            for i,src in enumerate(rows):
                if name in ('goriky_mesh_10','goriky_mesh_26') or (name=='goriky_mesh_09' and any(k in src for k in ('Bone_48','Bone_50','Bone_53','Bone_54'))):
                    if source_points[name][i,0]*side>0:chosen.append((name,i))
        src=np.array([source_points[n][i] for n,i in chosen])
        dst=np.array([bpy.data.objects[n].data.vertices[i].co for n,i in chosen])
        a,b=src.mean(0),dst.mean(0)
        u,s,vt=np.linalg.svd((src-a).T@(dst-b));rot=vt.T@u.T
        if np.linalg.det(rot)<0:vt[-1]*=-1;rot=vt.T@u.T
        scale=float(s.sum()/np.sum((src-a)**2))
        mapping={tuple(p.round(5)): (p-a)@rot.T*scale+b for p in src}
        for name,co in source_points.items():
            ob=bpy.data.objects.get(name)
            if ob is None:continue
            for i,p in enumerate(co):
                key=tuple(p.round(5))
                if key in mapping:
                    ob.data.vertices[i].co=mapping[key];set_weights(ob,i,{joint:1.});changed+=1
            ob.data.update()
        print('Machoke source fist',joint,'uniform scale',scale,flush=True)
    print('Machoke fingers:',changed,'source points and shared wrist copies',flush=True)


def round_seams(ns, frozen):
    """Round local folded rims in idle, with bounded alternating passes.

    Only the short joint bands move, with a fixed displacement limit. The head,
    belt and source foot surface are constraints, not smoothing targets.
    """
    from collections import defaultdict
    meshes = ns['mesh_objects'](); skin = ns['idle_skin']('Ganondorf')
    ns['pose'](meshes, skin)
    groups = {}; lookup = {}; neighbors = defaultdict(set)
    locked_positions = set()
    for ob in meshes:
        ws = weights(ob)
        for v in ob.data.vertices:
            key = tuple(np.round(v.co, 4))
            if key not in groups: groups[key] = dict(p=np.array(v.co), at=[], w=ws[v.index])
            groups[key]['at'].append((ob,v.index)); lookup[ob.name,v.index] = key
            if ob.name in BELT | FEET or ob.name.startswith('eyes_') or ws[v.index].get(53,0)>1e-7 or any(ws[v.index].get(j,0)>.999 for j in (9,15)):
                locked_positions.add(key)
        for p in ob.data.polygons:
            f = [lookup[ob.name,i] for i in p.vertices]
            for a,b in zip(f,f[1:]+f[:1]): neighbors[a].add(b);neighbors[b].add(a)
    view = view_helpers(); frame = view['frame']('Ganondorf','Wait1-1'); C = view['C']
    joints = {j:(C@m)[:3,3] for j,m in frame.items()}
    bands = [(6,7,9,2.2),(12,13,15,2.2),(22,23,25,1.9),(66,67,69,1.9),
             (20,22,23,2.1),(64,66,67,2.1),(7,9,10,2.25),(13,15,16,2.25)]
    amounts={}
    for key,p in groups.items():
        amount=0.
        for parent,child,tip,span in bands:
            if sum(p['w'].get(j,0) for j in (parent,child)) < .5: continue
            axis=joints[tip]-joints[child];axis/=np.linalg.norm(axis)
            s=abs((p['p']-joints[child])@axis)
            amount=max(amount,float(np.clip(1-s/span,0,1)))
        if key in locked_positions: amount=0.
        amounts[key]=amount
    # The actual shoulder seam lies off the bone axis. Follow its topology,
    # not just a cylinder around the joint, so the folded collar is included.
    collar={k for k,p in groups.items() if any('machoke_join' in ob.data.attributes and
            ob.data.attributes['machoke_join'].data[i].value>.1 for ob,i in p['at'])}
    for level,amount in enumerate((1.,.8,.4)):
        for k in collar:
            if k not in locked_positions:amounts[k]=max(amounts[k],amount)
        collar={j for k in collar for j in neighbors[k]}-collar
    original={k:p['p'].copy() for k,p in groups.items()}
    for factor in (.5,-.35)*8:
        moved={}
        for k,p in groups.items():
            if not amounts[k] or not neighbors[k]: continue
            mean=np.mean([groups[j]['p'] for j in sorted(neighbors[k])],axis=0)
            q=p['p']+factor*amounts[k]*(mean-p['p'])
            delta=q-original[k];length=np.linalg.norm(delta)
            moved[k]=original[k]+delta*min(1,1.1/max(length,1e-9))
        for k,q in moved.items():groups[k]['p']=q
    max_move=max(np.linalg.norm(p['p']-original[k]) for k,p in groups.items())
    for k,p in groups.items():
        for ob,i in p['at']:ob.data.vertices[i].co=p['p']
    # Reuse round_out's across-mesh shading. A shallow skin crease (including the
    # original 33-34 degree knee split) is smoothed across the unlocked skin.
    for ob in meshes:
        ob.data.update()
        tag=ob.data.attributes.new(ns['RIP'],'FLOAT_VECTOR','CORNER')
        nn=ns['stored_normals'](ob.data)
        for loop in ob.data.loops:
            k=lookup[ob.name,loop.vertex_index]
            if k not in locked_positions or ob.name.startswith('shoulder_seam_'):nn[loop.index]=[0,0,1]
        tag.data.foreach_set('vector',nn.ravel())
    ns['shade'](meshes)
    for ob in meshes:ob.data.attributes.remove(ob.data.attributes[ns['RIP']])
    ns['bind_back'](meshes,skin)
    restore_frozen(frozen)
    # The foot is immutable; carry its boundary normals into the adjoining shin.
    foot_normals={}
    for ob in meshes:
        if ob.name not in FEET:continue
        for loop,n in zip(ob.data.loops,ob.data.corner_normals):
            foot_normals[tuple(np.array(ob.data.vertices[loop.vertex_index].co).round(4))]=np.array(n.vector)
    for ob in meshes:
        if ob.name not in ('goriky_mesh_29','goriky_mesh_30','goriky_mesh_31'):continue
        nn=ns['stored_normals'](ob.data)
        for loop in ob.data.loops:
            key=tuple(np.array(ob.data.vertices[loop.vertex_index].co).round(4))
            if key in foot_normals:nn[loop.index]=foot_normals[key]
        ob.data.normals_split_custom_set(nn.tolist());ob.data.update()
    print('Machoke local rim rounding, maximum idle displacement',max_move,flush=True)


def preserve_belt_contact(ns):
    """The belt keeps fix1's midpoint positions; adjoining skin must share them."""
    from collections import Counter
    from mathutils.kdtree import KDTree
    skin=ns['idle_skin']('Ganondorf');reference=[]
    for name in BELT:
        ob=bpy.data.objects[name];co=points(ob);ws=weights(ob);mat=ns['vertex_skins'](ob,skin)
        posed=np.einsum('nij,nj->ni',mat[:,:3,:3],co)+mat[:,:3,3]
        for i,p in enumerate(posed):reference.append((p,co[i],ws[i]))
    locations=np.array([p for p,co,w in reference]);count=0
    ob=bpy.data.objects['goriky_mesh_08'];co=points(ob);mat=ns['vertex_skins'](ob,skin)
    normals=ns['stored_normals'](ob.data)
    posed=np.einsum('nij,nj->ni',mat[:,:3,:3],co)+mat[:,:3,3]
    # Snap only an actual open seam, never an unrelated point merely near the belt.
    all_points=[];indices={};meshes=ns['mesh_objects']()
    for mesh in meshes:
        cp=points(mesh);cm=ns['vertex_skins'](mesh,skin)
        pp=np.einsum('nij,nj->ni',cm[:,:3,:3],cp)+cm[:,:3,3]
        indices[mesh.name]=np.arange(len(cp))+len(all_points);all_points.extend(pp)
    tree=KDTree(len(all_points))
    for i,p in enumerate(all_points):tree.insert(p,i)
    tree.balance();groups=np.array([min(j for q,j,d in tree.find_range(p,1e-4)) for p in all_points])
    edges=Counter()
    for mesh in meshes:
        for face in mesh.data.polygons:
            f=groups[indices[mesh.name][list(face.vertices)]]
            for a,b in zip(f,np.roll(f,-1)):
                if a!=b:edges[tuple(sorted((int(a),int(b))))]+=1
    boundary={i for e,c in edges.items() if c==1 for i in e}
    for i,p in enumerate(posed):
        if groups[indices[ob.name][i]] not in boundary:continue
        ds=np.linalg.norm(locations-p,axis=1);nearest=int(ds.argmin())
        if ds[nearest]>.21:continue
        q,at,w=reference[nearest];ob.data.vertices[i].co=at;set_weights(ob,i,w);count+=1
    ob.data.update();ob.data.normals_split_custom_set(normals.tolist());ob.data.update()
    print('Machoke belt contact:',count,'adjoining skin points share the unchanged belt',flush=True)


def round_machoke():
    ns = round_helpers(); build = Path(sys.argv[1]); args = list(sys.argv)
    # Baseline pass is deliberately unchanged: the protected result stays exact.
    ns['main']()
    frozen = frozen_parts(ns['mesh_objects'](),ns)
    bpy.ops.wm.open_mainfile(filepath=SOURCE)
    source_weights = {}; source_points={};source={}
    for ob in bpy.data.objects:
        if ob.type != 'MESH': continue
        names={g.index:g.name for g in ob.vertex_groups}
        source_weights[ob.name]=[{names[g.group]:g.weight for g in v.groups if g.weight>1e-7} for v in ob.data.vertices]
        source_points[ob.name]=points(ob)
        source[ob.name]=dict(p=points(ob),f=[list(p.vertices) for p in ob.data.polygons])
    bpy.ops.wm.open_mainfile(filepath=str(build/'edited.blend'))
    fix_finger_weights(source_weights,source_points);join_shoulders(source)
    bpy.ops.wm.save_as_mainfile(filepath=str(build/'edited.blend'))
    sys.argv = [str(Path(__file__).parent/'soft_legs.py'),str(build),'Ganondorf','--bind-rings']
    code = Path(sys.argv[0]).read_text(encoding='utf-8')
    exec(compile(code,sys.argv[0],'exec'),{'__name__':'machoke_soft_bind','__file__':sys.argv[0]})
    original_tags=ns['tag_creases']
    def muscle_tags(meshes,rip):
        original_tags(meshes,rip)
        for ob in meshes:
            if ob.name in {'goriky_mesh_'+str(i).zfill(2) for i in (8,11,21,22,23,24,25,28,29,30,31)}:
                ob.data.attributes[ns['RIP']].data.foreach_set('vector',np.tile([0.,0.,1.],len(ob.data.loops)))
    ns['tag_creases']=muscle_tags
    sys.argv = args + ['--idle','Ganondorf']
    ns['main']()
    restore_frozen(frozen)
    bpy.ops.wm.save_as_mainfile(filepath=str(build/'build.blend'))
    # The shared ring tool is used on both arm and leg chains, then the actual
    # folded idle rims are rounded separately; reweighting alone cannot do that.
    sys.argv = [str(Path(__file__).parent/'soft_legs.py'),str(build),'Ganondorf']
    code = Path(sys.argv[0]).read_text(encoding='utf-8')
    exec(compile(code,sys.argv[0],'exec'),{'__name__':'machoke_soft','__file__':sys.argv[0]})
    round_seams(ns,frozen)
    preserve_belt_contact(ns)
    bpy.ops.wm.save_as_mainfile(filepath=str(build/'build.blend'))
    sys.argv=args


def fix_eyes(build, panel, panel_uv, atlas, fit):
    xy = panel_uv * [32, -256] + [0, 256]
    low = np.floor(xy.min(0)).astype(int) - 1
    high = np.ceil(xy.max(0)).astype(int) + 1
    size = high - low
    for name in EYES:
        ob = bpy.data.objects[name]
        near = (points(ob) - fit[3]) @ np.linalg.inv(fit[:3])
        indices = np.linalg.norm(near[:, None] - panel, axis=2).argmin(1)
        assert len(set(indices)) == len(indices), (name, indices)
        ob.data.vertices.foreach_set('co', head(panel[indices]).ravel())
        for loop in ob.data.loops:
            uv = (xy[indices[loop.vertex_index]] - low) / size
            ob.data.uv_layers.active.data[loop.index].uv = (uv[0], 1 - uv[1])
        ob.data.update()
    # Keep the existing blink pictures, extending CLAMP at the image edge instead of moving UV triangles.
    # Open comes straight from the source atlas, including the column the old crop omitted.
    xx, yy = np.meshgrid(np.arange(low[0], high[0]), np.arange(low[1], high[1]))
    for state in ('open', 'half', 'closed'):
        path = build / 'eyes' / f'{state}.png'
        if state == 'open':
            pic = atlas[np.clip(yy, 0, 34), np.clip(xx, 0, 31)]
        else:
            old = np.array(Image.open(path).convert('RGBA'))
            assert old.shape[:2] == (35, 31), (state, old.shape)
            pic = old[np.clip(yy, 0, 34), np.clip(xx - 1, 0, 30)]
        Image.fromarray(pic).save(path)
    old_image = bpy.data.images.get('eyes_open')
    new_image = bpy.data.images.load(str((build / 'eyes/open.png').resolve()), check_existing=False)
    new_image.pack()
    for node in bpy.data.materials['eyes'].node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            node.image = new_image
            node.extension = 'EXTEND'
    if old_image is not None:
        bpy.data.images.remove(old_image)
    new_image.name = 'eyes_open'
    record = json.loads((build / 'eyes.json').read_text(encoding='utf-8'))
    record['crop'] = [*map(int, low), *map(int, size)]
    record['notes'] = ['hand_machoke.py: original panel UVs, no per-triangle wrap; crop padded with CLAMP skin texels.']
    (build / 'eyes.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
    print('Machoke eyes: 24 source triangles, one eye per side; clamped crop', record['crop'])


def place_feet(source, source_ankles, source_normals, source_faces):
    ns = view_helpers()
    C, rest, idle = ns['C'], ns['rests']('Ganondorf'), ns['frame']('Ganondorf', 'Wait1-1')
    skin = {j: C @ idle[j] @ np.linalg.inv(rest[j]) @ np.linalg.inv(C) for j in rest if j in idle}
    sole = source['goriky_mesh_33'][0]
    foot = source['goriky_mesh_32'][0]
    report = {}
    for side, sign, joint, toe, bone in [('L', 1, 9, 10, 'Bone_07'), ('R', -1, 15, 16, 'Bone_18')]:
        ankle = source_ankles[bone]
        verts = foot[foot[:, 0] * sign > 0]
        bottom = sole[sole[:, 0] * sign > 0]
        # The actual sole polygons define its plane; this is not a convex hull of curled-up toes.
        normal = np.zeros(3)
        for face in source_faces['goriky_mesh_33']:
            tri = sole[face]
            if tri[:, 0].mean() * sign > 0:
                normal += np.cross(tri[1] - tri[0], tri[2] - tri[0])
        if normal[2] < 0:
            normal *= -1
        normal /= np.linalg.norm(normal)
        flatten = np.array(Vector(normal).rotation_difference(Vector((0, 0, 1))).to_matrix())
        target_ankle = (C @ idle[joint])[:3, 3]
        along = (C @ idle[toe])[:3, 3] - target_ankle
        along[2] = 0
        along /= np.linalg.norm(along)
        forward = flatten @ np.array([0., -1., 0.])
        yaw = np.arctan2(along[1], along[0]) - np.arctan2(forward[1], forward[0])
        spin = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]]) @ flatten
        translated = target_ankle.copy()
        translated[2] = -((verts - ankle) @ spin.T * FOOT_SCALE)[:, 2].min()
        inv = np.linalg.inv(skin[joint])
        change_normal = inv[:3, :3] @ spin
        changed = 0
        for name, (co, _) in source.items():
            ob = bpy.data.objects.get(name)
            if ob is None:
                continue
            # Carry every copy of the ankle boundary with the foot, keeping the shin sewn to it.
            selected = np.linalg.norm(co[:, None] - verts, axis=2).min(1) < 1e-5
            if not selected.any():
                continue
            placed = (co[selected] - ankle) @ spin.T * FOOT_SCALE + translated
            bind = placed @ inv[:3, :3].T + inv[:3, 3]
            now = points(ob)
            now[selected] = bind
            ob.data.vertices.foreach_set('co', now.ravel())
            ids = np.flatnonzero(selected).tolist()
            for group in ob.vertex_groups:
                group.remove(ids)
            group = ob.vertex_groups.get(f'JOBJ_{joint}') or ob.vertex_groups.new(name=f'JOBJ_{joint}')
            group.add(ids, 1., 'REPLACE')
            normals = np.array([n.vector for n in ob.data.corner_normals])
            for loop in ob.data.loops:
                if selected[loop.vertex_index]:
                    normals[loop.index] = change_normal @ source_normals[name][loop.index]
            normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
            ob.data.normals_split_custom_set(normals.tolist())
            ob.data.update()
            changed += len(ids)
        placed_sole = (bottom - ankle) @ spin.T * FOOT_SCALE + translated
        report[side] = dict(joint=joint, vertices=changed, scale=FOOT_SCALE,
                            ankle_idle=target_ankle.tolist(), placed_ankle=translated.tolist(),
                            sole_z=[float(placed_sole[:, 2].min()), float(placed_sole[:, 2].max())])
        print('Machoke', side, 'source foot:', report[side])
    bpy.context.scene['machoke_idle_source_feet'] = True
    return report


def main():
    build = Path(sys.argv[1]).resolve()
    if sys.argv[2:] == ['--round']:
        round_machoke()
        return
    bpy.ops.wm.open_mainfile(filepath=SOURCE)
    bones = next(o for o in bpy.data.objects if o.type == 'ARMATURE').data.bones
    on_head = {b for name in HEAD_BONES if name in bones for b in [name] + [c.name for c in bones[name].children_recursive]}
    source_ankles = {name: np.array(bones[name].head_local) for name in ('Bone_07', 'Bone_18')}
    source, source_normals, source_faces = {}, {}, {}
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            names = {g.index: g.name for g in ob.vertex_groups}
            share = [sum(g.weight for g in v.groups if names[g.group] in on_head) / (sum(g.weight for g in v.groups) or 1)
                     for v in ob.data.vertices]
            source[ob.name] = points(ob), np.array(share)
            source_normals[ob.name] = np.array([n.vector for n in ob.data.corner_normals])
            source_faces[ob.name] = [list(p.vertices) for p in ob.data.polygons]
    panel_ob = bpy.data.objects['goriky_mesh_13']
    panel_uv = np.empty((len(panel_ob.data.vertices), 2))
    for loop in panel_ob.data.loops:
        panel_uv[loop.vertex_index] = panel_ob.data.uv_layers.active.data[loop.index].uv
    im = bpy.data.images['tex_3D38']
    atlas = np.uint8(np.clip(np.array(im.pixels[:]).reshape(im.size[1], im.size[0], 4)[::-1], 0, 1) * 255)
    bpy.ops.wm.open_mainfile(filepath=str(build / 'base.blend'))
    was, port = [], []
    for name, (co, share) in source.items():
        if name in bpy.data.objects:
            was.append(co[share > .99])
            port.append(points(bpy.data.objects[name])[share > .99])
    was, port = np.concatenate(was), np.concatenate(port)
    fit = np.linalg.lstsq(np.column_stack([was, np.ones(len(was))]), port, rcond=None)[0]
    print('head points', len(was), 'fit scale', np.linalg.norm(fit[:3], axis=1).round(2))
    for name, (co, share) in source.items():
        ob = bpy.data.objects.get(name)
        if ob is not None:
            now = points(ob)
            ob.data.vertices.foreach_set('co', (now + share[:, None] * (head(co) - now)).ravel())
            ob.data.update()
    fix_eyes(build, source['goriky_mesh_13'][0], panel_uv, atlas, fit)
    report = place_feet(source, source_ankles, source_normals, source_faces)
    (build / 'machoke-feet.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(build / 'edited.blend'))
    print('Machoke: head at the source shape, scale', HEAD_SCALE)


if __name__ == '__main__':
    main()
