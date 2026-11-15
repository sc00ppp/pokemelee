"""Scizor v4: chest-seated shoulders and uniformly scaled source pincers.

Run without arguments to place the original vertices; --round-shells runs only
round_out's PN subdivision/shading, twice on the larger armour and arm shafts. The
round_cast scizor-v4 entry runs that after stand_feet and before hand_finish.
No normals are discarded by this tool; original corner normals accompany every
face when the material meshes are separated into anatomical shell regions.
"""

from cast_paths import WORK, TARGETS
import json
import sys
from collections import Counter
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image

R = Path(str(WORK / ''))
ASSETS = R / 'hand/scizor-Marth'
ROOT = ASSETS / 'v4'
BUILD = ROOT / '3-build'
SOURCE = R / 'mons/scizor/1-load/models/1-212_Scizor.blend'
SCALE = 8.0  # one source-derived cross-section scale, including the entire head
SHAFT_FACTOR = 1.7


def smooth(value):
    x = float(np.clip(value, 0., 1.))
    return x*x*(3.-2.*x)


def arm_weights(ob, record):
    """Seat the medial shoulder on the chest; blend outward into the arm.

    Apply the same spatial rule to both copies of each shared shoulder/shaft
    vertex. The pincers, including their collar vertices, remain rigid.
    """
    for side, upper, fore, hand in [('l','JOBJ_28','JOBJ_29','JOBJ_31'),
                                     ('r','JOBJ_70','JOBJ_71','JOBJ_73')]:
        is_upper = ob.name.endswith('__shaft_upper_'+side)
        is_fore = ob.name.endswith('__shaft_fore_'+side)
        is_shoulder = ob.name.endswith('__shoulder_'+side)
        if not (is_upper or is_fore or is_shoulder):
            continue
        a, b, c = [np.array(record['arm_joints'][side][k]) for k in ('shoulder','elbow','wrist')]
        axis = unit(c-b)
        for v in ob.data.vertices:
            # A shaft object also owns the joining triangles at the pincer
            # collar. Their shared jaw vertices must remain on the blade.
            pincer = ob.data.attributes.get('scizor_pincer')
            if pincer and pincer.data[v.index].value > .999:
                continue
            p = np.array(v.co)
            s = float((p-b)@axis)
            elbow = smooth((s+.95)/1.90)
            wrist = smooth((s-(np.linalg.norm(c-b)-.85))/.85)
            if side=='l':
                # Signed distance along the two joined centerlines makes the
                # shared ring blend identically on the shaft and jaw sides.
                rel = p-c
                jaw_axis = np.array(record['pincer_l']['forward'])
                f, j = float(rel@axis), float(rel@jaw_axis)
                on_fore = f<0 and np.linalg.norm(rel-f*axis)<np.linalg.norm(rel-max(j,0)*jaw_axis)
                bend = f if on_fore else j
                wrist = smooth((bend+.85)/1.70)
            if is_upper or is_shoulder:
                wrist = 0.
            if is_shoulder:
                elbow = 0.
            chest = 1-smooth((abs(p[0])-.85)/.90) if is_shoulder or is_upper else 0.
            weights(ob,v.index,{'JOBJ_22':chest,upper:(1-chest)*(1-elbow)*(1-wrist),
                                fore:(1-chest)*elbow*(1-wrist),hand:(1-chest)*wrist})


def unit(v):
    return np.asarray(v) / np.linalg.norm(v)


def rotation(a, b):
    return np.array(Vector(a).normalized().rotation_difference(Vector(b).normalized()).to_matrix())


def tube(p, a, b, ta, tb, radial=SCALE):
    d = b - a
    f = np.dot(p-a, d) / np.dot(d, d)
    return ta + f*(tb-ta) + radial * rotation(d, tb-ta) @ (p-a-f*d), f


def read(ob):
    names = {g.index: g.name for g in ob.vertex_groups}
    return (np.array([ob.matrix_world @ v.co for v in ob.data.vertices]),
            np.array([names[max(v.groups, key=lambda g:g.weight).group] for v in ob.data.vertices]))


