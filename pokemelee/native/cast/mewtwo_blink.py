"""Mewtwo's iris track has no closed key; use its lid track for full-eye tiles.

Per-costume post-export repair only. Preserve texture IDs, linked lists, image
payloads, geometry and fighter scripts; redirect each full-eye animation to the
already exported open/half/closed lid table and AObj.
"""

from cast_paths import WORK, TARGETS
import json,sys,shutil
from pathlib import Path
from rigswap.plugins.melee.export import eyes

home=Path(str(WORK / 'hand/mewtwo-Mewtwo'))
build=home/'3-build';dat=home/'4-export/Mewtwo.dat'
report=json.loads((build/'export/readback.json').read_text(encoding='utf-8'))
d=eyes.Dat.read(dat);tables=report['dobjs']['eyes']['tables']
lid=next(t for t in tables if 'closed' in t['images'])
src=lid['texture_animation'];fixed=[]
for table in tables:
    if 'closed' in table['images']:continue
    dst=table['texture_animation']
    for off in (8,12,16):d.point(dst+off,d.ptr(src+off))
    d.data[dst+20:dst+24]=d.data[src+20:src+24]
    states={s:lid['images'][eyes.value_at(eyes.tracks(d,dst)[eyes.TRACK_IMAGE],f)] for s,f in [('open',0),('half',1),('closed',2)]}
    assert states==dict(open='open',half='half',closed='closed'),states
    fixed.append({'texture_animation':dst,'states':states})
d.save(dat)
record={'reason':'Iris tracks alias texture frames 1 and 2; full-eye tiles must follow the lid track.','fixed':fixed,'bytes':dat.stat().st_size}
(build/'blink-post.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
if len(sys.argv)>1:
    run=Path(sys.argv[1])/'colomewtwo-Mewtwo'
    shutil.copyfile(dat,run/'4-export/Mewtwo.dat')
    shutil.copyfile(build/'blink-post.json',run/'3-build/blink-post.json')
print(json.dumps(record),flush=True)
