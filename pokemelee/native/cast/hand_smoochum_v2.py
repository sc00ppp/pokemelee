"""Replay the accepted source-proportioned Smoochum v2 finishing recipe."""
import inspect
import json
import sys
from cast_paths import WORK
ROOT = WORK
HOME = ROOT / 'hand/smoochum-Nana/v2'
BUILD = HOME / '3-build'
SCALE = 21.0

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')

def setup():
    import bpy
    import numpy as np
    from ics_runtime import enable, helpers, TARGETS
    enable()
    v = helpers('hand_view.py')
    C = v['C']
    rest, idle = v['rests']('Nana'), v['frame']('Nana', 'Wait1-1')
    skin = {j: C @ idle[j] @ np.linalg.inv(rest[j]) @ np.linalg.inv(C) for j in rest}
    return bpy, np, helpers, TARGETS, skin, {j: (C @ m)[:3, 3] for j, m in idle.items()}

def build():
    bpy, np, helpers, targets, skin, joints = setup()
    from mathutils import Matrix
    from rigswap.core import eyes
    BUILD.mkdir(parents=True, exist_ok=True)
    source = next((ROOT / 'mons/smoochum/1-load/models').glob('*.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(source))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    sb = {int(b.name.split('_')[1]): np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
    yaw = np.arctan2(skin[4][1, 0], skin[4][0, 0])
    rot = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1.]])
    # round_out's curved sole extends 0.1574 below the source's z=0 plane.
    # Place the whole source up by that depth plus 0.01 clearance. This is one
    # translation for every part: no foot flattening, stretching or ankle warp.
    origin = np.array([joints[4][0], joints[4][1], .168])
    eye = bpy.data.objects['muchul_mesh_02']
    rec = eyes.make_fixed(BUILD, [eyes.Surface(1, eye, 0, list(range(len(eye.data.polygons))), 'tex_2F10')],
                         {'tex_2F10': eyes._pixels(bpy.data.images['tex_2F10'])},
                         {'band': 48, 'half': [0, 96], 'closed': [0, 192]})
    write(BUILD / 'eyes.json', rec)

    def smooth(t):
        t = float(np.clip(t, 0, 1))
        return t*t*(3-2*t)

    def held(p, bone):
        if 5 <= bone <= 41:
            return {19: 1.}
        if 42 <= bone <= 49:
            start, tip, upper = (42,45,9) if bone <=45 else (46,49,24)
            axis = sb[tip]-sb[start]
            t = (p-sb[start]) @ axis / (axis @ axis)
            # The source arm remains short. No elbow/wrist reach fit. The root
            # joins the torso; a limited upper-arm share gives a compact gesture.
            share = .18*smooth((t+.15)/.90)
            return {4:1-share, upper:share}
        if 50 <= bone <= 59:
            foot = 45 if bone <55 else 39
            # Smoochum has foot lobes, not Nana-length thighs. Their upper rim
            # stays with the belly; the underside takes a limited ankle gesture.
            share = .22*smooth((.040-p[2])/.040)
            return {4:1-share, foot:share}
        # One rigid source torso: no independently bound cream/pink panel seam.
        return {4:1.}

    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.polygons)]
    rows, normals, source_pts = [], {}, {}
    for ob in meshes:
        ob.data.transform(ob.matrix_world)
        ob.parent = None
        ob.matrix_world = Matrix.Identity(4)
        normals[ob.name] = np.array([n.vector[:] for n in ob.data.corner_normals])
        source_pts[ob.name] = np.array([v.co[:] for v in ob.data.vertices])
        for vertex in ob.data.vertices:
            p = np.array(vertex.co)
            g = max(vertex.groups, key=lambda a:a.weight)
            bone = int(ob.vertex_groups[g.group].name.split('_')[1])
            rows.append((ob, vertex.index, p, held(p, bone)))
        for mod in list(ob.modifiers):
            ob.modifiers.remove(mod)
    # Source duplicate vertices must receive precisely the same position/weight.
    seams = {}
    for row in rows:
        seams.setdefault(tuple(row[2].round(6)), []).append(row)
    normal_xform = {}
    for same in seams.values():
        p = np.mean([r[2] for r in same], axis=0)
        w = {}
        for row in same:
            for j, share in row[3].items():
                w[j] = w.get(j,0) + share/len(same)
        w = {j:a for j,a in w.items() if a > 1e-6}
        total = sum(w.values())
        w = {j:a/total for j,a in w.items()}
        m = sum(a*skin[j] for j,a in w.items())
        q = origin + SCALE * (rot @ p)
        bound = np.linalg.solve(m, np.r_[q,1])[:3]
        linear = np.linalg.inv(m[:3,:3]) @ rot * SCALE
        for ob, vi, _, _ in same:
            ob.data.vertices[vi].co = bound
            normal_xform[ob.name,vi] = np.linalg.inv(linear).T
            for group in ob.vertex_groups:
                group.remove([vi])
            for j,a in w.items():
                name = f'JOBJ_{j}'
                (ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)).add([vi], a, 'REPLACE')
    bpy.data.objects.remove(arm, do_unlink=True)
    with bpy.data.libraries.load(str(targets/'Nana.blend'), link=False) as (_, data):
        data.objects = ['Armature']
    arm = data.objects[0]
    bpy.context.scene.collection.objects.link(arm)
    arm.name = 'Armature'
    bpy.context.view_layer.update()
    # The target armature library includes an unlinked Icosphere bone widget.
    # round_out enumerates all mesh datablocks, so keep only the source surfaces.
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH' and ob not in meshes:
            bpy.data.objects.remove(ob, do_unlink=True)
    for ob in meshes:
        ns = np.array([normal_xform[ob.name,l.vertex_index] @ normals[ob.name][l.index] for l in ob.data.loops])
        ns /= np.maximum(np.linalg.norm(ns,axis=1,keepdims=True),1e-9)
        ob.data.normals_split_custom_set(ns.tolist())
        ob.data.update()
        for g in list(ob.vertex_groups):
            if not g.name.startswith('JOBJ_'):
                ob.vertex_groups.remove(g)
        mod = ob.modifiers.new('Armature','ARMATURE')
        mod.object = arm
        ob.parent = arm
        ob.matrix_parent_inverse = arm.matrix_world.inverted()
        ob.matrix_world = Matrix.Identity(4)
        if ob.data.uv_layers:
            ob.data.uv_layers.active.name = 'UVMap'
    for im in bpy.data.images:
        if im.size[0] and not im.packed_file:
            im.pack()
    write(BUILD/'target.json', {'name':'Nana','skeleton':str(targets/'Nana.glb')})
    write(HOME/'design.json', {'source':str(source),'scale':SCALE,'head_scale':SCALE,'body_scale':SCALE,
          'arm_scale':SCALE,'foot_scale':SCALE,'idle':'Wait1-1','dropped':[],
          'arm_tip_upper_share':.18,'sole_ankle_share':.22,
          'grounding':'Uniform source placement z=0.168 compensates round_out sole bulge; final sole z~0.01. No shape or length fit.',
          'rounding':'round_out.py in idle space, source crease tags transported to idle first',
          'soft_legs':'No source thigh/shin spans Nana knees; compact source-lobe envelopes are authored here.',
          'recipe':'accepted Smoochum v2'})
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'base.blend'))
    bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'edited.blend'))
    print('Source geometry rebound at uniform scale',SCALE,'vertices',len(rows),flush=True)