def weights(ob, i, held):
    for g in ob.vertex_groups:
        g.remove([i])
    for name, w in held.items():
        if w > 1e-6:
            (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([i], float(w), 'REPLACE')


def definitions(filename):
    ns = {'__name__': 'scizor_helpers', '__file__': str(R/'tools'/filename)}
    code = (R/'tools'/filename).read_text(encoding='utf-8').rsplit('\nmain()', 1)[0]
    exec(compile(code, filename, 'exec'), ns)
    return ns


def round_shells():
    """Use round_out itself for all cuts and all shading, preserving its RIP tags."""
    out = ROOT / 'round/3-build'
    ro = definitions('round_out.py')
    bpy.ops.wm.open_mainfile(filepath=str(out/'base.blend'))
    rip = {o.name: ro['stored_normals'](o.data) for o in ro['mesh_objects']()}
    bpy.ops.wm.open_mainfile(filepath=str(out/'edited.blend'))
    meshes = ro['mesh_objects']()
    ro['tag_creases'](meshes, rip)
    initial = sum(len(o.data.polygons) for o in meshes)
    nums, bulge = ro['offsets'](meshes)
    for ob, number in zip(meshes, nums):
        ro['cut'](ob, number, bulge)
    record = json.loads((ROOT/'edit-record.json').read_text(encoding='utf-8'))
    for ob in meshes:
        arm_weights(ob,record)
    ro['shade'](meshes)
    once = sum(len(o.data.polygons) for o in meshes)
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'review/one-pass.blend'))
    # The two jaw halves, head, abdomen, chest, teardrop shins and arm shafts.
    # V4 shoulder caps also get a second pass after seating them on the chest.
    # Thigh tubes, membranes and small jaw interiors retain v3's first pass.
    shells = [o for o in meshes if o.get('scizor_second_pass', False) or
              o.name in {'eyes_left','eyes_right','hassam_mesh_01','hassam_mesh_02',
                         'hassam_mesh_03','hassam_mesh_04','hassam_mesh_05'}]
    nums, bulge = ro['offsets'](meshes)
    # A twice-cut shell meeting a once-cut tube must keep their common edge
    # straight. Otherwise its new midpoint bows away from the uncut neighbour.
    selected_edges, plain_edges = set(), set()
    for ob, number in zip(meshes, nums):
        edges = selected_edges if ob in shells else plain_edges
        for poly in ob.data.polygons:
            loops = list(poly.loop_indices)
            for a,b in zip(loops,loops[1:]+loops[:1]):
                edges.add(tuple(sorted((int(number[a]),int(number[b])))))
    for edge in selected_edges & plain_edges:
        bulge.pop(edge,None)
    for ob, number in zip(meshes, nums):
        if ob in shells:
            ro['cut'](ob, number, bulge)
    for ob in meshes:
        arm_weights(ob,record)
    # Both jaws keep the source geometry at one scale. No reach deformation.
    ro['shade'](meshes)
    # Locate the rounded shell under each existing front plate. A source
    # coplanar overlay must stay just in front even where its triangulation
    # differs from the armour; this changes placement, not surface smoothing.
    clearance = {}
    for plate_name, shell_labels in [('hassam_mesh_03',('chest',)),('hassam_mesh_04',('abdomen',)),
                                    ('eyes_left',('head',)),('eyes_right',('head',))]:
        points, faces = [], []
        for shell in meshes:
            if any(shell.name.endswith('__'+label) for label in shell_labels):
                start = len(points)
                points.extend([v.co[:] for v in shell.data.vertices])
                faces.extend([[start+i for i in f.vertices] for f in shell.data.polygons])
        tree = BVHTree.FromPolygons(points,faces)
        plate = bpy.data.objects[plate_name]
        largest = 0.
        for v in plate.data.vertices:
            hit = tree.ray_cast(Vector((v.co.x,-40,v.co.z)),Vector((0,1,0)),80)[0]
            if plate_name.startswith('eyes_') and abs(v.co.x)<.50:
                # The source eye triangles deliberately tuck under the red
                # bridge. Keep the atlas margins underneath the rounded bridge.
                if hit:
                    v.co.y = max(v.co.y,hit.y+.12)
                continue
            margin = .018 if plate_name.startswith('eyes_') else .045
            if hit and (plate_name.startswith('eyes_') or v.co.y>hit.y-margin):
                largest = max(largest,abs(v.co.y-(hit.y-margin)))
                v.co.y = hit.y-margin
        plate.data.update()
        clearance[plate_name] = largest
    marks = bpy.data.objects['hassam_mesh_02']
    names = {g.index:g.name for g in marks.vertex_groups}
    for side,joint in [('l','JOBJ_31'),('r','JOBJ_75')]:
        points, faces = [], []
        for shell in meshes:
            if shell.name.endswith('__jaw_'+side):
                start = len(points)
                points.extend([v.co[:] for v in shell.data.vertices])
                faces.extend([[start+i for i in f.vertices] for f in shell.data.polygons])
        tree = BVHTree.FromPolygons(points,faces)
        for v,normal in zip(marks.data.vertices,marks.data.attributes['scizor_mark_axis'].data):
            if any(names[g.group]==joint and g.weight>.99 for g in v.groups):
                axis = Vector(normal.vector).normalized()
                hit = tree.ray_cast(v.co+axis*3,-axis,6)[0]
                if hit:
                    v.co = hit+axis*.015
    marks.data.update()
    ro['shade'](meshes)
    twice = sum(len(o.data.polygons) for o in meshes)
    assert twice <= 10000, twice
    print(f'Scizor selective round_out: {initial} -> {once} -> {twice} faces')
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'build.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'review/rounded.blend'))
    (ROOT/'review/subdivision.json').write_text(json.dumps({
        'original': initial, 'one_pass': once, 'selected_second_pass': twice,
        'second_pass_objects': [o.name for o in shells],
        'plate_clearance_max': clearance,
        'method': 'round_out.offsets, cut and shade, retaining its original rip_normal tags'
    }, indent=2), encoding='utf-8')


