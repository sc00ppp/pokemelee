"""Colosseum menus for the Melee CSS (MnSlChr.usd): the art and the menugraft spec that puts it in.

Pieces (md5s are the textures of the build's own MnSlChr.usd, from `menugraft dump`):
- the "MELEE" mode plate (MenuModel j36, frame 0 of its texture animation) -> the Pokemon Colosseum logo from the title
  scene (title.fsys logo_demo.rdat), in colour, its material made white so the logo is not tinted;
- the series emblems behind a picked fighter's portrait (j46-j49, frames 1-12) -> all the Pokemon emblem: every fighter
  is a mon now;
- the closed door (j138/j139 and the other ports, 128x200 IA8, a diagonal half) -> a Colosseum battle-menu panel:
  deep purple with a Poke Ball line emblem, kept to the door's own alpha;
- the coin's shading (TokenModel j3 d0, I8) -> a Poke Ball pattern over the player's colour;
- the frame (j85), the door frames (j61, j67, j73, j79), the mode plate (j1) and BACK (j39) -> vertex colours mapped to
  a purple ramp.

usage: python menu_art.py <dump dir of the build's MnSlChr.usd> <out dir>    writes <out>/spec.json and the .bgra files
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

COLO = SOURCE
LOGO = COLO / 'logotex' / 'd0_j19_o0_t0_540x224.png'

MELEE_PLATE = 'b805fe5dc129de3b0795a69c2700be5e'      # j36 m0 frame 0: "MELEE"
POKEMON_EMBLEM = 'b9cd58b6b25a205853c3833e03723a17'   # j46 m1 frame 7
DOOR = 'bbba35'
COIN = 'e4cbbb'
BACKING = 'f69ba110'     # 64x56 I4 grey plate behind every CSS icon (IconModel jN d0, MenuModel j4.. d0): made clear,
                         # the new icons fill their whole tile ("theres like background shit hanging out")

# BackgroundModel: translucent shapes (a=0.47) over a dark plane (j21). White and light blue over navy read grey-blue;
# these make them the Colosseum menus' purples.
TINTS = [('#FFFFFF', '#7a58d0'), ('#80B3FF', '#4b2c9e'), ('#070DFF', '#a040ff'), ('#000B1A', '#0d0620')]

# deep purple -> violet -> lavender, the Colosseum battle-menu panels
FRAME_STOPS = [[0.0, '#120a26'], [0.35, '#3a2470'], [0.7, '#7a5cc4'], [1.0, '#f2eaff']]


def load(dump, md5):
    man = {e['md5']: e for e in json.loads((Path(dump) / 'manifest.json').read_text())}
    full = next(k for k in man if k.startswith(md5))
    e = man[full]
    px = np.frombuffer((Path(dump) / f'{full}.bgra').read_bytes(), np.uint8).reshape(e['height'], e['width'], 4)
    return full, Image.fromarray(px[..., [2, 1, 0, 3]].copy(), 'RGBA'), e


def emit(out, specs, md5, im, fmt):
    px = np.array(im.convert('RGBA'))[..., [2, 1, 0, 3]]
    path = Path(out) / f'{md5}.bgra'
    path.write_bytes(px.tobytes())
    Image.fromarray(np.array(im.convert('RGBA')), 'RGBA').save(Path(out) / f'{md5}.png')
    specs.append({'md5': md5, 'bgra': str(path), 'width': im.width, 'height': im.height, 'format': fmt})


def logo(size=(176, 64)):
    src = Image.open(LOGO).convert('RGBA')
    src = src.crop(src.getbbox())
    scale = min(size[0] / src.width, size[1] / src.height)
    small = src.resize((round(src.width * scale), round(src.height * scale)), Image.LANCZOS)
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    out.alpha_composite(small, ((size[0] - small.width) // 2, (size[1] - small.height) // 2))
    return out


def logo_ink(size=(176, 64)):
    """The mode plate draws its texture as black ink whatever its colours (Melee's CSS code; REPLACE, a white material
    and a colour resting texture all still drew black), so the logo is inked by darkness: its dark outlines and
    shading black, its bright letters clear, the purple behind showing through them."""
    px = np.asarray(logo(size), float) / 255
    lum = px[..., :3] @ [0.299, 0.587, 0.114]
    a = px[..., 3] * np.clip((1 - lum) * 1.4, 0, 1)
    out = np.zeros(px.shape)
    out[..., 3] = a
    return Image.fromarray((out * 255).round().astype(np.uint8), 'RGBA')


def pokeball_lines(size, width, colour):
    """A Poke Ball as lines: the ring, the band across, the button ring. Symmetric under a half turn."""
    w, h = size
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = min(w, h) * 0.36
    cx, cy = w / 2, h / 2
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=colour, width=width)
    d.line((cx - r, cy, cx - r * 0.3, cy), fill=colour, width=width)
    d.line((cx + r * 0.3, cy, cx + r, cy), fill=colour, width=width)
    d.ellipse((cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3), outline=colour, width=width)
    d.ellipse((cx - r * 0.13, cy - r * 0.13, cx + r * 0.13, cy + r * 0.13), fill=colour)
    return im


def door(mask_src, size=(128, 200)):
    """Purple panel, darker at the edges, fine horizontal lines, a Poke Ball line emblem in the middle; the original
    door's alpha (the diagonal half and its soft edge) is kept."""
    w, h = size
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    edge = np.minimum(np.minimum(x, 1 - x), np.minimum(y, 1 - y))
    glow = np.clip(edge * 6, 0, 1)
    base = np.array([0x2a, 0x18, 0x55], float)
    top = np.array([0x6a, 0x4a, 0xb8], float)
    k = (0.35 + 0.65 * glow)[..., None] * (1 - 0.35 * np.abs(y - 0.5)[..., None] * 2)
    rgb = base + (top - base) * k
    rgb[(np.arange(h) % 6 == 0)] *= 0.86
    im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.full((h, w), 255)]).astype(np.uint8), 'RGBA')
    emblem = pokeball_lines(size, 5, (232, 220, 255, 150)).filter(ImageFilter.GaussianBlur(0.6))
    im.alpha_composite(emblem)
    a = np.array(mask_src.convert('RGBA'))[..., 3]
    px = np.array(im)
    px[..., 3] = a
    return Image.fromarray(px, 'RGBA')


