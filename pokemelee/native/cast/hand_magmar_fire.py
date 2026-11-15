"""hand_magmar_fire.py <build dir>: Magmar's tail flame, as its Colosseum sprite shows it. The game draws that flame as a
particle, so the rip's tail stops at a bare point. This adds a round flame about that point, on the tail's own joint, with
real texture coordinates so anim_fire.py has a picture to play. Writes edited.blend; round_out cuts it with the rest."""
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anim_fire  # noqa: E402

JOINT = 'JOBJ_4'
TAIL = 'boober_mesh_02'
SIDES = 8
WIDE, TALL = 64, 128
RADIUS, HEIGHT = 1.15, 3.4     # the sprite's flame is 8 by 11 pixels on a 50 pixel Magmar, here 14.4 tall
SINK = .6                      # how far below the tail's point the flame starts, so the point ends inside it
PROFILE = [(0, .28, 0), (.13, .78, 0), (.33, 1, .02), (.55, .84, .08), (.75, .48, .2), (.9, .18, .34), (1, .02, .42)]   # up, wide, lean back


def main():
    build = Path(sys.argv[1])
    picture = build / 'magmar-flame.png'
    colours = anim_fire.RAMP[anim_fire.flame_frames(WIDE, TALL)[0]]
    Image.fromarray(np.rint(colours * 255).astype('u1'), 'RGB').save(picture)
    bpy.ops.wm.open_mainfile(filepath=str(build / 'edited.blend'))
    tail = bpy.data.objects[TAIL]
    tip = np.array(max((tail.matrix_world @ v.co for v in tail.data.vertices), key=lambda c: c.y))

    corners, uv, faces = [], [], []
    for up, wide, lean in PROFILE:
        for side in range(SIDES):
            turn = 2 * np.pi * side / SIDES
            corners.append(tip + (RADIUS * wide * np.cos(turn), RADIUS * wide * np.sin(turn) + lean, HEIGHT * up - SINK))
    rings = len(PROFILE)
    for ring in range(rings - 1):
        for side in range(SIDES):
            a, b = ring * SIDES + side, ring * SIDES + (side + 1) % SIDES
            faces.extend([(a, b, b + SIDES), (a, b + SIDES, a + SIDES)])
    faces.extend((0, side + 1, side) for side in range(1, SIDES - 1))

    me = bpy.data.meshes.new('magmar_tail_flame')
    me.from_pydata([tuple(c) for c in corners], [], faces)
    material = bpy.data.materials.new('magmar_flame')
    material.use_nodes = True
    image = bpy.data.images.load(str(picture))
    image.pack()
    node = material.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    material.node_tree.links.new(node.outputs['Color'], material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    me.materials.append(material)
    layer = me.uv_layers.new(name='UVMap')
    for loop in me.loops:
        ring, side = divmod(loop.vertex_index, SIDES)
        layer.data[loop.index].uv = (abs(2 * side / SIDES - 1), PROFILE[ring][0])
    for face in me.polygons:
        face.use_smooth = True
    me.update()
    ob = bpy.data.objects.new('magmar_tail_flame', me)
    bpy.context.scene.collection.objects.link(ob)
    ob.modifiers.new('Armature', 'ARMATURE').object = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    ob.vertex_groups.new(name=JOINT).add(range(len(corners)), 1, 'REPLACE')
    bpy.ops.wm.save_as_mainfile(filepath=str(build / 'edited.blend'))
    print('flame', len(corners), 'verts at', tip.round(2))


main()
