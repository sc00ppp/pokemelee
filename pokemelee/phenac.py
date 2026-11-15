"""Approved Phenac v7 procedural meshes and materials, from extracted Colosseum textures."""
from types import SimpleNamespace
import numpy as np
from PIL import Image
from . import stage_geometry as body
from . import stage_geometry as stage_make

Z, X = 55.0, 87.75
UPPER = body.outline([(X, 0), (X, -4), (73.75, -15), (73.75, -17.5), (60, -17.5), (60, -38)])       # the deck and the block under it, on the collision's lines
PIER = body.outline([(60, -38), (15, -60), (15, -135)])                                             # the collision's taper and its stem, down into the fountain's water
PIER_Z = 40.0
PLATFORMS = [(-55, -25, 25), (25, 55, 25)]
FALL = 0.22


def crop(box, size=None, gain=1.0):
    c = ATLAS.crop(box)
    if size:
        # The approved door plate was resized vertically first. Make the order
        # explicit: Pillow versions can choose a different separable pass order.
        if box == BLUE:
            c = c.resize((c.width, size[1]), Image.LANCZOS)
        c = c.resize(size, Image.LANCZOS)
    return np.asarray(c, float) * gain


def img(arr):
    return Image.fromarray(np.asarray(arr).clip(0, 255).astype('u1'))


def even(t, keep=0.1):
    """A crop with its broad light and dark taken out (the atlas shades its plaster toward the edges), so that repeated it shows no bands."""
    from scipy.ndimage import gaussian_filter
    low = gaussian_filter(t, (t.shape[0] / 5, t.shape[1] / 5, 0), mode='reflect')
    return t - (low - low.mean((0, 1))) * (1 - keep)


def solid(mask, least):
    """A line mask without its specks: only runs of at least so many pixels stay."""
    from scipy.ndimage import label
    lab, n = label(mask, structure=np.ones((3, 3)))
    sizes = np.bincount(lab.ravel())
    return (mask & (sizes[lab] >= least)).astype(float)


def mirrored(t, nx, ny=1):
    """A crop repeated by mirroring, so no seam shows where it meets itself."""
    row = np.concatenate([t if i % 2 == 0 else t[:, ::-1] for i in range(nx)], 1)
    return np.concatenate([row if j % 2 == 0 else row[::-1] for j in range(ny)], 0)


PLASTER = (354, 826, 506, 990)        # the city wall's plain white plaster
CREST = (176, 594, 368, 814)          # the same plaster with the city's crest cut into it
TRACES = (0, 880, 336, 1022)          # the same plaster where the wall meets the ground: the dark lines that rise out of it
BRICK = (192, 34, 448, 126)           # the terraces' sandstone courses
COBBLE = (192, 128, 416, 256)         # the fountain plaza
TILES = (192, 288, 320, 416)          # the pale paving round it, two tiles by two
SLAB = (448, 96, 576, 224)            # the yellow slabs of the paths and bridges
BLUE = (452, 228, 524, 412)           # a door's blue riveted plate


