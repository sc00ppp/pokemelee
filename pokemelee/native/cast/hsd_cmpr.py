"""hsd_cmpr.py <pkx bin> <image offset hex> <w> <h> <out.png>: one CMPR image out of a Colosseum model's HSD data."""

from cast_paths import WORK, TARGETS
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def rgb565(c):
    return np.array([((c >> 11) & 31) * 255 / 31, ((c >> 5) & 63) * 255 / 63, (c & 31) * 255 / 31, 255.0])


def cmpr(raw, w, h, expand=rgb565):
    """GameCube CMPR: 8x8 tiles of four DXT1 blocks, indices read from the top bit down."""
    out = np.zeros((h, w, 4), np.uint8)
    p = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for by, bx in ((0, 0), (0, 4), (4, 0), (4, 4)):
                c0, c1 = struct.unpack('>HH', raw[p:p + 4])
                a, b = expand(c0), expand(c1)
                if c0 > c1:
                    pal = [a, b, (2 * a + b) / 3, (a + 2 * b) / 3]
                else:
                    pal = [a, b, (a + b) / 2, np.zeros(4)]
                for y in range(4):
                    bits = raw[p + 4 + y]
                    for x in range(4):
                        px, py = tx + bx + x, ty + by + y
                        if px < w and py < h:
                            out[py, px] = pal[(bits >> (6 - 2 * x)) & 3]
                p += 8
    return out


if __name__ == '__main__':
    src, at, w, h, dest = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    d = Path(src).read_bytes()
    Image.fromarray(cmpr(d[0x60 + at:], w, h), 'RGBA').save(dest)
