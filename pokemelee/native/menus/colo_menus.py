"""Colosseum chrome for the Melee menus, on top of menu_art.py's purples (owner 2026-11-11: "the selector token looks
bad, and the top bar area still just looks like straight melee (same with the bottom)", "the sss could use a total
overhaul too to feel coloseum like", the doors "a bit restyled", keeping the purple Poke Ball).

Melee's CSS top and bottom bands are one piece, MenuModel j1 (d0 the top band with the VS circle, banner and swooshes,
d1 the banner's inner quad, d2 the bottom band): their shape is Melee's own geometry, so no recolour changes the look.
Here they go clear and j1 gets new quads (menugraft `quads`, appended DOBJs: no joint index moves, j1 still draws first
so everything else stays on top): Colosseum's own menu backdrop (bgtex, the two big Poke Balls) over the whole screen,
an orange Battle-Mode plate behind the logo, a chrome title pill behind the rules text. BACK (j39) becomes a blue
Colosseum pill; the token gets a Poke Ball quad over its player-coloured disc (TokenModel j3 d1).

Pieces are drawn here in Colosseum's style (orange gloss, chrome bezels, rivets, Poke Ball badge), sizes from the
CSS camera: x px = 640 + 18.5 x, y px = 480 - 16.8 y on a 1280x960 shot (from the doors' joints).

usage: python colo_menus.py <dump dir of the MnSlChr.usd being patched> <out dir>   writes <out>/css-spec.json
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

COLO = SOURCE
BGTEX = COLO / 'bgtex' / 'd0_j1_o0_t0_640x480.png'
FONTS = FONTS
SS = 4          # supersampling for every drawn piece

J1 = (-25.7, 23.7)      # MenuModel j1's world position: its quads are in its local space


def px_to_world(x, y):
    return (x - 640) / 18.5, (480 - y) / 16.8


def local_rect(x0, y0, x1, y1, joint=J1):
    """A screen rect (1280x960 px, top-left, bottom-right) -> [left, top, right, bottom] in the joint's local space."""
    wx0, wy0 = px_to_world(x0, y0)
    wx1, wy1 = px_to_world(x1, y1)
    return [round(wx0 - joint[0], 3), round(wy0 - joint[1], 3), round(wx1 - joint[0], 3), round(wy1 - joint[1], 3)]


# ---- drawing helpers (all at SS x, then reduced) ----

def vgrad(h, stops):
    ys = np.linspace(0, 1, h)
    xs = [s for s, _ in stops]
    return np.stack([np.interp(ys, xs, [c[k] for _, c in stops]) for k in range(3)], -1)


def rr_mask(size, box, r):
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, r, fill=255)
    return m


def fill_rgb(size, rgb):
    """rgb: (h, 3) column gradient or (h, w, 3)."""
    w, h = size
    a = np.asarray(rgb, float)
    if a.ndim == 2:
        a = np.repeat(a[:, None, :], w, 1)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


def layer(base, rgb_img, mask):
    base.paste(rgb_img.convert('RGBA'), (0, 0), mask)


def reduce(im, size):
    return im.resize(size, Image.LANCZOS)


CHROME = [(0.0, (250, 250, 252)), (0.18, (226, 228, 234)), (0.5, (150, 152, 160)), (0.62, (120, 122, 130)),
          (0.85, (196, 198, 206)), (1.0, (236, 236, 240))]
ORANGE = [(0.0, (255, 214, 140)), (0.12, (255, 168, 50)), (0.5, (240, 120, 10)), (0.85, (196, 84, 0)),
          (1.0, (150, 60, 0))]
BLUE = [(0.0, (190, 220, 255)), (0.15, (110, 170, 245)), (0.55, (50, 110, 210)), (1.0, (30, 70, 160))]
VIOLET = [(0.0, (70, 64, 128)), (0.5, (52, 46, 104)), (1.0, (38, 32, 84))]


def rivet(d, cx, cy, r, ring=(60, 60, 70, 255)):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ring)
    r2 = r * 0.8
    d.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=(170, 172, 180, 255))
    r3 = r * 0.45
    d.ellipse((cx - r3 - r * 0.15, cy - r3 - r * 0.2, cx + r3 - r * 0.15, cy + r3 - r * 0.2), fill=(250, 250, 252, 255))


def pokeball_badge(size):
    """Red and white Poke Ball with a chrome rim (Colosseum's panel badge)."""
    s = size * SS
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = s / 2
    d.ellipse((0, 0, s - 1, s - 1), fill=(40, 40, 48, 255))
    r = s * 0.46
    chrome = fill_rgb((s, s), vgrad(s, CHROME))
    layer(im, chrome, rr_mask((s, s), (c - r, c - r, c + r, c + r), r))
    r = s * 0.38
    top = rr_mask((s, s), (c - r, c - r, c + r, c + r), r)
    tm = Image.new('L', (s, s), 0)
    ImageDraw.Draw(tm).rectangle((0, 0, s, c), fill=255)
    red = fill_rgb((s, s), vgrad(s, [(0.0, (255, 120, 110)), (0.3, (230, 30, 30)), (0.5, (170, 10, 10)), (1, (120, 0, 0))]))
    white = fill_rgb((s, s), vgrad(s, [(0.0, (255, 255, 255)), (0.5, (250, 250, 252)), (1, (190, 192, 200))]))
    layer(im, white, top)
    layer(im, red, Image.fromarray(np.minimum(np.asarray(top), np.asarray(tm))))
    d = ImageDraw.Draw(im)
    band = s * 0.045
    d.rectangle((c - r, c - band, c + r, c + band), fill=(25, 25, 30, 255))
    for rr, col in ((s * 0.13, (25, 25, 30, 255)), (s * 0.09, (245, 245, 248, 255)), (s * 0.05, (200, 200, 208, 255))):
        d.ellipse((c - rr, c - rr, c + rr, c + rr), fill=col)
    return reduce(im, (size, size))


