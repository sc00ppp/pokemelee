"""hand_finish.py <build dir> <out.dat>: a hand-edited build.blend through rigswap's prep and export."""
import json
import sys

from rigswap.plugins import melee

report = melee.prep(sys.argv[1])
dat = melee.export(sys.argv[1], sys.argv[2])
print('exported', dat)