def coin(size=32):
    """Intensity = how dark the overlay makes the player's coloured disc: top half clear (full colour), bottom half
    half dark, black band and button ring, clear button."""
    s = size * 4
    im = Image.new('L', (s, s), 0)
    d = ImageDraw.Draw(im)
    r = s / 2
    d.rectangle((0, r, s, s), fill=120)
    band = s * 0.07
    d.rectangle((0, r - band, s, r + band), fill=255)
    br = s * 0.2
    d.ellipse((r - br, r - br, r + br, r + br), fill=255)
    br2 = s * 0.12
    d.ellipse((r - br2, r - br2, r + br2, r + br2), fill=0)
    im = im.resize((size, size), Image.LANCZOS)
    v = np.array(im)
    return Image.fromarray(np.dstack([v, v, v, v]), 'RGBA')


def main():
    dump, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    specs = []
    emit(out, specs, MELEE_PLATE, logo_ink(), 'IA4')   # one colour (black ink), alpha only: IA4 is half of IA8 (online CSS memory)
    man = json.loads((dump / 'manifest.json').read_text())
    _, poke, _ = load(dump, POKEMON_EMBLEM)
    for e in man:
        if (e['width'], e['height'], e['format']) == (80, 64, 'I4') and e['md5'] != POKEMON_EMBLEM \
                and any('j46 m1' in u or 'j46 d1' in u for u in e['uses']):
            emit(out, specs, e['md5'], poke, 'I4')
    full, door_src, door_e = load(dump, DOOR)
    emit(out, specs, full, door(door_src), 'RGB5A3')
    door_joints = sorted({int(u.split()[1][1:]) for u in door_e['uses'] if u.startswith('MenuModel j')})
    full, _, _ = load(dump, COIN)
    emit(out, specs, full, coin(), 'I8')
    full, _, _ = load(dump, BACKING)
    emit(out, specs, full, Image.new('RGBA', (64, 56), (0, 0, 0, 0)), 'I4')
    spec = {
        'images': specs,
        'recolor': [{'model': 'MenuModel', 'joints': [85, 61, 67, 73, 79, 1, 39], 'stops': FRAME_STOPS, 'mix': 1.0}],
        'tints': [{'model': 'BackgroundModel', 'from': a, 'to': b} for a, b in TINTS],
        'materials': [
            # the logo in its own colours: the plate's material (and its animation) draws the I4 "MELEE" black
            {'model': 'MenuModel', 'joint': 36, 'dobj': 0, 'diffuse': '#FFFFFFFF', 'colormap': 'REPLACE'},
            {'model': 'TokenModel', 'joint': 3, 'dobj': 0, 'alpha': 0.85},
        ] + [{'model': 'MenuModel', 'joint': j, 'dobj': 0, 'diffuse': '#FFFFFFFF'} for j in door_joints],
    }
    (out / 'spec.json').write_text(json.dumps(spec, indent=1))
    print(len(specs), 'images ->', out / 'spec.json')


if __name__ == '__main__':
    main()
