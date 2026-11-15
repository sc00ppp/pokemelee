"""Stage bodies on their exact collision lines: an extruded outline with a top, a face, an underside band and platforms.
All in stage file units. The outline runs counter-clockwise from the front, from the left ledge, and closes at the right ledge."""
import os

import numpy as np

import struct
from PIL import Image


def outline(right):
    """A symmetric outline from its right half, ledge first."""
    return [(-x, y) for x, y in right] + [(x, y) for x, y in right[:0:-1]] + [right[0]]


def ear_clip(poly):
    pts = [np.array(p, float) for p in poly]
    idx = list(range(len(pts)))
    out = []

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for i in range(len(idx)):
            ia, ib, ic = idx[i - 1], idx[i], idx[(i + 1) % len(idx)]
            a, b, c = pts[ia], pts[ib], pts[ic]
            if cross(a, b, c) <= 1e-6:
                continue
            if any(cross(a, b, pts[q]) >= -1e-5 and cross(b, c, pts[q]) >= -1e-5 and cross(c, a, pts[q]) >= -1e-5
                   for q in idx if q not in (ia, ib, ic)):
                continue
            out += [a, b, c]
            idx.pop(i)
            break
    out += [pts[q] for q in idx]
    return out


def face_tris(line, z, top=0.0, fall=0.34):
    """Front and back. The picture spans the outline's bounds; the face darkens fall of its light toward the bottom."""
    xs, ys = [p[0] for p in line], [p[1] for p in line]
    x0, w = min(xs), max(xs) - min(xs)
    h = top - min(ys)
    t = []
    for zz in (z, -z):
        for q in ear_clip(line):
            s = 1.0 - fall * ((top - q[1]) / h)
            t.append((q[0], q[1], zz, (q[0] - x0) / w, (top - q[1]) / h, s, s, s, 1))
    return t


def under_tris(line, z, tile=40.0, seg=10.0):
    """The band round the outline, front to back: dark underneath, lit toward the sun on the sides."""
    t = []
    ld = np.array([-0.4, 0.8, 0.6]) / np.linalg.norm([-0.4, 0.8, 0.6])
    for i in range(len(line) - 1):
        a, b = np.array(line[i], float), np.array(line[i + 1], float)
        d = b - a
        ln = np.linalg.norm(d)
        if ln < 1e-3:
            continue
        n = np.array([d[1], -d[0]]) / ln
        shade = 0.5 if n[1] < -0.5 else 0.6 + 0.3 * max(0.0, n[0] * ld[0] + n[1] * ld[1])
        segs = max(1, int(np.ceil(ln / seg)))
        for s in range(segs):
            p0, p1 = a + d * s / segs, a + d * (s + 1) / segs
            s0, s1 = ln * s / segs, ln * (s + 1) / segs

            def v(p, zz, arc):
                return (p[0], p[1], zz, (zz + z) / tile, arc / tile, shade, shade, shade, 1)

            t += [v(p0, z, s0), v(p1, -z, s1), v(p1, z, s1), v(p0, z, s0), v(p0, -z, s0), v(p1, -z, s1)]
    return t


def top_tris(x0, x1, z, y=0.0, nx=12, nz=4, front=None):
    t = []
    w = x1 - x0

    def v(x, zz):
        return (x, y, zz, (x - x0) / w, (zz + z) / (2 * z), 1, 1, 1, 1)

    for i in range(nx):
        for k in range(nz):
            a, b = x0 + w * i / nx, x0 + w * (i + 1) / nx
            c, d = -z + 2 * z * k / nz, -z + 2 * z * (k + 1) / nz
            t += [v(a, c), v(b, c), v(b, d), v(a, c), v(b, d), v(a, d)]
    return t


