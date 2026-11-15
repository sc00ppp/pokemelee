"""Colosseum purples for Melee's main menus (MnMaAll.usd): every blue in the file turned to the purples of the
character and stage selects (menu_art.py, map_art.py), by menugraft's `hue` op: materials, TEV colours, vertex colours
and the colour textures (a CI's palette, an RGB/CMPR image re-encoded at its own size). Gold, white and grey stay.

The patch is IN PLACE (spec "inplace"): only changed bytes are written and every struct keeps its offset. Slippi
finds things in MnMaAll by offset; a file HSDRaw rewrote, even unchanged, loses the 1P menu's "Online Play" label.

The fighters' face strips and the snapshot pictures keep their colours.

usage: python main_art.py <out dir>      writes <out>/spec.json
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import json
import sys
from pathlib import Path

HUE = {'from': 175, 'to': 262, 'shift': 42, 'sat': 1.0, 'minSat': 0.12, 'textures': True,
       'keepTextures': ['MenMainFaceB_Top_joint', 'MenMainFaceB_Top_matanim_joint', 'MenMainPhotoSn_Top_joint',
                        'MenMainConSn_Top_joint', 'MenMainLoadSn_Top_joint']}


def spec():
    return {'images': [], 'recolor': [], 'tints': [], 'materials': [], 'hue': [HUE], 'inplace': True}


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'spec.json').write_text(json.dumps(spec(), indent=1), encoding='utf-8')
    print('->', out / 'spec.json')


if __name__ == '__main__':
    main()
