"""Fixed Colosseum archive conversion, executed by the pinned Blender runtime."""
import json
from pathlib import Path
import sys

import bpy


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    manifest = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    sys.path.insert(0, manifest["reader"])
    from importer.importer import Importer
    from shared.helpers.logger import Logger
    for row in manifest["models"]:
        source = Path(row["source"])
        bpy.ops.wm.read_factory_settings(use_empty=True)
        status = Importer.run(
            bpy.context, source.read_bytes(), source.name,
            {"ik_hack": True, "verbose": False, "max_frame": 1000000000,
             "section_names": [], "filepath": str(source)},
            logger=Logger(verbose=False, model_name=row["label"]),
        )
        if "FINISHED" not in str(status):
            raise RuntimeError(f"Model conversion failed: {row['label']}: {status}")
        bpy.ops.export_scene.gltf(filepath=row["output"])
        print("Converted", row["label"], flush=True)


if __name__ == "__main__":
    main()
