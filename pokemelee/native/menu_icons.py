"""New CSS icons: each mon's own Colosseum model rendered head and shoulders (icon_render.py in Blender), on a
background in its type's colour, filling m-ex's whole 64x56 icon so no Melee tile shows around it. Ice Climbers and the
Plusle & Minun pick show both mons together.

usage: python css_icons.py <out dir> [--flat] [mon ...]     writes css-<mon>.png (64x56) and raw/<mon>.png (the render)
--flat renders texture colour only with no light (the AniMelee look); an outline is added after.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


SIZE = (64, 56)
SCALE = 4

TYPE = {'fire': ('#ff9a3c', '#a8320c'), 'water': ('#6aa8ff', '#1f3f9e'), 'grass': ('#86d860', '#256b1e'),
        'psychic': ('#ff7fb8', '#8c1f5c'), 'electric': ('#ffe14a', '#b07a00'), 'normal': ('#d8d0b8', '#6e6450'),
        'fighting': ('#e0663c', '#7a1f12'), 'bug': ('#c2d43a', '#55650f'), 'ice': ('#9fe6f0', '#2f7d96'),
        'steel': ('#c8c8dc', '#5a5a78')}

# mon -> (model, type, view overrides). Model: a cast folder under mons/, else a rip folder under the pokedex repo.
CAST = {
    'magmar': ('magmar', 'fire', {'top': 0.62}), 'miltank': ('miltank', 'normal', {}),
    'breloom': ('breloom', 'grass', {'yaw': 15}),
    'blastoise': ('blastoise', 'water', {'yaw': 10, 'top': 0.6}), 'gardevoir': ('gardevoir', 'psychic', {'top': 0.35, 'yaw': 20}),
    'blaziken': ('blaziken', 'fire', {}), 'machoke': ('machoke', 'fighting', {}), 'quilava': ('quilava', 'fire', {}),
    'combusken': ('combusken', 'fire', {'top': 0.6}), 'deoxys': ('deoxys', 'psychic', {'top': 0.4}),
    'alakazam': ('alakazam', 'psychic', {}),
    'sceptile': ('sceptile', 'grass', {'top': 0.55, 'head': 0.3}),       # its top is the crest, its tail is wide
    'scyther': ('scyther', 'bug', {'at': [0.5, 0.45]}),                  # the head sits below the wing tips
    'swampert': ('swampert', 'water', {}),
    'farfetchd': ('farfetchd', 'normal', {}), 'wigglytuff': ('wigglytuff', 'normal', {}),
    'kecleon': ('kecleon', 'normal', {'yaw': 10, 'top': 0.65}), 'charmeleon': ('charmeleon', 'fire', {}),
    'ralts': ('ralts', 'psychic', {'top': 0.7, 'yaw': 15, 'pitch': -15}),
    'scizor': ('scizor', 'steel', {'at': [0.72, 0.42], 'cx': 0.02}), 'unownx': ('g3_unknown_x', 'psychic', {'top': 1.0, 'yaw': 0}),
    'pikachu': ('025_Pikachu', 'electric', {'top': 0.65}), 'jigglypuff': ('039_Jigglypuff', 'normal', {'top': 1.0}),
    'mewtwo': ('150_Mewtwo', 'psychic', {}), 'pichu': ('172_Pichu', 'electric', {'top': 0.8}),
}
PAIRS = {
    'plusle-minun': ('electric', {'top': 0.62, 'yaw': 0, 'fitw': True, 'head': 1.0},
                     [{'mon': 'plusle', 'x': -0.3, 'turn': -15}, {'mon': 'minun', 'x': 0.3, 'y': 0.1, 'turn': 15}]),
    'jynx-smoochum': ('ice', {'top': 0.85, 'yaw': 10, 'fitw': True, 'head': 1.0},
                      [{'mon': 'jynx', 'x': 0.18, 'y': 0.3}, {'mon': 'smoochum', 'height': 0.6, 'x': -0.34, 'y': -0.25, 'turn': 10}]),
}
# per-model options for icon_render (texture wrap the rip lost)
# Gardevoir: the eyes' UVs are mirrored (the rip clamps them) and sample the strip's top frame, the closed eye; the open
# eye is the frame at row 288 (the saved Gardevoir eye recipe)
# Deoxys: the rip keeps only the face's second layer (the slit); the eyes were the pkx's blink strip (img 585c0), which
# the hand port baked into one front-on face picture (hand/deoxys-Samus/look/face.png, UVs 0.019 in from each edge)
MODEL = {'deoxys': {'hide': ['deoxys_mesh_21', 'deoxys_mesh_22'],    # tentacle strips stretched to twice its height
                    'face': {'deoxys_mesh_10': {'image': '{deoxys_face}',
                                                'margin': 0.019}}},
         'gardevoir': {'wrap': {'sirnight_mesh_25': 'MIRROR'}, 'rows': {'sirnight_mesh_25': [0, 288, 96]}}}


def background(kind, size):
    """Type colour, light at the top left to dark at the bottom right, a faint Poke Ball line at the right."""
    w, h = size
    light, dark = (np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float) for c in TYPE[kind])
    yy, xx = np.mgrid[0:h, 0:w]
    t = np.clip((xx / w * 0.4 + yy / h * 0.6), 0, 1)[..., None]
    rgb = light * (1 - t) + dark * t
    im = Image.fromarray(np.dstack([rgb, np.full((h, w), 255)]).astype(np.uint8), 'RGBA')
    ball = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ball)
    r, cx, cy = h * 0.62, w * 0.78, h * 0.62
    lw = max(2, h // 22)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 46), width=lw)
    d.line((cx - r, cy, cx - r * 0.32, cy), fill=(255, 255, 255, 46), width=lw)
    d.line((cx + r * 0.32, cy, cx + r, cy), fill=(255, 255, 255, 46), width=lw)
    d.ellipse((cx - r * 0.32, cy - r * 0.32, cx + r * 0.32, cy + r * 0.32), outline=(255, 255, 255, 46), width=lw)
    im.alpha_composite(ball)
    return im


def outline(render, px):
    """A black line around the silhouette, `px` wide (the AniMelee look)."""
    a = render.split()[3]
    grown = a.filter(ImageFilter.MaxFilter(px * 2 + 1))
    line = Image.new('RGBA', render.size, (0, 0, 0, 255))
    line.putalpha(grown)
    line.alpha_composite(render)
    return line


def compose(render, kind, flat):
    big = (SIZE[0] * SCALE, SIZE[1] * SCALE)
    im = background(kind, big)
    fig = render.convert('RGBA').resize(big, Image.LANCZOS)
    if flat:
        fig = outline(fig, 5)
    else:
        shadow = Image.new('RGBA', big, (0, 0, 0, 0))
        shadow.putalpha(fig.split()[3].point(lambda v: v * 0.45))
        im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)), (6, 6))
    im.alpha_composite(fig)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, big[0] - 1, big[1] - 1), outline=(20, 12, 40, 255), width=SCALE * 2)
    d.rectangle((SCALE * 2, SCALE * 2, big[0] - 1 - SCALE * 2, big[1] - 1 - SCALE * 2), outline=(255, 255, 255, 90), width=SCALE)
    return im.resize(SIZE, Image.LANCZOS)


def sheet(out, names, scale=3):
    ims = [Image.open(out / f'css-{n}.png') for n in names if (out / f'css-{n}.png').is_file()]
    cols = 9
    rows = (len(ims) + cols - 1) // cols
    w, h = SIZE[0] * scale + 8, SIZE[1] * scale + 8
    sh = Image.new('RGBA', (cols * w, rows * h), (30, 24, 50, 255))
    for i, im in enumerate(ims):
        sh.alpha_composite(im.resize((SIZE[0] * scale, SIZE[1] * scale), Image.NEAREST), ((i % cols) * w + 4, (i // cols) * h + 4))
    sh.save(out / 'sheet.png')
