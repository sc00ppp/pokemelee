"""Decode GameCube CMPR blocks for the fixed recolor recipes."""
import struct
import numpy as np

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
