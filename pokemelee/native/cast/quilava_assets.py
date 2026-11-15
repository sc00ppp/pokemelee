"""Rebuild the saved Fox local transforms and rounded eye placement surface."""
import json
import struct
import sys
from cast_paths import WORK, FILES

home = WORK / "hand/quilava-Fox"
out = home / "reference"
if sys.argv[1] == "rest":
    from rigswap.plugins.melee.dat import Dat, joints
    dat = Dat.read(FILES / "PlFxNr.dat")
    rows = []
    for index, at in enumerate(joints(dat, "PlyFox5K_Share_joint")):
        row = {"index": index}
        for name, offset in (("rotation", 0x14), ("scale", 0x20), ("translation", 0x2C)):
            row[name] = [round(v, 6) for v in struct.unpack_from(">3f", dat.data, at + offset)]
        rows.append(row)
    (out / "fox-rest-local.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
elif sys.argv[1] == "eye":
    import bpy
    bpy.ops.wm.open_mainfile(filepath=str(home / "3-build/build.blend"))
    ob = bpy.data.objects["magmarashi_mesh_00"]
    data = {"points": [list(v.co) for v in ob.data.vertices], "faces": [list(f.vertices) for f in ob.data.polygons]}
    (out / "rounded-eye-surface.json").write_text(json.dumps(data), encoding="utf-8")
else:
    raise ValueError("Unknown Quilava preparation step")
