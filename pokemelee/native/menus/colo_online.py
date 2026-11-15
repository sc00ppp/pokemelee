"""Colosseum look for the one-door character select: 1P modes and Slippi's online CSS (owner 2026-11-12: "can we make that
online screen more pokemon themed too? its kinda just normal melee screen mostly ... basically just redesign that one
too").

That screen is MnSlChr's SingleMenuModel tree (the VS screen is MenuModel, colo_menus.css_spec). Its j1 sits where
MenuModel's J1 does and shares the CSS camera, so the VS screen's pictures and screen rects carry over; quads added here
draw only in the one-door screen, and the ones whose picture matches a VS quad's share it (menugraft shares identical
quad pictures within one patch).

Pieces (1280x960 shot):
- j1 d0 / d1, Melee's grey top band with the "1-P" circle and the bottom band: off-screen;
- j36 d1, the 1P mode name, which Slippi's online CSS shows as "MELEE", and j36 d0, the multi-man subtitle: off-screen;
  the Colosseum logo plate there instead (the VS plate's three slices and the logo in its own colours, the picture
  the VS plate's logo shares) and the violet title pill (VS's), plain (owner 11-12: "remove the choose your pokemon
  text on singeplayer, just have the pill thing"; j36's blank frame picture is shared with a dozen VS frames: never
  replace it);
- the player's card (j41 d0): a Colosseum panel in the player's colour with a Poke Ball emblem, a picture of its own
  (Melee's card picture is also the VS cards' and PortraitModel j2's: owner 11-12, "the vs mode doors got fucked up
  now"; menugraft's per-use `only`), a chrome frame around it (the VS doors' frame pieces), the flat grey outline (d2)
  clear, the name tray (j51) in the doors' purple;
- Slippi's own text (the name, the mode, the matchmaking lines) is drawn at fixed screen places right of the card and
  is never moved here: a chrome-framed violet panel sits behind it, deep enough not to hide it.

Memory: this screen shares a 5,760 KB heap with Slippi's MnExtAll (colo_menus.css_spec MEMORY); dead_pictures() blanks
Melee's 25 original icon pictures (MenuModel / SingleMenuModel j4-j34 d1, drawn by nothing: m-ex draws its own
IconModel), about 94 KB, so this file ends smaller than vanilla's.
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import colo_menus as cm

S_J1 = cm.J1                      # SingleMenuModel j1: MenuModel J1's place
S_CARD = (-30.0, -2.5)            # SingleMenuModel j41, the player's card
S_CARD_QUAD = (0.4, -0.3, 16.9, -22.1)   # its d0 quad (x0, ytop, x1, ybottom) in j41's space (menugraft tree)
LOGO_PLATE = (36, 20, 282, 138)   # VS's plate (cm.LOGO_PLATE), the same size, 14 px higher
LOGO = (74, 48, 244, 110)         # the logo on the plate's chrome inner panel
TITLE = (378, 66, 1038, 130)      # VS's title pill (cm.TITLE), 12 px higher

# BackgroundModel j21, Melee's dark plane behind the CSS (both screens; scale 0.1): its local units on a 1280x960 shot,
# measured with a labelled grid (preview t4). Quads here draw BEFORE Slippi's online text; quads on SingleMenuModel draw
# after it and hide it at any depth (preview t3: strips from z -1 to -50 all hid it).
BG_X, BG_Y, BG_KX, BG_KY = 640.0, 479.3, 1.8333, 1.6667
BACKDROP = (-40, -30, 1320, 990)
TEXT_PANEL = (410, 516, 1252, 904)  # behind Slippi's text (name at x 436, mode at 767-1096, from y 544), right of the card
                                    # (its name tray, px 70-420, overlaps the left edge a little at the bottom)


def bg_rect(x0, y0, x1, y1):
    f = lambda x, y: (round((x - BG_X) / BG_KX, 2), round((BG_Y - y) / BG_KY, 2))
    (a, b), (c, d) = f(x0, y0), f(x1, y1)
    return [a, b, c, d]


def panel_fill(size=(8, 64)):
    return cm.fill_rgb(size, cm.vgrad(size[1], [(0.0, (84, 74, 156)), (0.45, (58, 50, 116)), (1.0, (34, 28, 80))])).convert('RGBA')


def stripes(size=(8, 8)):
    """Colosseum's fine panel lines: one bright row in four, mostly clear (IA4, repeated)."""
    i = np.ones(size[::-1])
    a = np.where((np.arange(size[1]) % 4 == 0)[:, None], 0.16, 0.0) * np.ones(size[::-1])
    return cm.grey((i, a))


