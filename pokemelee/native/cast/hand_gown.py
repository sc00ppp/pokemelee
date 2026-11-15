"""hand_gown.py <base.blend> <out.blend> <vanilla.blend> [--zig H] [--top Z]

Gardevoir's gown remade from Peach's own dress. Her gown is a shredded set of panels, a white outer shell and a green
lining, too coarse to bend the way the dress does; the dress's surface, with its weights, bends right in every move.
So the panels go, and the dress surface comes in below her waist, in her colours: the white with pleats, the green
reversed just inside it, which prep culls as a surface and its own back (sidedness.py).

--zig H raises every other hem point by H: her pointed hem. --vee Z opens the white at her front below Z, the lining and
her legs showing through. --drop names more of her own objects to take out."""

from cast_paths import WORK, TARGETS
import argparse
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

DRESS = ('Joint_0_Object_50', 'Joint_0_Object_51')
PANELS = tuple(f'sirnight_mesh_{n}' for n in ('07', '08', '09', '11', '12', '13', '17', '27', '28',
                                              '32', '33', '34', '35', '36', '37'))
BODY = ('sirnight_mesh_29', 'sirnight_mesh_10')      # her thighs and waist, under the gown
WHITE, GREEN = 'sirnight_mat_27', 'sirnight_mat_32'
LINED = 0.03        # how far inside the shell the lining lies
PLEATS = 8


def dress(vanilla):
    """(points, triangles, per-point {joint: weight}) of the dress, world space."""
    bpy.ops.wm.open_mainfile(filepath=vanilla)
    points, faces, weights = [], [], []
    for name in DRESS:
        ob = bpy.data.objects[name]
        groups = {g.index: g.name for g in ob.vertex_groups}
        base = len(points)
        for v in ob.data.vertices:
            points.append(tuple(ob.matrix_world @ v.co))
            weights.append({groups[g.group]: g.weight for g in v.groups if g.weight > 0})
        faces.extend([base + i for i in p.vertices] for p in ob.data.polygons)
    return np.array(points), faces, weights


def trim(points, faces, weights, top):
    """The surface below ``top``, each point once per use."""
    kept = [f for f in faces if points[f][:, 2].max() <= top]
    used = sorted({i for f in kept for i in f})
    new = {old: i for i, old in enumerate(used)}
    return points[used], [[new[i] for i in f] for f in kept], [weights[i] for i in used]


def normals(points, faces):
    """Per point, the smooth normal, sharing across points at one place (the halves' seams)."""
    _, place = np.unique(points.round(3), axis=0, return_inverse=True)
    n = np.zeros((place.max() + 1, 3))
    for f in faces:
        a, b, c = points[f[:3]]
        area = np.cross(b - a, c - a)
        n[place[f]] += area
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    return n[place]


def hem_points(points):
    """Hem points by their way round: index, azimuth."""
    hem = np.where(points[:, 2] < points[:, 2].min() + 0.35)[0]
    return hem[np.argsort(np.arctan2(points[hem, 0], -points[hem, 1]))]


def tuck(names, points, faces, inside):
    """Her own body's points that stand through the gown (the tops of her thighs), pulled ``inside`` under its surface."""
    tree = BVHTree.FromPolygons(points.tolist(), faces)
    moved = 0
    for name in names:
        ob = bpy.data.objects[name]
        for v in ob.data.vertices:
            at, normal, _, dist = tree.find_nearest(v.co)
            if (v.co - at).dot(normal) > -inside:
                v.co = at - normal * inside
                moved += 1
        ob.data.update()
    return moved


def cut_below(name, z):
    """The faces of ``name`` with a point below ``z``: a mesh mostly elsewhere, with a scrap of it on the gown."""
    import bmesh
    me = bpy.data.objects[name].data
    bm = bmesh.new()
    bm.from_mesh(me)
    gone = [f for f in bm.faces if min(v.co.z for v in f.verts) < z]
    n = len(gone)
    bmesh.ops.delete(bm, geom=gone, context='FACES')
    bm.to_mesh(me)
    bm.free()
    me.update()
    return n


def surface(name, points, faces, weights, uv, material, armature):
    me = bpy.data.meshes.new(name)
    me.from_pydata(points.tolist(), [], faces)
    me.update()
    me.materials.append(material)
    layer = me.uv_layers.new(name='UVMap')
    for loop in me.loops:
        layer.data[loop.index].uv = uv(loop.vertex_index)
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = armature
    for v, w in enumerate(weights):
        for joint, share in w.items():
            (ob.vertex_groups.get(joint) or ob.vertex_groups.new(name=joint)).add([v], share, 'REPLACE')
    return ob


def main():
    a = argparse.ArgumentParser()
    a.add_argument('base')
    a.add_argument('out')
    a.add_argument('vanilla')
    a.add_argument('--zig', type=float, default=0)
    a.add_argument('--top', type=float, default=9.6)
    a.add_argument('--vee', type=float, default=0)
    a.add_argument('--drop', default='')
    a = a.parse_args()
    points, faces, weights = trim(*dress(a.vanilla), a.top)
    if a.zig:
        _, place = np.unique(points.round(3), axis=0, return_inverse=True)
        hem = hem_points(points)
        order = list(dict.fromkeys(place[hem]))
        raised = {p for i, p in enumerate(order) if i % 2}
        for i in hem:
            if place[i] in raised:
                points[i, 2] += a.zig
    n = normals(points, faces)
    round_ = np.arctan2(points[:, 0], -points[:, 1])
    z = points[:, 2]
    bpy.ops.wm.open_mainfile(filepath=a.base)
    armature = bpy.data.objects['Armature']
    white, green = bpy.data.materials[WHITE], bpy.data.materials[GREEN]
    for name in PANELS + tuple(n for n in a.drop.split(',') if n):
        bpy.data.objects.remove(bpy.data.objects[name])
    pleat = 0.5 + 0.47 * np.cos(PLEATS * round_)
    shell = faces
    if a.vee:       # the opening narrows as it rises: a face stays out while it lies inside the V
        shell = [f for f in faces if not (points[f][:, 2].mean() < a.vee and
                                          abs(round_[f].mean()) < 0.5 * (1 - points[f][:, 2].mean() / a.vee) + 0.12
                                          and np.ptp(round_[f]) < 2)]
    surface('gown_shell', points, shell, weights, lambda v: (float(pleat[v]), 0.5), white, armature)
    surface('gown_lining', points - LINED * n, [f[::-1] for f in faces], weights,
            lambda v: (0.5, float(np.clip(z[v] / a.top, 0.02, 0.98))), green, armature)
    print('cut', cut_below('sirnight_mesh_23', 10), 'faces of her face mesh off the gown')
    print('tucked', tuck(BODY, points, faces, 0.2), 'body points under the gown')
    bpy.ops.wm.save_as_mainfile(filepath=a.out)
    print(f'gown: {len(points)} points, {len(faces)} faces, top {z.max():.2f}, hem radius '
          f'{np.hypot(*points[z < z.min() + .4][:, :2].T).max():.2f}')


main()
