"""Recover Unown X's eye using the accepted RGB565 bit-replication decoder."""
import sys
import numpy as np
from PIL import Image
from hsd_scene import Scene, pkx
from hsd_cmpr import cmpr

def expand(value):
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return np.array([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255.])


scene = Scene(pkx("unknown_x"))
root = scene.u32(scene.u32(scene.u32(scene.roots["scene_data"])))
found = {t["image"]: t for j in scene.joints(root) for d in j["dobjs"] for t in d["mobj"]["tobjs"]
         if tuple(t["size"]) == (40, 200) and t["fmt"] == 14}
if len(found) != 1:
    raise ValueError("Expected one Unown X CMPR eye atlas")
at = next(iter(found))
Image.fromarray(cmpr(scene.data[at:], 40, 200, expand=expand)).save(sys.argv[1])
