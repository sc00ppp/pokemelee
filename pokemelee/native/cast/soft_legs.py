"""soft_legs.py <3-build> <Fighter>: blended rings at the hips and knees, the way Melee's own models skin them.

A hand port takes one joint per source bone, so a thigh sits rigid on its joint with a hard line at the hip and a thin
one at the knee. Any bend or twist there shears the triangles across that line: Swampert's pelvis shattered, Sceptile's
and Deoxys's legs read as twisted. This runs on the rounded build (after round_out, before hand_finish). Round each hip
and knee the skin crosses from the parent joint to the child over a short ring, measured along the leg. A pelvis on a
chest joint (PELVIS) goes to the hips first. Then every moved point is bound again through the fighter's idle matrices,
so idle stays exactly what it was, and only the bends change. Feet are left alone.
Ganondorf also has chest, shoulder and elbow rings, with surface-connected weight smoothing.
--bind-rings operates on edited.blend at fixed bind coordinates before the rounded idle pass."""

from cast_paths import WORK, TARGETS
import sys
from pathlib import Path

import bpy
import numpy as np

R = Path(str(WORK / ''))
ns = {'__name__': 'view_helpers'}
exec(compile((R / 'tools/hand_view.py').read_text(encoding='utf-8').rsplit('\nmain()', 1)[0], 'hand_view.py', 'exec'), ns)
C = ns['C']

CHAINS = {  # (hip, (thigh, knee, ankle), (thigh, knee, ankle))
    'DonkeyKong': (4, (6, 7, 9), (16, 17, 19)),
    'Sheik': (4, (6, 7, 9), (12, 13, 15)),
    'Samus': (4, (6, 7, 9), (13, 14, 16)),
    # 8/14 are ankle helpers; 9/15 are the actual foot joints.
    'Ganondorf': (4, (6, 7, 9), (12, 13, 15)),
}
ARMS = {'Ganondorf': ((20, 22, 23, 25), (64, 66, 67, 69))}
PELVIS = {'DonkeyKong': 26}        # the chest joint a port's pelvis was left on
SPANS = {'Samus': (.14, .16), 'DonkeyKong': (.42, 0), 'Ganondorf': (.20, .32)}
HIP_SPAN, KNEE_SPAN = .28, .2
REACH = 1.7                      # how far from the leg's axis a ring reaches, in leg radii
STEP = 8                         # weights in eighths: fewer distinct blends for the export
MOST = 3                         # joints per vertex


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def read(meshes):
    """Every place on the surface once, so coincident corners of different meshes keep one weight."""
    places = {}
    for ob in meshes:
        names = {g.index: int(g.name.split('_')[1]) for g in ob.vertex_groups if g.name.startswith('JOBJ_')}
        mw = np.array(ob.matrix_world)
        for v in ob.data.vertices:
            p = mw[:3, :3] @ np.array(v.co) + mw[:3, 3]
            key = tuple(p.round(4))
            w = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 1e-4}
            place = places.setdefault(key, dict(p=p, w=w, at=[]))
            place['at'].append((ob, v.index))
    return places


def idle_skin(fighter):
    rest = ns['rests'](fighter)
    frame = ns['frame'](fighter, 'Wait1-1')
    return {j: C @ m @ np.linalg.inv(rest[j]) @ np.linalg.inv(C) for j, m in frame.items() if j in rest}


def posed(p, w, skin):
    total = sum(v for v in w.values())
    return sum(v / total * (skin[j] @ np.r_[p, 1])[:3] for j, v in w.items())


def bind(q, w, skin):
    """The rest place that weights w skin to q in idle."""
    total = sum(v for v in w.values())
    m = sum(v / total * skin[j] for j, v in w.items())
    return (np.linalg.inv(m) @ np.r_[q, 1])[:3]


def blended(w, skin):
    total = sum(w.values())
    return sum(v / total * skin[j][:3, :3] for j, v in w.items())


def stored_normals(me):
    values = np.empty(len(me.loops) * 3)
    me.corner_normals.foreach_get('vector', values)
    return values.reshape(-1, 3)


def pelvis(places, joints, hip, chest):
    """Up the torso from the hips to the chest joint, the weight goes from one to the other."""
    span = joints[chest] - joints[hip]
    moved = 0
    for place in places.values():
        w = place['w']
        if w.get(chest, 0) < .5:
            continue
        up = float(smooth(((place['p'] - joints[hip]) @ span) / (span @ span)))
        if up < 1:
            share = w[chest]
            place['w'] = {**{j: v for j, v in w.items() if j != chest}, chest: share * up, hip: w.get(hip, 0) + share * (1 - up)}
            moved += 1
    return moved


