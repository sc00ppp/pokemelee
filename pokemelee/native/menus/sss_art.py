"""The six Colosseum stages on the stage select: each one's icon is a picture of the stage as it is in the game
(stage_shots.py), its banner reads "Pokemon Colosseum" over the place's name, as Melee's read "Past Stages / Dream Land".

In an m-ex project a stage's icon and banner are assets/sss/icon_NNN.png with a .tex beside it; m-ex builds the menu
from the .tex (as with stock icons, stock_tex.py). Icons are CI8 with an RGB565 palette at the vanilla icon's own size
(64x56, Dream Land's 48x48), banners 224x56 I4 (white, the intensity is the alpha).

usage: python sss_art.py <stage shots dir> <out dir>      writes the pictures and a sheet, for a look
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS = FONTS
SERIES = 'Pokémon Colosseum'
I4, CI8, RGB565 = 0, 9, 1

# Melee stage file (its stem) -> (capture name, the Colosseum place)
STAGES = {'GrOp': ('dreamland', 'Agate Village'),
          'GrIz': ('fountainofdreams', 'Realgam Colosseum'),
          'GrNBa': ('battlefield', 'Phenac Stadium'),
          'GrNLa': ('finaldestination', 'Mt. Battle Crater'),
          'GrSt': ('yoshisstory', 'Mt. Battle Garden'),
          'GrPs': ('pokemonstadium', 'Phenac City')}


def stem(file_name):
    return Path(str(file_name or '').replace('\\', '/')).name.split('.')[0]


def banner(place, size=(224, 56)):
    """White on clear, at 4x then shrunk: the series in a small serif, the place in a big italic sans."""
    k = 4
    w, h = size[0] * k, size[1] * k
    im = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(im)
    top = ImageFont.truetype(str(FONTS / 'timesbd.ttf'), 15 * k)
    tw = d.textlength(SERIES, font=top)
    d.text(((w - tw) / 2, 1 * k), SERIES, font=top, fill=255)
    pt = 34
    while True:
        big = ImageFont.truetype(str(FONTS / 'arialbi.ttf'), pt * k)
        bw = d.textlength(place, font=big)
        if bw <= w - 8 * k or pt <= 18:
            break
        pt -= 1
    box = d.textbbox((0, 0), place, font=big)
    d.text(((w - bw) / 2, h - 3 * k - box[3]), place, font=big, fill=255)
    small = im.resize(size, Image.LANCZOS)
    out = Image.new('RGBA', size, (255, 255, 255, 0))
    out.putalpha(small)
    return out


def icon(shot, size):
    """The stage picture cut to the icon's shape from the middle of the shot, a touch above centre (the stage)."""
    im = Image.open(shot).convert('RGB')
    aspect = size[0] / size[1]
    w, h = im.size
    cw, ch = (w, round(w / aspect)) if w / h < aspect else (round(h * aspect), h)
    cw, ch = round(cw * 0.86), round(ch * 0.86)                 # a little closer than the whole frame
    x0, y0 = (w - cw) // 2, max(0, (h - ch) // 2 - h // 20)
    return im.crop((x0, y0, x0 + cw, y0 + ch)).resize(size, Image.LANCZOS)


def tex_header(fmt, tlut, w, h, image, palette=b''):
    return (b'TEX\0' + bytes([fmt, tlut, 0, 0]) +
            struct.pack('<6I', w, h, 32, len(image), 32 + len(image), len(palette)) + image + palette)


def tex_i4(im):
    a = np.array(im.convert('RGBA'))[..., 3] >> 4
    h, w = a.shape
    tiles = a.reshape(h // 8, 8, w // 8, 8).transpose(0, 2, 1, 3).reshape(-1, 2)
    return tex_header(I4, 0, w, h, (tiles[:, 0] << 4 | tiles[:, 1]).astype(np.uint8).tobytes())


def tex_ci8(im):
    q = im.convert('RGB').quantize(256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
    idx = np.array(q, np.uint8)
    h, w = idx.shape
    tiles = idx.reshape(h // 4, 4, w // 8, 8).transpose(0, 2, 1, 3).reshape(-1)
    pal = np.array(q.getpalette()[:768] + [0] * (768 - len(q.getpalette()[:768])), np.uint16).reshape(256, 3)
    words = (pal[:, 0] >> 3) << 11 | (pal[:, 1] >> 2) << 5 | pal[:, 2] >> 3
    return tex_header(CI8, RGB565, w, h, tiles.tobytes(), struct.pack('>256H', *words.tolist()))


def install(proj_dir, shots, log=print):
    """Every legal Colosseum stage's icon, banner, name and place in the project, as png and .tex."""
    proj_dir, shots = Path(proj_dir), Path(shots)
    done = 0
    for sj in sorted((proj_dir / 'data' / 'stages').glob('*.json')):
        j = json.loads(sj.read_text(encoding='utf-8'))
        if stem(j.get('fileName')) not in STAGES:
            continue
        capture, place = STAGES[stem(j['fileName'])]
        assets = j['assets']
        base_icon = proj_dir / 'assets' / assets['icon'].replace('\\', '/')
        base_banner = proj_dir / 'assets' / assets['banner'].replace('\\', '/')
        size = Image.open(base_icon.with_suffix('.png')).size
        ic = icon(shots / f'{capture}.png', size)
        ic.save(base_icon.with_suffix('.png'))
        base_icon.with_suffix('.tex').write_bytes(tex_ci8(ic))
        bn = banner(place)
        bn.save(base_banner.with_suffix('.png'))
        base_banner.with_suffix('.tex').write_bytes(tex_i4(bn))
        j['name'], j['location'] = place, SERIES
        sj.write_text(json.dumps(j, indent=2), encoding='utf-8')
        done += 1
        log(f'sss: {j["fileName"]} -> {place} ({assets["icon"]} {size[0]}x{size[1]}, {assets["banner"]})')
    if done != len(STAGES):
        raise SystemExit(f'sss art: {done} of {len(STAGES)} stages found in {proj_dir}')
    return done


def main():
    shots, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for capture, place in STAGES.values():
        ic = icon(shots / f'{capture}.png', (64, 56)).convert('RGBA')
        bn = banner(place)
        ic.save(out / f'icon-{capture}.png')
        bn.save(out / f'banner-{capture}.png')
        tile = Image.new('RGBA', (64 * 3 + 224 * 2 + 12, 56 * 2), (40, 30, 90, 255))
        tile.alpha_composite(ic.resize((192, 168)).crop((0, 28, 192, 140)), (0, 0))
        tile.alpha_composite(bn.resize((448, 112)), (204, 0))
        tiles.append(tile)
    sheet = Image.new('RGBA', (tiles[0].width, sum(t.height + 6 for t in tiles)), (20, 15, 40, 255))
    for i, t in enumerate(tiles):
        sheet.alpha_composite(t, (0, i * (t.height + 6)))
    sheet.save(out / 'sheet.png')


if __name__ == '__main__':
    main()
