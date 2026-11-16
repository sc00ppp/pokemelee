"""Replay the accepted character recipes with no authoring or cached projects."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess

from .catalog import PACKAGE, load
from .export import fingerprint
from .geometry import worker_command
from .targets import conversion_environment
from .workspace import output_directory, receipt, write_json


def selection(selected=None):
    available = load("cast-finishing.json")["recipes"]
    catalog = load("cast.json")
    cast = {row["pokemon"].lower() for row in catalog["fighters"] + catalog["partners"]}
    names = [name.lower() for name in selected] if selected is not None else sorted(cast)
    if not names or len(names) != len(set(names)) or set(names) - cast:
        raise ValueError("Unknown, duplicate, or empty character selection")
    missing = set(names) - available.keys()
    if missing:
        raise ValueError("Character recipes still awaiting verification: " + ", ".join(sorted(missing)))
    return [(name, available[name]) for name in names]


# the Melee disc files later steps read: the plain extraction, or the older Blender targets step that also carried them
MELEE_FILES = ("melee-files", "melee-targets")


def checked_component(path, operation):
    path = Path(path).resolve()
    record = json.loads((path / "receipt.json").read_text(encoding="utf-8"))
    operations = (operation,) if isinstance(operation, str) else tuple(operation)
    if record.get("operation") not in operations or record.get("complete") is not True:
        raise ValueError(f"Expected a completed {' or '.join(operations)} component")
    for row in record["outputs"] + record.get("supporting_outputs", []):
        file = path / row["path"]
        if not file.resolve().is_relative_to(path) or fingerprint(file)["sha256"] != row["sha256"]:
            raise ValueError(f"Generated component changed: {row['path']}")
    return path


def build_cast(colosseum, models, targets, output, runtime, selected=None, *, hsd=None, blender=None, jobs=2):
    recipes = selection(selected)
    if not 1 <= jobs <= 4:
        raise ValueError("Character jobs must be between 1 and 4")
    models = checked_component(models, "source-models")
    targets = checked_component(targets, "melee-targets")
    source_hashes = {row["label"] + ".glb": row["sha256"] for row in load("source-models.json")["models"]}
    environment = conversion_environment(runtime, targets / "files", targets / "targets", hsd=hsd, blender=blender)
    with output_directory(output, "cast") as root:
        shutil.copytree(PACKAGE / "native/cast", root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        environment.update(POKEMELEE_CAST_WORK=str(root), POKEMELEE_COLOSSEUM=str(colosseum.path))

        def one(item):
            name, finishing = item
            base = load("cast/" + name + ".json")
            source = models / "models" / base["source_model"]
            if fingerprint(source)["sha256"] != source_hashes[base["source_model"]]:
                raise ValueError(f"Incorrect source model for {name}")
            raw = root / "replay" / name
            raw.parent.mkdir(exist_ok=True)
            job = root / (name + ".json")
            write_json(job, {"recipe": str(PACKAGE / "recipes/cast" / (name + ".json")),
                             "model": str(source), "targets": str(targets / "targets"), "out": str(raw)})
            with (root / (name + ".log")).open("w", encoding="utf-8") as log:
                def run(script, *args):
                    log.write("\nSTEP " + script.name + "\n")
                    log.flush()
                    result = subprocess.run(worker_command(runtime, script, *args), env=environment,
                                            stdout=log, stderr=subprocess.STDOUT, timeout=1200)
                    if result.returncode:
                        raise ValueError(f"{name}: {script.name} failed; see {name}.log")

                home = root / "hand" / (name + "-" + base["fighter"])
                build = home / finishing["seed"]
                source_blend = ""
                if finishing.get("procedural"):
                    build.mkdir(parents=True)
                    write_json(build / "target.json", {"name": base["fighter"]})
                elif finishing.get("hand_source"):
                    source_dir = root / "mons" / name / "1-load"
                    run(root / "tools/pair_sources.py", PACKAGE / "recipes/cast" / (name + ".json"),
                        models / "models", source_dir)
                    source_blend = str(next((source_dir / "models").glob("*.blend")))
                else:
                    run(PACKAGE / "native/replay_cast.py", job)
                    shutil.copytree(raw / "3-build", build)
                    source_dir = root / "mons" / name / "1-load"
                    shutil.copytree(raw / "1-load", source_dir)
                    source_blend = str(next((source_dir / "models").glob("*.blend")))
                    for filename in ("base.blend", "edited.blend"):
                        shutil.copyfile(build / "build.blend", build / filename)
                out = home / "4-export" / (base["fighter"] + ".dat")
                out.parent.mkdir(parents=True, exist_ok=True)
                values = {"root": str(root), "home": str(home), "build": str(build), "out": str(out),
                          "model": str(source),
                          "replay": str(raw),
                          "finish": str(home / finishing["finish"]),
                          "source": source_blend}
                for folder in ["{home}/look", "{home}/reference", "{home}/review", *finishing["directories"]]:
                    Path(folder.format_map(values)).mkdir(parents=True, exist_ok=True)
                for script, *arguments in finishing["steps"]:
                    args = [arg.format_map(values) for arg in arguments]
                    if script == "copy":
                        shutil.copyfile(*args)
                    elif script == "copy_tree":
                        shutil.copytree(*args)
                    else:
                        run(root / "tools" / script, *args)
                actual = fingerprint(out)
                if actual["sha256"] != finishing["sha256"]:
                    raise ValueError(f"{name}: final costume differs from the accepted recipe")
                return {"pokemon": finishing["pokemon"], "fighter": base["fighter"],
                        "path": out.relative_to(root).as_posix(), **actual}

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            outputs = list(pool.map(one, recipes))
        face = root / 'hand/deoxys-Samus/look/face.png'
        supporting = ([{'path': face.relative_to(root).as_posix(), **fingerprint(face)}]
                      if face.is_file() else [])
        return receipt(root, "cast", {"colosseum": colosseum.info(), "models": str(models), "targets": str(targets)},
                       outputs, supporting_outputs=supporting, authoring="disabled", network="disabled")
