"""main_colo.py: Melee's main menus (MnMaAll.usd: main, 1P, VS, Trophies, Options, Data) in Pokemon Colosseum's look.

A second pass after main_art.py. Slippi Dolphin patches MnMaAll.usd as the game loads it (Sys/GameFiles/GALE01/
MnMaAll.usd.diff, which builds Online Play and its menus), so every edit here is made on that patched file, the one the
game runs, and carried back to the disc file through the patch (slippi_patch.back): the disc file keeps its size and
only bytes the patch copies are touched. Bytes the patch writes itself cannot change; the report says which, if any.
What it changes:
  - the background: Melee's grid, swirls, rays and lettering give way to Colosseum's menu backdrop, big soft Poke Balls
    in deep indigo (the panel's grid tile becomes a quarter Poke Ball, mirrored both ways, coloured by its TEV
    registers and made opaque; the MenMainBack scene is hidden)
  - the menu frame: a solid plate border with bevels instead of Melee's see-through band, lit per menu in Colosseum's
    plate colours (purple, orange, gold, green, red: a DOL light table, so a Gecko code), the title tab solid too with a
    Poke Ball on its step
  - the buttons: Colosseum's battle-menu pills, a silver rim around a navy plate with a Poke Ball on the end cap; the
    selected one solid orange
  - the description box and the preview box: dark plates with silver rims
Button labels and menu titles stay Melee's: Slippi builds its own labels (Online Play, Ranked, Unranked, Direct, Teams,
Party) and its "Online Play" title from Melee's pictures and sets their colours (2026-11-12, tested in Dolphin), so the
rest of the text keeps Melee's lettering to match.

  python main_colo.py <disc MnMaAll.usd> <out MnMaAll.usd>     the whole pass on one file (report printed)
  python main_colo.py code                                     print the Gecko code
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slippi_patch

MENUGRAFT = MENUGRAFT
FONT = FONTS / 'seguibl.ttf'
CODE_NAME = 'PokeMelee Colosseum Menu Lights'
FILE = 'MnMaAll.usd'
SS = 4

# the menu light per colour index (mnmain.c mn_8022BFBC: 0 1P/main, 1 VS and rules, 2 Trophies, 3 Options, 4 Data)
LIGHT_TABLE = 0x804D4B50
LIGHTS = [(0x84, 0x4C, 0xFF), (0xFF, 0x84, 0x1E), (0xF0, 0xB4, 0x28), (0x2C, 0xC8, 0x3C), (0xF0, 0x3C, 0x46)]
MELEE_LIGHTS = bytes.fromhex('5A73FFFF FF5A41FF 0ED241FF F0C85AFF 9B41FFFF'.replace(' ', ''))

# buttons: texture-animation keys of MenMainCursor j2 (frame 0 unselected, 50 selected; the greys of the disabled frames
# 100 / 150 stay) give the colour of picture intensity 1; intensity 0 takes the TEV's tev0 register (Melee: black)
SILVER, ORANGE, NAVY = '#CDD2E6', '#FF8A1A', '10132E'
TEXKEYS = [
    {'model': 'MenMainCursor_Top_matanim_joint', 'joint': 2, 'track': 'KONST', 'frame': 0, 'rgb': SILVER},
    {'model': 'MenMainCursor_Top_matanim_joint', 'joint': 2, 'track': 'KONST', 'frame': 50, 'rgb': ORANGE},
]
# backdrop: TEV colour at picture intensity 0 and 1
BACK_DARK, BACK_LIGHT = '0A0926', '6870C4'
# plates (description box, preview box): material colour of the silver rim
PLATE = 'D2D6EE'

# MenMainBack joints that draw (all hidden: the backdrop is the panel's grid now). j13, j31, j55, j59, j87 take their
# flags from the patch itself, so they cannot be hidden from the disc; they are covered by the opaque backdrop or tiny.
BACK_HIDE = [3, 5, 7, 8, 9, 10, 11, 15, 16, 17, 18, 20, 21, 22, 23, 24, 25, 27, 28, 29, 32, 33, 34, 35, 36, 37, 38,
             39, 40, 41, 42, 44, 45, 46, 47, 48, 49, 50, 51, 53, 56, 57, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70,
             72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 88, 89, 90, 93, 94, 95, 96, 97, 98, 99, 100,
             101]
PANEL_ARCS = [6, 7, 24, 25]        # the big arcs behind the panel; j40's flags are the patch's: its picture is blanked


# ---------------------------------------------------------------------------------------------------------- drawing
def _font(px):
    return ImageFont.truetype(str(FONT), int(px))


def down(m):
    """supersampled coverage -> output pixels (box filter)"""
    h, w = m.shape[0] // SS, m.shape[1] // SS
    return m[:h * SS, :w * SS].reshape(h, SS, w, SS).mean(axis=(1, 3))


def ia(i, a):
    """intensity and alpha arrays (0..1) -> RGBA image (menugraft's IA / I encoders read (r+g+b)/3 and a)"""
    i8 = np.clip(np.round(i * 255), 0, 255).astype(np.uint8)
    a8 = np.clip(np.round(a * 255), 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([i8, i8, i8, a8]), 'RGBA')


def disc(cx, cy, r, w, h, ss=8):
    """coverage of a disc on a (h, w) grid, `ss` x `ss` samples a pixel"""
    ys, xs = np.mgrid[0:h * ss, 0:w * ss]
    d = np.hypot((xs + 0.5) / ss - cx, (ys + 0.5) / ss - cy)
    return (d <= r).reshape(h, ss, w, ss).mean(axis=(1, 3))


def band(cy, half, w, h, ss=8):
    ys = (np.arange(h * ss) + 0.5) / ss
    row = (np.abs(ys - cy) <= half).astype(np.float32).reshape(h, ss).mean(axis=1)
    return np.repeat(row[:, None], w, axis=1)


def pokeball(w, h, cx, cy, r, rim, bar, btn_r, btn_rim):
    """the Poke Ball's line work and parts as coverages: (body, lines, top half, button)"""
    body = disc(cx, cy, r, w, h)
    ring = body - disc(cx, cy, r - rim, w, h)
    knob_out, knob_in = disc(cx, cy, btn_r, w, h), disc(cx, cy, btn_r - btn_rim, w, h)
    bar_m = band(cy, bar / 2, w, h) * disc(cx, cy, r - rim * 0.5, w, h) * (1 - knob_out)
    lines = np.clip(ring + bar_m + (knob_out - knob_in), 0, 1)
    top = disc(cx, cy, r, w, h) * (1 - band(cy, bar / 2, w, h)) * (np.arange(h)[:, None] + 0.5 < cy)
    return body, lines, top, knob_in


def backdrop_tile(n=32, R=29.0, bar=3.2, ring_o=11.0, ring_i=7.5, ss=8):
    """the panel's grid tile (32x32 I4) as a quarter of a big Poke Ball, its centre on the (n, n) corner: the tile is
    mirrored both ways, so four tiles make one ball. Intensity picks between the TEV's two colours (BACK_DARK at 0,
    BACK_LIGHT at 1): the ball a little lighter towards its top and bottom, the band and the button ring dark, a thin
    bright rim"""
    acc = np.zeros((n, n))
    for sy in range(ss):
        for sx in range(ss):
            y = np.arange(n)[:, None] + (sy + .5) / ss
            x = np.arange(n)[None, :] + (sx + .5) / ss
            dy, dx = n - y, n - x
            r = np.hypot(dx, dy)
            body = r < R
            v = np.where(body, 0.36 + 0.24 * np.clip((dy - bar) / (R - bar), 0, 1), 0.0)
            v = np.where(body & (dy < bar), 0.12, v)
            v = np.where((r < ring_o) & (r >= ring_i), 0.12, v)
            v = np.where(r < ring_i, 0.50, v)
            v = np.where(body & (r > R - 1.4), 0.72, v)
            acc += v
    m = acc / (ss * ss)
    return ia(m, np.ones_like(m))


# ---------------------------------------------------------------------------------------------------------- buttons
# MenMainCursor j2 is every menu button: one mesh (Melee's: an arrow tip, a long middle, a round end cap and a soft halo
# ring fading to alpha 0) and a 64x48 IA4 picture, two texture-animation frames (unselected, selected). The mesh is
# rebuilt as a Colosseum plate: a rounded rectangle with a drop shadow. It owns position slots 4-51 and UV slots 0-47
# of the cursor model's shared arrays (the label, glow rings and flash use the others) and its own display list.
# Model units: x along the button, y up; the selection glow rings are centred on (6.32, -0.09).
BTN_X0, BTN_X1, BTN_YT, BTN_YB, BTN_R = -6.95, 7.12, 1.08, -1.16, 0.50
BTN_XA, BTN_XB = -5.80, 5.25          # the picture's left end (u 0..23/64) | stretched middle (23..25) | right end
BTN_BALL = (6.30, -0.09, 0.55)        # Poke Ball centre and radius, on the glow rings' centre
BTN_SHADOW = (0.10, -0.13, -0.10, 38)  # drop shadow offset x, y, z and vertex alpha (of 63)
BTN_POS0, BTN_POS, BTN_UV = 0xC24C0, 4, 0     # the shared arrays (patched file), the button's first slots
BTN_W, BTN_H = 64, 48
BTN_U = ((0, 23), (23, 25), (25, 64))         # picture columns of the three parts
BTN_ROW0 = 8.5     # picture row at the plate's top edge: rows 0-7 of the selected frame are bytes Slippi's patch shares
                   # with another texture (solid white), so the plate keeps off them and they stay as they are


def _btn_u(x):
    """model x -> picture u (0..1), piecewise linear over the three parts"""
    (a0, a1), (b0, b1), (c0, c1) = BTN_U
    x = np.asarray(x, np.float64)
    return np.where(x <= BTN_XA, a0 + (x - BTN_X0) / (BTN_XA - BTN_X0) * (a1 - a0),
           np.where(x <= BTN_XB, b0 + (x - BTN_XA) / (BTN_XB - BTN_XA) * (b1 - b0),
                    c0 + (x - BTN_XB) / (BTN_X1 - BTN_XB) * (c1 - c0))) / BTN_W


def _btn_v(y):
    return (BTN_ROW0 + (BTN_YT - np.asarray(y, np.float64)) / (BTN_YT - BTN_YB) * (BTN_H - BTN_ROW0)) / BTN_H


def _btn_x(col):
    """picture column (texel units, may be fractional) -> model x; the middle part reads as the button's middle"""
    (a0, a1), (b0, b1), (c0, c1) = BTN_U
    col = np.asarray(col, np.float64)
    return np.where(col < a1, BTN_X0 + (col - a0) / (a1 - a0) * (BTN_XA - BTN_X0),
           np.where(col < b1, 0.0, BTN_XB + (col - c0) / (c1 - c0) * (BTN_X1 - BTN_XB)))


def btn_outline():
    """the plate's columns: [(x, y_top, y_bottom)], corners as quarter circles"""
    cols = []
    angs = np.radians([0, 22.5, 45, 67.5, 90])
    for t in angs:
        cols.append((BTN_X0 + BTN_R * (1 - np.cos(t)), BTN_YT - BTN_R + BTN_R * np.sin(t), BTN_YB + BTN_R - BTN_R * np.sin(t)))
    cols += [(BTN_XA, BTN_YT, BTN_YB), (BTN_XB, BTN_YT, BTN_YB)]
    for t in angs[::-1]:
        cols.append((BTN_X1 - BTN_R * (1 - np.cos(t)), BTN_YT - BTN_R + BTN_R * np.sin(t), BTN_YB + BTN_R - BTN_R * np.sin(t)))
    return cols


def btn_sdf(x, y):
    """signed distance to the plate's edge (negative inside)"""
    cx, cy = (BTN_X0 + BTN_X1) / 2, (BTN_YT + BTN_YB) / 2
    hx, hy = (BTN_X1 - BTN_X0) / 2 - BTN_R, (BTN_YT - BTN_YB) / 2 - BTN_R
    qx, qy = np.abs(x - cx) - hx, np.abs(y - cy) - hy
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - BTN_R


def btn_shade(x, y, selected):
    """(intensity, alpha) of the plate at model points: intensity 1 takes the colour key (silver / orange), 0 navy"""
    d = btn_sdf(x, y)
    s = -d
    e = 1e-3
    ny = (btn_sdf(x, y + e) - btn_sdf(x, y - e)) / (2 * e)        # outward normal's y: +1 on the top edge
    cy = (BTN_YT + BTN_YB) / 2
    hy = (BTN_YT - BTN_YB) / 2
    t = np.clip((s - 0.06) / 0.14, 0, 1)
    rim = np.clip(0.52 + 0.30 * (1 - t) + 0.22 * ny, 0.30, 1.0)
    upper = y > cy + 0.04
    if selected:
        face = np.where(upper, 1.0 - 0.06 * (1 - (y - cy) / hy), 0.80 - 0.10 * (cy - y) / hy)
    else:
        face = np.where(upper, 0.20 + 0.12 * (y - cy) / hy, 0.07 + 0.03 * (y - (cy - hy)) / hy)
    I = np.where(s < 0.06, 0.0, np.where(s < 0.20, rim, np.where(s < 0.25, 0.04, face)))
    A = (s >= 0).astype(np.float64)
    bx, by, br = BTN_BALL
    r = np.hypot(x - bx, y - by)
    well = r < br + 0.07
    body = r < br
    band_ = np.abs(y - by) < 0.06
    top = y > by
    knob_o, knob_i = r < 0.20, r < 0.13
    if selected:
        ball = np.where(top, 0.82, 1.0)
        ball = np.where(band_ | (knob_o & ~knob_i) | (r > br - 0.08), 0.0, ball)
        ball = np.where(knob_i, 1.0, ball)
    else:
        ball = np.where(top, 0.92, 0.50)
        ball = np.where(band_ | (knob_o & ~knob_i) | (r > br - 0.07), 0.0, ball)
        ball = np.where(knob_i, 1.0, ball)
    I = np.where(body, ball, np.where(well, 0.0, I))
    return I, A


def button_picture(selected, ss=4):
    """the 64x48 IA4 button picture: every texel sampled ss x ss times at its own model points"""
    acc_i = np.zeros((BTN_H, BTN_W))
    acc_a = np.zeros((BTN_H, BTN_W))
    for sy in range(ss):
        for sx in range(ss):
            col = np.arange(BTN_W)[None, :] + (sx + 0.5) / ss + np.zeros((BTN_H, 1))
            row = np.arange(BTN_H)[:, None] + (sy + 0.5) / ss + np.zeros((1, BTN_W))
            x = _btn_x(col)
            y = BTN_YT - (row - BTN_ROW0) / (BTN_H - BTN_ROW0) * (BTN_YT - BTN_YB)
            i, a = btn_shade(x, y, selected)
            acc_i += i * a
            acc_a += a
    A = acc_a / (ss * ss)
    I = np.where(acc_a > 0, acc_i / np.maximum(acc_a, 1e-9), 0.0)
    return ia(I, A)


def button_mesh(h, log=print):
    """rewrite the button's vertices, UVs and display list in the patched file (a slippi_patch.Hsd)"""
    cols = btn_outline()
    jo = h.joints('MenMainCursor')[2]
    po = h.u32(h.dobjs(jo)[0] + 12)
    nblk = struct.unpack('>H', h.get(po + 0xE, 2))[0]
    dl = h.u32(po + 0x10)
    old = h.get(dl, nblk * 32)
    # keep Melee's winding: the sign of its first triangles (the strip flips every other one)
    n_old = struct.unpack('>H', old[1:3])[0]
    signs = []
    for k in range(n_old - 2):
        pts = []
        for m in range(3):
            pi = old[3 + 5 * (k + m)]
            pts.append([v / 2048 for v in struct.unpack('>3h', h.get(BTN_POS0 + 6 * pi, 6))][:2])
        (ax, ay), (bx, by), (qx, qy) = pts
        ar = (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
        if abs(ar) > 1e-3:
            signs.append(np.sign(ar) * (-1) ** k)
    want = np.sign(sum(signs))
    pos, uvs, strip_b, strip_s = [], [], [], []
    for x, yt, yb in cols:
        for y in (yt, yb):
            pos.append((x, y, 0.0))
            uvs.append((float(_btn_u(x)), float(_btn_v(y))))
    first = [(pos[k][0], pos[k][1]) for k in range(3)]
    ar = (first[1][0] - first[0][0]) * (first[2][1] - first[0][1]) - (first[1][1] - first[0][1]) * (first[2][0] - first[0][0])
    order = list(range(len(pos)))
    if np.sign(ar) != want:                       # swap top and bottom of each column
        order = [k ^ 1 for k in order]
    sx, sy, sz, sa = BTN_SHADOW
    shadow = [(x + sx, y + sy, sz) for x, y, _ in pos]
    allpos = shadow + pos
    if BTN_POS + len(allpos) > 52 or len(uvs) + 1 > 48:
        raise SystemExit('button mesh: too many vertices for its slots')
    for k, (x, y, z) in enumerate(allpos):
        h.put(BTN_POS0 + 6 * (BTN_POS + k), struct.pack('>3h', *(int(round(v * 2048)) for v in (x, y, z))))
    uv0 = h.u32(h.u32(po + 8) + 0x18 * 2 + 0x14)      # TEX0 array (third descriptor)
    for k, (u, v) in enumerate(uvs):
        h.put(uv0 + 4 * (BTN_UV + k), struct.pack('>2h', int(round(u * 8192)), int(round(v * 8192))))
    dark_uv = len(uvs)                                # the plate's dark outline texel, for the shadow
    h.put(uv0 + 4 * (BTN_UV + dark_uv), struct.pack('>2h', int(round(24 / BTN_W * 8192)), int(round(BTN_ROW0 / BTN_H * 8192))))
    col = lambda a: ((63 << 18) | (63 << 12) | (63 << 6) | a).to_bytes(3, 'big')
    out = bytearray()
    for part, base, alpha, uvi in (('shadow', BTN_POS, sa, None), ('plate', BTN_POS + len(shadow), 63, 0)):
        out += bytes([0x98]) + struct.pack('>H', len(order))
        for k in order:
            out += bytes([base + k]) + col(alpha) + bytes([BTN_UV + (dark_uv if uvi is None else k)])
    if len(out) > len(old):
        raise SystemExit('button mesh: display list too long')
    h.put(dl, bytes(out) + bytes(len(old) - len(out)))
    log(f'button mesh: {len(allpos)} vertices, {len(uvs) + 1} UVs, display list {len(out)} of {len(old)} bytes')


PANEL_BODY_I, PANEL_BODY_A = 0.30, 0.90
# the panel's corner bolts: radius, and the centre's distance in from the body's edges, in texels. The panel mesh draws
# the picture's corners (about 38 texels in from each side) at a sixth of its middle's scale, about 2 px a texel
BOLT_R, BOLT_IN = 6.5, 10.5


def bolt(w, h, cx, cy, r, ss=6):
    """a domed bolt head (coverage, intensity): lit from the upper left, with a dark ring round it"""
    cov, lum = np.zeros((h, w)), np.zeros((h, w))
    for sy in range(ss):
        for sx in range(ss):
            y = np.arange(h)[:, None] + (sy + .5) / ss
            x = np.arange(w)[None, :] + (sx + .5) / ss
            dx, dy = (x - cx) / r, (y - cy) / r
            d = np.hypot(dx, dy)
            inside = d < 1.0
            dome = 0.50 + 0.50 * np.clip(0.45 - 0.75 * (dx + dy), 0, 1)
            v = np.where(d >= 0.72, 0.05, dome)
            cov += inside
            lum += np.where(inside, v, 0)
    cov /= ss * ss
    return cov, np.where(cov > 0, lum / np.maximum(cov * ss * ss, 1e-6), 0)


def panel_colo(px):
    """the menu panel (MenMainPanel j43, 176x120 IA4, cut into the whole panel: its body, its frame and the title
    step). Melee's: a black body at 33% alpha, a light band at 53% between two solid lines. Colosseum's: a dark,
    nearly solid plate inside a solid metal rim (the band shaded as a rounded tube, both lines bright, a thin shadow
    just inside), the step's "///" stripes gone and a Poke Ball sitting on the step. The menu light colours all of it."""
    a = np.asarray(px, np.float32) / 255
    I, A = a[..., 0].copy(), a[..., 3].copy()
    I0, A0 = I.copy(), A.copy()
    h, w = I.shape
    fill_i, fill_a = I[5, 76], A[5, 76]            # a pixel between two stripes: the step's own band
    for y in range(2, 28):                          # rows 0-1 are the step's top line
        runs, x = [], 0
        while x < 112:
            if A[y, x] > 0.9:
                s = x
                while x < w and A[y, x] > 0.9:
                    x += 1
                runs.append((s, x))
            x += 1
        if len(runs) < 4:
            continue
        x0 = runs[0][1] + 1
        x1 = runs[4][0] - 1 if len(runs) > 4 else runs[3][1] + 1
        I[y, x0:x1], A[y, x0:x1] = fill_i, fill_a
    from scipy import ndimage
    near = lambda v, t: np.abs(v - t) < 0.035
    pure = {'out': A < 0.02,
            'body': near(A, 85 / 255) & (I < 0.035),
            'band': near(A, 136 / 255) & near(I, 238 / 255),
            'line': (A > 0.965) & (I > 0.965)}
    d_out = ndimage.distance_transform_edt(~pure['out'])
    d_body = ndimage.distance_transform_edt(~pure['body'])
    t = d_out / np.maximum(d_out + d_body, 1e-6)                      # 0 at the outside, 1 at the body
    tube = 0.42 + 0.48 * np.exp(-((t - 0.40) / 0.24) ** 2)              # lit from above the middle
    body_edge = ndimage.distance_transform_edt(pure['body'])            # inside the body: distance to its edge
    new = {'out': (np.zeros_like(I), np.zeros_like(I)),
           'body': (np.where(body_edge <= 2.0, 0.08, PANEL_BODY_I), np.full_like(I, PANEL_BODY_A)),
           'band': (tube, np.ones_like(I)),
           'line': (np.where(d_out < d_body, 1.0, 0.92), np.ones_like(I))}
    old = {'out': (0.0, 0.0), 'body': (0.0, 85 / 255), 'band': (238 / 255, 136 / 255), 'line': (1.0, 1.0)}
    names = list(pure)
    cls = np.full(I.shape, -1)
    for k, n in enumerate(names):
        cls[pure[n]] = k
    I2, A2 = np.zeros_like(I), np.zeros_like(I)
    for k, n in enumerate(names):
        I2 = np.where(cls == k, new[n][0], I2)
        A2 = np.where(cls == k, new[n][1], A2)
    for y, x in zip(*np.nonzero(cls < 0)):        # antialiased pixels: split between the two classes around them
        win = cls[max(0, y - 2):y + 3, max(0, x - 2):x + 3].ravel()
        win = win[win >= 0]
        cnt = np.bincount(win, minlength=len(names))
        k1, k2 = np.argsort(-cnt)[:2]
        if cnt[k2] == 0:
            k2 = k1
        (i1, a1), (i2, a2) = old[names[k1]], old[names[k2]]
        if abs(a1 - a2) > 0.05:
            c = np.clip((A[y, x] - a2) / (a1 - a2), 0, 1)
        elif abs(i1 - i2) > 0.05:
            c = np.clip((I[y, x] - i2) / (i1 - i2), 0, 1)
        else:
            c = 1.0
        ni1, na1 = new[names[k1]][0][y, x], new[names[k1]][1][y, x]
        ni2, na2 = new[names[k2]][0][y, x], new[names[k2]][1][y, x]
        aa = c * na1 + (1 - c) * na2
        A2[y, x] = aa
        I2[y, x] = (c * na1 * ni1 + (1 - c) * na2 * ni2) / aa if aa > 0 else 0
    I, A = I2, A2
    body, lines, top, knob = pokeball(w, h, 80.0, 14.5, 10.5, rim=1.8, bar=2.2, btn_r=3.8, btn_rim=1.5)
    I = I * (1 - body) + body * np.where(top > 0, 0.75, 1.0)
    A = A * (1 - body) + body * 1.0
    I = I * (1 - lines)
    A = np.maximum(A, lines)
    I = np.maximum(I, knob)
    # a bolt in each corner of the body, as on Colosseum's plates
    body_px = pure['body']
    ys, xs = np.nonzero(body_px)
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        k = np.argmax(sx * xs + sy * ys)                       # the body's corner on that diagonal
        px_, py_ = xs[k], ys[k]
        rows = body_px[min(py_, py_ - 14 * sy):max(py_, py_ - 14 * sy) + 1]
        cols = body_px[:, min(px_, px_ - 14 * sx):max(px_, px_ - 14 * sx) + 1]
        xe = (np.nonzero(rows.any(0))[0].min() if sx < 0 else np.nonzero(rows.any(0))[0].max())
        ye = (np.nonzero(cols.any(1))[0].min() if sy < 0 else np.nonzero(cols.any(1))[0].max())
        c, v = bolt(w, h, xe - sx * BOLT_IN, ye - sy * BOLT_IN, BOLT_R)
        I = I * (1 - c) + c * v
        A = A * (1 - c) + c
    # pixels that stay invisible keep their old bytes (the picture's first tile is also copied into a Slippi texture)
    I = np.where((A < 1e-3) & (A0 < 1e-3), I0, I)
    return ia(I, A)


def plate_box(px):
    """a nine-sliced box (description box, preview box; IA4): its rim kept as full intensity (the material's silver),
    its inside a dark, nearly opaque plate"""
    a = np.asarray(px, np.float32) / 255
    I, A = a[..., 0], a[..., 3]
    # Melee's box is a bright rim (intensity i_rim, alpha a_rim) over a black inside (alpha a_in), antialiased against
    # each other and against the outside: split every pixel into rim and inside coverage, then redraw both
    a_rim = A[I > 0.5].max()
    i_rim = np.median(I[(A >= a_rim - 1e-3) & (I > 0.5)])
    a_in = np.median(A[(I < 0.02) & (A > 0.05)])
    c_rim = np.clip(I * A / (i_rim * a_rim), 0, 1)
    c_in = np.clip((A - c_rim * a_rim) / a_in, 0, 1 - c_rim)
    A2 = c_rim * 1.0 + c_in * 0.92
    I2 = np.where(A2 > 0, (c_rim * 1.0 + c_in * 0.92 * 0.12) / np.maximum(A2, 1e-6), 0)
    return ia(I2, A2)


def preview_box(px):
    """the preview box (j60/j65, 48x96 IA4): Melee's chevron down the left side filled in to a straight edge and the
    square left corners rounded like the right ones, then drawn as a plate"""
    a = np.asarray(px).copy()
    h, w = a.shape[:2]
    plain = a[h // 8].copy()                                  # a row of rim, inside, rim
    c = w // 4                                                # the right corners' width
    for r in range(h):
        if (a[r, -c:] == plain[-c:]).all() and not (a[r] == plain).all():
            a[r] = plain                                      # a row of the chevron (its tip reaches past the middle)
    a[:, :c] = a[:, ::-1][:, :c]                              # the left corners mirror the right ones
    return plate_box(Image.fromarray(a, 'RGBA'))


def blank(px):
    a = np.asarray(px)
    return ia(np.zeros(a.shape[:2]), np.zeros(a.shape[:2]))


# ---------------------------------------------------------------------------------------------------------- the pass
def _load(dump, e):
    return Image.frombytes('RGBA', (e['width'], e['height']), (Path(dump) / f'{e["md5"]}.bgra').read_bytes(), 'raw', 'BGRA')


def _pictures(dump):
    """{md5: (manifest entry, new RGBA)} for a menugraft dump of the patched file"""
    man = json.loads((Path(dump) / 'manifest.json').read_text())
    by_use = {}
    for e in man:
        for u in e['uses']:
            by_use[u] = e

    def at(use):
        if use not in by_use:
            raise SystemExit(f'MnMaAll: no picture at {use}')
        return by_use[use]

    pics = {}

    def put(e, im):
        if im.size != (e['width'], e['height']):
            raise SystemExit(f'{e["md5"]}: drew {im.size}, the file has {e["width"]}x{e["height"]}')
        if e['format'] in ('IA4', 'IA8'):
            # texels invisible before and after keep their old bytes: Slippi's patch copies some runs of them into
            # its own textures as well, so changing them would be refused (or change those)
            new, old = np.asarray(im).copy(), np.asarray(_load(dump, e))
            keep = (new[..., 3] < 8) & (old[..., 3] < 8)
            new[keep] = old[keep]
            im = Image.fromarray(new, 'RGBA')
        pics[e['md5']] = (e, im)

    btn = 'MenMainCursor_Top_matanim_joint j2 m0 a0'
    for f, sel in (('f0', False), ('f1', True)):
        e = at(f'{btn} {f}')
        new, old = np.asarray(button_picture(selected=sel)).copy(), np.asarray(_load(dump, e))
        new[:int(BTN_ROW0)] = old[:int(BTN_ROW0)]          # rows the plate keeps off
        put(e, Image.fromarray(new, 'RGBA'))
    panel = 'MenMainPanel_Top_joint'
    put(at(f'{panel} j1 d0 t0'), backdrop_tile())
    plate = at(f'{panel} j43 d0 t0')
    put(plate, panel_colo(_load(dump, plate)))
    e = at(f'{panel} j60 d0 t0')
    put(e, preview_box(_load(dump, e)))
    e = at(f'{panel} j77 d0 t0')
    put(e, plate_box(_load(dump, e)))
    arc = at(f'{panel} j40 d0 t0')
    put(arc, blank(_load(dump, arc)))
    nxt = at(f'{panel} j74 d0 t0')           # "NEXT SCREEN" down the preview box (the game shows j74 itself)
    put(nxt, blank(_load(dump, nxt)))
    return pics


def design(tgt, work, log=print):
    """the patched file (bytes) -> the patched file as it should be"""
    work = Path(work)
    dump, art = work / 'mnmaall-dump', work / 'main-colo-art'
    src, out = work / 'MnMaAll-target.usd', work / 'MnMaAll-target-colo.usd'
    for d in (dump, art):
        shutil.rmtree(d, ignore_errors=True)
    art.mkdir(parents=True)
    src.write_bytes(tgt)
    r = subprocess.run([str(MENUGRAFT), 'dump', str(src), str(dump)], capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise SystemExit(f'menugraft dump of the patched MnMaAll failed: {r.stderr[-300:]}')
    images = []
    for md5, (e, im) in _pictures(dump).items():
        p = art / f'{md5}.bgra'
        p.write_bytes(im.tobytes('raw', 'BGRA'))
        im.save(art / f'{md5}.png')
        images.append({'md5': md5, 'bgra': str(p), 'width': e['width'], 'height': e['height'], 'format': e['format']})
    spec = art / 'main-colo-spec.json'
    spec.write_text(json.dumps({'images': images, 'texkeys': TEXKEYS, 'inplace': True}, indent=1), encoding='utf-8')
    r = subprocess.run([str(MENUGRAFT), 'patch', str(src), str(spec), str(out)], capture_output=True, text=True,
                       timeout=300)
    log(f'main menus colosseum (menugraft) {r.returncode} {(r.stdout or r.stderr).strip()[-300:]}')
    if r.returncode or not out.is_file() or out.stat().st_size != len(tgt):
        raise SystemExit('menugraft in-place patch of the patched MnMaAll failed')
    h = slippi_patch.Hsd(out.read_bytes())
    # the backdrop: the grid tile mirrored both ways, about two and a half balls across, opaque, TEV-coloured
    to = h.tobj('MenMainPanel', 1)
    h.put(to + 0x34, struct.pack('>II', 2, 2))                               # wrap MIRROR, MIRROR
    h.put(to + 0x3C, bytes((12, 9)))                                         # repeat
    h.put(to + 0x40, struct.pack('>I', 0x10 | (5 << 16) | (4 << 20)))       # colour and alpha from the TEV, as is
    tev = h.u32(to + 0x58)
    h.put(tev + 15, bytes([0x43]))                                           # alpha_d = KONST_A
    h.put(tev + 16, bytes.fromhex(BACK_LIGHT) + b'\xff')                     # konst: intensity 1
    h.put(tev + 20, bytes.fromhex(BACK_DARK) + b'\xff')                      # tev0: intensity 0
    h.put(tev + 28, struct.pack('>I', 0xC000007F))                           # + KONST_A
    h.hide('MenMainBack', BACK_HIDE)
    h.hide('MenMainPanel', PANEL_ARCS)
    # the buttons' plate: navy instead of black
    btev = h.u32(h.tobj('MenMainCursor', 2) + 0x58)
    h.put(btev + 20, bytes.fromhex(NAVY) + b'\xff')
    button_mesh(h, log)                                                      # the Colosseum plate shape
    # the description and preview boxes: a silver material, opaque
    for j in (60, 65, 77):
        mat = h.u32(h.mobj('MenMainPanel', j) + 0x0C)
        h.put(mat + 4, bytes.fromhex(PLATE) + b'\xff')                       # diffuse
        h.put(mat + 0x0C, struct.pack('>f', 1.0))                             # alpha
    for d in (dump, art):
        shutil.rmtree(d, ignore_errors=True)
    src.unlink()
    out.unlink()
    return bytes(h.b)


def recolor(disc, work, log=print):
    """the disc file -> the disc file whose Slippi-patched form is the Colosseum design; raises if the patch blocks
    anything that matters"""
    ok = slippi_patch.live_matches(FILE)
    if ok is False:
        log("WARNING: Slippi Launcher's MnMaAll patch differs from the one pinned in tools/slippi: re-check the menus")
    tgt, _ = slippi_patch.target(FILE, disc)
    want = design(tgt, work, log)
    new, rep = slippi_patch.back(FILE, disc, want)
    log(f"main menus colosseum: {rep['changed']} bytes changed in the patched file, {rep['written']} disc bytes "
        f"written, {len(rep['literal'])} the patch's own, {len(rep['shared'])} shared, {len(rep['miss'])} not reached")
    lit = [hex(i - 0x20) for i in rep['literal']]
    if lit:
        log(f'  the patch\'s own bytes (left as they are): {lit[:12]}')
    if rep['shared']:
        log(f"  shared disc bytes (left as they are): {[hex(s - 0x20) for s in list(rep['shared'])[:12]]}")
    if len(rep['miss']) > 64:
        raise SystemExit('main_colo: too much of the design is out of the disc file\'s reach')
    return new


def install(files, work, log=print):
    p = Path(files) / FILE
    disc = p.read_bytes()
    new = recolor(disc, work, log)
    if len(new) != len(disc):
        raise SystemExit('main_colo changed the size of MnMaAll.usd')
    p.write_bytes(new)


# ---------------------------------------------------------------------------------------------------------- code
def code():
    """Gecko 04 lines: the five menu light colours"""
    lines = []
    for i, (r, g, b) in enumerate(LIGHTS):
        lines.append(f'04{(LIGHT_TABLE + 4 * i) & 0x01FFFFFF:06X} {r:02X}{g:02X}{b:02X}FF')
    return '\n'.join(lines)


def light_bytes():
    return b''.join(bytes((r, g, b, 0xFF)) for r, g, b in LIGHTS)


def install_code(proj, mexcli, log=print):
    text = code()
    r = subprocess.run([str(mexcli), 'add-code', str(proj), CODE_NAME, text], capture_output=True, text=True, timeout=120)
    log(f'menu lights code: {r.returncode} {(r.stdout or r.stderr).strip()[-200:]}')
    if r.returncode:
        raise SystemExit('menu lights code not added')


if __name__ == '__main__':
    if sys.argv[1:] == ['code']:
        print(code())
    else:
        src, dst = Path(sys.argv[1]), Path(sys.argv[2])
        work = dst.parent / (dst.stem + '-work')
        work.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(recolor(src.read_bytes(), work))
        shutil.rmtree(work, ignore_errors=True)
