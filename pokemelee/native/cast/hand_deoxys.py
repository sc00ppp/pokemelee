"""hand_deoxys.py <base.blend> <out.blend> <look dir>: Deoxys's hand port on Samus.

Rigswap read the blue arms' whole length onto her upper arm (his hand at her elbow) and put the orange tendrils rigid on
her forearm, where they fly. It also dropped the chest gem as a variant of its socket, and the rip lost the face's real
texture layers. Here each tube of the source is mapped along a new path by its centreline, so a tube keeps its shape,
taper and paddle tip. His four arms become two limbs: on each side the orange and blue tubes wind round her arm as a
double helix, then fork past the wrist into two tips. The hands and the cuffs follow the tube they sit on.
The face is baked from the pkx: layer 0 (the eye strip, through UV0, clamped) under layer 1 (the oval crystal, through
UV1, alpha masked). The gem comes back with layer 0 of its five. Samus has no blink, so the open eye is all there is."""

from cast_paths import WORK, TARGETS
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from PIL import Image

base, dest, look = sys.argv[1:4]
look = Path(look)
SOURCE = str(WORK / "mons" / 'deoxys/1-load/models/1-g3_deoxys.blend')
K = 10.5                    # across a tube, build units per source unit
BLUE_TIP = .25              # source length of the paddle, kept at BLUE_TIP_ALONG per unit
BLUE_TIP_ALONG = 12.0
TURNS = 1.5                 # to the fork. Sugimori's art has three crossings a side, loose, with gaps between them
PHASES = {'orange': 0, 'blue': np.pi}                   # at the root: orange from the shoulder, blue from the chest below
ROOT_R, HELIX_R, FORK_R = .5, .75, 1.05                 # the tube's line from the arm's: shoulder, along it, at the tip
RINGS = 30                  # along a tube, so it bends round the helix
WINDOW = .7                 # half a joint's bend, in build units
EYE, CRYSTAL = 'img_585c0.png', 'img_5cbe0.png'
GEM = 'img_5c8e0.png'
FACE_SIDE = 128
LEG_FROM, LEG_TO = (0, .6, 5.0, 6.0, 10.9, 13.4), (0, .6, 7.4, 8.6, 11.2, 13.4)     # heights: the knee ring onto hers
CUTS = (1.4, 2.4)           # new rings above the foot
ANKLE = (.6, 2.4)           # the foot's weight fades out between these heights
HEAD = ('deoxys_mesh_07', 'deoxys_mesh_10', 'deoxys_mesh_11')
TUBES = {'deoxys_mesh_01': 'orange L', 'deoxys_mesh_00': 'orange R', 'deoxys_mesh_09': 'blue L', 'deoxys_mesh_08': 'blue R'}
RIDERS = ('deoxys_mesh_19', 'deoxys_mesh_20', 'deoxys_mesh_21', 'deoxys_mesh_22')


