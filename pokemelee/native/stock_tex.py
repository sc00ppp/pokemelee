"""Every costume's stock icon at its picture's own size, in an m-ex project, just before the export.

m-ex shrinks an icon to 24x24 when it imports one and keeps the picture it was given beside it, but it builds IfAll
from whatever the .tex holds, at that size (GenerateIfAll.Generate_Stc_icns, MexImage.ToTObj). The stock's wrap is clamp,
so any size draws. A sprite at its own pixels stays sharp where a 24x24 one turns to mush.
"""
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

CI4, RGB5A3 = 8, 2
SMALL = 24


def word(colour):
    """RGB5A3 for an opaque colour."""
    r, g, b = (int(c) >> 3 for c in colour)
    return 0x8000 | r << 10 | g << 5 | b


def tex(im):
    """A picture of at most 15 solid colours as m-ex's .tex: CI4 in 8x8 tiles, entry 0 clear."""
    px = np.array(im.convert('RGBA'))
    h, w = px.shape[:2]
    solid = px[..., 3] > 127
    colours = np.unique(px[solid][:, :3], axis=0)
    if len(colours) > 15:
        raise ValueError(f'{len(colours)} colours')
    index = np.zeros((h, w), np.uint8)
    for i, c in enumerate(colours, 1):
        index[solid & (px[..., :3] == c).all(2)] = i
    tall, wide = (h + 7) // 8 * 8, (w + 7) // 8 * 8
    grid = np.zeros((tall, wide), np.uint8)
    grid[:h, :w] = index
    tiles = grid.reshape(tall // 8, 8, wide // 8, 4, 2).transpose(0, 2, 1, 3, 4).reshape(-1, 2)
    image = (tiles[:, 0] << 4 | tiles[:, 1]).astype(np.uint8).tobytes()
    palette = struct.pack('>16H', *([0] + [word(c) for c in colours] + [0] * (15 - len(colours))))
    return b'TEX\0' + bytes([CI4, RGB5A3, 0, 0]) + struct.pack('<6I', w, h, 32, len(image), 32 + len(image), len(palette)) + image + palette


def project(proj_dir, log=print):
    done = 0
    for fj in sorted((Path(proj_dir) / 'data' / 'fighters').glob('*.json')):
        for costume in json.loads(fj.read_text(encoding='utf-8')).get('costumes') or []:
            base = Path(proj_dir) / 'assets' / (costume.get('icon') or '').replace('\\', '/')
            png = base.with_suffix('.png')
            if not png.is_file():
                continue
            im = Image.open(png)
            if im.width > SMALL or im.height > SMALL:
                base.with_suffix('.tex').write_bytes(tex(im))
                done += 1
    log(f'stock icons at full size: {done}')
    return done