def split_shells(ob, regions):
    """Partition original faces, retaining their exact topology, UVs and normals."""
    me = ob.data
    old_normals = np.array([n.vector[:] for n in me.corner_normals])
    buckets = {}
    for f in me.polygons:
        labels = [regions[i] for i in f.vertices]
        # A face joining a narrow shaft to a cuff belongs to that shaft.
        label = next((s for s in labels if s.startswith('shaft_fore')),
                     next((s for s in labels if s.startswith('shaft')), Counter(labels).most_common(1)[0][0]))
        buckets.setdefault(label, []).append(f)
    for label, faces in buckets.items():
        used = sorted({i for f in faces for i in f.vertices})
        remap = {old:new for new,old in enumerate(used)}
        nm = bpy.data.meshes.new(ob.name+'__'+label)
        nm.from_pydata([me.vertices[i].co[:] for i in used], [],
                      [[remap[i] for i in f.vertices] for f in faces])
        for mat in me.materials:
            nm.materials.append(mat)
        loops = [i for f in faces for i in f.loop_indices]
        for old_uv in me.uv_layers:
            uv = nm.uv_layers.new(name=old_uv.name)
            for i, old in enumerate(loops):
                uv.data[i].uv = old_uv.data[old].uv
        for p, old in zip(nm.polygons, faces):
            p.material_index = old.material_index
            p.use_smooth = old.use_smooth
        nm.normals_split_custom_set(old_normals[loops].tolist())
        for key in ('scizor_jaw_half','scizor_jaw_r','scizor_pincer'):
            if key in me.attributes:
                at = nm.attributes.new(key,'FLOAT','POINT')
                for i, old in enumerate(used):
                    at.data[i].value = me.attributes[key].data[old].value
        new = bpy.data.objects.new(nm.name, nm)
        bpy.context.scene.collection.objects.link(new)
        for g in ob.vertex_groups:
            new.vertex_groups.new(name=g.name)
        for i, old in enumerate(used):
            for g in me.vertices[old].groups:
                if g.weight > 0:
                    new.vertex_groups[g.group].add([i], g.weight, 'REPLACE')
        mod = new.modifiers.new('Armature', 'ARMATURE')
        mod.object = bpy.data.objects['Armature']
        new['scizor_second_pass'] = label in {'head','chest','abdomen','jaw_l','jaw_r','shin_l','shin_r',
                                             'shoulder_l','shoulder_r','shaft_upper_l','shaft_upper_r','shaft_fore_l','shaft_fore_r'}
    bpy.data.objects.remove(ob, do_unlink=True)