def plate(size, inner=None, badge=True):
    """Colosseum's orange Battle-Mode panel: glossy orange frame, chrome bezel, rivets, a Poke Ball badge; the inner
    panel a light chrome (the inked logo's bright letters show it)."""
    w, h = size
    W, H = w * SS, h * SS
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    R = H * 0.16
    layer(im, Image.new('RGB', (W, H), (70, 30, 0)), rr_mask((W, H), (0, 0, W - 1, H - 1), R))
    o = SS * 2
    layer(im, fill_rgb((W, H), vgrad(H, ORANGE)), rr_mask((W, H), (o, o, W - 1 - o, H - 1 - o), R - o))
    # the frame's gloss: a pale band along the top
    gl = Image.new('L', (W, H), 0)
    ImageDraw.Draw(gl).rounded_rectangle((W * 0.18, o * 2, W * 0.95, o * 2 + H * 0.06), H * 0.03, fill=150)
    im.alpha_composite(Image.merge('RGBA', (*[Image.new('L', (W, H), 255)] * 3, gl.filter(ImageFilter.GaussianBlur(SS * 2)))))
    t = H * 0.17
    box = (t, t, W - t, H - t)
    r2 = R * 0.55
    layer(im, Image.new('RGB', (W, H), (60, 60, 68)), rr_mask((W, H), (box[0] - SS, box[1] - SS, box[2] + SS, box[3] + SS), r2 + SS))
    layer(im, fill_rgb((W, H), vgrad(H, CHROME)), rr_mask((W, H), box, r2))
    b2 = SS * 5
    ib = (box[0] + b2, box[1] + b2, box[2] - b2, box[3] - b2)
    layer(im, Image.new('RGB', (W, H), (90, 90, 100)), rr_mask((W, H), (ib[0] - SS, ib[1] - SS, ib[2] + SS, ib[3] + SS), r2 * 0.6))
    inner_rgb = inner or [(0.0, (252, 252, 255)), (0.5, (226, 228, 236)), (1.0, (186, 188, 200))]
    layer(im, fill_rgb((W, H), vgrad(H, inner_rgb)), rr_mask((W, H), ib, r2 * 0.6))
    d = ImageDraw.Draw(im)
    rv = SS * 4.2
    for cx, cy in ((box[0] + rv * 0.2, box[1] + rv * 0.2), (box[2] - rv * 0.2, box[1] + rv * 0.2),
                   (box[0] + rv * 0.2, box[3] - rv * 0.2), (box[2] - rv * 0.2, box[3] - rv * 0.2)):
        rivet(d, cx, cy, rv)
    out = reduce(im, (w, h))
    if badge:
        bs = int(h * 0.27)
        out.alpha_composite(pokeball_badge(bs), (int(h * 0.05), int(h * 0.03)))
    return out


