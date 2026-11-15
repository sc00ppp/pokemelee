"""Read the Ralts PKX textures and verify its Gen 3 menu-art index."""

from cast_paths import WORK, TARGETS
import json
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hsd_scene import Scene, pkx
from hsd_cmpr import cmpr

out = Path(str(WORK / 'hand/ralts-Ness'))
s = Scene(pkx('ralts'))
root = s.u32(s.u32(s.u32(s.roots['scene_data'])))
seen = set()
info = []
for j in s.joints(root):
    for dob in j['dobjs']:
        for t in dob['mobj']['tobjs']:
            if t['image'] in seen:
                continue
            seen.add(t['image'])
            info.append(t)
            w,h = t['size']
            Image.fromarray(cmpr(s.data[t['image']:],w,h)).save(out/f"pkx-{t['image']:x}.png")
(out/'pkx-materials.json').write_text(json.dumps(info,indent=1),encoding='utf-8')
