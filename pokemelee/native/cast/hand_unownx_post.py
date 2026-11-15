"""hand_unownx_post.py <in.dat> <readback.json> <out.dat>: the game's Game & Watch rules laid onto the Unown X costume
rigswap exported. The readback names which material each exported DObj holds.

The export knows nothing of these (decomp ftGw_Init.c, ftmaterial.c, ftdrawcommon.c; PlGw.dat):
- the grey outline is the group-4 DObjs (places 1, 4, 5 ...: items[10] of PlGw.dat), drawn in the outline colour under
  the body. The export fills set-0 places and blanks group 4, so the hull's DObjs move there and leave set 0 and the
  low-detail set, or they would draw as a black body.
- the game overwrites every material's diffuse with the slot's fill: black in a vanilla slot, white in a slot the app's
  importer made (core/gaw_colors.py). The body keeps its black texture on a CONSTANT material, which draws black under
  any fill; the hull needs no texture, the game draws it in the outline colour.
- only a REPLACE texture on a CONSTANT material ignores the fill: the eye.
- the head is model 2, four options the moves pick from: places 17, 16, 42 and 108, up smash's. The +-X eye is all of the
  first three, so up smash, where the head turns 66 degrees and that eye would hang off the ball, drops it. Up smash's
  own place, a vanilla helmet that would stand in front of the pit's eye, goes with its outline: the ball is the helmet."""

from cast_paths import WORK, TARGETS
import json
import struct
import sys
from pathlib import Path

from rigswap.plugins.melee.dat import Dat, joint_dobjs, joints

SYMBOL = 'PlyGamewatch5K_Share_joint'
HULL_PLACES = (1, 4)                # model 0 option 0 of group 4: always shown
HEAD_PLACES = (17, 16, 42)          # model 2's options 0, 1 and 2
USMASH_PLACES = (108, 107)          # model 2 option 3 and its outline
RENDER_CONSTANT, RENDER_TEX0 = 1, 1 << 4
TOBJ_FLAGS = 0x40
REPLACE_DIFFUSE = (5 << 16) | (1 << 4)     # colour map REPLACE, diffuse light map
MOBJ, POBJ, POBJ_NEXT = 0x08, 0x0C, 0x04


def main():
    source, readback, dest = sys.argv[1:4]
    d = Dat.read(source)
    places = [o for j in joints(d, SYMBOL) for o in joint_dobjs(d, j)]
    back = json.loads(Path(readback).read_text(encoding='utf-8'))
    at = back['dobjs']['places']
    built = {}                          # material family: [places in the DObj list]
    names = {}                          # build DObj: family
    for row in back['joins']['texture_samplers']['materials']:
        family = row['material'].split('.')[0]
        built.setdefault(family, []).append(at[row['place']])
        names[row['place']] = family
    print(built)
    low = {int(p): {names[i] for i in shown} for p, shown in back['dobjs']['low_detail']['places'].items()}
    print('low', low)
    eye, pit, fill, hull = (built[k] for k in ('unown_eye', 'unown_pit', 'unown_black', 'unown_edge'))
    if len(hull) != len(HULL_PLACES):
        raise SystemExit('not the layout this was written for')

    def material(place):
        return d.ptr(places[place] + MOBJ)

    for place in eye + pit:
        mobj = material(place)
        struct.pack_into('>I', d.data, mobj + 0x04, RENDER_CONSTANT | RENDER_TEX0)
        struct.pack_into('>I', d.data, d.ptr(mobj + 0x08) + TOBJ_FLAGS, REPLACE_DIFFUSE)
    for place in fill:
        struct.pack_into('>I', d.data, material(place) + 0x04, RENDER_CONSTANT | RENDER_TEX0)
    for place in hull:
        struct.pack_into('>I', d.data, material(place) + 0x04, RENDER_CONSTANT)
        d.point(material(place) + 0x08, None)

    for to, place in zip(HULL_PLACES, hull):
        d.point(places[to] + MOBJ, material(place))
        d.point(places[to] + POBJ, d.ptr(places[place] + POBJ))
    for place in hull:
        d.point(places[place] + POBJ, None)

    # the eye's DObjs joined into one chain, as one option of the head names one place; a chain has one material
    head = d.ptr(places[eye[0]] + POBJ)
    last = d.chain(head, POBJ_NEXT)[-1]
    for place in eye[1:]:
        d.point(last + POBJ_NEXT, d.ptr(places[place] + POBJ))
        last = d.chain(head, POBJ_NEXT)[-1]
    side = material(eye[0])
    for place in eye:
        d.point(places[place] + POBJ, None)
    for to in HEAD_PLACES:
        d.point(places[to] + MOBJ, side)
        d.point(places[to] + POBJ, head)

    for place in USMASH_PLACES:
        d.point(places[place] + POBJ, None)
    for place, shown in low.items():    # shadows and the magnifier: the body and the eye on the side
        if shown & {'unown_edge', 'unown_pit'}:
            d.point(places[place] + POBJ, None)
    d.save(dest)
    print('wrote', dest, Path(dest).stat().st_size)


main()