def round_model():
    bpy, np, helpers, targets, skin, _ = setup()
    ns = helpers('round_out.py')
    ns['idle_skin'] = lambda fighter: skin
    original_tag = ns['tag_creases']
    def tag(meshes, rip):
        # Base normals are in bind space. The crease tags must be carried into
        # idle along with the surface before round_out reconstructs its shading.
        transported = {}
        for ob in meshes:
            matrices = ns['vertex_skins'](ob, skin)
            if np.min(np.abs(np.linalg.det(matrices[:,:3,:3]))) < 1e-10:
                bad = np.where(np.abs(np.linalg.det(matrices[:,:3,:3])) < 1e-10)[0]
                raise RuntimeError((ob.name,[(int(i),[(ob.vertex_groups[g.group].name,g.weight) for g in ob.data.vertices[i].groups]) for i in bad[:8]]))
            ids = np.array([l.vertex_index for l in ob.data.loops])
            values = np.einsum('nij,nj->ni',np.linalg.inv(matrices[ids,:3,:3]).transpose(0,2,1),rip[ob.name])
            transported[ob.name] = values / np.maximum(np.linalg.norm(values,axis=1,keepdims=True),1e-9)
        original_tag(meshes, transported)
    ns['tag_creases'] = tag
    # Existing BMesh helper's deform-layer allocation invalidates the old slice.
    code = inspect.getsource(ns['cut']).replace(
        'new = bm.verts[before:]\n    weights = bm.verts.layers.deform.verify()',
        'weights = bm.verts.layers.deform.verify()\n    new = bm.verts[before:]')
    exec(compile(code,'smoochum-round-cut','exec'),ns)
    sys.argv = ['round_out',str(BUILD),'--idle','Nana']
    ns['main']()

if __name__ == "__main__":
    build()
    round_model()