def pill(size, fill, rim=CHROME, stripes=False):
    """A rounded bar: chrome rim, a fill (gradient stops), optional fine horizontal stripes (Colosseum's title bars)."""
    w, h = size
    W, H = w * SS, h * SS
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    R = H / 2
    layer(im, Image.new('RGB', (W, H), (40, 40, 50)), rr_mask((W, H), (0, 0, W - 1, H - 1), R))
    o = SS * 1.5
    layer(im, fill_rgb((W, H), vgrad(H, rim)), rr_mask((W, H), (o, o, W - 1 - o, H - 1 - o), R - o))
    t = H * 0.16
    layer(im, Image.new('RGB', (W, H), (30, 28, 50)), rr_mask((W, H), (t - SS, t - SS, W - t + SS, H - t + SS), R - t + SS))
    inner = fill_rgb((W, H), vgrad(H, fill))
    if stripes:
        a = np.asarray(inner, float)
        a[(np.arange(H) // SS) % 3 == 0] *= 1.22
        inner = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')
    layer(im, inner, rr_mask((W, H), (t, t, W - t, H - t), R - t))
    gl = Image.new('L', (W, H), 0)
    ImageDraw.Draw(gl).rounded_rectangle((t + R * 0.5, t + SS, W - t - R * 0.5, t + (H - 2 * t) * 0.32), H * 0.1, fill=70)
    im.alpha_composite(Image.merge('RGBA', (*[Image.new('L', (W, H), 255)] * 3, gl.filter(ImageFilter.GaussianBlur(SS)))))
    return reduce(im, (w, h))


def label(im, text, font, pt, box, fill=(255, 255, 255), stroke=(20, 24, 80), sw=0.12):
    """White Colosseum lettering with a dark outline, centred in box (at im's own scale)."""
    big = im.resize((im.width * SS, im.height * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    f = ImageFont.truetype(str(FONTS / font), int(pt * SS))
    x0, y0, x1, y1 = (v * SS for v in box)
    bb = d.textbbox((0, 0), text, font=f, stroke_width=int(pt * SS * sw))
    pos = ((x0 + x1 - (bb[2] - bb[0])) / 2 - bb[0], (y0 + y1 - (bb[3] - bb[1])) / 2 - bb[1])
    d.text(pos, text, font=f, fill=fill + (255,), stroke_width=int(pt * SS * sw), stroke_fill=stroke + (255,))
    return reduce(big, im.size)


def three_slice(img, cap):
    """Left cap, a 1-column middle, right cap: three textures for three quads (a long bar at any width)."""
    w, h = img.size
    return img.crop((0, 0, cap, h)), img.crop((w // 2 - 4, 0, w // 2 + 4, h)), img.crop((w - cap, 0, w, h))


# ---- the pieces ----

def backdrop(size=(320, 240)):
    """Colosseum's own menu background, darkened a little so the icons and doors keep their contrast."""
    im = Image.open(BGTEX).convert('RGB').resize(size, Image.LANCZOS)
    a = np.asarray(im, float) * 0.82
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')


def back_button(size=(128, 80)):
    """BACK's texture: j39 maps it onto the screen rect px 1040-1190 x 30-125; transparent edges (the quad is clamped
    beyond the picture)."""
    w, h = size
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    p = pill((int(w * 0.96), int(h * 0.62)), BLUE)
    y = int(h * 0.22)
    im.alpha_composite(p, ((w - p.width) // 2, y))
    return label(im, 'BACK', 'seguibl.ttf', h * 0.34, ((w - p.width) / 2, y, (w + p.width) / 2, y + p.height))


def token_ball(size=96):
    """A Poke Ball drawn over the token's player-coloured disc (TokenModel j3 d1, radius 2.3 of the quad's 3): the top
    half clear (the disc's colour) with a gloss, the bottom half white, the black band and button, a black rim."""
    s = size * SS
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    c = s / 2
    unit = s / 6
    R = 2.3 * unit
    d = ImageDraw.Draw(im)
    d.ellipse((c - R - unit * 0.18, c - R - unit * 0.18, c + R + unit * 0.18, c + R + unit * 0.18), fill=(20, 20, 24, 255))
    clear = Image.new('L', (s, s), 0)
    ImageDraw.Draw(clear).ellipse((c - R + unit * 0.02, c - R + unit * 0.02, c + R - unit * 0.02, c + R - unit * 0.02), fill=255)
    im.putalpha(Image.fromarray(np.where(np.asarray(clear) > 0, 0, np.asarray(im.getchannel('A'))).astype(np.uint8)))
    bottom = Image.new('L', (s, s), 0)
    ImageDraw.Draw(bottom).pieslice((c - R, c - R, c + R, c + R), 0, 180, fill=255)
    white = fill_rgb((s, s), vgrad(s, [(0.5, (255, 255, 255)), (0.75, (236, 236, 242)), (1.0, (170, 172, 184))]))
    layer(im, white, bottom)
    gl = Image.new('L', (s, s), 0)
    ImageDraw.Draw(gl).ellipse((c - R * 0.72, c - R * 0.86, c + R * 0.1, c - R * 0.42), fill=120)
    im.alpha_composite(Image.merge('RGBA', (*[Image.new('L', (s, s), 255)] * 3, gl.filter(ImageFilter.GaussianBlur(unit * 0.12)))))
    d = ImageDraw.Draw(im)
    band = unit * 0.22
    d.rectangle((c - R, c - band, c + R, c + band), fill=(20, 20, 24, 255))
    for rr, col in ((unit * 0.78, (20, 20, 24, 255)), (unit * 0.56, (250, 250, 252, 255)), (unit * 0.34, (210, 210, 218, 255))):
        d.ellipse((c - rr, c - rr, c + rr, c + rr), fill=col)
    return reduce(im, (size, size))


def emit(out, name, im, fmt):
    px = np.array(im.convert('RGBA'))[..., [2, 1, 0, 3]]
    path = Path(out) / f'{name}.bgra'
    path.write_bytes(px.tobytes())
    im.save(Path(out) / f'{name}.png')
    return {'bgra': str(path), 'width': im.width, 'height': im.height, 'format': fmt}


def load_image(dump, md5):
    e = next(x for x in json.loads((Path(dump) / 'manifest.json').read_text()) if x['md5'] == md5)
    px = np.frombuffer((Path(dump) / f'{md5}.bgra').read_bytes(), np.uint8).reshape(e['height'], e['width'], 4)
    return Image.fromarray(px[..., [2, 1, 0, 3]].copy(), 'RGBA')


def by_use(dump, use):
    """md5 of the image a model piece draws (e.g. 'TokenModel j3 d0 t0'): works on vanilla and patched dumps alike."""
    for e in json.loads((Path(dump) / 'manifest.json').read_text()):
        if use in e['uses']:
            return e['md5']
    raise KeyError(use)


def grey(a):
    """An intensity/alpha picture (for IA formats: the game tints it) from two float arrays."""
    i, al = [(np.clip(np.asarray(x, float), 0, 1) * 255).round().astype(np.uint8) for x in a]
    return Image.fromarray(np.dstack([i, i, i, al]), 'RGBA')


def tag(text, size=(72, 28)):
    """The HMN / CPU / N/A and team tags (IA4, tinted by the game in the player's or team's colour): a rounded
    Colosseum tab with a Poke Ball button at its left end, the word in dark letters."""
    w, h = size
    W, H = w * SS, h * SS
    shape = rr_mask((W, H), (SS, SS * 2, W - SS, H - SS * 2), (H - SS * 4) / 2)
    inner = rr_mask((W, H), (SS * 2.5, SS * 3.5, W - SS * 2.5, H - SS * 3.5), (H - SS * 7) / 2)
    ys = np.linspace(0, 1, H)[:, None]
    shade = np.repeat(np.interp(ys, [0, 0.25, 0.6, 1], [1.0, 0.98, 0.78, 0.6]), W, 1)
    inten = np.where(np.asarray(inner) > 127, shade, 0.12)
    im = grey((inten, np.asarray(shape) / 255))
    d = ImageDraw.Draw(im)
    cy, r = H / 2, H * 0.3
    cx = SS * 3 + r
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(30, 30, 30, 255))
    d.rectangle((cx - r, cy - SS * 0.8, cx + r, cy + SS * 0.8), fill=(30, 30, 30, 255))
    r2 = r * 0.42
    d.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=(255, 255, 255, 255))
    f = ImageFont.truetype(str(FONTS / 'seguibl.ttf'), int(H * 0.56))
    x0, x1 = cx + r + SS * 2, W - SS * 5
    bb = d.textbbox((0, 0), text, font=f)
    scale = min(1.0, (x1 - x0) / (bb[2] - bb[0]))
    if scale < 1:
        f = ImageFont.truetype(str(FONTS / 'seguibl.ttf'), int(H * 0.56 * scale))
        bb = d.textbbox((0, 0), text, font=f)
    d.text(((x0 + x1 - (bb[2] - bb[0])) / 2 - bb[0], (H - (bb[3] - bb[1])) / 2 - bb[1]), text, font=f, fill=(28, 28, 28, 255))
    return reduce(im, size)


def frame_pieces(w, h, border=0.6, corner=1.3, px_per_unit=20):
    """A chrome frame of w x h units as 8 quads (4 corners with rivets, 4 stretched edges), IA8: a few small textures
    instead of one big one (the CSS is near its memory limit). Returns [(name, image, (x0, y0, x1, y1) in units from
    the frame's top-left, y down)]."""
    C = int(round(corner * px_per_unit))
    S = C * 2 + 8
    b = border * px_per_unit
    W = S * SS
    ys, xs = np.mgrid[0:W, 0:W] / SS
    # distance inside the rounded outer edge, for the bevel's cross-section
    m = rr_mask((W, W), (0, 0, W - 1, W - 1), C * SS * 0.55)
    inner = rr_mask((W, W), (b * SS, b * SS, W - 1 - b * SS, W - 1 - b * SS), max(1, (C * 0.55 - b) * SS))
    from scipy.ndimage import distance_transform_edt
    dist = distance_transform_edt(np.pad(np.asarray(m) > 127, 1))[1:-1, 1:-1] / SS   # px from the outer edge
    t = np.clip(dist / b, 0, 1)
    prof = np.interp(t, [0, 0.12, 0.3, 0.55, 0.8, 0.92, 1.0], [0.25, 0.98, 0.92, 0.62, 0.45, 0.2, 0.2])
    # light from above: the top and left faces brighter than the bottom and right
    face = np.where(ys + xs < W / SS, 1.0, 0.82)
    inten = prof * np.where(t < 0.5, face, 1.0)
    alpha = (np.asarray(m) > 127) & (np.asarray(inner) < 128)
    im = grey((inten, alpha.astype(float)))
    full = reduce(im, (S, S))
    cu = C / px_per_unit
    pieces = [('tl', full.crop((0, 0, C, C)), (0, 0, cu, cu)), ('tr', full.crop((S - C, 0, S, C)), (w - cu, 0, w, cu)),
              ('bl', full.crop((0, S - C, C, S)), (0, h - cu, cu, h)), ('br', full.crop((S - C, S - C, S, S)), (w - cu, h - cu, w, h)),
              ('t', full.crop((S // 2 - 2, 0, S // 2 + 2, C)), (cu, 0, w - cu, cu)),
              ('b', full.crop((S // 2 - 2, S - C, S // 2 + 2, S)), (cu, h - cu, w - cu, h)),
              ('l', full.crop((0, S // 2 - 2, C, S // 2 + 2)), (0, cu, cu, h - cu)),
              ('r', full.crop((S - C, S // 2 - 2, S, S // 2 + 2)), (w - cu, cu, w, h - cu))]
    return pieces


def door_rivets(door):
    """Chrome rivets in the closed door's four corners (half-turn symmetric, like the door's two halves)."""
    im = door.convert('RGBA').copy()
    w, h = im.size
    big = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    r = 4.2 * SS
    for cx, cy in ((10, 10), (w - 10, 10), (10, h - 10), (w - 10, h - 10)):
        rivet(d, cx * SS, cy * SS, r, ring=(110, 104, 140, 255))
    rv = reduce(big, (w, h))
    a = np.asarray(im)[..., 3].copy()
    # The second sliding half uses 1 - texture alpha. Its visible RGB lives
    # under alpha zero, so composite the decoration onto an opaque panel first.
    im.putalpha(255)
    im.alpha_composite(rv)
    out = np.asarray(im).copy()
    out[..., 3] = a       # the door's own halves
    return Image.fromarray(out, 'RGBA')


# the four door cards (MenuModel j41-j44): joint positions and the closed door's rect (world units)
CARDS = {41: (-33.2, 19.5), 42: (19.0, 19.5), 43: (-33.2, -4.0), 44: (19.0, -4.0)}
DOOR_W, DOOR_H = 14.2, 22.3          # the card's d0 rect from its joint: x 0..14.2, y 0..-22.2


# the CSS's top-area layout (1280x960 px)
LOGO_PLATE = (36, 34, 282, 152)
TITLE = (378, 78, 1038, 142)
BADGE = (288, 64, 362, 138)

# The mode plate (MenuModel j36). Melee's code draws its pictures as black ink whatever their colours, so the logo in
# its own colours is a quad on j1 (the one-door screen's logo picture, shared) and the plate's mode words go in a strip
# under it, one line each (owner 11-12: "make the pokemon colo logo in the top left colored in both single and vs").
# j36's three meshes (read from MnSlChr, 1280x960 px): d0 = the whole panel, frames f0 MELEE (now FREE-FOR-ALL),
# f1 TEAM BATTLE, f2 blank; d1 = its lower half, the Special Melee names (f1-f10; f0 is the shared blank, untouched);
# d2 = its upper half, SPECIAL / TEAM: blanked (it would cross the logo; the cards' team tags still show teams).
VS_LOGO = (98, 58, 241, 110)       # the 176x64 logo picture (the logo 155 texels wide in it), centred on the panel
MODE_STRIP = (98, 111, 240, 129)   # under it, the same centre; d1's mesh ends at x 240
MODE_D0, MODE_D1 = (64, 56, 249, 135), (64, 85, 240, 135)
SPECIAL_NAMES = {1: 'CAMERA MODE', 2: 'STAMINA MODE', 3: 'SUDDEN DEATH', 4: 'FIXED CAMERA', 5: 'GIANT MELEE',
                 6: 'TINY MELEE', 7: 'INVISIBLE MELEE', 8: 'SINGLE-BUTTON', 9: 'LIGHTNING MELEE', 10: 'SLO-MO MELEE'}
# (short enough to stay full size in the strip; d1's pictures are 128x32 for it, Melee's were 88x24)


def logo_picture():
    """The Pokemon Colosseum logo in its own colours, 176x64 (both screens' plates: one shared picture)."""
    import menu_art
    return menu_art.logo()


def mode_label(text, quad, size, strip=MODE_STRIP, cap=11):
    """A mode word for the plate (I4, white = ink: the game draws it black): one line, centred in the strip, on a
    picture that the mesh `quad` (px) stretches to its own size."""
    qx0, qy0, qx1, qy1 = quad
    W, H = round((qx1 - qx0) * SS), round((qy1 - qy0) * SS)
    im = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(im)
    sx0, sy0, sx1, sy1 = (strip[0] - qx0) * SS, (strip[1] - qy0) * SS, (strip[2] - qx0) * SS, (strip[3] - qy0) * SS
    pt = cap * SS / 0.72
    f = ImageFont.truetype(str(FONTS / 'seguibl.ttf'), int(pt))
    bb = d.textbbox((0, 0), text, font=f)
    if bb[2] - bb[0] > sx1 - sx0:
        f = ImageFont.truetype(str(FONTS / 'seguibl.ttf'), int(pt * (sx1 - sx0) / (bb[2] - bb[0])))
        bb = d.textbbox((0, 0), text, font=f)
    d.text(((sx0 + sx1 - (bb[2] - bb[0])) / 2 - bb[0], (sy0 + sy1 - (bb[3] - bb[1])) / 2 - bb[1]), text, font=f, fill=255)
    small = np.asarray(im.resize(size, Image.LANCZOS), float) / 255
    return grey((small, small))


# The portrait joints' own picture: Melee's first portrait (136x188 CI8, 25 KB). m-ex clears these joints' texture
# animations and shows every portrait through its own one (mexSelectChr's CSP animation), so this picture is never on
# screen; 8x8 clear in its place (2026-11-17, online character select memory).
PORTRAIT_USES = {'MenuModel j51 d0 t0', 'MenuModel j52 d0 t0', 'MenuModel j53 d0 t0', 'MenuModel j54 d0 t0',
                 'SingleMenuModel j45 d0 t0', 'PortraitModel j6 d0 t0'}


def csp_placeholder(dump):
    md5 = by_use(dump, 'MenuModel j51 d0 t0')
    e = next(x for x in json.loads((Path(dump) / 'manifest.json').read_text()) if x['md5'] == md5)
    if set(e['uses']) != PORTRAIT_USES or (e['width'], e['height'], e['format']) != (136, 188, 'CI8'):
        raise SystemExit(f'MnSlChr: the portrait placeholder {md5[:8]} is not the one expected: {e}')
    return md5


def plate_md5(dump, use):
    """md5 of a mode-plate picture, refused if anything outside j36 draws it too (shared blanks stay as they are)."""
    md5 = by_use(dump, use)
    e = next(x for x in json.loads((Path(dump) / 'manifest.json').read_text()) if x['md5'] == md5)
    if not all(u.startswith(('MenuModel j36 ', 'MenuMaterialAnimation j36 ')) for u in e['uses']):
        raise SystemExit(f'{use}: picture {md5[:8]} is shared outside the mode plate: {e["uses"]}')
    return md5


def plate_pieces(dump, out):
    """The VS mode plate's new pictures: the words in the strip, SPECIAL / TEAM clear."""
    images = [{**emit(out, 'mode-ffa', mode_label('FREE-FOR-ALL', MODE_D0, (176, 64)), 'I4'),
               'md5': plate_md5(dump, 'MenuMaterialAnimation j36 m0 a0 f0')},
              {**emit(out, 'mode-team', mode_label('TEAM BATTLE', MODE_D0, (176, 64)), 'I4'),
               'md5': plate_md5(dump, 'MenuMaterialAnimation j36 m0 a0 f1')}]
    for k, name in SPECIAL_NAMES.items():
        images.append({**emit(out, f'mode-special-{k}', mode_label(name, MODE_D1, (128, 32)), 'I4'),
                       'md5': plate_md5(dump, f'MenuMaterialAnimation j36 m1 a0 f{k}')})
    for k in (1, 2):
        images.append({**emit(out, f'mode-head-{k}', Image.new('RGBA', (8, 8), (0, 0, 0, 0)), 'I4'),
                       'md5': plate_md5(dump, f'MenuMaterialAnimation j36 m2 a0 f{k}')})
    return images


def css_spec(dump, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    images, quads = [], []

    def quad(name, im, fmt, rect_px, model='MenuModel', joint=1, z=0.0, joint_at=J1):
        q = emit(out, name, im, fmt)
        q.update({'model': model, 'joint': joint, 'rect': local_rect(*rect_px, joint=joint_at), 'z': z})
        quads.append(q)

    # MEMORY (owner 11-12, Cast Test 25: "it crashes on online menus"): Slippi's online CSS holds this file AND its own
    # MnExtAll (1.3 MB) in a 5,760 KB heap; Cast 21 (before this chrome) left 150 KB free there, the full-colour chrome
    # (+180 KB) ran it out (assertion "adr" in memory.c). So: paletted CI8 for the full-colour pieces (256 colours look
    # the same), a half-size backdrop (a soft picture), one shared copy of the four door frames (menugraft shares
    # identical quad pictures), and the unused debug-camera picture blanked. Check with online_check.py (menu3/work).
    quad('backdrop', backdrop((128, 96)), 'CMP', (-40, -30, 1320, 990), z=-0.2)
    lp = plate((LOGO_PLATE[2] - LOGO_PLATE[0], LOGO_PLATE[3] - LOGO_PLATE[1]))
    # three slices: the badge end, an 8-column middle stretched, the right end (the plate is plain between them)
    PL, PR = 72, 48
    pw, ph = lp.size
    quad('logo-plate-l', lp.crop((0, 0, PL, ph)), 'CI8', (LOGO_PLATE[0], LOGO_PLATE[1], LOGO_PLATE[0] + PL, LOGO_PLATE[3]))
    quad('logo-plate-m', lp.crop((pw // 2 - 4, 0, pw // 2 + 4, ph)), 'CI8',
         (LOGO_PLATE[0] + PL - 1, LOGO_PLATE[1], LOGO_PLATE[2] - PR + 1, LOGO_PLATE[3]))
    quad('logo-plate-r', lp.crop((pw - PR, 0, pw, ph)), 'CI8', (LOGO_PLATE[2] - PR, LOGO_PLATE[1], LOGO_PLATE[2], LOGO_PLATE[3]))
    tw, th = TITLE[2] - TITLE[0], TITLE[3] - TITLE[1]
    left, mid, right = three_slice(pill((48 * 4, 48), VIOLET, stripes=True), 48)   # 48 texels for a 64 px bar
    quad('title-l', left, 'CI8', (TITLE[0], TITLE[1], TITLE[0] + th, TITLE[3]))
    quad('title-m', mid, 'CI8', (TITLE[0] + th - 1, TITLE[1], TITLE[2] - th + 1, TITLE[3]))
    quad('title-r', right, 'CI8', (TITLE[2] - th, TITLE[1], TITLE[2], TITLE[3]))
    quad('logo', logo_picture(), 'CI8', VS_LOGO, z=0.02)
    images += plate_pieces(dump, out)
    tb =emit(out, 'token-ball', token_ball(64), 'CI8')
    tb.update({'model': 'TokenModel', 'joint': 3, 'rect': [-3, 3, 3, -3], 'z': 0.05})
    quads.append(tb)
    bb = emit(out, 'back', back_button(), 'CI8')
    images.append({**bb, 'md5': by_use(dump, 'MenuModel j39 d0 t0')})
    clear = emit(out, 'coin-clear', Image.new('RGBA', (8, 8), (0, 0, 0, 0)), 'IA4')
    images.append({**clear, 'md5': by_use(dump, 'TokenModel j3 d0 t0')})
    images.append({**emit(out, 'debugcam-clear', Image.new('RGBA', (8, 8), (0, 0, 0, 255)), 'I4'),
                   'md5': by_use(dump, 'DebugCameraModel j0 d0 t0')})
    images.append({**emit(out, 'portrait-clear', Image.new('RGBA', (8, 8), (0, 0, 0, 0)), 'CI8'), 'md5': csp_placeholder(dump)})
    # the doors: a chrome frame around each (j41-j44 get 8 quads, drawn before the door and its portrait), rivets in
    # the closed door, the flat grey outline (j41-j44 d1) clear
    e = 0.55
    for j in CARDS:
        for name, im, (x0, y0, x1, y1) in frame_pieces(DOOR_W + 2 * e, DOOR_H + 2 * e):
            q = emit(out, f'frame-{j}-{name}', im, 'IA4')
            q.update({'model': 'MenuModel', 'joint': j, 'z': 0.05,
                      'rect': [round(-e + x0, 3), round(e - y0, 3), round(-e + x1, 3), round(e - y1, 3)]})
            quads.append(q)
    door_md5 = by_use(dump, 'MenuModel j138 d0 t0')
    door_now = load_image(dump, door_md5)
    # CI8 quantization discards RGB under alpha zero, turning the half drawn
    # with inverted alpha black. RGB5A3 preserves both halves' colour data.
    images.append({**emit(out, 'door', door_rivets(door_now), 'RGB5A3'), 'md5': door_md5})
    for use, text in (('MenuMaterialAnimation j166 m1 a0 f0', 'CPU'), ('MenuModel j166 d1 t0', 'HMN'),
                      ('MenuMaterialAnimation j166 m1 a0 f2', 'N/A')):
        images.append({**emit(out, 'tag-' + text.replace('/', ''), tag(text), 'IA4'), 'md5': by_use(dump, use)})
    for use, text in (('MenuModel j56 d1 t0', 'BLUE'), ('MenuMaterialAnimation j56 m1 a0 f1', 'GREEN'),
                      ('MenuMaterialAnimation j56 m1 a0 f2', 'RED')):
        images.append({**emit(out, 'team-' + text, tag(text, (72, 24)), 'IA4'), 'md5': by_use(dump, use)})
    # Melee's bands take their alpha from vertex colours (material alpha does nothing): their geometry goes off-screen
    moves = [{'model': 'MenuModel', 'dobjs': [[1, 0], [1, 1], [1, 2]], 'dx': 0, 'dy': 400}]
    materials = [{'model': 'TokenModel', 'joint': 3, 'dobj': 1, 'alpha': 1.0}]
    materials += [{'model': 'MenuModel', 'joint': j, 'dobj': 1, 'alpha': 0.0} for j in CARDS]
    # the tags' black chevron shadows (CONSTANT, so material alpha works): the new tabs carry their own outline
    materials += [{'model': 'MenuModel', 'joint': j, 'dobj': 0, 'alpha': 0.0} for j in (166, 168, 170, 172, 56, 57, 58, 59)]
    # the one-door screen (1P and Slippi's online CSS, owner 11-12: "redesign that one too"), and Melee's dead icon
    # pictures blanked to pay for it (colo_online.py). Its quads go after VS's, so the shared pictures are VS's copies.
    import colo_online
    one = colo_online.parts(dump, out)
    images += one['images'] + colo_online.dead_pictures(dump, out)
    quads += one['quads']
    materials += one['materials']
    moves += one['moves']
    spec = {'images': images, 'quads': quads, 'materials': materials, 'moves': moves, 'recolor': one['recolor'], 'tints': []}
    (out / 'css-spec.json').write_text(json.dumps(spec, indent=1))
    return spec


# ---- the stage select (MnSlMap) ----
#
# Two depths, measured with a probe grid in Dolphin (1280x960 shot): the panel layer (StageSelect2Model, the icons'
# own depth: sss_layout's units) at x px = 640 + 22.4 x, y px = 476 - 20.5 y, and the backdrop plane (BackgroundModel
# j1, 29 units back) at x px = 645 + 19.0 x, y px = 457 - 19.1 y. Quads on StageSelect2Model j0 draw under the icons.

PLATE = SOURCE / 'colosseumbattle_menu/27_menu_069.png'    # Colosseum's Battle-Mode plate, 269x185
PLATE_CUT = (66, 56, 44, 50)       # left, top, right, bottom borders kept whole (the Poke Ball badge's tab, rivets)
LEGAL_PLATE = (99, 383, 1181, 590)   # behind sss_layout's legal row (y -0.6, icons px 137-1143 x 425-557)
INFO_PLATE = (20, 606, 660, 906)     # behind the hovered stage's name and preview
STAGE_PILL = (700, 792, 1090, 860)   # STAGE SELECT, bottom right, left of the Random button and its hover box (sss_layout.RANDOM_AT)
# The Random button (owner 11-12: "the random button looks weird like the outline but also its too big, maybe we could put it
# in the bottom right"): the game draws RandomIconModel at its own size whatever the layout's scale says, so its mesh is
# scaled here (menugraft move scale); its frame picture is tiled twice with MIRROR (rep 2,2), so only a quarter is drawn.
# Owner 11-12 on Cast Test 25: "random button still scuffed, make it like fill into that red outline": the red outline is the
# game's hover box (SelectBoxModel), scaled by the layout's scale (sss_layout.RANDOM_BOX); the button is sized to fill it.
RANDOM_K = 0.82
RANDOM_FRAME = (3.84, 2.8)           # the frame quad's half-extents at scale 1 (menugraft verts RandomIconModel 0)


def ss_rect(x0, y0, x1, y1):
    f = lambda x, y: (round((x - 640) / 22.4, 3), round((476 - y) / 20.5, 3))
    (a, b), (c, d) = f(x0, y0), f(x1, y1)
    return [a, b, c, d]


def bg_rect(x0, y0, x1, y1):
    f = lambda x, y: (round((x - 645) / 19.0, 3), round((457 - y) / 19.1, 3))
    (a, b), (c, d) = f(x0, y0), f(x1, y1)
    return [a, b, c, d]


def violet(im):
    """The orange plate as Colosseum's Story-Mode violet: orange hues turned violet, the chrome, badge and panel kept."""
    import colorsys
    a = np.asarray(im.convert('RGBA'), float) / 255
    out = a.copy()
    rgb = a[..., :3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    h = np.vectorize(lambda r, g, b: colorsys.rgb_to_hsv(r, g, b)[0])(rgb[..., 0], rgb[..., 1], rgb[..., 2])
    m = (sat > 0.35) & (h > 0.04) & (h < 0.16)
    for y, x in zip(*np.nonzero(m)):
        r, g, b = colorsys.hsv_to_rgb(0.72, sat[y, x] * 0.85, mx[y, x] * 0.78)
        out[y, x, :3] = (r, g, b)
    return Image.fromarray((out * 255).round().astype(np.uint8), 'RGBA')


def stripe_tile():
    """The plate's inner panel (dark see-through stripes), as an 8x8 tile repeated over the stretched middle."""
    t = np.zeros((8, 8, 4), np.uint8)
    for y in range(8):
        t[y] = (71, 71, 71, 163) if y % 4 < 2 else (22, 22, 22, 138)
    return Image.fromarray(t, 'RGBA')


def nine_slice(name, img, cut, rect_px, k, add):
    """img's borders kept whole at scale k (screen px per texture px), its edges stretched, its middle the stripe tile
    repeated: 9 quads filling rect_px on the panel layer. add(name, image, fmt, rect_px, uv=None, wrap=None)."""
    w, h = img.size
    l, t, r, b = cut
    X0, Y0, X1, Y1 = rect_px
    xs = [X0, X0 + l * k, X1 - r * k, X1]
    ys = [Y0, Y0 + t * k, Y1 - b * k, Y1]
    us = [0, l, w - r, w]
    vs = [0, t, h - b, h]
    for i in range(3):
        for j in range(3):
            box = (xs[i], ys[j], xs[i + 1], ys[j + 1])
            if i == 1 and j == 1:
                tile = stripe_tile()
                add(f'{name}-mid', tile, 'RGB5A3', box, uv=[0, 0, (box[2] - box[0]) / 8, (box[3] - box[1]) / 8], wrap='REPEAT')
                continue
            crop = (us[i], vs[j], us[i + 1], vs[j + 1])
            if i == 1:          # top or bottom edge: a few middle columns, stretched across
                c = (us[1] + us[2]) // 2
                crop = (c - 2, crop[1], c + 2, crop[3])
            if j == 1:          # left or right edge: a few middle rows (a whole stripe period), stretched down
                c = (vs[1] + vs[2]) // 2
                crop = (crop[0], c - 2, crop[2], c + 3)
            add(f'{name}-{i}{j}', img.crop(crop), 'RGB5A3', box)


def bevel_frame(w, h, r, rim=2, fill=0.45):
    """An icon frame plate (IA4, tinted by the game, red when hovered): rounded, a chrome bevel at the edge (lit from
    the top left), a plain fill under the picture."""
    W, H = w * SS, h * SS
    m = np.asarray(rr_mask((W, H), (0, 0, W - 1, H - 1), r * SS)) > 127
    from scipy.ndimage import distance_transform_edt
    dist = distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1] / SS
    ys, xs = np.mgrid[0:H, 0:W]
    lit = np.where((xs / W) + (ys / H) < 1.0, 1.0, 0.7)
    t = np.clip(dist / rim, 0, 1)
    inten = np.where(t < 1, np.interp(t, [0, 0.25, 0.5, 1.0], [0.3, 1.0, 0.85, 0.5]) * lit, fill)
    return reduce(grey((inten, m.astype(float))), (w, h))


def random_face(size=(128, 96)):
    """The Random box's face over its chrome plate: Colosseum's violet panel, a Poke Ball, RANDOM in white."""
    w, h = size
    W, H = w * SS, h * SS
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    layer(im, fill_rgb((W, H), vgrad(H, [(0.0, (110, 96, 200)), (0.5, (72, 60, 150)), (1.0, (44, 36, 104))])),
          rr_mask((W, H), (0, 0, W - 1, H - 1), H * 0.12))
    a = np.asarray(im, float)
    a[..., :3][(np.arange(H) // SS) % 3 == 0] *= 1.12
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')
    out = reduce(im, size)
    bs = int(h * 0.48)
    out.alpha_composite(pokeball_badge(bs), ((w - bs) // 2, int(h * 0.06)))
    return label(out, 'RANDOM', 'seguibl.ttf', h * 0.25, (0, h * 0.56, w, h * 0.97))


def random_frame_quarter(w=48, h=36, r=8, rim=3, fill=0.45):
    """The BOTTOM-left quarter of the Random button's chrome frame. The game tiles this picture twice each way, mirrored,
    with u running 0..2 (the picture's left column at both outer edges) but v running 1..-1 (HSD flips v: the picture's
    bottom row at the top and bottom edges, its top row in the middle). So the quarter with its rim on the left and the
    bottom puts the rounded corners at the four outer corners. (A whole frame drew a frame inside a frame; the top-left
    quarter put the corners at the middles of the sides, the 'scuffed' notches of Cast Test 25.)"""
    full = bevel_frame(2 * w, 2 * h, r, rim=rim, fill=fill)
    return full.crop((0, h, w, 2 * h))


def text_quad(text, size, pt):
    """White Colosseum lettering with a dark outline on clear (IA8: the colour is the texture's own)."""
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    return label(im, text, 'seguibl.ttf', pt, (0, 0, size[0], size[1]))


def sss_spec(dump, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    images, quads = [], []

    def add(name, im, fmt, rect_px, uv=None, wrap=None, model='StageSelect2Model', joint=0, z=0.0, rect=None):
        q = emit(out, name, im, fmt)
        q.update({'model': model, 'joint': joint, 'rect': rect or ss_rect(*rect_px), 'z': z})
        if uv:
            q['uv'] = [round(v, 4) for v in uv]
        if wrap:
            q['wrap'] = wrap
        quads.append(q)

    def clear(use, fmt):
        """I4 is its own alpha (black is clear); IA4 gets alpha 0."""
        px = (0, 0, 0, 255) if fmt == 'I4' else (0, 0, 0, 0)
        images.append({**emit(out, 'clear-' + use.replace(' ', '-'), Image.new('RGBA', (8, 8), px), fmt),
                       'md5': by_use(dump, use)})

    # Colosseum's menu backdrop over the old grid plane; the old lettering, glow, frame lines, emblem and STAGE SELECT
    # text cleared
    add('sss-backdrop', backdrop(), 'CMP', None, model='BackgroundModel', joint=1, z=2.0,
        rect=bg_rect(-260, -200, 1540, 1150))
    clear('BackgroundModel j2 d1 t0', 'IA4')
    clear('BackgroundModel j2 d0 t0', 'I4')
    clear('StageSelect2Model j1 d0 t0', 'I4')
    clear('StageSelect2Model j0 d0 t0', 'IA4')
    clear('StageSelect2Model j0 d1 t0', 'I4')
    # the legal row on Colosseum's orange Battle-Mode plate; the hovered stage's name on its violet twin
    plate_img = Image.open(PLATE).convert('RGBA')
    nine_slice('legal', plate_img, PLATE_CUT, LEGAL_PLATE, 0.8, add)
    nine_slice('info', violet(plate_img), PLATE_CUT, INFO_PLATE, 0.8, add)
    # STAGE SELECT on a violet title pill (the CSS's rules bar)
    ph = STAGE_PILL[3] - STAGE_PILL[1]
    left, mid, right = three_slice(pill((ph * 4, ph), VIOLET, stripes=True), ph)
    add('stage-pill-l', left, 'RGB5A3', (STAGE_PILL[0], STAGE_PILL[1], STAGE_PILL[0] + ph, STAGE_PILL[3]))
    add('stage-pill-m', mid, 'RGB5A3', (STAGE_PILL[0] + ph - 1, STAGE_PILL[1], STAGE_PILL[2] - ph + 1, STAGE_PILL[3]))
    add('stage-pill-r', right, 'RGB5A3', (STAGE_PILL[2] - ph, STAGE_PILL[1], STAGE_PILL[2], STAGE_PILL[3]))
    tw = STAGE_PILL[2] - STAGE_PILL[0] - 2 * ph
    add('stage-text', text_quad('STAGE SELECT', (256, 32), 22), 'IA8',
        (STAGE_PILL[0] + ph, STAGE_PILL[1] + ph * 0.18, STAGE_PILL[0] + ph + tw, STAGE_PILL[3] - ph * 0.18), z=0.02)
    # chrome icon frames (the picture covers all but their edge; the game still tints them red on hover)
    images.append({**emit(out, 'icon-frame', bevel_frame(64, 56, 5), 'IA4'), 'md5': by_use(dump, 'IconModel j1 d0 t0')})
    images.append({**emit(out, 'icon-frame-sq', bevel_frame(32, 32, 3, rim=1.2), 'IA4'),
                   'md5': by_use(dump, 'IconLargeModel j1 d0 t0')})
    # Random: a chrome plate, its face a violet panel with a Poke Ball (its RANDOM lettering cleared)
    images.append({**emit(out, 'random-frame', random_frame_quarter(), 'IA4'),
                   'md5': by_use(dump, 'RandomIconModel j0 d0 t0')})
    clear('RandomIconModel j0 d1 t0', 'I4')
    fx, fy = RANDOM_FRAME[0] * RANDOM_K - 0.2, RANDOM_FRAME[1] * RANDOM_K - 0.2     # inside the frame's rim
    add('random-face', random_face(), 'RGB5A3', None, model='RandomIconModel', joint=0, z=0.05,
        rect=[round(-fx, 3), round(fy, 3), round(fx, 3), round(-fy, 3)])
    materials = [{'model': 'RandomIconModel', 'joint': 0, 'dobj': 0, 'diffuse': '#FFFFFFFF'}]
    # the hovered stage's name down into the violet plate, its hologram preview into the free space on the right; the
    # Random button's own quads (frame, old lettering) down to RANDOM_K
    moves = [{'model': 'StageNameModel', 'joints': [1], 'dx': 0.6, 'dy': -4.5},
             {'model': 'StagePreviewModel', 'joints': [1], 'dx': 33.7, 'dy': 2.1},
             {'model': 'RandomIconModel', 'dobjs': [[0, 0], [0, 1]], 'dx': 0, 'dy': 0, 'scale': RANDOM_K}]
    spec = {'images': images, 'quads': quads, 'materials': materials, 'moves': moves, 'recolor': [], 'tints': []}
    (out / 'sss-spec.json').write_text(json.dumps(spec, indent=1))
    return spec


MENUGRAFT = MENUGRAFT


def install(files, work, log=print):
    """Second pass over the project's menu files, after menu_art / map_art: dump each file as it now is (so every md5
    is the texture really there, the purple door included), draw the spec, patch, put the file back."""
    import shutil
    import subprocess
    sys.path.insert(0, str(Path(__file__).parent))
    import colo_pause      # the pause screen (owner 11-12), same menugraft pass
    work = Path(work)
    for name, make, spec_name in (('MnSlChr.usd', css_spec, 'css-spec.json'), ('MnSlMap.usd', sss_spec, 'sss-spec.json'),
                                  ('GmPause.usd', colo_pause.pause_spec, 'pause-spec.json')):
        src = Path(files) / name
        dump, art, patched = work / f'{name}-dump', work / f'{name}-art', work / f'{name}-colo'
        res = subprocess.run([str(MENUGRAFT), 'dump', str(src), str(dump)], capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise SystemExit(f'menugraft dump {name}: {res.stdout[-300:]} {res.stderr[-300:]}')
        make(dump, art)
        spec = art / spec_name
        res = subprocess.run([str(MENUGRAFT), 'patch', str(src), str(spec), str(patched)], capture_output=True, text=True,
                             timeout=300)
        log(f'colosseum chrome {name}: {res.returncode} {(res.stdout or res.stderr).strip()[-300:]}')
        if res.returncode != 0 or not patched.is_file():
            raise SystemExit(f'menugraft patch of {name} (colo_menus) failed')
        log(f'{name}: {src.stat().st_size} -> {patched.stat().st_size} bytes')
        shutil.copyfile(patched, src)
        for p in (dump, art):
            shutil.rmtree(p, ignore_errors=True)
        patched.unlink()


def mock(out):
    """The top of the CSS as these pieces would put it (no game; for judging the art quickly)."""
    out = Path(out)
    scr = Image.open(BGTEX).convert('RGB').resize((1280, 960), Image.LANCZOS)
    scr = Image.fromarray((np.asarray(scr, float) * 0.82).astype(np.uint8)).convert('RGBA')
    for name, box in (('logo-plate', LOGO_PLATE),):
        im = Image.open(out / f'{name}.png').resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
        scr.alpha_composite(im, box[:2])
    th = TITLE[3] - TITLE[1]
    for name, box in (('title-l', (TITLE[0], TITLE[1], TITLE[0] + th, TITLE[3])),
                      ('title-m', (TITLE[0] + th, TITLE[1], TITLE[2] - th, TITLE[3])),
                      ('title-r', (TITLE[2] - th, TITLE[1], TITLE[2], TITLE[3]))):
        im = Image.open(out / f'{name}.png').resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
        scr.alpha_composite(im, box[:2])
    sys.path.insert(0, str(Path(__file__).parent))
    import menu_art
    ink = menu_art.logo_ink().resize((185, 77), Image.LANCZOS)
    scr.alpha_composite(ink, (65, 57))
    back = Image.open(out / 'back.png').resize((150, 95), Image.LANCZOS)
    scr.alpha_composite(back, (1040, 30))
    d = ImageDraw.Draw(scr)
    f = ImageFont.truetype(str(FONTS / 'arialbd.ttf'), 40)
    d.text((470, 88), '4-man survival test!', font=f, fill=(255, 255, 255, 255))
    tok = Image.open(out / 'token-ball.png').resize((110, 110), Image.LANCZOS)
    disc = Image.new('RGBA', (110, 110), (0, 0, 0, 0))
    r = 110 * 2.3 / 6
    ImageDraw.Draw(disc).ellipse((55 - r, 55 - r, 55 + r, 55 + r), fill=(230, 30, 30, 255))
    disc.alpha_composite(tok)
    scr.alpha_composite(disc, (640, 300))
    scr.crop((0, 0, 1280, 420)).save(out / 'mock-top.png')


if __name__ == '__main__':
    if sys.argv[1] == 'sss':
        sss_spec(sys.argv[2], sys.argv[3])
    else:
        css_spec(sys.argv[1], sys.argv[2])
        mock(sys.argv[2])
    print('ok')