def torso(places, joints, hip, chest):
    """Undo the port's torso-to-pelvis mapping without moving its idle surface."""
    axis=joints[chest]-joints[hip]
    moved=0
    for place in places.values():
        w=place['w'];share=w.get(hip,0)
        if share<1e-5:continue
        up=float(smooth(((place['p']-joints[hip])@axis)/(axis@axis)))
        if up<=0:continue
        place['w']={**w,hip:share*(1-up),chest:w.get(chest,0)+share*up};moved+=1
    return moved


def ring(places, joints, parent, child, tip, span, radius):
    """Move each place near joint `child` to its share of parent and child, by where it sits along the bone."""
    origin = joints[child]
    axis = joints[tip] - origin
    axis = axis / np.linalg.norm(axis)
    moved = 0
    for place in places.values():
        d = place['p'] - origin
        s = d @ axis
        if abs(s) >= span or np.linalg.norm(d - s * axis) > radius:
            continue
        w = place['w']
        kin = sum(v for j, v in w.items() if j in (parent, child))
        if kin < .5:     # something else's surface passing near: a tail, a hand, the other thigh
            continue
        share = float(smooth((s + span) / (2 * span)))
        other = {j: v for j, v in w.items() if j not in (parent, child)}
        new = {j: v for j, v in other.items()}
        new[child] = kin * share
        new[parent] = kin * (1 - share)
        place['w'] = new
        moved += 1
    return moved


def tidy(w,step=STEP,most=MOST):
    top = sorted(w.items(), key=lambda kv: -kv[1])[:most]
    total = sum(v for _, v in top)
    eighths = {j: round(v / total * step) for j, v in top}
    eighths = {j: n for j, n in eighths.items() if n}
    largest = max(eighths, key=eighths.get)
    eighths[largest] += step - sum(eighths.values())
    return {j: n / step for j, n in eighths.items()}


def relax_rings(places,meshes):
    """Make the ring field continuous on the actual joined surface.

    The imported bind has separately fitted pieces. Its axis cylinders can put
    neighboring points on opposite sides of a ring's eligibility threshold.
    Diffuse only around weight transitions before the idle-preserving rebind.
    """
    from collections import defaultdict
    neighbors=defaultdict(set)
    for ob in meshes:
        mw=np.array(ob.matrix_world)
        keys=[tuple((mw[:3,:3]@np.array(v.co)+mw[:3,3]).round(4)) for v in ob.data.vertices]
        for e in ob.data.edges:
            a,b=[keys[i] for i in e.vertices]
            if a!=b:neighbors[a].add(b);neighbors[b].add(a)
    for k,p in places.items():
        if p['locked']:p['w']=dict(p['was'])
    active=set()
    for k,near in neighbors.items():
        w=places[k]['w']
        if any(sum(abs(w.get(j,0)-places[n]['w'].get(j,0)) for j in set(w)|set(places[n]['w']))>.05 for n in near):active.add(k)
    for _ in range(2):active|={n for k in active for n in neighbors[k]}
    active={k for k in active if not places[k]['locked']}
    initial={k:dict(p['w']) for k,p in places.items()}
    for _ in range(24):
        updated={}
        for k in active:
            near=neighbors[k]
            if not near:continue
            w=defaultdict(float)
            for j,v in initial[k].items():w[j]+=.08*v
            for j,v in places[k]['w'].items():w[j]+=.42*v
            for n in sorted(near):
                for j,v in places[n]['w'].items():w[j]+=.5*v/len(near)
            updated[k]=dict(w)
        for k,w in updated.items():places[k]['w']=w
    print('continuous joint rings',len(active),'surface places',flush=True)


