"""Render the accepted character-select tiles from regenerated source models."""
import json
from pathlib import Path
import subprocess

from PIL import Image

from .cast import checked_component
from .catalog import PACKAGE, load
from .export import fingerprint
from .native import menu_icons as art
from .runtime import lock
from .workspace import output_directory, receipt, write_json


def generate_icons(models, cast, output, runtime, profiles=("normal", "animelee"), *, blender=None):
    models = checked_component(models, "source-models")
    cast = checked_component(cast, "cast")
    profiles = tuple(profiles)
    if not profiles or len(set(profiles)) != len(profiles) or set(profiles) - {"normal", "animelee"}:
        raise ValueError("Expected distinct normal/animelee icon profiles")
    converter = lock()["tools"]["blender-target-reader"]["platforms"]["win-x64"]
    blender = Path(blender or Path(runtime) / "blender-target-reader/win-x64" / converter["entrypoint"]).resolve()
    if not blender.is_file():
        raise ValueError("Install the pinned Blender 4.3.2 icon renderer")
    source = {}
    catalog = load("cast.json")
    for row in catalog["fighters"] + catalog["partners"]:
        name = row["pokemon"].lower()
        recipe = load("cast/" + name + ".json")
        path = models / "models" / recipe["source_model"]
        source[name] = source[path.stem] = str(path)
    face = cast / "hand/deoxys-Samus/look/face.png"
    if not face.is_file():
        raise ValueError("The generated Deoxys face is missing")
    with output_directory(output, "css-icons") as root:
        outputs = []
        for profile in profiles:
            folder = root / profile
            (folder / "raw").mkdir(parents=True)
            flat = profile == "animelee"
            views, kinds = [], {}
            for name in [*art.CAST, *art.PAIRS]:
                if name in art.PAIRS:
                    kind, view, members = art.PAIRS[name]
                    mons = [{**{k: v for k, v in member.items() if k != "mon"},
                             **art.MODEL.get(member["mon"], {}), "glb": source[member["mon"]]}
                            for member in members]
                else:
                    model, kind, view = art.CAST[name]
                    options = json.loads(json.dumps(art.MODEL.get(name, {})).replace("{deoxys_face}", face.as_posix()))
                    mons = [{**options, "glb": source[model]}]
                kinds[name] = kind
                views.append({"out": str(folder / "raw" / (name + ".png")), "mons": mons,
                              "top": .5, "yaw": 25, "flat": flat, **view})
            job = folder / "job.json"
            write_json(job, {"size": [art.SIZE[0] * art.SCALE, art.SIZE[1] * art.SCALE], "views": views})
            with (folder / "render.log").open("w", encoding="utf-8") as log:
                subprocess.run([str(blender), "-b", "--factory-startup", "-P",
                                str(PACKAGE / "native/icon_render.py"), "--", str(job)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
            for name, kind in kinds.items():
                with Image.open(folder / "raw" / (name + ".png")) as raw:
                    if not raw.convert("RGBA").getchannel("A").getbbox():
                        raise ValueError("Empty character icon: " + name)
                    target = folder / ("css-" + name + ".png")
                    art.compose(raw, kind, flat).save(target)
                outputs.append({"profile": profile, "pokemon": name,
                                "path": target.relative_to(root).as_posix(), **fingerprint(target)})
            art.sheet(folder, list(kinds))
        return receipt(root, "css-icons", {"models": str(models), "cast": str(cast), "profiles": profiles}, outputs)
