"""The character select grid in straight, centred rows (owner 2026-11-11: "the css icons grid is like weird rn too its
not nice and symmetrical").

Melee's grid is 9 / 9 / 7 with the end icons of each row dropped back and down (z -1, y -0.3), and the pair's icon was
tacked onto the bottom row's right end, so the bottom row was 8 hanging off-centre. Here every row is flat (z 0) and
centred on the screen's middle, the rows keep Melee's order (so Fox is still where a Melee player looks for him), and
the pair sits at the bottom row's left end, beside Pichu and Pikachu: 9 / 9 / 8.

usage: from build_iso, after the pair is placed: css_grid.straighten(mex, first=pair_pichu.PAIR)
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json

CENTRE_X = 0.05          # Melee's own grid centre and pitch (get-css-layout's template)
STEP_X = 7.05
ROWS_Y = [16.7, 9.5, 2.3]
PER_ROW = 9


def rows_of(icons, first=None):
    """Melee's rows top to bottom, each left to right; `first` (a fighter name) goes to the front of its row."""
    rows = {}
    for ic in icons:
        nearest = min(range(len(ROWS_Y)), key=lambda k: abs(ROWS_Y[k] - ic['y']))   # 16.4 and 16.7 are one row
        rows.setdefault(-nearest, []).append(ic)
    out = []
    for key in sorted(rows, reverse=True):
        out.append(sorted(rows[key], key=lambda ic: (-1e9 if first and ic.get('fighterName') == first else ic['x'])))
    return out


def layout(rows):
    """[(icon, x, y)] for rows of at most PER_ROW, each centred, rows at Melee's heights."""
    if len(rows) > len(ROWS_Y) or any(len(r) > PER_ROW for r in rows):
        raise ValueError(f'rows {[len(r) for r in rows]} do not fit {len(ROWS_Y)} rows of {PER_ROW}')
    placed = []
    for row, y in zip(rows, ROWS_Y):
        for i, ic in enumerate(row):
            placed.append((ic, round(CENTRE_X + (i - (len(row) - 1) / 2) * STEP_X, 4), y))
    return placed


# VS with side doors (css_doors.py; owner 11-11: "make the icons bigger so they fill the space, not just half of it"):
# the grid fills the whole middle column, from the top bar down to the doors' bottom, five across in honeycomb rows
# 5 / 4 / 5 / 4 / 5 / rest. The file keeps the straight 9 / 9 / 8 rows (straighten) for 1P and Slippi online, whose
# one door and Slippi's text sit under the grid; css_doors' code moves the icons and their hit boxes in VS only.
VS_LEFT, VS_RIGHT = -18.8, 19.1          # the doors' inner edges (visual = icon coordinates)
VS_TOP, VS_BOTTOM = 20.3, -26.3          # under the top bar, down to the doors' bottom
VS_ROWS = (5, 4)


def vs_rows(n):
    rows, k = [], 0
    while sum(rows) < n:
        rows.append(min(VS_ROWS[k % 2], n - sum(rows)))
        k += 1
    return rows


def vs_layout(n):
    """(scale, [(x, y)] in icon order, rows) for n icons in VS"""
    rows = vs_rows(n)
    s = 0.985 * min((VS_RIGHT - VS_LEFT) / (VS_ROWS[0] * STEP_X), (VS_TOP - VS_BOTTOM) / (len(rows) * 7.2))
    cx, h = (VS_LEFT + VS_RIGHT) / 2, 7.2 * s
    top = (VS_TOP + VS_BOTTOM) / 2 + h * len(rows) / 2 - h / 2       # first row's centre, the block centred
    out = []
    for r, m in enumerate(rows):
        for i in range(m):
            out.append((round(cx + (i - (m - 1) / 2) * STEP_X * s, 4), round(top - r * h, 4)))
    return round(s, 4), out, rows


# Side doors, first try (superseded by vs_layout): seven columns at 0.72 of Melee's icon, rows 7 / 6 / 7 / 6, above
# y -1 in every mode.
SIDE_SCALE = 0.72
SIDE_ROWS = [7, 6, 7, 6]
SIDE_ROWS_Y = [17.6, 12.4, 7.2, 2.0]


def side_layout(order):
    if sum(SIDE_ROWS) < len(order):
        raise ValueError(f'{len(order)} icons do not fit rows {SIDE_ROWS}')
    step = STEP_X * SIDE_SCALE
    placed, k = [], 0
    for n, y in zip(SIDE_ROWS, SIDE_ROWS_Y):
        row = order[k:k + n]
        k += n
        for i, ic in enumerate(row):
            placed.append((ic, round((i - (len(row) - 1) / 2) * step, 4), y))
    return placed


def side_doors(mex, first=None, log=print):
    data = mex.get_css_layout()
    order = [ic for row in rows_of(data['icons'], first) for ic in row]     # Melee's reading order
    w, h = data['template'].get('iconWidth', STEP_X), data['template'].get('iconHeight', 7.2)
    icons = [{**ic, 'x': x, 'y': y, 'z': 0, 'scaleX': SIDE_SCALE, 'scaleY': SIDE_SCALE,
              'collisionSizeX': round(w * SIDE_SCALE, 4), 'collisionSizeY': round(h * SIDE_SCALE, 4)}
             for ic, x, y in side_layout(order)]
    template = {**(data.get('template') or {}), 'iconSideDropX': 0, 'iconSideDropY': 0, 'iconSideDropZ': 0}
    mex.set_css_layout(json.dumps({'template': template, 'icons': icons}))
    back = mex.get_css_layout()['icons']
    scales = sorted({(ic.get('scaleX'), ic.get('collisionSizeX')) for ic in back})
    log(f'css grid (side doors): {len(back)} icons, rows {SIDE_ROWS}, scale/collision {scales}', flush=True)
    return back


def straighten(mex, first=None, log=print):
    """Melee-size straight rows (1P, Slippi online; VS too without css_doors). Returns the icons as m-ex stores them,
    in its order (the order css_doors' code walks)."""
    data = mex.get_css_layout()
    rows = rows_of(data['icons'], first)
    icons = []
    for ic, x, y in layout(rows):
        icons.append({**ic, 'x': x, 'y': y, 'z': 0, 'scaleX': 1.0, 'scaleY': 1.0,
                      'collisionSizeX': STEP_X, 'collisionSizeY': 7.2, 'collisionOffsetX': 0, 'collisionOffsetY': 0})
    template = {**(data.get('template') or {}), 'iconSideDropX': 0, 'iconSideDropY': 0, 'iconSideDropZ': 0}
    mex.set_css_layout(json.dumps({'template': template, 'icons': icons}))
    back = mex.get_css_layout()['icons']
    shape = [len(r) for r in rows_of(back)]
    flat = all(ic.get('z', 0) == 0 for ic in back)
    log(f'css grid: rows {shape}, all flat {flat}', flush=True)
    return back


def box(ic):
    """the hit box m-ex builds for an icon (MexCharacterSelectIcon.ToIcon): X1, X2, Y2, Y1 in its table's order"""
    sx, sy = ic.get('scaleX', 1.0), ic.get('scaleY', 1.0)
    w, h = ic.get('collisionSizeX', STEP_X), ic.get('collisionSizeY', 7.2)
    ox, oy = ic.get('collisionOffsetX', 0), ic.get('collisionOffsetY', 0)
    return (ic['x'] - w / 2 * sx + ox, ic['x'] + w / 2 * sx + ox, ic['y'] + h / 2 * sy + oy, ic['y'] - h / 2 * sy + oy)
