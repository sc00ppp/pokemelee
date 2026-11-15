"""deoxys_tex.py: every image in Deoxys's pkx, decoded by hsd_scene, on one sheet at 4x."""

from cast_paths import WORK, TARGETS
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(WORK / 'tools'))
from hsd_cmpr import cmpr
from hsd_scene import Scene, pkx

OUT = Path(str(WORK / 'hand/deoxys-Samus/look'))
OUT.mkdir(exist_ok=True)
d = pkx('deoxys')
s = Scene(d)
root = s.roots['scene_data']
js = s.joints(s.u32(s.u32(s.u32(root))))
seen = {}
for j in js:
    for dob in j['dobjs']:
        for t in dob['mobj']['tobjs']:
            seen.setdefault(t['image'], t['size'])
sheet = Image.new('RGBA', (1760, 900), (90, 90, 90, 255))
dr = ImageDraw.Draw(sheet)
x, y, row = 8, 8, 0
for img, (w, h) in seen.items():
    a = cmpr(s.data[img:], w, h)
    im = Image.fromarray(a, 'RGBA')
    im.save(OUT / f'img_{img:x}.png')
    k = 4 if w <= 128 else 2
    big = im.resize((w * k, h * k), Image.NEAREST)
    if x + big.width > 1750:
        x, y, row = 8, y + row + 22, 0
    bg = Image.new('RGBA', big.size, (255, 0, 255, 255))
    bg.alpha_composite(big)
    sheet.paste(bg, (x, y + 14))
    dr.text((x, y), f'{img:x} {w}x{h}', fill='white')
    x += big.width + 10
    row = max(row, big.height)
sheet.save(OUT / 'textures.png')
