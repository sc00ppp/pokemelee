"""Generate only Popo and Nana targets, frames and base blends from vanilla files."""

from cast_paths import WORK, TARGETS
import json
from ics_runtime import enable, TARGETS
enable()
from rigswap.plugins import melee
from rigswap.plugins.melee.facts.fighters import fighter
from rigswap.plugins.melee.targets import frames
from rigswap.plugins.melee.export.write import hsdraw, vanilla_copies
from ics_runtime import FILES
import tempfile

report = melee.prepare(names=['Popo', 'Nana'])
print(report, flush=True)
if any(v.startswith('failed') for v in report.values()):
    raise RuntimeError(report)
import bpy
for name in ('Popo', 'Nana'):
    if name == 'Nana':
        # PlNnAJ holds only eight partner specials. Common moves live in PlPpAJ.
        with tempfile.TemporaryDirectory(dir=TARGETS) as temp:
            costume, aj = vanilla_copies(temp, FILES/'PlNnNr.dat', FILES/'PlPpAJ.dat')
            listing = hsdraw('--anim', 'list', aj)
            for action, frame in frames.FRAMES:
                dst = TARGETS/'frames/Nana'/f'{action}-{frame}.json'
                symbol = frames.symbol(listing, action)
                if symbol and not dst.is_file():
                    hsdraw('--dump-pose', costume, aj, symbol, dst, frame)
        (TARGETS/'Nana.animation-source.json').write_text(json.dumps({
            'common':'PlPpAJ.dat', 'costume':'PlNnNr.dat',
            'partner_specials':'PlNnAJ.dat', 'method':'evaluated Popo common animation against Nana skeleton'}), encoding='utf-8')
    try:
        melee.describe_from_tables(name)
    except Exception as e:
        # Hand binding needs the real skeleton, not automatic body reading.
        print('description:', name, repr(e), flush=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(TARGETS / f'{name}.glb'))
    for o in bpy.data.objects:
        if o.type == 'ARMATURE':
            o.name = 'Armature'
    bpy.ops.wm.save_as_mainfile(filepath=str(TARGETS / f'{name}.blend'))
    print(name, 'base saved', fighter(name), flush=True)
