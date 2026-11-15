"""Opt-in Ice Climbers support for this hand port; no rigswap checkout edits."""

from cast_paths import WORK, TARGETS, FILES
import os
import sys
import struct
from dataclasses import replace
from pathlib import Path

ROOT = Path(str(WORK / ''))


def enable():
    from rigswap.plugins.melee.facts import fighters, memory, parts
    from rigswap.plugins.melee.targets import bones
    from rigswap.plugins.melee.dat import Dat, joints, joint_dobjs
    tables = bones.bone_tables(FILES / 'PlCo.dat')
    revised = []
    for f in fighters.FIGHTERS:
        if f.name in ('Popo', 'Nana'):
            d = Dat.read(FILES / f'Pl{f.code}Nr.dat')
            objects = [o for j in joints(d, f.symbol) for o in joint_dobjs(d, j)]
            hammer = sum(memory._triangles(d, p) for i in (37, 38, 39)
                         for p in d.chain(d.ptr(objects[i] + 12), 4))
            ft = Dat.read(FILES / f'Pl{f.code}.dat')
            root = next(o for n, o in ft.roots if n.startswith('ftData'))
            scale = struct.unpack_from('>f', ft.data, ft.ptr(root) + 0x8c)[0]
            measured = memory.measure(f, FILES)
            f = replace(f, in_scope=True, why_out='', triangles=measured['triangles'],
                        kept=measured['kept'], shown=(0, 1), keep=tuple(range(37, 43)), scale=scale)
            bones.JOINT_NAMES[f.name] = {int(k): v for k, v in tables[f.name]['names'].items()}
            parts.PARTS[f.name] = (('hammer', f.keep, 'vanilla hammer, including low detail'),)
            parts.KEPT[f.name] = f.keep
            parts.PART_TRIANGLES[f.name] = {'hammer': hammer}
            parts.KEPT_TRIANGLES[f.name] = hammer
        revised.append(f)
    fighters.FIGHTERS = tuple(revised)
    from rigswap.plugins.melee.export import eyes
    if not hasattr(eyes, '_ics_original_idle_blink'):
        eyes._ics_original_idle_blink = eyes.idle_blink
        def common_blink(path):
            # Nana's ftData contains special-action scripts only. Her common
            # action scripts, including Wait's Animate Texture commands, are Popo's.
            if Path(path).name == 'PlNn.dat':
                return eyes._ics_original_idle_blink(FILES / 'PlPp.dat')
            return eyes._ics_original_idle_blink(path)
        eyes.idle_blink = common_blink


def helpers(filename):
    """Load a hand tool without its trailing main(), using our isolated targets."""
    import ast
    path = ROOT / 'tools' / filename
    tree = ast.parse(path.read_text(encoding='utf-8'))
    if isinstance(tree.body[-1], ast.Expr) and isinstance(tree.body[-1].value, ast.Call):
        tree.body.pop()
    ns = {'__name__': 'ics_helpers', '__file__': str(path)}
    exec(compile(tree, str(path), 'exec'), ns)
    ns['T'] = TARGETS
    if 'ns' in ns:
        ns['ns']['T'] = TARGETS
    return ns


if __name__ == '__main__':
    enable()
    import runpy
    script = sys.argv.pop(1)
    sys.argv[0] = script
    runpy.run_path(script, run_name='__main__')