def card(size=(128, 192)):
    """The player's card (IA4, the game tints it in the player's colour): a rounded panel, lighter at the top, fine
    horizontal stripes like Colosseum's panels, a pale inner rim, a Poke Ball line emblem in the middle."""
    w, h = size
    W, H = w * cm.SS, h * cm.SS
    S = cm.SS
    outer = np.asarray(cm.rr_mask((W, H), (2 * S, 2 * S, W - 1 - 2 * S, H - 1 - 2 * S), 12 * S), float) / 255
    rim = np.asarray(cm.rr_mask((W, H), (6 * S, 6 * S, W - 1 - 6 * S, H - 1 - 6 * S), 9 * S), float) / 255
    inner = np.asarray(cm.rr_mask((W, H), (8 * S, 8 * S, W - 1 - 8 * S, H - 1 - 8 * S), 8 * S), float) / 255
    ys = np.linspace(0, 1, H)[:, None]
    base = np.repeat(np.interp(ys, [0, 0.4, 1], [1.0, 0.86, 0.6]), W, 1)
    stripes = np.where((np.arange(H)[:, None] // S) % 4 == 0, 0.86, 1.0)
    inten = base * stripes
    inten = np.where(rim - inner > 0.5, 1.0, inten)            # the pale inner rim
    inten = np.where(outer - rim > 0.5, 0.55, inten)           # the darker outer edge
    em = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(em)
    cx, cy, r, lw = W / 2, H * 0.47, W * 0.33, 3 * S
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=255, width=lw)
    d.line((cx - r, cy, cx - r * 0.32, cy), fill=255, width=lw)
    d.line((cx + r * 0.32, cy, cx + r, cy), fill=255, width=lw)
    d.ellipse((cx - r * 0.32, cy - r * 0.32, cx + r * 0.32, cy + r * 0.32), outline=255, width=lw)
    d.ellipse((cx - r * 0.14, cy - r * 0.14, cx + r * 0.14, cy + r * 0.14), fill=255)
    e = np.asarray(em.filter(ImageFilter.GaussianBlur(S * 0.6)), float) / 255
    inten = inten * (1 - e) + 1.0 * e
    alpha = outer * np.where(rim > 0.5, 0.8 + 0.15 * e, 1.0)
    return cm.reduce(cm.grey((inten, alpha)), size)


def dead_pictures(dump, out):
    """Melee's original icon pictures (and their grey backing), which nothing draws: 8x8 clear, same format."""
    import json
    images = []
    for e in json.loads((Path(dump) / 'manifest.json').read_text()):
        uses = e['uses']
        icon = (e['width'], e['height']) == (64, 56) and uses and all(
            u.split()[0] in ('MenuModel', 'SingleMenuModel', 'MenuMaterialAnimation', 'SingleMenuMaterialAnimation')
            and (' d1 ' in u or ' m1 ' in u or ' d0 ' in u) and 4 <= int(u.split()[1][1:]) <= 34 for u in uses)
        if icon:
            images.append({**cm.emit(out, 'dead-' + e['md5'][:8], Image.new('RGBA', (8, 8), (0, 0, 0, 0)), e['format']),
                           'md5': e['md5']})
    return images


def parts(dump, out):
    """menugraft spec pieces for SingleMenuModel: {images, quads, materials, moves, recolor}"""
    import menu_art
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    images, quads = [], []

    def quad(name, im, fmt, rect_px, joint=1, z=0.0, joint_at=S_J1):
        q = cm.emit(out, name, im, fmt)
        q.update({'model': 'SingleMenuModel', 'joint': joint, 'rect': cm.local_rect(*rect_px, joint=joint_at), 'z': z})
        quads.append(q)

    # top: the VS plate (same three pictures) with the logo, the VS title pill; both a little higher
    # than in VS, where nothing sits under them (here the icons' top row starts at px 144)
    L = LOGO_PLATE
    lp = cm.plate((L[2] - L[0], L[3] - L[1]))
    PL, PR = 72, 48
    pw, ph = lp.size
    quad('s-logo-plate-l', lp.crop((0, 0, PL, ph)), 'CI8', (L[0], L[1], L[0] + PL, L[3]))
    quad('s-logo-plate-m', lp.crop((pw // 2 - 4, 0, pw // 2 + 4, ph)), 'CI8', (L[0] + PL - 1, L[1], L[2] - PR + 1, L[3]))
    quad('s-logo-plate-r', lp.crop((pw - PR, 0, pw, ph)), 'CI8', (L[2] - PR, L[1], L[2], L[3]))
    quad('s-logo', cm.logo_picture(), 'CI8', LOGO, z=0.02)
    T = TITLE
    th = T[3] - T[1]
    left, mid, right = cm.three_slice(cm.pill((48 * 4, 48), cm.VIOLET, stripes=True), 48)
    quad('s-title-l', left, 'CI8', (T[0], T[1], T[0] + th, T[3]))
    quad('s-title-m', mid, 'CI8', (T[0] + th - 1, T[1], T[2] - th + 1, T[3]))
    quad('s-title-r', right, 'CI8', (T[2] - th, T[1], T[2], T[3]))
    # j36 d0 (the multi-man subtitles) goes off-screen; the pill stays plain
    # the card: new panel picture for this card only (VS's cards keep Melee's), the doors' chrome frame around it
    images.append({**cm.emit(out, 'card', card(), 'IA4'), 'md5': cm.by_use(dump, 'SingleMenuModel j41 d0 t0'),
                   'only': ['SingleMenuModel j41 d0 t0']})
    x0, yt, x1, yb = S_CARD_QUAD
    k0, k1 = 4 / 128, 124 / 128                   # the panel's own edge in the picture (card(): 2 px in + 2 px rim)
    cx0, cx1 = x0 + (x1 - x0) * k0, x0 + (x1 - x0) * k1
    cyt, cyb = yt + (yb - yt) * (4 / 192), yt + (yb - yt) * (188 / 192)
    e = 0.45
    for name, im, (a0, b0, a1, b1) in cm.frame_pieces((cx1 - cx0) + 2 * e, (cyt - cyb) + 2 * e):
        q = cm.emit(out, f's-frame-{name}', im, 'IA4')
        q.update({'model': 'SingleMenuModel', 'joint': 41, 'z': 0.05,
                  'rect': [round(cx0 - e + a0, 3), round(cyt + e - b0, 3), round(cx0 - e + a1, 3), round(cyt + e - b1, 3)]})
        quads.append(q)
    # behind everything, on the background plane (drawn before Slippi's text): Colosseum's backdrop (VS's picture) and a
    # chrome-framed violet panel under Slippi's text
    def bg_quad(name, im, fmt, rect_px, z, uv=None, wrap=None):
        q = cm.emit(out, name, im, fmt)
        q.update({'model': 'BackgroundModel', 'joint': 21, 'rect': bg_rect(*rect_px), 'z': z})
        if uv:
            q.update({'uv': uv, 'wrap': wrap})
        quads.append(q)
    bg_quad('s-backdrop', cm.backdrop((128, 96)), 'CMP', BACKDROP, 5)
    P = TEXT_PANEL
    m = 6                                           # the fill reaches under the frame's inner bevel
    bg_quad('s-panel-fill', panel_fill(), 'CI8', (P[0] + m, P[1] + m, P[2] - m, P[3] - m), 6)
    bg_quad('s-panel-lines', stripes(), 'IA4', (P[0] + m, P[1] + m, P[2] - m, P[3] - m), 6.5,
            uv=[0, 0, (P[2] - P[0] - 2 * m) / 16, (P[3] - P[1] - 2 * m) / 8], wrap='REPEAT')
    pw_u, ph_u = (P[2] - P[0]) / 18.5, (P[3] - P[1]) / 16.8      # the frame in CSS units (its corners' size)
    for name, im, (a0, b0, a1, b1) in cm.frame_pieces(pw_u, ph_u):
        bg_quad(f's-panel-frame-{name}', im, 'IA4', (P[0] + a0 * 18.5, P[1] + b0 * 16.8, P[0] + a1 * 18.5, P[1] + b1 * 16.8), 7)
    bs = 34
    bg_quad('s-panel-badge', cm.pokeball_badge(32), 'CI8', (P[2] - bs - 14, P[1] + 12, P[2] - 14, P[1] + 12 + bs), 7.5)
    materials = [{'model': 'SingleMenuModel', 'joint': 41, 'dobj': 2, 'alpha': 0.0}]
    recolor = [{'model': 'SingleMenuModel', 'joints': [51], 'stops': menu_art.FRAME_STOPS, 'mix': 1.0}]
    moves = [{'model': 'SingleMenuModel', 'dobjs': [[1, 0], [1, 1], [36, 0], [36, 1]], 'dx': 0, 'dy': 400}]
    return {'images': images, 'quads': quads, 'materials': materials, 'moves': moves, 'recolor': recolor}