def read(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    return co.reshape(n, 3), [tuple(e.vertices) for e in me.edges], [tuple(p.vertices) for p in me.polygons]


def islands(n, edges):
    seen, out = set(), []
    adj = {i: [] for i in range(n)}
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    for i in range(n):
        if i in seen:
            continue
        seen.add(i)
        stack, comp = [i], []
        while stack:
            k = stack.pop()
            comp.append(k)
            for m in adj[k]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        out.append(comp)
    return out


def centreline(points, edges):
    """Ring centres from the root to the tip, by graph distance from the tip vertex."""
    adj = {i: [] for i in range(len(points))}
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    tip = int(np.argmin(points[:, 2]))
    level = {tip: 0}
    queue = [tip]
    for k in queue:
        for m in adj[k]:
            if m not in level:
                level[m] = level[k] + 1
                queue.append(m)
    top = max(level.values())
    rings = [points[[v for v, l in level.items() if l == i]].mean(0) for i in range(top + 1)]
    c = np.array(rings[::-1])
    c[1:-1] = c[:-2] * .25 + c[1:-1] * .5 + c[2:] * .25
    return c


class Curve:
    """A polyline by arc length, with a frame carried along it."""

    def __init__(self, knots, start=None):
        knots = np.asarray(knots, float)
        seg = np.linalg.norm(np.diff(knots, axis=0), axis=1)
        arc = np.concatenate([[0], np.cumsum(seg)])
        self.length = arc[-1]
        self.arc = np.linspace(0, arc[-1], 240)
        self.at = np.column_stack([np.interp(self.arc, arc, knots[:, i]) for i in range(3)])
        t = np.gradient(self.at, axis=0)
        t /= np.linalg.norm(t, axis=1, keepdims=True)
        for _ in range(12):             # the polyline's corners rounded for the frame only
            t[1:-1] = (t[:-2] + 2 * t[1:-1] + t[2:]) / 4
        t /= np.linalg.norm(t, axis=1, keepdims=True)
        self.t = t
        n = np.zeros_like(t)
        if start is None:
            start = np.cross(t[0], [0, 1, 0])
        n[0] = start - start.dot(t[0]) * t[0]
        n[0] /= np.linalg.norm(n[0])
        for i in range(1, len(t)):
            m = n[i - 1] - n[i - 1].dot(t[i]) * t[i]
            n[i] = m / np.linalg.norm(m)
        self.n = n
        self.b = np.cross(t, n)

    def nearest(self, p):
        i = int(np.argmin(((self.at - p) ** 2).sum(1)))
        lo, hi = max(i - 1, 0), min(i + 1, len(self.arc) - 1)
        d = self.at[hi] - self.at[lo]
        u = np.clip((p - self.at[lo]).dot(d) / d.dot(d), 0, 1)
        return self.arc[lo] + u * (self.arc[hi] - self.arc[lo]), i

    def index(self, a):
        return int(np.clip(np.searchsorted(self.arc, a), 0, len(self.arc) - 1))


def turn(a, b):
    """The rotation taking unit a to unit b."""
    v = np.cross(a, b)
    c = a.dot(b)
    m = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + m + m @ m / (1 + c)


def lift(points, line):
    """Each point as its offset across the line and its arc along it, past the ends where the tip runs on."""
    out = np.empty_like(points)
    for v, p in enumerate(points):
        _, i = line.nearest(p)
        d = p - line.at[i]
        out[v] = d.dot(line.n[i]), d.dot(line.b[i]), line.arc[i] + d.dot(line.t[i])
    return out


def drop(lifted, length, new, along):
    """Lifted points set down on `new`: the same offset from the line, K times as big."""
    on = np.clip(lifted[:, 2], 0, length)
    arc = along(on)
    at, n, b, t = [np.column_stack([np.interp(arc, new.arc, f[:, k]) for k in range(3)]) for f in (new.at, new.n, new.b, new.t)]
    return at + K * (lifted[:, :1] * n + lifted[:, 1:2] * b + (lifted[:, 2:] - on[:, None]) * t * .2)


def rings(ob, lifted, every):
    """New rings across a tube, cut while its points are lifted, so each ring is square to the line. UVs interpolate."""
    place(ob, lifted)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for a in np.arange(every, lifted[:, 2].max(), every):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, a), plane_no=(0, 0, 1))
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(ob.data)
    bm.free()
    return read(ob)[0]


def helix(path, sign, phase, fork):
    """One tube's line round an arm's path, and each knot's arc on that path: it winds out from the shoulder at HELIX_R,
    stops winding at the fork, and leaves the path from there. sign mirrors the winding, so the arms match."""
    s = np.linspace(0, path.length, 720)
    c, n, b = [np.column_stack([np.interp(s, path.arc, f[:, k]) for k in range(3)]) for f in (path.at, path.n, path.b)]
    angle = (phase + np.clip(s / fork, 0, 1) * TURNS * 2 * np.pi)[:, None]
    r = (ROOT_R + (HELIX_R - ROOT_R) * blend(s, (0, 1.2)) + (FORK_R - HELIX_R) * blend(s, (fork, path.length)))[:, None]
    return c + r * (np.cos(angle) * n + sign * np.sin(angle) * b), s


def along_tube(src, new):
    a, b = src.length - BLUE_TIP, new.length - BLUE_TIP * BLUE_TIP_ALONG
    return lambda x: np.interp(x, [0, a, src.length], [0, b, new.length])


def blend(x, ends):
    """Smooth 0 to 1 across (lo, hi)."""
    t = np.clip((x - ends[0]) / (ends[1] - ends[0]), 0, 1)
    return t * t * (3 - 2 * t)


def arm_weights(a, cuts, joints):
    """Along an arm: one joint per stretch, shared across WINDOW at each cut."""
    w = {joints[0]: 1.0}
    for cut, joint in zip(cuts, joints[1:]):
        t = blend(a, (cut - WINDOW, cut + WINDOW))
        w = {k: x * (1 - t) for k, x in w.items()}
        w[joint] = t
    return {k: x for k, x in w.items() if x > .002}


