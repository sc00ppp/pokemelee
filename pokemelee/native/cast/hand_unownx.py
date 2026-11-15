"""hand_unownx.py <template.blend> <out.blend> <eye atlas png> <work dir>: Unown X built by hand on Mr. Game & Watch.

No skeleton match: G&W is a normal skinned biped, not one mesh per pose. What the game does to him decides the shape
(decomp ftGw_Init.c, ftmaterial.c, ftdrawcommon.c; PlGw.dat):
- every model is flattened along model X to 0.01, on the root joint, after all the joints have moved: it is always
  drawn as its outline in the YZ plane, so a solid of revolution keeps its shape while his torso joints turn about Y
  by up to 120 degrees. A flat disc would foreshorten: the body has to be a ball.
- every material's diffuse is set to the costume's colour, black: textures that modulate come out black. That suits an
  Unown's body. Only a REPLACE texture on a CONSTANT material shows (hand_unownx_post.py).
- the grey outline is a second set of DObjs a little fatter than the first, drawn first in the outline colour.

So: a ball on the neck joint (J20), which turns least and stays in the plane, with the rip's eye on it; his own arm and
leg tubes as the X's four limbs, thickened, with club ends in place of his mitts and boots; and a hull of all of it.
Weights are his own.

The head turns 90 degrees about Y in down smash and forward throw, so the eye is on four sides. The two on +-X stand
proud and are the head's option models (hand_unownx_post.py), so up smash can drop them. The two on +-Z sit on the floor
of a pit in the ball: with the head a few degrees off straight, as it always is, a disc on the surface shows as a white
sliver at the rim, and the pit's wall hides it. A pit would cut the outline the game draws, so a flat fin in the plane
x = 0 gives the circle back; head on to a pit, the fin is edge-on and draws nothing."""

from cast_paths import WORK, TARGETS
import json
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image

GLB = str(TARGETS / 'GameAndWatch.glb')
CENTRE = np.array([0, 9.41, 0.0])       # J20's pivot: the ball stays put whichever way the head turns
RADIUS = 3.9
EDGE = 0.35                             # how much fatter the hull is, as vanilla's outline in game
LIMB = 1.3                              # limbs thickened by this
HULL_ARM, HULL_LEG = 1.37, 1.2          # his hull tubes (radius .59, .67) brought to the thick limb plus EDGE
EYE = 0.72                              # eye radius over ball radius, as the rip's
BALL_X = 0.8                            # the ball's depth: unseen in the plane, it gives the eye its room in depth
EYE_X = 3.95                            # the +-X eye: flattened to 0.01, this less RADIUS * BALL_X is all it stands proud
PIT_EYE, PIT_FLOOR = 1.5, 1.1           # the +-Z eye and the pit's floor: 1.2 below the rim hides it to 12 degrees off
HULL_X = 0.9
BLACK_UV = (0.02, 0.02)                 # a black corner of the eye picture, which the discs never reach
HEAD, HAND_L, HAND_R = 'JOBJ_20', 'JOBJ_14', 'JOBJ_29'
FOOT = {1: ('JOBJ_39', 'JOBJ_40'), -1: ('JOBJ_47', 'JOBJ_48')}


