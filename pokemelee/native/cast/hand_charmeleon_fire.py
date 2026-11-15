"""Charmeleon's tail flame with real texture coordinates, so anim_fire.py has a texture to play.

The hand port's flame was two nested shapes in one flat colour each, every corner at one UV. This keeps the outer shape and
its skin weights, gives it the flame picture running root to tip and takes out the core, which the picture now paints. A
third bigger, about its root: the picture needs the room to read. hand/charmeleon-Roy/3-build stays; the result is fire/3-build.
"""

from cast_paths import WORK, TARGETS
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anim_fire  # noqa: E402

R = Path(str(WORK / ''))
HOME = R / 'hand/charmeleon-Roy'
OUT = HOME / 'fire/3-build'
SIDES = 8           # hand_charmeleon.flame: rings of eight corners, root first
RINGS = 5
GROW = 1.35
WIDE, TALL = 64, 128


def main():
    shutil.copytree(HOME / '3-build', OUT)
    picture = OUT / 'charmeleon-flame.png'
    colours = anim_fire.RAMP[anim_fire.flame_frames(WIDE, TALL)[0]]
    Image.fromarray(np.rint(colours * 255).astype('u1'), 'RGB').save(picture)
    bpy.ops.wm.open_mainfile(filepath=str(OUT / 'edited.blend'))
    bpy.data.objects.remove(bpy.data.objects['charmeleon_flame_core'], do_unlink=True)
    ob = bpy.data.objects['charmeleon_flame_outer']
    me = ob.data
    assert len(me.vertices) == SIDES * RINGS, len(me.vertices)
    co = np.array([v.co for v in me.vertices])
    root = co[:SIDES].mean(0)
    co = root + (co - root) * GROW
    me.vertices.foreach_set('co', co.ravel())
    uv = me.uv_layers.active.data
    for loop in me.loops:
        ring, side = divmod(loop.vertex_index, SIDES)
        uv[loop.index].uv = (abs(2 * side / SIDES - 1), ring / (RINGS - 1))
    image = bpy.data.images.load(str(picture))
    image.pack()
    node = next(n for n in me.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE')
    node.image = image
    me.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'edited.blend'))
    print('flame', len(me.vertices), 'verts, root', root.round(2))


main()
