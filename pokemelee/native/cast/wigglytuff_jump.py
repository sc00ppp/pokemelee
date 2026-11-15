"""Kirby puffs up in his jumps: the animation swaps body places 3-5 for 0-2, and low detail 11-13 for 8-10. Wigglytuff's
body and eyes sit in 4, 5, 11 and 12 only, so a jump drew nothing. The empty places get the same geometry and material
(two DObjs may share them: rigswap export/dobjs.py); each pair has equal TObj counts, so the eye animation's places hold.
The stones' low-detail places were empty too, which left the magnifier bubble blank; they get the kept stones.

wigglytuff_jump.py <dat in> <dat out>"""

from cast_paths import WORK, TARGETS
import sys
from rigswap.plugins.melee.dat import Dat, joints, joint_dobjs

COPIED = {1: 4, 2: 5, 8: 11, 9: 12,
          31: 20, 32: 21, 33: 22, 34: 23, 35: 24, 36: 26, 37: 25, 38: 27, 39: 28, 40: 29, 41: 30}

d = Dat.read(sys.argv[1])
listed = [o for j in joints(d, 'PlyKirby5K_Share_joint') for o in joint_dobjs(d, j)]


def tobjs(place):
    return len(d.chain(d.ptr(d.ptr(listed[place] + 8) + 8), 4))


for target, source in COPIED.items():
    assert tobjs(target) == tobjs(source), (target, source)
    assert d.ptr(listed[target] + 12) is None and d.ptr(listed[source] + 12) is not None, (target, source)
    for field in (8, 12):
        d.point(listed[target] + field, d.ptr(listed[source] + field))
d.save(sys.argv[2])
print('filled', len(COPIED), 'places')
