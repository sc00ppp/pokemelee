"""hand_view.py <build.blend> <out.png> [--fighter Peach] [--parts] [--views side,front] <pose>...

A hand port's build posed in the fighter's real animation frames, with no Dolphin pass: each pose (rest, or a frame of
frames/<Fighter>/, as Run-6) a row, each view a column. --parts colours each object apart, to see the panels;
--cull draws one side of each face, as the game does.
Skinning is the game's: frame world * inverse rest world, read from <Fighter>.glb."""

from cast_paths import WORK, TARGETS
import argparse
import json
import random
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image

T = Path(str(TARGETS / ''))
C = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)    # game (y up, +z front) to Blender
TILE = 460


def _local(node):
    if 'matrix' in node:
        return np.array(node['matrix'], float).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0, 0, 0, 1])
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    m[:3, :3] = m[:3, :3] @ np.diag(node.get('scale', [1, 1, 1]))
    m[:3, 3] = node.get('translation', [0, 0, 0])
    return m


def rests(fighter):
    """{joint index: its rest world matrix}, game space."""
    b = (T / f'{fighter}.glb').read_bytes()
    n = struct.unpack('<I', b[12:16])[0]
    nodes = json.loads(b[20:20 + n])['nodes']
    out = {}

    def walk(i, parent):
        world = parent @ _local(nodes[i])
        name = nodes[i].get('name', '')
        if name.startswith('JOBJ_'):
            out[int(name[5:])] = world
        for c in nodes[i].get('children', []):
            walk(c, world)
    children = {c for nd in nodes for c in nd.get('children', [])}
    for i in range(len(nodes)):
        if i not in children:
            walk(i, np.eye(4))
    return out


def frame(fighter, pose):
    d = json.loads((T / 'frames' / fighter / f'{pose}.json').read_text())
    return {b['index']: np.array(b['matrix'], float).reshape(4, 4).T for b in d['bones']}


def skin_table(ob):
    """(world points, [vertex, joint, weight] rows) of a mesh."""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(n, 3)
    mw = np.array(ob.matrix_world)
    names = {g.index: g.name for g in ob.vertex_groups}
    rows = [(v.index, int(names[g.group][5:]), g.weight) for v in me.vertices for g in v.groups
            if names[g.group].startswith('JOBJ_') and g.weight > 0]
    return co @ mw[:3, :3].T + mw[:3, 3], rows


def posed(points, rows, moves):
    """Points moved by the weighted joints, in Blender space."""
    p = np.column_stack([points, np.ones(len(points))]) @ np.linalg.inv(C).T     # points as rows: x' = x @ M.T
    out, total = np.zeros((len(points), 4)), np.zeros(len(points))
    for v, j, w in rows:
        if j in moves:
            out[v] += w * (moves[j] @ p[v])
            total[v] += w
    held = total > 0
    out[held] /= total[held, None]
    out[~held] = p[~held]
    return (out @ C.T)[:, :3]


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    a = argparse.ArgumentParser()
    a.add_argument('blend')
    a.add_argument('out')
    a.add_argument('poses', nargs='+')
    a.add_argument('--fighter', default='Peach')
    a.add_argument('--parts', action='store_true')
    a.add_argument('--cull', action='store_true')
    a.add_argument('--views', default='side,front,back')
    a = a.parse_args(argv)
    a.out = str(Path(a.out).resolve())
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.blend).resolve()))
    from rigswap.core import render
    meshes = render._prepare_scene()
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = TILE
    scene.render.film_transparent = False
    scene.world = scene.world or bpy.data.worlds.new('w')
    scene.world.color = (0.28, 0.3, 0.34)
    scene.display.shading.background_type = 'WORLD' if hasattr(scene.display.shading, 'background_type') else None
    scene.display.shading.show_backface_culling = a.cull
    if a.parts:
        scene.display.shading.color_type = 'OBJECT'
        random.seed(3)
        for ob in meshes:
            ob.color = (random.random(), random.random(), random.random(), 1)
    tables = {}
    for ob in meshes:
        tables[ob.name] = skin_table(ob)
        for m in list(ob.modifiers):
            ob.modifiers.remove(m)
        ob.parent = None
        ob.matrix_world = np.eye(4).tolist()
    cam = bpy.data.objects.new('view', bpy.data.cameras.new('view'))
    scene.collection.objects.link(cam)
    cam.hide_render = False
    cam.data.type = 'ORTHO'
    scene.camera = cam
    rest = rests(a.fighter)
    views = a.views.split(',')
    sides = {'side': (-1, 0), 'side34': (-.85, -.5), 'front': (0, -1), 'back': (0, 1), 'other': (1, 0)}
    sheet = Image.new('RGB', (TILE * len(views), TILE * len(a.poses)), (20, 22, 28))
    tmp = Path(a.out).with_suffix('.tile.png')
    for r, pose in enumerate(a.poses):
        moves = {} if pose == 'rest' else {j: m @ np.linalg.inv(rest[j]) for j, m in frame(a.fighter, pose).items()
                                           if j in rest}
        spread = []
        for ob in meshes:
            pts = posed(*tables[ob.name], moves)
            ob.data.vertices.foreach_set('co', pts.ravel())
            ob.data.update()
            spread.append(pts)
        spread = np.concatenate(spread)
        lo, hi = spread.min(0), spread.max(0)
        mid = (lo + hi) / 2
        size = max(hi[2] - lo[2], np.linalg.norm(hi[:2] - lo[:2])) * 1.08
        for c, view in enumerate(views):
            dx, dy = sides[view]
            at = mid + np.array([dx, dy, 0]) * 60
            cam.location = at.tolist()
            cam.rotation_mode = 'XYZ'
            cam.rotation_euler = (np.pi / 2, 0, np.arctan2(dy, dx) + np.pi / 2 + np.pi * 0)
            cam.data.ortho_scale = float(size)
            cam.data.clip_end = 400
            scene.render.filepath = str(tmp)
            bpy.ops.render.render(write_still=True)
            sheet.paste(Image.open(tmp).convert('RGB'), (c * TILE, r * TILE))
    tmp.unlink(missing_ok=True)
    sheet.save(a.out)
    print('wrote', a.out, sheet.size)


main()
