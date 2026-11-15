"""The stage select with the six legal (Colosseum) stages in their own big row under the rest (owner 2026-11-11: "put
the 6 legal stages at the bottom so they stand out").

Melee's 30 icons: two rows of ten across the top (group 0, with Icicle Mountain and Flat Zone hung at the sides), the
Random box and two rows of six in the middle (group 1), and five small past stages at the bottom (group 2). Here the 23
other stages go in three rows of eight at the top, small, in straight columns; under them the six legal stages, larger, in
one centred row, high enough to clear the stage name banner the menu draws at the bottom left; Random, small, in the
bottom right corner (since 11-12). Each group slides in as Melee's groups do.

World units on this screen: x about 22.4 px per unit across 1280 px (0 is the middle), y about 20.5 px per unit (y 0 is
px 476). An icon's width/height are half-extents at scale 1 (3.1 x 2.7).

usage: from build_iso, after the stages are in: sss_layout.arrange(mex)
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json

# Melee stage ids (m-ex stageID) of the legal stages, in the order they show left to right
LEGAL = [31, 32, 28, 8, 2, 3]     # Battlefield, Final Destination, Dream Land N64, Yoshi's Story, Fountain, Stadium
SMALL, BIG = 0.78, 1.15
ROWS_Y = [16.3, 11.7, 7.1]        # the others, three rows of eight, in straight columns (the last row ends short)
COLS = 8
STEP_SMALL = 6.5
LEGAL_Y = -0.6
STEP_BIG = 7.5
# Random (owner 11-12: "too big, maybe we could put it in the bottom right or something so its easy to click random"): in the
# bottom right corner, where the cursor stops when the stick is held down-right (mnstagesel clamps it to x +-27, y +-19), right
# of the STAGE SELECT bar (colo_menus.STAGE_PILL). The game draws the Random model at its own size whatever its scale here
# says; colo_menus shrinks its mesh (RANDOM_K .82: drawn half-extents 3.15 x 2.30). The hit box reaches the clamp corner.
# Owner 11-12 on Cast Test 25 ("make it like fill into that red outline"): the red outline is the game's hover box
# (SelectBoxModel, +-3.2 x 2.78), which mnstagesel scales by the icon's layout scale (x14/x18, fn_8025A560): RANDOM_BOX
# sizes it, colo_menus.RANDOM_K sizes the button to fill it, and the whole box stays on screen.
RANDOM_AT = (24.5, -17.07)
RANDOM_HIT = (3.2, 2.35)
RANDOM_BOX = 0.9


def placements(icons):
    """[(icon, x, y, z, scale, group)]: everything not legal in rows of COLS, the legal row under, Random in the corner."""
    legal = sorted([ic for ic in icons if ic.get('stageID') in LEGAL], key=lambda ic: LEGAL.index(ic['stageID']))
    if len(legal) != len(LEGAL):
        raise ValueError(f'legal stages found: {[ic.get("stageName") for ic in legal]}')
    others = [ic for ic in icons if ic.get('stageID') not in LEGAL and ic.get('status') != 3]
    others.sort(key=lambda ic: (-round(ic['y']), ic['x']))            # Melee's own reading order
    if len(others) > COLS * len(ROWS_Y):
        raise ValueError(f'{len(others)} other icons do not fit {len(ROWS_Y)} rows of {COLS}')
    out = []
    for k, ic in enumerate(others):
        r, c = divmod(k, COLS)
        out.append((ic, round((c - (COLS - 1) / 2) * STEP_SMALL, 3), ROWS_Y[r], 0.5, SMALL, 0))
    for c, ic in enumerate(legal):
        out.append((ic, round((c - (len(legal) - 1) / 2) * STEP_BIG, 3), LEGAL_Y, 1.0, BIG, 2))
    for ic in [ic for ic in icons if ic.get('status') == 3]:
        out.append((ic, RANDOM_AT[0], RANDOM_AT[1], 1.0, RANDOM_BOX, 2))
    return out


def arrange(mex, log=print):
    data = mex.get_sss_layout()
    page = data['pages'][0]
    icons = []
    for ic, x, y, z, s, g in placements(page['icons']):
        w, h = (round(3.1 * s, 3), round(2.7 * s, 3)) if ic.get('status') != 3 else RANDOM_HIT
        icons.append({**ic, 'x': x, 'y': y, 'z': z, 'scaleX': s, 'scaleY': s, 'group': g, 'width': w, 'height': h})
    page = {**page, 'icons': icons, 'template': {**page['template'], 'iconPlacements': [
        {'group': ic['group'], 'width': ic['width'], 'height': ic['height'], 'x': ic['x'], 'y': ic['y'], 'z': ic['z'],
         'scaleX': ic['scaleX'], 'scaleY': ic['scaleY']} for ic in icons]}}
    mex.set_sss_layout(json.dumps({'pages': [page] + data['pages'][1:]}))
    back = mex.get_sss_layout()['pages'][0]['icons']
    legal = sorted((round(ic['x'], 1), ic['stageName']) for ic in back if ic.get('stageID') in LEGAL and abs(ic['y'] - LEGAL_Y) < 0.01)
    log(f'sss layout: {len(back)} icons, legal row {[n for _, n in legal]}', flush=True)
    return legal
