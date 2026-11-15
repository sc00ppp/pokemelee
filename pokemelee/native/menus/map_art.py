"""Colosseum look for the Melee stage select (MnSlMap.usd), to match the character select (menu_art.py).

- the background (BackgroundModel j1, 128x128 CMPR, a blue glow band over hexagons) -> the same picture mapped through
  the Colosseum purple ramp by its brightness;
- the round "STAGE SELECT" emblem (StageSelect2Model j0, 128x128 IA4) -> a Poke Ball ring with STAGE SELECT on its band;
- the big faint lettering behind (BackgroundModel j2, 320x240 CI4: "SUPER SMASH BROS", "NINTENDO ALL STAGE ...") ->
  Colosseum lettering in the same faint blocks.

usage: python map_art.py <dump dir of the vanilla MnSlMap.usd> <out dir>   writes <out>/spec.json and the .bgra files
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from menu_art import emit, load

FONTS = FONTS
BACKGROUND = '615911da'
EMBLEM = '3370b0e5'
LETTERING = 'e85c2342'
RAMP = [(0.0, (0x0d, 0x06, 0x20)), (0.35, (0x3a, 0x24, 0x70)), (0.7, (0x8a, 0x5c, 0xd8)), (1.0, (0xf2, 0xea, 0xff))]


def ramp(lum):
    xs = [s for s, _ in RAMP]
    return np.stack([np.interp(lum, xs, [c[k] for _, c in RAMP]) for k in range(3)], -1)


def background(src):
    px = np.asarray(src.convert('RGB'), float) / 255
    lum = px @ [0.299, 0.587, 0.114]
    return Image.fromarray(ramp(np.clip(lum * 1.15, 0, 1)).round().astype(np.uint8), 'RGB').convert('RGBA')


def emblem(size=128):
    """White on clear (IA4: the menu colours it): an outer ring, a band across with STAGE / SELECT, a button ring."""
    k = 4
    s = size * k
    im = Image.new('L', (s, s), 0)
    a = Image.new('L', (s, s), 0)
    d, da = ImageDraw.Draw(im), ImageDraw.Draw(a)
    c, r = s / 2, s * 0.47
    for draw, v in ((d, 235), (da, 255)):
        draw.ellipse((c - r, c - r, c + r, c + r), outline=v, width=int(s * 0.035))
        draw.ellipse((c - r * 0.82, c - r * 0.82, c + r * 0.82, c + r * 0.82), outline=v, width=int(s * 0.012))
    band = s * 0.11
    da.rectangle((c - r, c - band, c + r, c + band), fill=255)
    d.rectangle((c - r, c - band, c + r, c + band), fill=150)
    for draw, v in ((d, 235), (da, 255)):
        draw.ellipse((c - s * 0.13, c - s * 0.13, c + s * 0.13, c + s * 0.13), fill=v)
    d.ellipse((c - s * 0.075, c - s * 0.075, c + s * 0.075, c + s * 0.075), fill=60)
    font = ImageFont.truetype(str(FONTS / 'arialbd.ttf'), int(s * 0.085))
    for text, x0, x1 in (('STAGE', c - r * 0.95, c - s * 0.15), ('SELECT', c + s * 0.15, c + r * 0.95)):
        w = d.textlength(text, font=font)
        box = d.textbbox((0, 0), text, font=font)
        pos = ((x0 + x1 - w) / 2, c - (box[1] + box[3]) / 2)
        d.text(pos, text, font=font, fill=30)
    im, a = im.resize((size, size), Image.LANCZOS), a.resize((size, size), Image.LANCZOS)
    v = np.asarray(im)
    return Image.fromarray(np.dstack([v, v, v, np.asarray(a)]), 'RGBA')


def lettering(size=(320, 240)):
    """Faint blocks of Colosseum words where Melee had its own: white text, its alpha the ink."""
    w, h = size
    k = 3
    im = Image.new('L', (w * k, h * k), 0)
    d = ImageDraw.Draw(im)
    blocks = [('POKEMON', 'arialbd.ttf', 34, (172, 6)), ('COLOSSEUM', 'arialbd.ttf', 28, (172, 44)),
              ('ORRE', 'impact.ttf', 40, (176, 82)), ('PHENAC  PYRITE  AGATE', 'arial.ttf', 9, (176, 132)),
              ('REALGAM  MT. BATTLE  THE UNDER', 'arial.ttf', 9, (176, 146)), ('STAGE', 'impact.ttf', 30, (12, 20)),
              ('SELECT', 'impact.ttf', 30, (12, 58)), ('BATTLE  NOW', 'arialbd.ttf', 12, (14, 104)),
              ('SINGLE  DOUBLE', 'arial.ttf', 9, (14, 124)), ('SNAG MACHINE', 'arialbd.ttf', 14, (14, 186)),
              ('CIPHER', 'impact.ttf', 26, (190, 180))]
    for text, font, pt, (x, y) in blocks:
        while True:      # shrink to fit before the texture's right edge
            f = ImageFont.truetype(str(FONTS / font), pt * k)
            if d.textlength(text, font=f) <= (w - x - 4) * k or pt <= 6:
                break
            pt -= 1
        d.text((x * k, y * k), text, font=f, fill=255)
    a = np.asarray(im.resize(size, Image.LANCZOS))
    return Image.fromarray(np.dstack([np.full_like(a, 255)] * 3 + [a]), 'RGBA')


def main():
    dump, out = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    specs = []
    full, src, _ = load(dump, BACKGROUND)
    emit(out, specs, full, background(src), 'RGB565')
    full, _, _ = load(dump, EMBLEM)
    emit(out, specs, full, emblem(), 'IA4')
    full, _, _ = load(dump, LETTERING)
    emit(out, specs, full, lettering(), 'IA4')
    (out / 'spec.json').write_text(json.dumps({'images': specs, 'recolor': [], 'tints': [], 'materials': []}, indent=1))
    print(len(specs), 'images ->', out / 'spec.json')


if __name__ == '__main__':
    main()