def plat_tris(platforms, pz, pt, tile=32.0):
    """Returns (top faces, sides): slabs on the exact lines, the underside chamfered in."""
    top, side = [], []
    for x0, x1, y in platforms:
        c = 1.6
        tr = [(x0, y, -pz), (x1, y, -pz), (x1, y, pz), (x0, y, pz)]
        mid = [(x, y - pt * 0.6, z) for x, _, z in tr]
        bot = [(x0 + c, y - pt, -pz + c), (x1 - c, y - pt, -pz + c), (x1 - c, y - pt, pz - c), (x0 + c, y - pt, pz - c)]

        def vt(p, s):
            return (*p, p[0] / tile, (p[2] + pz) / (tile / 2), s, s, s, 1)

        for k in (0, 1, 2, 0, 2, 3):
            top.append(vt(tr[k], 1.0))
        for k in (0, 2, 1, 0, 3, 2):
            top.append(vt(bot[k], 0.42))
        for e in range(4):
            f = (e + 1) % 4
            ln = np.hypot(tr[f][0] - tr[e][0], tr[f][2] - tr[e][2])
            front = 1.0 if e == 2 else 0.8

            def vs(p, u, v, s):
                return (*p, u / tile, v, s, s, s, 1)

            side += [vs(tr[e], 0, 0, front), vs(mid[f], ln, 1, front), vs(tr[f], ln, 0, front),
                     vs(tr[e], 0, 0, front), vs(mid[e], 0, 1, front), vs(mid[f], ln, 1, front)]
            d = front * 0.6
            side += [vs(mid[e], 0, 1, d), vs(bot[f], ln, 0.6, d), vs(mid[f], ln, 1, d),
                     vs(mid[e], 0, 1, d), vs(bot[e], 0, 0.6, d), vs(bot[f], ln, 0.6, d)]
    return top, side


def piece(out, name, tris, image, wrap='clamp', mips=True, **kw):
    """One mesh and its picture into out; returns its cs spec entry. image may be a PIL image, or the name of a picture already written."""
    write_mesh(os.path.join(out, f'{name}.mesh'), tris)
    if isinstance(image, str):
        img = image
    else:
        img = name
        write_image(os.path.join(out, f'{name}.img'), image)
    return dict(name=name, mesh=f'{out}/{name}.mesh', tex=f'{out}/{img}.img', wrap=wrap, mips=mips, colors=True, **kw)


def write_mesh(path, verts):
    """verts: N x 9 floats px py pz u v r g b a, triangle list, stage file units."""
    v = np.asarray(verts, 'f4').reshape(-1, 9)
    with open(path, 'wb') as f:
        f.write(struct.pack('<i', len(v)))
        f.write(v.tobytes())

def write_image(path, im):
    """PIL image to int32 w, int32 h, BGRA bytes."""
    a = np.asarray(im.convert('RGBA'))
    with open(path, 'wb') as f:
        f.write(struct.pack('<ii', im.width, im.height))
        f.write(a[..., [2, 1, 0, 3]].tobytes())

LIGHT = (-0.35, 0.8, 0.5)

def _shade(n):
    import numpy as np
    l = np.array(LIGHT) / np.linalg.norm(LIGHT)
    return 0.5 + 0.5 * max(0.0, float(np.dot(n, l)))

def box_tris(lo, hi, colour=(1, 1, 1), tile=32.0):
    """A plain box, each face shaded by where it faces; its texture repeats every tile units."""
    import numpy as np
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    t = []
    for n, c in (((0, 0, 1), [(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)]), ((0, 0, -1), [(x1, y1, z0), (x0, y1, z0), (x0, y0, z0), (x1, y0, z0)]),
                 ((0, 1, 0), [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]), ((0, -1, 0), [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)]),
                 ((1, 0, 0), [(x1, y1, z1), (x1, y1, z0), (x1, y0, z0), (x1, y0, z1)]), ((-1, 0, 0), [(x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (x0, y0, z0)])):
        s = _shade(np.array(n, float))
        ax = [i for i in range(3) if n[i] == 0]
        q = [(*p, p[ax[0]] / tile, -p[ax[1]] / tile, colour[0] * s, colour[1] * s, colour[2] * s, 1) for p in c]
        t += [q[0], q[1], q[2], q[0], q[2], q[3]]
    return t

def plain_piece(out, name, tris):
    """Solids that are one colour each (their vertex colours): they share a white texture."""
    from PIL import Image
    return piece(out, name, tris, Image.new('RGB', (8, 8), (255, 255, 255)), wrap='repeat')