def face_image():
    """The side of the stage: the city wall. White plaster, the crest cut into it in the middle, the wall's own lines rising from its foot either side."""
    w, h = 768, 168
    px, py = w / (2 * X), h / 38.0
    p = even(crop(PLASTER))
    c = np.asarray(img(mirrored(p, 8, 2)).resize((w, h), Image.LANCZOS), float)
    if a.anime:     # one flat colour: the AniMelee build's flattening turns plaster's mottle into smears
        c[:] = p.mean((0, 1)) * 1.03
    # the crest, 30 units tall in the middle of the face; its cut lines are faint in the atlas, so they are deepened to read from the camera's distance
    ch = int(round(31 * py))
    cw = int(round(ch * (CREST[2] - CREST[0]) / (CREST[3] - CREST[1])))
    cr = crop(CREST, (cw, ch))
    base = np.asarray(img(cr).resize((max(cw // 12, 1), max(ch // 12, 1)), Image.BOX).resize((cw, ch), Image.BICUBIC), float)     # the plaster without its lines
    line = np.clip((base.mean(2) - cr.mean(2)) / 26.0, 0, 1)[..., None]                                                            # how much line each pixel holds
    if a.anime:
        line = solid(line[..., 0] > 0.36, 30)[..., None] / 0.62 * 0.9
    x0, y0 = (w - cw) // 2, int(round(3.5 * py))
    under = c[y0:y0 + ch, x0:x0 + cw]
    c[y0:y0 + ch, x0:x0 + cw] = under * (1 - line * 0.62) + np.array((120.0, 112, 84)) * line * 0.62
    # the lines at the wall's foot, on the block's lower edge either side of the crest (the block is x +-60)
    th = int(round(17 * py))
    tw = int(round(th * (TRACES[2] - TRACES[0]) / (TRACES[3] - TRACES[1])))
    tr = crop(TRACES, (tw, th))
    tb = np.asarray(img(tr).resize((max(tw // 16, 1), max(th // 16, 1)), Image.BOX).resize((tw, th), Image.BICUBIC), float)
    tl = np.clip((tb.mean(2) - tr.mean(2)) / 60.0, 0, 1)[..., None]
    if a.anime:
        tl = solid(tl[..., 0] > 0.35, 12)[..., None]
    for side in (-1, 1):
        xa = int(round((X + side * 39) * px)) - tw // 2
        t2 = tl if side < 0 else tl[:, ::-1]
        u = c[h - th:h, xa:xa + tw]
        c[h - th:h, xa:xa + tw] = u * (1 - t2) + np.array((98.0, 92, 40)) * t2
    c[:2] = c[:2] * 0.8                                 # a shadow line under the paving's edge
    return img(c)


def floor_image():
    """The moving floor (x +-70, z +-50): the fountain plaza's cobbles inside a border of the yellow path slabs."""
    w, h = 512, 256                                     # powers of two: it has mips
    px, pz = w / 140.0, h / 100.0
    cb = crop(COBBLE)                                   # the plaza's own tile, which repeats as it is
    k = 0.62 * w / 512
    c = np.asarray(img(np.tile(cb, (6, 4, 1))).resize((int(cb.shape[1] * 4 * k), int(cb.shape[0] * 6 * k)), Image.LANCZOS), float)[:h, :w].copy()
    sl = crop(SLAB, (int(8 * px), int(8 * px)))
    sw = sl.shape[0]
    top = mirrored(sl, w // sw + 1)[:, :w]
    c[:sw] = top
    c[-sw:] = top[::-1]
    side = np.rot90(mirrored(sl, h // sw + 1)[:, :h])
    c[:, :sw] = side
    c[:, -sw:] = side[:, ::-1]
    for r in (slice(sw, sw + 2), slice(h - sw - 2, h - sw)):      # a dark joint where slab meets cobble
        c[r, sw:w - sw] *= 0.72
    for r in (slice(sw, sw + 2), slice(w - sw - 2, w - sw)):
        c[sw:h - sw, r] *= 0.72
    return img(c)


def ring_tris(y=0.0, xi=70.0, zi=50.0, tile_=16.0):
    def q(x0, x1, z0, z1):
        def v(x, z):
            return (x, y, z, x / tile_, z / tile_, 1, 1, 1, 1)
        return [v(x0, z0), v(x1, z0), v(x1, z1), v(x0, z0), v(x1, z1), v(x0, z1)]
    return q(-X, X, -Z, -zi) + q(-X, X, zi, Z) + q(-X, -xi, -zi, zi) + q(xi, X, -zi, zi)


def pit_tris(depth=5.5, xi=70.0, zi=50.0, tile_=16.0):
    """Shows only while a form rises or sinks."""
    def v(x, y, z, s):
        return (x, y, z, (x + z) / tile_, y / tile_, s, s, s, 1)
    t = []
    for (x0, z0), (x1, z1) in (((-xi, -zi), (xi, -zi)), ((xi, -zi), (xi, zi)), ((xi, zi), (-xi, zi)), ((-xi, zi), (-xi, -zi))):
        t += [v(x0, 0, z0, .6), v(x1, 0, z1, .6), v(x1, -depth, z1, .4), v(x0, 0, z0, .6), v(x1, -depth, z1, .4), v(x0, -depth, z0, .4)]
    return t + [v(-xi, -depth, -zi, .35), v(xi, -depth, -zi, .35), v(xi, -depth, zi, .35), v(-xi, -depth, -zi, .35), v(xi, -depth, zi, .35), v(-xi, -depth, zi, .35)]


def housing(c, s, rim=5.0, deep=3.0):
    """The frame the screen sits in, c the middle of its picture. The picture is 110 x 70 at scale 1."""
    x, y, z = c
    hw, hh, r = 55 * s, 35 * s, rim * s
    top, back = z + 1.0 * s, z - deep * s

    def q(p0, p1, p2, p3, g=1.0):
        def v(p):
            return (*p, (p[0] + p[2]) / (60 * s), p[1] / (60 * s), g, g, g, 1)
        return [v(p0), v(p1), v(p2), v(p0), v(p2), v(p3)]
    ox, oy = hw + r, hh + r
    t = q((x - ox, y + oy, top), (x + ox, y + oy, top), (x + ox, y + hh, top), (x - ox, y + hh, top))
    t += q((x - ox, y - hh, top), (x + ox, y - hh, top), (x + ox, y - oy, top), (x - ox, y - oy, top))
    t += q((x - ox, y + hh, top), (x - hw, y + hh, top), (x - hw, y - hh, top), (x - ox, y - hh, top))
    t += q((x + hw, y + hh, top), (x + ox, y + hh, top), (x + ox, y - hh, top), (x + hw, y - hh, top))
    t += q((x - ox, y + oy, back), (x + ox, y + oy, back), (x + ox, y + oy, top), (x - ox, y + oy, top), 1.1)
    t += q((x - ox, y - oy, top), (x + ox, y - oy, top), (x + ox, y - oy, back), (x - ox, y - oy, back), 0.55)
    t += q((x - ox, y + oy, top), (x - ox, y + oy, back), (x - ox, y - oy, back), (x - ox, y - oy, top), 0.75)
    t += q((x + ox, y + oy, back), (x + ox, y + oy, top), (x + ox, y - oy, top), (x + ox, y - oy, back), 0.75)
    t += q((x - hw, y + hh, z - s), (x + hw, y + hh, z - s), (x + hw, y - hh, z - s), (x - hw, y - hh, z - s), 0.1)      # dark behind the picture
    return t


def stage():
    """The stage: the plaza's paving on top, the city wall for its side, a sandstone foot like the terraces', two path slabs for platforms."""
    ptop, pside = body.plat_tris(PLATFORMS, 10.0, 4.0, tile=20.0)
    foot = [(*v[:3], v[3] * 120 / 32, v[4] * 97 / 16, *v[5:]) for v in body.face_tris(PIER, PIER_Z, top=-38.0, fall=0.3)]       # a course every 4 units
    foot_side = [(*v[:4], v[4] * 2, *v[5:]) for v in body.under_tris(PIER, PIER_Z, tile=32.0)]
    return [body.piece(out, 'ring', ring_tris(), img(crop(TILES)), wrap='repeat'),
            body.piece(out, 'pit', pit_tris(), img(crop(BRICK, (128, 64), 0.7)), wrap='repeat'),
            body.piece(out, 'floor', body.top_tris(-70, 70, 50, y=0.02, nx=14, nz=10), floor_image(), joint=[5, 0]),
            body.piece(out, 'plat_top', ptop, img(crop(SLAB)), wrap='mirror', joint=[5, 1], minus_joint=True),
            body.piece(out, 'plat_side', pside, 'plat_top', wrap='mirror', joint=[5, 1], minus_joint=True),
            body.piece(out, 'face', body.face_tris(UPPER, Z, fall=FALL * 38 / 60), face_image(), mips=False),
            body.piece(out, 'under', body.under_tris(UPPER, Z), img(np.asarray(img(even(crop(PLASTER))).resize((128, 128), Image.LANCZOS), float) * 0.86), wrap='mirror'),
            body.piece(out, 'pier', foot, img(crop(BRICK, (128, 64), 0.8)), wrap='mirror'),
            body.piece(out, 'pier_side', foot_side, 'pier', wrap='mirror')]


# Where the city stands. The resting camera (file 0, 65, 310) is at EYE in the city's own units: just inside the south gate, 71 over the plaza, looking north.
# At K the stage's top is 45 city units over the plaza, which puts the plaza 112 file units under it: below the bottom blast line, so nothing of the city is
# ever between the camera and a fighter under the stage.
K = 2.5
EYE = np.array((0.0, 72.0, 305.0))      # 124 south of the fountain's middle, so the stage's foot stands in the fountain
REST = np.array((0.0, 65.0, 310.0))
CITY_T = (REST - K * EYE).tolist()


def city(p):
    """A point of the city (its own units) in stage file units."""
    return np.array(p, float) * K + np.array(CITY_T)


# Stadium's screen is a copy of the frame buffer, so it costs nothing to move. No towers: a board in a blue door-plate frame on two posts, standing on the
# upper terrace right of the mayor's house, where the match camera shows it with fighters close in the middle (tools/gamecam.py; round one's stood on a pier
# over the far dome).
SCREEN_AT = city((64.0, 66.0, -72.0))       # the middle of the picture
SCREEN_S = 0.9
TERRACE_Y = city((0, 34.0, 0))[1]
middle = SCREEN_AT


def posts(c, s):
    """Two posts from the terrace up to the board's frame."""
    x, y, z = c
    t = []
    for sx in (-1, 1):
        px = x + sx * 38 * s
        t += stage_make.box_tris((px - 2.5 * s, TERRACE_Y - 4, z - 5 * s), (px + 2.5 * s, y - 40 * s, z - 1 * s), colour=(0.86, 0.86, 0.82), tile=40.0)
    return t



def generate(atlas, output, anime=False):
    global ATLAS, out, a
    ATLAS = atlas.convert('RGB')
    out = str(output)
    a = SimpleNamespace(anime=anime)
    meshes = stage()
    meshes.append(body.piece(out, 'housing', housing(middle, SCREEN_S), img(crop(BLUE, (64, 128))), wrap='mirror'))
    meshes.append(stage_make.plain_piece(out, 'posts', posts(middle, SCREEN_S)))
    return meshes
