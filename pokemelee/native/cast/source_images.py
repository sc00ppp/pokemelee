"""Write original model textures from the freshly imported source blend."""
import sys
from pathlib import Path
import bpy
import numpy as np
from PIL import Image

source, output = map(Path, sys.argv[1:3])
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source))
for image in bpy.data.images:
    if image.type == "RENDER_RESULT" or not image.size[0]:
        continue
    rgba = np.array(image.pixels[:]).reshape(image.size[1], image.size[0], 4)[::-1]
    pixels = np.uint8(np.clip(rgba, 0, 1) * 255)
    Image.fromarray(pixels).save(output / (image.name.replace("/", "_") + ".png"))
