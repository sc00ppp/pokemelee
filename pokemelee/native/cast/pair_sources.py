"""Import a partner's disc-derived source model and apply its saved visibility."""
import json
from pathlib import Path
import sys
import bpy
from rigswap.load.open import run as load_model
from rigswap.core import rig, variants

recipe_path, models, output = map(Path, sys.argv[1:4])
recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
result = load_model(models / recipe["source_model"], output)
if len(result) != 1 or not result[0].get("opened") or not result[0].get("skinned"):
    raise ValueError("Expected one skinned partner source model")
source = rig.read(output / "models" / result[0]["blend"])
source = variants.drop(source, recipe["source_drop"])
bpy.ops.wm.save_as_mainfile(filepath=source.blend)