def fold(source, build):
    """The rotation and scale taking one ring of the source onto the same ring of the build."""
    a, b = source - source.mean(0), build - build.mean(0)
    u, _, vt = np.linalg.svd(b.T @ a)
    d = np.sign(np.linalg.det(u @ vt))
    return u @ np.diag([1, 1, d]) @ vt, np.sqrt((b ** 2).sum() / (a ** 2).sum())


def legs(ob, source):
    """His knee ring lay 2.4 below hers, and nothing but one long cone lay between it and the foot. The heights are
    moved so the ring sits on her knee. The foot ring had come out turned against the knee ring, which wrung the shin
    into a ribbon, so it is placed again from the source, turned as the knee ring was. The shin is cut above the ankle,
    so a bent ankle turns the foot and not the whole cone. Only the shin takes new weights."""
    me = ob.data
    z = np.array([v.co[2] for v in me.vertices])
    co = np.array([v.co for v in me.vertices])
    co[:, 2] = np.interp(z, LEG_FROM, LEG_TO)
    for sign, ankle in ((1, (1.39, .81)), (-1, (-1.37, .85))):
        side = np.sign(co[:, 0]) == sign
        knee = np.where(side & (z > 4.9) & (z < 6.1))[0]
        foot = np.where(side & (z < .8))[0]
        turn_k, k = fold(source[knee], co[knee])
        s_knee, b_knee = source[knee].mean(0), co[knee].mean(0)
        now = (turn_k @ (source[foot] - s_knee).T).T
        was = now.mean(0)
        want = np.array([*ankle, .3]) - b_knee
        r = turn(was / np.linalg.norm(was), want / np.linalg.norm(want))
        now = (r @ now.T).T * k
        axis = want / np.linalg.norm(want)
        down = now @ axis
        now += np.outer(down * (np.linalg.norm(want) / (down.mean()) - 1), axis)
        co[foot] = now + b_knee
        co[foot, 2] -= co[foot, 2].min()
    me.vertices.foreach_set('co', co.ravel())
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    for cut in CUTS:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, cut), plane_no=(0, 0, 1))
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(me)
    bm.free()
    side = {g: ob.vertex_groups[g] for g in ('JOBJ_7', 'JOBJ_9', 'JOBJ_14', 'JOBJ_16')}
    for v in me.vertices:
        if v.co[2] > 7.3:
            continue
        shin, foot = ('JOBJ_7', 'JOBJ_9') if v.co[0] > 0 else ('JOBJ_14', 'JOBJ_16')
        t = 1 - blend(v.co[2], (ANKLE[0], ANKLE[1]))
        for g in list(v.groups):
            ob.vertex_groups[g.group].remove([v.index])
        if t < 1:
            side[shin].add([v.index], float(1 - t), 'REPLACE')
        if t > 0:
            side[foot].add([v.index], float(t), 'REPLACE')
    me.update()


def rig(ob, weights):
    ob.vertex_groups.clear()
    for v, w in enumerate(weights):
        for joint, share in w.items():
            (ob.vertex_groups.get(joint) or ob.vertex_groups.new(name=joint)).add([v], share, 'REPLACE')


def place(ob, points):
    me = ob.data
    me.vertices.foreach_set('co', points.ravel())
    if 'custom_normal' in me.attributes:
        me.attributes.remove(me.attributes['custom_normal'])
    me.update()


def sample(pic, u, v):
    """Bilinear, clamped: the GameCube's wrap for these layers. u, v in pixels of the picture."""
    h, w = pic.shape[:2]
    u, v = np.clip(u - .5, 0, w - 1), np.clip(v - .5, 0, h - 1)
    x0, y0 = np.floor(u).astype(int), np.floor(v).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (u - x0)[..., None], (v - y0)[..., None]
    return (pic[y0, x0] * (1 - fx) * (1 - fy) + pic[y0, x1] * fx * (1 - fy)
            + pic[y1, x0] * (1 - fx) * fy + pic[y1, x1] * fx * fy)