def main():
    if '--round-shells' in sys.argv:
        round_shells()
        return
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    source = {o.name:read(o) for o in bpy.data.objects if o.type=='MESH'}
    # The marks occupy two opposite planes. Fitting one plane to both marks
    # confuses pincer thickness with the marks' short axis. Use one real face.
    mark_points, mark_owners = source['hassam_mesh_02']
    mark_faces = [list(p.vertices) for p in bpy.data.objects['hassam_mesh_02'].data.polygons]
    mark_axes = {}
    for owner,sign in [('Bone_56',1),('Bone_35',-1)]:
        face = next(f for f in mark_faces if all(mark_owners[i]==owner for i in f))
        a,b,c = mark_points[face[:3]]
        normal = unit(np.cross(b-a,c-a))
        mark_axes[owner] = normal if normal[0]*sign>0 else -normal
    sa = next(o for o in bpy.data.objects if o.type=='ARMATURE')
    sb = {b.name:np.array(sa.matrix_world @ b.head_local) for b in sa.data.bones}
    bpy.ops.wm.open_mainfile(filepath=str(BUILD/'base.blend'))
    arm = bpy.data.objects['Armature']
    tb = {b.name:np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
    # Recover source points for the generated eye objects from the base skull's
    # affine map. Every other vertex uses its original source coordinate/index.
    sp, bp = [], []
    for name, (pts, owner) in source.items():
        if name in bpy.data.objects:
            mask = owner == 'Bone_43'
            sp.extend(pts[mask])
            bp.extend(read(bpy.data.objects[name])[0][mask])
    affine = np.linalg.lstsq(np.column_stack([sp,np.ones(len(sp))]), np.array(bp), rcond=None)[0]
    for name in ('eyes_left','eyes_right'):
        p = read(bpy.data.objects[name])[0]
        source[name] = ((p-affine[3]) @ np.linalg.inv(affine[:3]), np.array(['Bone_43']*len(p)))

    head_at = np.array([0., -.22, 14.45])
    body_a, body_b = sb['Bone_15'], sb['Bone_42']
    body_ta, body_tb = tb['JOBJ_4'], np.array([0., -.22, 14.12])
    report = {'source':str(SOURCE), 'scale':SCALE,
              'shape':'V3 body retained; chest-seated source shoulder caps; both source pincers uniformly scaled by 8 with their original jaw opening.',
              'head_crown_width_source':float(np.ptp(source['hassam_mesh_11'][0][source['hassam_mesh_11'][1]=='Bone_43'],axis=0)[0]),
              'normals':'Stored corner normals retained for every original face; round_out alone subdivides and shades.'}
    widths = {}
    for name, owner in [('head_crown','Bone_43'),('chest','Bone_30'),('abdomen','Bone_15')]:
        pts = np.concatenate([p[o==owner] for p,o in source.values() if np.any(o==owner)])
        widths[name] = float(np.ptp(pts[:,0]))
    report['source_widths'] = widths
    report['head_to_chest_width'] = widths['head_crown']/widths['chest']
    report['head_to_abdomen_width'] = widths['head_crown']/widths['abdomen']
    weapon = json.loads(Path(str(TARGETS / 'Marth.weapons.json')).read_text(encoding='utf-8'))['weapons'][0]
    direction = unit(weapon['tip_direction'])
    target_tip = np.array(weapon['grip']) + weapon['length']*direction
    pincers = {}
    for side, upper, lower, tip_name, wrist in (
        ('l','Bone_56','Bone_59','Bone_58_HandLeft','JOBJ_31'),
        ('r','Bone_35','Bone_38','Bone_37_HandRight','JOBJ_73')):
        hi = np.concatenate([p[o==upper] for p,o in source.values() if np.any(o==upper)])
        lo = np.concatenate([p[o==lower] for p,o in source.values() if np.any(o==lower)])
        forward = unit(sb[tip_name]-sb[upper])
        # A real eye-mark triangle supplies the broad-side axis.
        broad = mark_axes[upper]
        broad = unit(broad-forward*np.dot(broad,forward))
        sf = np.column_stack([broad,forward,np.cross(broad,forward)])
        tfwd = direction if side=='r' else np.array([.20,-.97,-.12])
        tfwd = unit(tfwd)
        tbroad = unit(np.array([1.,0.,0.]) - tfwd*tfwd[0])
        if side=='r':
            tbroad = -tbroad
        tf = np.column_stack([tbroad,tfwd,np.cross(tbroad,tfwd)])
        rot = tf @ sf.T
        close = np.eye(3)
        closed_lo = (lo-sb[lower]) @ close.T + sb[lower]
        along = ((np.concatenate([hi,closed_lo])-sb[upper]) @ rot.T) @ tfwd
        anchor = tb[wrist].copy()
        pincers[side] = dict(upper=upper,lower=lower,rot=rot,close=close,anchor=anchor,wrist=wrist,forward=tfwd)
        report['pincer_'+side] = {'scale':SCALE,'anchor':anchor.tolist(),'rotation':rot.tolist(),
                                  'joint':'JOBJ_75' if side=='r' else wrist,
                                  'natural_length':float(SCALE*along.max()),'forward':tfwd.tolist()}
    report['sword_tip'] = target_tip.tolist()
    report['sword_direction'] = direction.tolist()
    report['right_elbow'] = tb['JOBJ_71'].tolist()
    report['right_weapon_root'] = tb['JOBJ_75'].tolist()
    report['arm_joints'] = {side:{key:tb[joint].tolist() for key,joint in
        zip(('shoulder','elbow','wrist'),joints)} for side,joints in
        [('l',('JOBJ_28','JOBJ_29','JOBJ_31')),('r',('JOBJ_70','JOBJ_71','JOBJ_73'))]}
    report['shaft_radial_factor'] = SHAFT_FACTOR
    report['art_measurement'] = {'file':str(ASSETS/'v2/official-art.png'),
        'head_width_px':184,'shaft_width_px':[30,34],
        'shaft_to_head':[30/184,34/184],
        'note':'Visible face width below the crown; shaft measured normal to the raised arm.'}
    report['blade'] = 'Both original right jaws and eye marks use one rigid transform at scale 8 on JOBJ_75; the pincer starts at the wrist and does not extend to the sword tip.'
    report['shoulders'] = {'socket_x':.65,'source_scale':SCALE,'chest_weight_full_below_abs_x':.85,
                           'upper_arm_weight_full_above_abs_x':1.75,
                           'method':'Uniform source shoulder cap; longer shaft only after source f=.60; chest-to-upper-arm smooth weights.'}

    arms = {'Bone_53':('Bone_54','JOBJ_28','JOBJ_29','l'),
            'Bone_32':('Bone_33','JOBJ_70','JOBJ_71','r')}
    thighs = {'Bone_74':('Bone_75','JOBJ_6','JOBJ_7','l'),
              'Bone_17':('Bone_18','JOBJ_13','JOBJ_14','r')}
    shins = {'Bone_75':('Bone_84','JOBJ_7','JOBJ_9','l'),
             'Bone_18':('Bone_20','JOBJ_14','JOBJ_16','r')}
    footmap = {'Bone_77':('Bone_84','Bone_78_FootLeft','JOBJ_9','JOBJ_10'),
               'Bone_84':('Bone_84','Bone_78_FootLeft','JOBJ_9','JOBJ_10'),
               'Bone_20':('Bone_20','Bone_21_FootRight','JOBJ_16','JOBJ_17'),
               'Bone_27':('Bone_20','Bone_21_FootRight','JOBJ_16','JOBJ_17')}
    regions_by_object = {}
    for ob in list(bpy.data.objects):
        if ob.type != 'MESH':
            continue
        pts, owners = source[ob.name]
        assert len(ob.data.vertices)==len(pts), ob.name
        regions = []
        for i,(p,owner) in enumerate(zip(pts,owners)):
            if owner in ('Bone_42','Bone_43'):
                q = head_at + SCALE*(p-sb['Bone_43'])
                held, label = {'JOBJ_60':1}, 'head'
            elif owner in ('Bone_29','Bone_30'):
                q,f = tube(p,body_a,body_b,body_ta,body_tb)
                # The V plate and red shell are rigid on the same chest joint.
                chest = float(np.clip((p[2]-.86)/.065,0,1))
                held, label = {'JOBJ_4':1-chest,'JOBJ_22':chest}, 'chest'
            elif owner=='Bone_15':
                q = body_ta + SCALE*(p-body_a)
                held, label = {'JOBJ_4':1}, 'abdomen'
            elif owner in ('Bone_65','Bone_66','Bone_68','Bone_69','Bone_70','Bone_72'):
                side = 1 if owner in ('Bone_65','Bone_66','Bone_68') else -1
                root = sb['Bone_65' if side==1 else 'Bone_69']
                # Fold each entire three-part wing assembly as one rigid piece.
                axis = unit(np.array([side*.15,.80,.60]))
                original = sb['Bone_67' if side==1 else 'Bone_71']-root
                folded = np.array([side*.10,.11,-.98])
                rot = rotation(original,folded)
                q = np.array([side*.65,.55,13.1]) + SCALE*.78*rot@(p-root)
                held,label = {'JOBJ_22':1}, 'wing'
            elif owner in arms:
                end,a,b,side = arms[owner]
                _,f = tube(p,sb[owner],sb[end],tb[a],tb[b])
                # Keep the cap at source proportions and start it inside the
                # chest. Only the narrow shaft spans the remaining joint gap.
                radial = SCALE*(1+(SHAFT_FACTOR-1)*smooth((f-.60)/.20))
                socket = tb[a].copy()
                socket[0] = .65 if side=='l' else -.65
                d = sb[end]-sb[owner]
                target_axis = unit(tb[b]-socket)
                cap_end = .60*np.linalg.norm(d)*SCALE
                along = f*np.linalg.norm(d)*SCALE if f<=.60 else cap_end+(f-.60)/.40*(np.linalg.norm(tb[b]-socket)-cap_end)
                q = socket+along*target_axis+radial*rotation(d,target_axis)@(p-sb[owner]-f*d)
                w = float(np.clip((f-.80)/.20,0,1))
                held,label = {a:1-w,b:w}, ('shoulder_' if f<=.60 else 'shaft_upper_')+side
            elif owner in ('Bone_54','Bone_33'):
                side = 'l' if owner=='Bone_54' else 'r'
                claw = pincers[side]
                elbow = 'JOBJ_29' if side=='l' else 'JOBJ_71'
                wrist = 'JOBJ_31' if side=='l' else 'JOBJ_73'
                q,f = tube(p,sb[owner],sb[claw['upper']],tb[elbow],tb[wrist],SCALE*SHAFT_FACTOR)
                # Source cuff ring is just beyond its bone origin. Put its
                # mean on the wrist, leaving all of the sword line to the jaw.
                q -= .079*(tb[wrist]-tb[elbow])
                if side=='l' and f>1.25:
                    # The fourth left point is the cuff's cap inside the
                    # pincer, not part of the three-vertex forearm end ring.
                    # Stretching it along the forearm creates a wrist spike.
                    q = claw['anchor']+SCALE*claw['rot']@(p-sb[claw['upper']])
                held = {wrist:1}
                label = 'shaft_fore_'+side
            elif owner in ('Bone_56','Bone_59','Bone_35','Bone_38'):
                side = 'l' if owner in ('Bone_56','Bone_59') else 'r'
                claw = pincers[side]
                if owner==claw['lower']:
                    p = sb[owner] + claw['close']@(p-sb[owner])
                q = claw['anchor'] + SCALE*claw['rot']@(p-sb[claw['upper']])
                held,label = {claw['wrist'] if side=='l' else 'JOBJ_75':1}, 'jaw_'+side
            elif owner in thighs:
                end,a,b,side = thighs[owner]
                q,f = tube(p,sb[owner],sb[end],tb[a],tb[b])
                w = float(np.clip((f-.90)/.10,0,1))
                held,label = {a:1-w,b:w}, 'shaft_thigh_'+side
            elif owner in shins:
                end,a,b,side = shins[owner]
                q,f = tube(p,sb[owner],sb[end],tb[a],tb[b])
                w = float(np.clip((f-.88)/.12,0,1))
                held,label = {a:1-w,b:w}, 'shin_'+side
            elif owner in footmap:
                ankle,tip,foot,toe = footmap[owner]
                forward = sb[tip]-sb[ankle]
                forward[2] = 0
                target = tb[toe]-tb[foot]
                target[2] = 0
                q = tb[foot] + SCALE*rotation(forward,target)@(p-sb[ankle])
                held,label = {foot:1}, 'claws'
            else:
                raise ValueError((ob.name,owner))
            ob.data.vertices[i].co = q
            weights(ob,i,held)
            regions.append(label)
        ob.data.update()
        regions_by_object[ob.name] = regions
        at = ob.data.attributes.new('scizor_pincer','FLOAT','POINT')
        for value, owner in zip(at.data,owners):
            value.value = float(owner in ('Bone_56','Bone_59','Bone_35','Bone_38'))
        if ob.name in ('hassam_mesh_12','hassam_mesh_08'):
            at = ob.data.attributes.new('scizor_jaw_half','FLOAT','POINT')
            for value, owner in zip(at.data,owners):
                value.value = -1. if owner=='Bone_38' else 1.
            at = ob.data.attributes.new('scizor_jaw_r','FLOAT','POINT')
            for value, owner in zip(at.data,owners):
                value.value = float(owner in ('Bone_35','Bone_38'))

    # Clearances for the real coplanar overlays; they keep their shells' joints.
    for name, shift in [('hassam_mesh_01',(0,-.025,-.025)),('hassam_mesh_03',(0,-.06,.01)),
                        ('hassam_mesh_04',(0,-.07,.01))]:
        for v in bpy.data.objects[name].data.vertices:
            v.co = np.array(v.co)+shift
    ob = bpy.data.objects['hassam_mesh_02']
    ob.data.update()
    # Each pincer has marks on opposite faces. A single average normal cancels
    # them and moves one mark inward; use each real surface's own normal.
    mark_normals = np.zeros((len(ob.data.vertices),3))
    for face in ob.data.polygons:
        a,b,c = [np.array(ob.data.vertices[i].co) for i in list(face.vertices)[:3]]
        normal = np.cross(b-a,c-a)
        for i in face.vertices:
            mark_normals[i] += normal
    mark_normals /= np.maximum(np.linalg.norm(mark_normals,axis=1,keepdims=True),1e-9)
    normal_layer = ob.data.attributes.new('scizor_mark_axis','FLOAT_VECTOR','POINT')
    for dst,normal in zip(normal_layer.data,mark_normals):
        dst.vector = normal

    # Restore the source sphere-map texture with usable UVs, as in v2.
    mat = bpy.data.materials.new('scizor_v3_red_armor')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(ASSETS/'textures/tex_2FD0.png'))
    tex.image.pack()
    tex.extension = 'EXTEND'
    nodes.active = tex
    mat.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = .3
    for name in ('hassam_mesh_10','hassam_mesh_11','hassam_mesh_12','hassam_mesh_13'):
        ob = bpy.data.objects[name]
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        uv = ob.data.uv_layers.get('UVMap') or ob.data.uv_layers.new(name='UVMap')
        for loop in ob.data.loops:
            n = ob.data.vertices[loop.vertex_index].normal
            uv.data[loop.index].uv = (.5+.43*n.x,.5+.43*n.z)

    atlas = Image.open(ASSETS/'textures/tex_359C.png').convert('RGBA')
    for state,offset in [('open',0),('half',48),('closed',96)]:
        atlas.crop((0,offset,32,offset+48)).save(BUILD/'eyes'/f'{state}.png')
    record = json.loads((BUILD/'eyes.json').read_text(encoding='utf-8'))
    x,y,w,h = record['crop']
    for name in ('eyes_left','eyes_right'):
        for uv in bpy.data.objects[name].data.uv_layers.active.data:
            uv.uv = ((uv.uv.x*w+x)/32, 1-((1-uv.uv.y)*h+y)/48)
    img = bpy.data.images.load(str(BUILD/'eyes/open.png'),check_existing=False)
    img.pack()
    old_eye = bpy.data.images.get('eyes_open')
    for n in bpy.data.materials['eyes'].node_tree.nodes:
        if n.type=='TEX_IMAGE':
            n.image = img
    if old_eye and old_eye!=img:
        bpy.data.images.remove(old_eye)
    img.name = 'eyes_open'
    record['eye_texture_size'] = [32,48]
    record.pop('drawn',None)
    record.pop('lid',None)
    record['made'] = {s:f'Scizor source atlas rows {k}..{k+47}' for s,k in [('open',0),('half',48),('closed',96)]}
    (BUILD/'eyes.json').write_text(json.dumps(record,indent=2),encoding='utf-8')

    # Red-only hue correction to 3 degrees, retaining each pixel's value,
    # saturation/highlight detail and original alpha. No colour-managed render.
    def crimson(pixels):
        rgba = pixels.copy()
        rgb = rgba[...,:3].astype(float)
        r,g,b = rgb[...,0],rgb[...,1],rgb[...,2]
        hue = 60*(g-b)/np.maximum(r-np.minimum(g,b),1)
        red = (r>g*1.25)&(r>b*1.20)&(hue<18)&(hue>-20)
        low = np.minimum(g,b)*.60
        rgb[...,0][red] = r[red]*.98
        rgb[...,2][red] = low[red]
        rgb[...,1][red] = low[red]+.05*(r[red]*.98-low[red])
        rgba[...,:3] = np.clip(rgb,0,255).round().astype(np.uint8)
        return rgba
    (ROOT/'textures').mkdir(exist_ok=True)
    used = {n.image for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image}
    for im in used:
        w,h = im.size
        values = np.array(im.pixels[:]).reshape(h,w,4)
        rgba = (values[::-1]*255).round().astype(np.uint8)
        result = crimson(rgba)
        if np.array_equal(rgba,result):
            continue
        path = ROOT/'textures'/(im.name.replace('.','_')+'.png')
        Image.fromarray(result).save(path)
        new = bpy.data.images.load(str(path),check_existing=False)
        new.pack()
        for m in bpy.data.materials:
            if m.use_nodes:
                for n in m.node_tree.nodes:
                    if n.type=='TEX_IMAGE' and n.image==im:
                        n.image = new
        old = im.name
        bpy.data.images.remove(im)
        new.name = old
    for state in ('open','half','closed'):
        path = BUILD/'eyes'/f'{state}.png'
        Image.fromarray(crimson(np.array(Image.open(path).convert('RGBA')))).save(path)
    # These old .blend materials arrive with Blender 5's new shader Weight
    # socket at zero. Keep their actual source colour graph, but let it render.
    for material in bpy.data.materials:
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type=='BSDF_PRINCIPLED' and 'Weight' in node.inputs:
                    node.inputs['Weight'].default_value = 1.
    # Membranes retain the source grey/vein pixels and translucent alpha.
    for name in ('hassam_mesh_06','hassam_mesh_07'):
        for m in bpy.data.objects[name].data.materials:
            if m and m.use_nodes:
                bs = next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
                if bs:
                    for link in list(bs.inputs['Alpha'].links):
                        m.node_tree.links.remove(link)
                    bs.inputs['Alpha'].default_value = .48
                    m.diffuse_color = (*m.diffuse_color[:3],.48)
                    m.surface_render_method = 'DITHERED'

    for name in ('hassam_mesh_11','hassam_mesh_12','hassam_mesh_13'):
        split_shells(bpy.data.objects[name],regions_by_object[name])
    slots = json.loads(Path(str(TARGETS / 'Marth.weapons.json')).read_text(encoding='utf-8'))['weapons']
    for slot in slots:
        slot['replacement'] = 'Scizor source pincer: two original jaws and eye marks, uniformly scaled by 8, seated at the wrist; no sword-tip extension'
        slot['attachment'] = 'JOBJ_75'
    slots += [{'part':'scabbard','places':list(range(63,73)),'replacement':'omitted with anatomical sword','attachment':'JOBJ_75'},
              {'part':'sword_stowed','places':[73,74],'replacement':'omitted with anatomical sword','attachment':'JOBJ_75'}]
    (BUILD/'weapons_replaced.json').write_text(json.dumps(slots,indent=2),encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'build.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'edited.blend'))
    (ROOT/'edit-record.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Scizor v4 rebuilt from source with chest-seated shoulders and unextended source pincers')


if __name__=='__main__':
    main()