def main():
    build, fighter = Path(sys.argv[1]), sys.argv[2]
    # A diagnosed, already-folded joint needs its initial bind weights corrected
    # before rounding; the default remains the existing idle-preserving operation.
    bind_rings = '--bind-rings' in sys.argv
    filename = 'edited.blend' if bind_rings else 'build.blend'
    bpy.ops.wm.open_mainfile(filepath=str(build / filename))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    joints = {int(b.name.split('_')[1]): np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones
              if b.name.startswith('JOBJ_')}
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.users_scene
              and not o.name.startswith('eyes_')]
    protected_keys=set()
    if fighter == 'Ganondorf' and bpy.context.scene.get('machoke_idle_source_feet'):
        for ob in meshes:
            if ob.name in ('goriky_mesh_07','goriky_mesh_19','goriky_mesh_27','goriky_mesh_32','goriky_mesh_33'):
                protected_keys.update(tuple(np.array(v.co).round(4)) for v in ob.data.vertices)
        meshes = [o for o in meshes if o.name not in ('goriky_mesh_07', 'goriky_mesh_19', 'goriky_mesh_27',
                                                     'goriky_mesh_32', 'goriky_mesh_33')]
    places = read(meshes)
    skin = idle_skin(fighter)
    for place in places.values():
        place['idle'] = posed(place['p'], place['w'], skin)
        place['was'] = dict(place['w'])
        # A shared ankle boundary must remain on the same rigid source foot.
        place['locked'] = fighter == 'Ganondorf' and (tuple(place['p'].round(4)) in protected_keys or place['w'].get(53,0)>1e-7 or any(place['w'].get(j, 0) > .999 for j in (9, 15)))
    hip, *legs = CHAINS[fighter]
    hip_span, knee_span = SPANS.get(fighter, (HIP_SPAN, KNEE_SPAN))
    if fighter in PELVIS:
        print('pelvis', pelvis(places, joints, hip, PELVIS[fighter]), 'places', flush=True)
    if fighter=='Ganondorf' and not bind_rings:
        print('torso',torso(places,joints,4,18),'places rebound from pelvis to chest',flush=True)
    for thigh, knee, ankle in legs:
        length = np.linalg.norm(joints[knee] - joints[thigh])
        axis = (joints[knee] - joints[thigh]) / length
        on_thigh = [p['p'] - joints[thigh] for p in places.values() if p['w'].get(thigh, 0) > .5]
        radius = np.median([np.linalg.norm(d - (d @ axis) * axis) for d in on_thigh]) * REACH
        a = ring(places, joints, hip, thigh, knee, hip_span * length, radius * 1.3)
        b = ring(places, joints, thigh, knee, ankle, knee_span * length, radius)
        print(f'leg {thigh}: thigh {length:.2f}, reach {radius:.2f}; {a} places at the hip, {b} at the knee', flush=True)
    for collar, upper, elbow, wrist in ARMS.get(fighter, ()):
        length = np.linalg.norm(joints[elbow] - joints[upper])
        a = 0 if bind_rings else ring(places, joints, 18, collar, upper, length * .45, length * 1.15)
        b = 0 if bind_rings else ring(places, joints, collar, upper, elbow, length * .65, length * 1.1)
        c = ring(places, joints, upper, elbow, wrist, length * .45, length * .9)
        print(f'arm {upper}: {a} chest, {b} shoulder, {c} elbow places', flush=True)
    if fighter=='Ganondorf' and not bind_rings:relax_rings(places,meshes)
    normals = {ob: stored_normals(ob.data) for ob in meshes}
    carry = {ob: np.tile(np.eye(3), (len(ob.data.vertices), 1, 1)) for ob in meshes}
    for place in places.values():
        w = place['was'] if place['locked'] else tidy(place['w'],32,4) if fighter=='Ganondorf' else tidy(place['w'])
        same = set(w) == set(place['was']) and all(abs(w[j] - place['was'][j]) < 1e-3 for j in w)
        at = place['p'] if same or bind_rings else bind(place['idle'], w, skin)
        turn = np.eye(3) if same or bind_rings else blended(w, skin).T @ np.linalg.inv(blended(place['was'], skin)).T
        for ob, index in place['at']:
            mw = np.array(ob.matrix_world)
            carry[ob][index] = turn
            ob.data.vertices[index].co = np.linalg.inv(mw[:3, :3]) @ (at - mw[:3, 3])
            for g in list(ob.vertex_groups):
                try:
                    g.remove([index])
                except RuntimeError:
                    pass
            for j, v in w.items():
                name = f'JOBJ_{j}'
                (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([index], v, 'REPLACE')
    for ob in meshes:      # a point bound again turns with its new skin, so its shading in idle stays what it was
        me = ob.data
        me.update()
        index = np.empty(len(me.loops), int)
        me.loops.foreach_get('vertex_index', index)
        turned = np.einsum('nij,nj->ni', carry[ob][index], normals[ob])
        turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-9)
        me.normals_split_custom_set(turned.tolist())
        me.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(build / filename))
    print('soft legs', fighter, len(places), 'places', flush=True)


main()