def bake_face(ob):
    """The face at FACE_SIDE, seen from the front: new UVs on one layer, the old two sampled through each triangle."""
    me = ob.data
    eye = np.array(Image.open(look / EYE).convert('RGBA'), float)
    crystal = np.array(Image.open(look / CRYSTAL).convert('RGBA'), float)
    uv0 = me.uv_layers['UVMap'].data
    uv1 = me.uv_layers['UVMap.001'].data
    co = np.array([v.co for v in me.vertices])
    lo, hi = co[:, [0, 2]].min(0), co[:, [0, 2]].max(0)
    span = (hi - lo) * 1.04
    mid = (lo + hi) / 2
    new = lambda p: (np.array([p[0], p[2]]) - mid) / span + .5
    pic = np.zeros((FACE_SIDE, FACE_SIDE, 3))
    done = np.zeros((FACE_SIDE, FACE_SIDE), bool)
    yy, xx = np.mgrid[0:FACE_SIDE, 0:FACE_SIDE]
    xx, yy = xx + .5, yy + .5
    plain = np.empty(len(me.loops) * 2)
    for poly in me.polygons:
        idx = list(poly.loop_indices)
        q = np.array([new(co[me.loops[i].vertex_index]) * [FACE_SIDE, FACE_SIDE] for i in idx])
        q[:, 1] = FACE_SIDE - q[:, 1]
        a0 = np.array([[uv0[i].uv[0] * eye.shape[1], (1 - uv0[i].uv[1]) * eye.shape[0]] for i in idx])
        a1 = np.array([[uv1[i].uv[0] * crystal.shape[1], (1 - uv1[i].uv[1]) * crystal.shape[0]] for i in idx])
        (ax, ay), (bx, by), (cx, cy) = q[:3]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-9:
            continue
        w0 = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / d
        w1 = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / d
        w2 = 1 - w0 - w1
        inside = (w0 >= -.02) & (w1 >= -.02) & (w2 >= -.02)
        if not inside.any():
            continue
        e = sample(eye, *[(w0 * a0[0, k] + w1 * a0[1, k] + w2 * a0[2, k])[inside] for k in (0, 1)])
        c = sample(crystal, *[(w0 * a1[0, k] + w1 * a1[1, k] + w2 * a1[2, k])[inside] for k in (0, 1)])
        al = c[..., 3:] / 255
        pic[inside] = c[..., :3] * al + e[..., :3] * (1 - al)
        done |= inside
    for _ in range(4):                  # edge pixels spread out, so filtering at a seam finds face and not black
        grow = ~done
        out = pic.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            s_done = np.roll(done, (dy, dx), (0, 1))
            hit = grow & s_done
            out[hit] = np.roll(pic, (dy, dx), (0, 1))[hit]
            done = done | hit
        pic = out
    path = look / 'face.png'
    Image.fromarray(pic.round().astype(np.uint8), 'RGB').save(path)
    for poly in me.polygons:
        for i in poly.loop_indices:
            uv0[i].uv = new(co[me.loops[i].vertex_index]).tolist()
    me.uv_layers.remove(me.uv_layers['UVMap.001'])
    return path


def picture(mat, path, name):
    """A material's texture swapped; the image is new, others sharing the old one keep it."""
    im = bpy.data.images.load(str(Path(path).resolve()))
    im.pack()
    im.name = name
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            node.image = im
        if node.type == 'UVMAP':
            node.uv_map = 'UVMap'