def glb_meshes():
    """{mesh node name: (game points, triangles, per-point {joint: weight})}."""
    b = Path(GLB).read_bytes()
    n = struct.unpack('<I', b[12:16])[0]
    g = json.loads(b[20:20 + n])
    start = 20 + n + 8

    def acc(i):
        a = g['accessors'][i]
        v = g['bufferViews'][a['bufferView']]
        at = start + v.get('byteOffset', 0) + a.get('byteOffset', 0)
        t = {5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[a['componentType']]
        c = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[a['type']]
        return np.frombuffer(b, t, a['count'] * c, at).reshape(-1, c)
    joints = [g['nodes'][j]['name'] for j in g['skins'][0]['joints']]
    out = {}
    for nd in g['nodes']:
        if 'mesh' not in nd:
            continue
        p = g['meshes'][nd['mesh']]['primitives'][0]
        at = p['attributes']
        w = acc(at['WEIGHTS_0'])
        j = acc(at['JOINTS_0'])
        weights = [{joints[int(a)]: float(x) for a, x in zip(ja, wa) if x > 0} for ja, wa in zip(j, w)]
        out[nd['name']] = (acc(at['POSITION']).astype(float), acc(p['indices']).astype(int).reshape(-1, 3), weights)
    return out


def to_blender(p):
    """Game (y up, +z front) to build space (+z up, -y front)."""
    return np.column_stack([p[:, 0], -p[:, 2], p[:, 1]])


class Part:
    """Points (game space), triangles, weights and UVs growing into one mesh."""

    def __init__(self):
        self.p, self.f, self.w, self.uv = [], [], [], []

    def add(self, points, faces, weights, uv=None):
        base = len(self.p)
        self.p.extend(map(tuple, points))
        self.f.extend([base + a, base + b, base + c] for a, b, c in faces)
        self.w.extend(weights)
        self.uv.extend(uv if uv is not None else [(0.5, 0.5)] * len(points))


def rings(profile, frame, weight, close=True, segments=24):
    """A surface of revolution: profile rows (s along the axis, radius), frame (origin, axis, a, b), weight(point row
    index) -> {joint: weight}. Ends close to a point. -> points, faces, weights."""
    o, ax, a, b = frame
    pts, wts, faces = [], [], []
    for r, (s, rad) in enumerate(profile):
        for k in range(segments):
            t = 2 * np.pi * k / segments
            pts.append(o + ax * s + rad * (np.cos(t) * a + np.sin(t) * b))
            wts.append(weight(r))
    for r in range(len(profile) - 1):
        for k in range(segments):
            i0, i1 = r * segments + k, r * segments + (k + 1) % segments
            j0, j1 = i0 + segments, i1 + segments
            faces += [(i0, i1, j1), (i0, j1, j0)]
    if close:
        for r, sign in ((0, 1), (len(profile) - 1, -1)):
            centre = len(pts)
            pts.append(o + ax * profile[r][0])
            wts.append(weight(r))
            for k in range(segments):
                i0, i1 = r * segments + k, r * segments + (k + 1) % segments
                faces.append((centre, i1, i0) if sign > 0 else (centre, i0, i1))
    return np.array(pts), faces, wts


def ball(radius):
    """The hull: rings round model X, so the outline the game draws is a ring's 40-gon."""
    n = 12      # even, so one ring is the equator
    profile = [(radius * np.cos(np.pi * i / n), radius * np.sin(np.pi * i / n)) for i in range(1, n)]
    frame = (CENTRE, np.array([-1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
    pts, faces, wts = rings(profile, frame, lambda r: {HEAD: 1.0}, segments=40)
    pts[:, 0] *= HULL_X
    return pts, faces, wts


def body():
    """The ball with a pit at +-Z: rings round Z, from one pit's floor up its wall, over the sphere, down the other."""
    r, rho = RADIUS, RADIUS * EYE
    rim = np.sqrt(r * r - rho * rho)
    start = np.arccos(rim / r)
    arc = [(-r * np.cos(t), r * np.sin(t)) for t in np.linspace(start, np.pi - start, 16)]
    profile = [(-PIT_FLOOR, rho)] + arc + [(PIT_FLOOR, rho)]
    frame = (CENTRE, np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
    pts, faces, wts = rings(profile, frame, lambda _: {HEAD: 1.0}, segments=24)
    pts[:, 0] *= BALL_X
    return pts, faces, wts


def fin(sign):
    """What the pit at ``sign`` * Z took off the circle, as a flat piece in the plane x = 0. It goes with the +-X eye,
    black from the picture's corner: in up smash, turned to the camera, it would cut across the pit's eye, and up smash
    drops that eye's DObj."""
    r = RADIUS
    rim = np.sqrt(r * r - (r * EYE) ** 2)
    start = np.arccos(rim / r)
    pts = [CENTRE + np.array([0, 0, sign * rim])]
    for t in np.linspace(-start, start, 15):
        pts.append(CENTRE + np.array([0, r * np.sin(t), sign * r * np.cos(t)]))
    n = len(pts)
    faces = [(0, i, i + 1) for i in range(1, n - 1)]
    faces += [(n, n + i + 1, n + i) for i in range(1, n - 1)]        # both sides, on points of its own: each gets culled
    return np.array(pts + pts), faces, [{HEAD: 1.0}] * (2 * n), [BLACK_UV] * (2 * n)


def eye_disc(axis, up, right, distance):
    """A flat disc of the eye, ``distance`` from the ball's middle towards ``axis``, the picture straight on and
    right-way-round from outside. ``right`` is the screen's right as seen from that side."""
    axis, up, right = map(lambda v: np.array(v, float), (axis, up, right))
    seg = 32
    middle = CENTRE + axis * distance
    pts, uv = [middle], [(0.5, 0.5)]
    for k in range(seg):
        t = 2 * np.pi * k / seg
        x, y = np.cos(t), np.sin(t)
        pts.append(middle + RADIUS * EYE * (right * x + up * y))
        uv.append((0.5 + 0.5 * x, 0.5 + 0.5 * y))
    faces = [(0, 1 + k, 1 + (k + 1) % seg) for k in range(seg)]
    if np.dot(np.cross(right, up), axis) < 0:
        faces = [(a, c, b) for a, b, c in faces]
    return np.array(pts), faces, [{HEAD: 1.0}] * len(pts), uv


def thicken(points, line, factor):
    """Tube points moved out from its centre line: line(p) -> the nearest centre point."""
    return np.array([line(p) + (p - line(p)) * factor for p in points])


def arm_line(side):
    y, z = (8.18, 0.0)

    def line(p):
        return np.array([p[0], y + 0.012 * (abs(p[0]) - 0.6), z])
    return line


def leg_line(side):
    def line(p):
        return np.array([0.52 * side, p[1], 0.0])
    return line


def arm_end(side, grow):
    """A club end from the wrist to where his fingers reach, as the X's limb ends, carried by the hand. Its start is
    round and on the wrist's pivot, so the arm tube's cut end stays inside it however the wrist bends."""
    wrist = np.array([4.8 * side, 8.2, 0.0])
    profile = [(-.56, .1), (-.48, .32), (-.28, .5), (0, .56), (.6, .56), (1.3, .66), (1.8, .78), (2.2, .8), (2.5, .68),
               (2.7, .42), (2.75, .15)]
    profile = [(s, r + grow) for s, r in profile]
    frame = (wrist, np.array([side, 0, 0.0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
    hand = HAND_L if side > 0 else HAND_R
    return rings(profile, frame, lambda r: {hand: 1.0}, segments=16)


def foot_end(side, grow):
    """A club foot in place of his boot: round at the heel, where the leg tube's cut end goes into it, forward to the
    toe, resting on the floor."""
    top = np.array([0.52 * side, 1.22, -0.12])
    toe = np.array([0.52 * side, 0.72, 1.45])
    ax = (toe - top) / np.linalg.norm(toe - top)
    a = np.cross(ax, [1.0, 0, 0])
    a /= np.linalg.norm(a)
    b = np.array([1.0, 0, 0])
    span = np.linalg.norm(toe - top)
    profile = [(-.60, .12), (-.52, .34), (-.32, .52), (0, .60), (.6, .60), (1.1, .62), (span, .64), (span + .35, .54),
               (span + .55, .30), (span + .62, .10)]
    profile = [(s, r + grow) for s, r in profile]
    ankle, tip = FOOT[side]

    def weight(r):
        at = profile[r][0]
        return {ankle: 1.0} if at <= .6 else {tip: 1.0} if at > 1.2 else {ankle: .5, tip: .5}
    return rings(profile, (top, ax, a, b), weight, segments=16)


def build():
    v = glb_meshes()
    fill, hull, eye, pit = Part(), Part(), Part(), Part()
    fill.add(*body())
    hull.add(*ball(RADIUS + EDGE))
    # his limbs: arm tubes 18 (left) and 37, hull 4 and 10; leg tubes 21 and 40, hull 7 and 13
    for side, tube, shell, ln, grown in ((1, 18, 4, arm_line, HULL_ARM), (-1, 37, 10, arm_line, HULL_ARM),
                                         (1, 21, 7, leg_line, HULL_LEG), (-1, 40, 13, leg_line, HULL_LEG)):
        for part, name, factor in ((fill, tube, LIMB), (hull, shell, grown)):
            p, f, w = v[f'Joint_0_Object_{name}']
            part.add(thicken(p, ln(side), factor), f.tolist(), w)
    for side in (1, -1):
        fill.add(*arm_end(side, 0.0))
        hull.add(*arm_end(side, EDGE))
        fill.add(*foot_end(side, 0.0))
        hull.add(*foot_end(side, EDGE))
    eye.add(*eye_disc((1, 0, 0), (0, 1, 0), (0, 0, -1), EYE_X))
    eye.add(*eye_disc((-1, 0, 0), (0, 1, 0), (0, 0, 1), EYE_X))
    eye.add(*fin(1))
    eye.add(*fin(-1))
    pit.add(*eye_disc((0, 0, 1), (0, 1, 0), (1, 0, 0), PIT_EYE))
    pit.add(*eye_disc((0, 0, -1), (0, 1, 0), (-1, 0, 0), PIT_EYE))
    return fill, hull, eye, pit


def solid_image(path, colour):
    Image.new('RGB', (8, 8), colour).save(path)
    return path


def material(name, image_path):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(Path(image_path).resolve()))
    tex.image.pack()
    tex.image.name = name
    mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


def mesh(name, part, mat, armature):
    me = bpy.data.meshes.new(name)
    me.from_pydata(to_blender(np.array(part.p)).tolist(), [], part.f)
    me.update()
    me.materials.append(mat)
    layer = me.uv_layers.new(name='UVMap')
    for loop in me.loops:
        layer.data[loop.index].uv = part.uv[loop.vertex_index]
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = armature
    for i, w in enumerate(part.w):
        for joint, share in w.items():
            (ob.vertex_groups.get(joint) or ob.vertex_groups.new(name=joint)).add([i], share, 'REPLACE')
    return ob


def eye_picture(atlas, out, twin):
    """Frame 0 of the rip's 40x200 atlas (open, half, nearly shut, shut, dizzy), sharpened up by resampling. ``twin`` is
    the same picture but for one corner pixel the discs never reach: the two eye materials must stay two."""
    im = Image.open(atlas).convert('RGB').crop((0, 0, 40, 40)).resize((128, 128), Image.LANCZOS)
    for x in (0, 120):
        for y in (0, 120):
            im.paste((0, 0, 0), (x, y, x + 8, y + 8))
    im.save(out)
    im.putpixel((0, 0), (200, 200, 200))
    im.save(twin)
    return out, twin


def main():
    template, dest, atlas, work = sys.argv[1:5]
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(template).resolve()))
    for ob in [o for o in bpy.data.objects if o.type != 'ARMATURE']:
        bpy.data.objects.remove(ob)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for i in list(bpy.data.images):
        bpy.data.images.remove(i)
    armature = bpy.data.objects['Armature']
    fill, hull, eye, pit = build()
    black = material('unown_black', solid_image(work / 'black.png', (0, 0, 0)))
    edge = material('unown_edge', solid_image(work / 'edge.png', (90, 90, 90)))
    side, front = eye_picture(atlas, work / 'eye.png', work / 'eye-pit.png')
    white = material('unown_eye', side)
    sunk = material('unown_pit', front)
    mesh('unown_fill', fill, black, armature)
    mesh('unown_hull', hull, edge, armature)
    mesh('unown_eye', eye, white, armature)
    mesh('unown_pit', pit, sunk, armature)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(dest).resolve()))
    print('fill', len(fill.p), 'hull', len(hull.p), 'eye', len(eye.p), 'pit', len(pit.p))


main()
