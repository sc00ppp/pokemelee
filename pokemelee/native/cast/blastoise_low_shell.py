"""Bowser's shell state has a low-detail copy, places 65-77, drawn for his shadow and the magnifier bubble; Blastoise's
were empty, so neither showed in nair or up-B. They get the thirteen biggest pieces of his shell state (78-96) that have
the one TObj these places have, which keeps every later TObj's number. One joint, so the static geometry holds.

blastoise_low_shell.py <dat in> <dat out>"""

from cast_paths import WORK, TARGETS
import sys
from rigswap.plugins.melee.dat import Dat, joints, joint_dobjs
from rigswap.plugins.melee.facts.memory import _triangles

LOW, SHELL = range(65, 78), range(78, 97)

d = Dat.read(sys.argv[1])
listed = [o for j in joints(d, 'PlyKoopa5K_Share_joint') for o in joint_dobjs(d, j)]


def tobjs(place):
    return len(d.chain(d.ptr(d.ptr(listed[place] + 8) + 8), 4))


def triangles(place):
    return sum(_triangles(d, p) for p in d.chain(d.ptr(listed[place] + 12), 4))


pieces = sorted((p for p in SHELL if tobjs(p) == 1), key=triangles, reverse=True)[:len(LOW)]
for target, source in zip(LOW, pieces):
    assert tobjs(target) == 1 and d.ptr(listed[target] + 12) is None, target
    for field in (8, 12):
        d.point(listed[target] + field, d.ptr(listed[source] + field))
d.save(sys.argv[2])
print('low shell from', pieces, sum(map(triangles, pieces)), 'of', sum(map(triangles, SHELL)), 'triangles')