def main():
    bpy.ops.wm.open_mainfile(filepath=SOURCE)
    src = {n: read(bpy.data.objects[n]) for n in (*TUBES, *RIDERS, 'deoxys_mesh_05', 'deoxys_mesh_15', 'deoxys_mesh_12', 'deoxys_mesh_16')}
    gem_ob = bpy.data.objects['deoxys_mesh_15']
    gem_uv = [(gem_ob.data.uv_layers['UVMap'].data[i].uv[0], gem_ob.data.uv_layers['UVMap'].data[i].uv[1]) for i in range(len(gem_ob.data.loops))]
    gem_loops = [gem_ob.data.loops[i].vertex_index for i in range(len(gem_ob.data.loops))]

    bpy.ops.wm.open_mainfile(filepath=str(Path(base).resolve()))
    for n in (*TUBES, 'deoxys_mesh_05'):
        assert read(bpy.data.objects[n])[2] == src[n][2], n
    arm = bpy.data.objects['Armature']

    # paths, in build space, T pose. Shoulder, elbow, wrist, tip of her arm. Each side's frame starts up, so they mirror
    up = np.array([0, 0, 1.0])
    left = Curve([(1.5, .85, 18.0), (2.9, .85, 17.8), (6.05, .87, 17.8), (10.0, .79, 18.06), (12.4, .79, 18.06)], start=up)
    right = Curve([(-1.5, .85, 18.0), (-2.9, .85, 17.8), (-6.05, .84, 17.85), (-10.7, .77, 17.93), (-13.0, .75, 17.93)], start=up)
    arms = {'L': (left, 1, (1.42, 4.57, 8.52), ('JOBJ_21', 'JOBJ_26', 'JOBJ_27', 'JOBJ_28')),
            'R': (right, -1, (1.42, 4.57, 9.23), ('JOBJ_43', 'JOBJ_48', 'JOBJ_49', 'JOBJ_50'))}
    curves = {}
    for name, label in TUBES.items():
        points, edges, _ = src[name]
        line = Curve(centreline(points, edges))
        colour, side = label.split()
        path, sign, cuts, joints = arms[side]
        knots, on_path = helix(path, sign, PHASES[colour], cuts[-1])
        arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(knots, axis=0), axis=1))])
        target = Curve(knots)
        target = Curve(target.at, start=turn(line.t[0], target.t[0]) @ line.n[0])
        along = along_tube(line, target)
        # the helix is longer than the arm, and her joints cut the arm: weights go by the arc on the arm
        weights = lambda a, arc=arc, on_path=on_path, cuts=cuts, joints=joints: arm_weights(np.interp(a, arc, on_path), cuts, joints)
        curves[label] = line, target, along, weights
        ob = bpy.data.objects[name]
        lifted = rings(ob, lift(points, line), line.length / RINGS)
        place(ob, drop(lifted, line.length, target, along))
        rig(ob, [weights(along(a)) for a in np.clip(lifted[:, 2], 0, line.length)])
        print(label, name, 'source length %.2f' % line.length, 'new %.2f' % target.length, 'points', len(points), '->', len(lifted))

    # the hands and cuffs ride whichever tube they sit nearest
    for name in RIDERS:
        points, edges, _ = src[name]
        moved = points.copy()
        weights = [None] * len(points)
        for comp in islands(len(points), edges):
            mid = points[comp].mean(0)
            label = min(curves, key=lambda k: ((curves[k][0].at - mid) ** 2).sum(1).min())
            line, target, along, w = curves[label]
            lifted = lift(points[comp], line)
            moved[comp] = drop(lifted, line.length, target, along)
            arcs = np.clip(lifted[:, 2], 0, line.length)
            for v, a in zip(comp, arcs):
                weights[v] = w(along(a))
            print(name, 'island', len(comp), 'on', label, 'at %.2f' % (arcs.mean() / line.length))
        place(bpy.data.objects[name], moved)
        rig(bpy.data.objects[name], weights)

    legs(bpy.data.objects['deoxys_mesh_05'], src['deoxys_mesh_05'][0])

    # the head stood straight: the source's is rolled about 9 degrees
    face = bpy.data.objects['deoxys_mesh_10']
    co = np.array([v.co for v in face.data.vertices])
    mid = co[[9, 11, 13, 3]]
    roll = np.arctan2(mid[-1, 0] - mid[0, 0], mid[-1, 2] - mid[0, 2])
    c, s = np.cos(roll), np.sin(roll)
    pivot = np.array([0, .79, 19.25])
    for name in HEAD:
        ob = bpy.data.objects[name]
        p = np.array([v.co for v in ob.data.vertices]) - pivot
        place(ob, np.column_stack([p[:, 0] * c - p[:, 2] * s, p[:, 1], p[:, 0] * s + p[:, 2] * c]) + pivot)
    print('head roll undone: %.1f degrees' % np.degrees(roll))

    picture(bpy.data.materials['deoxys_mat_10'], bake_face(face), 'deoxys_face')

    # the gem, by the same map as the chest around it, into the middle of its socket
    fit = np.linalg.lstsq(np.column_stack([src['deoxys_mesh_12'][0], np.ones(len(src['deoxys_mesh_12'][0]))]),
                          np.array([v.co for v in bpy.data.objects['deoxys_mesh_12'].data.vertices]), rcond=None)[0]
    points, _, faces = src['deoxys_mesh_15']
    moved = np.column_stack([points, np.ones(len(points))]) @ fit
    ring = np.array([v.co for v in bpy.data.objects['deoxys_mesh_16'].data.vertices])
    moved += ring.mean(0) - moved.mean(0)
    mat = bpy.data.materials['deoxys_mat_16'].copy()
    mat.name = 'deoxys_mat_15'
    picture(mat, look / GEM, 'deoxys_gem')
    me = bpy.data.meshes.new('deoxys_mesh_15')
    me.from_pydata(moved.tolist(), [], faces)
    me.update()
    me.materials.append(mat)
    layer = me.uv_layers.new(name='UVMap')
    for i, loop in enumerate(me.loops):
        v = next(k for k in range(len(gem_loops)) if gem_loops[k] == loop.vertex_index)
        layer.data[i].uv = gem_uv[v]
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    ob = bpy.data.objects.new('deoxys_mesh_15', me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
    rig(ob, [{'JOBJ_20': 1.0}] * len(points))
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(dest).resolve()))
    print('saved', dest)


main()
