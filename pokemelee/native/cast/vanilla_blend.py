"""Create a working template from a target rebuilt from the original Melee disc."""
from pathlib import Path
import sys
import bpy
from cast_paths import TARGETS

fighter, output = sys.argv[1:3]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(TARGETS / (fighter + ".glb")))
for ob in bpy.data.objects:
    if ob.type == "ARMATURE":
        ob.name = "Armature"
Path(output).parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=output)
