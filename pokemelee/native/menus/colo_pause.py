"""The pause screen in Colosseum's look (owner 2026-11-12: "we should redo the pause screen too").

GmPause.usd is one scene, ScGamPause_scene_data (gmpause.c): model 0 (menugraft name ScGamPause_scene_data.j0), 12
joints, every piece a textured quad (or a few) on its own joint:
  j6 the top-left corner bracket, j4 the right edge bracket, j5 the bottom-left bracket and j11 the camera stick's arrows
  (both from one picture), j1 > j2 the stick knob (a little dome the game tilts with the stick; its ring picture is a
  bump map, its shading vertex colours), j3 two end tiles and j8 'P1' (a texture animation, frames P1-P4: the game sets
  the frame to the pausing port), j7 'Pause', j9 L+R+A+Start RESET and j10 Z RETRY (the A, Start and Z discs get their
  green / grey / blue from extra quads' vertex colours over the same picture, so those pictures keep Melee's layout).
  The text pieces draw one quad per letter ('P a u s e' in boxes).
The game hides j9 / j10 / the stick by the match's rules; nothing reads the file by offset, so it may grow (it loads
with the match: kept to a few KB more than Melee's 33 KB).

Here: STAGE SELECT's violet title bar behind 'P1 PAUSE' (new quads on j0, drawn first), PAUSE as one word on that bar
(j7's letter tiles cleared), P1-P4 in the ports' colours, Poke Balls for the end tiles and the stick knob, chrome
brackets (Melee's shapes re-shaded as bevelled chrome), and the button hints redrawn as chrome buttons over a dark
Colosseum plate.

Camera (1280x960 shot): x px = 640 + 21.7 x, y px = 470 - 19.3 y (j0 space).

usage: python colo_pause.py <dump dir of GmPause.usd> <out dir> [paused shot.png]   writes <out>/pause-spec.json (and
       <out>/mock.png over a paused shot); from build_iso through colo_menus.install.
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt, gaussian_filter

sys.path.insert(0, str(Path(__file__).parent))
from colo_menus import (FONTS, SS, VIOLET, by_use, emit, grey, label, load_image, pill, pokeball_badge,  # noqa: E402
                        reduce, three_slice)

MODEL = 'ScGamPause_scene_data.j0'
PLAYER = [(236, 52, 52), (70, 120, 255), (250, 206, 30), (52, 190, 80)]    # P1-P4, Melee's port colours
J3 = (25.9, 18.6)                 # j3's place (j0 space)
TITLE = (4.9, 20.0, 27.3, 17.2)        # the violet bar behind 'P1 PAUSE' [x0, ytop, x1, ybottom], j0 space
PAUSE_AT = (13.4, 19.7, 24.6, 17.5)    # PAUSE as one word, where Melee spelled P a u s e (j7, 19.0 +- 5.4)
FONT = 'seguibl.ttf'


def to_px(x, y):
    return 640 + 21.7 * x, 470 - 19.3 * y


def chrome(van, rim=2.4, fill_a=0.5):
    """Melee's bracket shape (its alpha) re-shaded as bevelled chrome lit from the top left: a dark edge line, a bright
    rim, a dimmer see-through middle. Intensity and alpha for IA4 (the game tints it white)."""
    a = np.asarray(van.getchannel('A'), float) / 255
    h, w = a.shape
    big = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((w * SS, h * SS), Image.BICUBIC), float) / 255
    m = big > 0.3
    dist = distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1] / SS
    gy, gx = np.gradient(gaussian_filter(dist, SS * 0.6))
    n = np.hypot(gx, gy) + 1e-6
    facing = (gx * 0.7 + gy * 0.7) / n             # inward normal . light from the top left (image y down)
    t = np.clip(dist / rim, 0, 1)
    prof = np.interp(t, [0, 0.1, 0.22, 0.4, 0.7, 1.0], [0.08, 0.3, 1.0, 0.92, 0.6, 0.4])
    lit = np.where(t < 1, 0.78 + 0.22 * facing, 1.0)
    inten = np.where(m, np.clip(prof * lit, 0, 1), 0.8)
    alpha = np.where(m, np.interp(t, [0, 0.08, 0.75, 1.0], [0.95, 1.0, 1.0, fill_a]), 0.0)
    return reduce(grey((inten, alpha)), (w, h))


def knob_ball(size=32):
    """The stick knob as a Poke Ball seen from above (CI4; the dome's vertex colours shade it)."""
    im = Image.new('RGBA', (size, size), (210, 210, 216, 255))
    im.alpha_composite(pokeball_badge(size))
    return im


def end_ball(w=24, h=30):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    b = pokeball_badge(w)
    im.alpha_composite(b, (0, (h - w) // 2))
    return im


def port_tag(k, size=(56, 28)):
    """'P' and the port's digit, each centred in its own half (j8 draws them as two quads, u 0-.476 and .524-1), in the
    port's colour with a dark outline."""
    w, h = size
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    col = PLAYER[k]
    im = label(im, 'P', FONT, h * 0.78, (0, 0, w * 0.476, h), fill=col, stroke=(16, 18, 60), sw=0.14)
    return label(im, str(k + 1), FONT, h * 0.78, (w * 0.524, 0, w, h), fill=col, stroke=(16, 18, 60), sw=0.14)


def word(text, size, pt, spacing=0.0):
    """White Colosseum lettering with a dark outline on clear; spacing in ems between letters."""
    w, h = size
    big = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    f = ImageFont.truetype(str(FONTS / FONT), int(pt * SS))
    sw = int(pt * SS * 0.13)
    adv = [d.textbbox((0, 0), c, font=f, stroke_width=sw)[2] - d.textbbox((0, 0), c, font=f, stroke_width=sw)[0] for c in text]
    gap = spacing * pt * SS
    total = sum(adv) + gap * (len(text) - 1)
    x = (w * SS - total) / 2
    for c, a in zip(text, adv):
        bb = d.textbbox((0, 0), c, font=f, stroke_width=sw)
        d.text((x - bb[0], (h * SS - (bb[3] - bb[1])) / 2 - bb[1]), c, font=f, fill=(255, 255, 255, 255),
               stroke_width=sw, stroke_fill=(16, 18, 60, 255))
        x += a + gap
    return reduce(big, size)


def chrome_disc(d, cx, cy, r, letter, f, dark=0.12):
    """A bevelled chrome button with a dark letter, drawn as intensity (R) and alpha on an IA picture at SS scale."""
    ys, xs = np.mgrid[0:d.shape[0], 0:d.shape[1]]
    rr = np.hypot(xs - cx, ys - cy)
    inside = rr <= r
    t = np.clip((r - rr) / (r * 0.28), 0, 1)
    shade = np.interp(t, [0, 0.15, 0.45, 1], [0.3, 1.0, 0.8, 0.95]) * np.where((xs - cx) + (ys - cy) < 0, 1.0, 0.82)
    d[..., 0] = np.where(inside, shade, d[..., 0])
    d[..., 1] = np.where(inside, 1.0, d[..., 1])
    img = Image.fromarray((d[..., 0] * 255).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    bb = dr.textbbox((0, 0), letter, font=f)
    dr.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]), letter, font=f, fill=int(dark * 255))
    d[..., 0] = np.asarray(img, float) / 255


def hint(size, buttons, plus, word_box, text):
    """A button hint in Melee's layout (IA4, the game tints parts by vertex colour): chrome buttons along the top
    (buttons: [(cx, cy, r, letter)] in texture px), small '+' signs, and a dark rounded Colosseum plate with the word in
    white along the bottom (word_box in texture px)."""
    w, h = size
    W, H = w * SS, h * SS
    ia = np.zeros((H, W, 2))
    plate = Image.new('L', (W, H), 0)
    x0, y0, x1, y1 = (v * SS for v in word_box)
    ImageDraw.Draw(plate).rounded_rectangle((x0, y0, x1, y1), (y1 - y0) * 0.45, fill=255)
    rim = Image.new('L', (W, H), 0)
    ImageDraw.Draw(rim).rounded_rectangle((x0 + SS * 1.2, y0 + SS * 1.2, x1 - SS * 1.2, y1 - SS * 1.2), (y1 - y0) * 0.4, fill=255)
    p, r_ = np.asarray(plate) > 127, np.asarray(rim) > 127
    ia[..., 0] = np.where(p & ~r_, 0.85, np.where(r_, 0.16, 0))
    ia[..., 1] = np.where(p, 0.92, 0)
    for cx, cy, r, letter in buttons:
        f = ImageFont.truetype(str(FONTS / FONT), int(r * SS * (1.25 if len(letter) == 1 else 0.95)))
        chrome_disc(ia, cx * SS, cy * SS, r * SS, letter, f)
    img_i = Image.fromarray((ia[..., 0] * 255).astype(np.uint8))
    img_a = Image.fromarray((ia[..., 1] * 255).astype(np.uint8))
    di, da = ImageDraw.Draw(img_i), ImageDraw.Draw(img_a)
    for cx, cy in plus:
        s, t = SS * 3, SS * 1.1
        for box in ((cx * SS - s, cy * SS - t, cx * SS + s, cy * SS + t), (cx * SS - t, cy * SS - s, cx * SS + t, cy * SS + s)):
            di.rectangle(box, fill=245)
            da.rectangle(box, fill=255)
    f = ImageFont.truetype(str(FONTS / FONT), int((y1 - y0) * 0.78))
    bb = di.textbbox((0, 0), text, font=f)
    tx, ty = (x0 + x1 - (bb[2] - bb[0])) / 2 - bb[0], (y0 + y1 - (bb[3] - bb[1])) / 2 - bb[1]
    di.text((tx, ty), text, font=f, fill=255)
    da.text((tx, ty), text, font=f, fill=255)
    return reduce(grey((np.asarray(img_i, float) / 255, np.asarray(img_a, float) / 255)), size)


def pause_spec(dump, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    images, quads = [], []

    def image(name, im, fmt, use):
        images.append({**emit(out, name, im, fmt), 'md5': by_use(dump, f'{MODEL} {use}')})

    def quad(name, im, fmt, rect, z=0.0, first=False):
        """A quad on j3 (the end tiles' joint, drawn before 'Pause' and 'P1'; j0 has no render flags, so the game never
        draws pieces on it). rect in j0 space."""
        q = emit(out, name, im, fmt)
        jx, jy = J3
        q.update({'model': MODEL, 'joint': 3, 'rect': [round(v, 3) for v in (rect[0] - jx, rect[1] - jy, rect[2] - jx, rect[3] - jy)],
                  'z': z, 'first': first})
        quads.append(q)

    # the violet title bar (STAGE SELECT's), PAUSE on it as one word
    x0, yt, x1, yb = TITLE
    ph = yt - yb
    left, mid, right = three_slice(pill((128, 32), VIOLET, stripes=True), 32)
    # 'first' puts each before j3's own pieces (the end balls): right, middle, left, so the bar reads left to right
    quad('title-r', right, 'CI4', (x1 - ph, yt, x1, yb), z=-0.02, first=True)
    quad('title-m', mid, 'CI4', (x0 + ph - 0.02, yt, x1 - ph + 0.02, yb), z=-0.02, first=True)
    quad('title-l', left, 'CI4', (x0, yt, x0 + ph, yb), z=-0.02, first=True)
    quad('pause-word', word('PAUSE', (128, 24), 20, spacing=0.12), 'CI4', PAUSE_AT)
    image('clear-pause-letters', Image.new('RGBA', (8, 8), (0, 0, 0, 255)), 'I4', 'j7 d0 t0')
    # P1-P4 (one texture animation: frame k is port k+1; the joint's own picture is frame 0)
    for k in range(4):
        use = 'j8 d0 t0' if k == 0 else f'j8 m0 a0 f{k}'
        md5 = by_use(dump, f'{MODEL}.m0 {use}' if k else f'{MODEL} {use}')
        images.append({**emit(out, f'port-{k + 1}', port_tag(k), 'CI4'), 'md5': md5})
    image('end-ball', end_ball(), 'CI4', 'j3 d0 t0')
    # the stick knob: a Poke Ball (its bump flag dropped so the picture is colour, not a height map)
    image('knob-ball', knob_ball(), 'CI4', 'j2 d0 t0')
    # chrome brackets, Melee's shapes
    image('bracket-top-left', chrome(load_image(dump, by_use(dump, f'{MODEL} j6 d0 t0'))), 'IA4', 'j6 d0 t0')
    image('bracket-right', chrome(load_image(dump, by_use(dump, f'{MODEL} j4 d0 t0'))), 'IA4', 'j4 d0 t0')
    image('bracket-stick', chrome(load_image(dump, by_use(dump, f'{MODEL} j5 d0 t0'))), 'IA4', 'j5 d0 t0')
    # the button hints, Melee's layout (the A / Start / Z discs are where the tinting quads expect them)
    image('hint-reset', hint((124, 36), [(17, 10.5, 9.5, 'L'), (46.5, 10.5, 9.5, 'R'), (76.5, 10.5, 10, 'A'),
                                         (105.5, 10.5, 10, 'ST')],
                             [(31.8, 10.5), (61.5, 10.5), (91, 10.5)], (44, 22.5, 123, 35.5), 'RESET'), 'IA4', 'j9 d0 t0')
    image('hint-retry', hint((80, 36), [(37.5, 9.5, 9, 'Z')], [], (2, 22.5, 78, 35.5), 'RETRY'), 'IA4', 'j10 d0 t0')
    materials = [{'model': MODEL, 'joint': 2, 'dobj': 0, 'dropBump': True},
                 {'model': MODEL, 'joint': 8, 'dobj': 0, 'dropTev': True}]
    spec = {'images': images, 'quads': quads, 'materials': materials, 'recolor': [], 'tints': []}
    (out / 'pause-spec.json').write_text(json.dumps(spec, indent=1))
    return spec


def mock(out, shot):
    """The new pieces laid over a paused-match shot at their screen places (no game; for judging the art)."""
    out = Path(out)
    scr = Image.open(shot).convert('RGBA')

    def put(name, x0, yt, x1, yb):
        (a, b), (c, d) = to_px(x0, yt), to_px(x1, yb)
        im = Image.open(out / f'{name}.png').convert('RGBA')
        if im.mode == 'RGBA' and name.startswith(('bracket', 'hint')):
            a_ = np.asarray(im, float)
            im = Image.fromarray(np.dstack([a_[..., :3], a_[..., 3:]]).astype(np.uint8), 'RGBA')
        scr.alpha_composite(im.resize((int(c - a), int(d - b)), Image.LANCZOS), (int(a), int(b)))

    x0, yt, x1, yb = TITLE
    ph = yt - yb
    put('title-l', x0, yt, x0 + ph, yb)
    put('title-m', x0 + ph, yt, x1 - ph, yb)
    put('title-r', x1 - ph, yt, x1, yb)
    put('pause-word', *PAUSE_AT)
    put('port-1', 7.8, 19.6, 12.0, 17.6)
    put('end-ball', 5.5, 19.6, 7.1, 17.6)
    put('end-ball', 25.1, 19.6, 26.7, 17.6)
    put('bracket-top-left', -27.2, 20.1, -18.3, 12.7)
    put('bracket-right', 25.4, -9.1, 27.2, -20.1)
    put('bracket-stick', -27.2, -12.9, -18.4, -20.1)
    put('hint-reset', 13.0, -15.8, 25.4, -19.5)
    put('knob-ball', -24.2, -14.7, -21.0, -17.9)
    scr.save(out / 'mock.png')


if __name__ == '__main__':
    pause_spec(sys.argv[1], sys.argv[2])
    if len(sys.argv) > 3:
        mock(sys.argv[2], sys.argv[3])
    print('ok')
