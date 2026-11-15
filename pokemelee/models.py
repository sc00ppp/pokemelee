"""Reproduce the source models used by the accepted cast, with no rig changes."""
import os
from pathlib import Path
import subprocess

from .catalog import PACKAGE, load
from .export import fingerprint
from .runtime import lock
from .workspace import output_directory, receipt, write_blob, write_json


def convert_models(colosseum, output, runtime, selected=None, *, blender=None, reader=None):
    rows = load("source-models.json")["models"]
    names = set(selected if selected is not None else [r["pokemon"] for r in rows])
    if not names or names - {r["pokemon"] for r in rows}:
        raise ValueError("Unknown or empty source-model selection")
    runtime = Path(runtime).resolve()
    tools = lock()["tools"]
    blender = Path(blender or runtime / "blender-converter/win-x64" /
                   tools["blender-converter"]["platforms"]["win-x64"]["entrypoint"]).resolve()
    reader = Path(reader or (runtime / "colo-model-reader/win-x64" /
                  tools["colo-model-reader"]["platforms"]["win-x64"]["entrypoint"]).parent.parent).resolve()
    if not blender.is_file() or not (reader / "importer/importer.py").is_file():
        raise ValueError("Install the pinned Blender converter and Colosseum model reader")
    with output_directory(output, "source-models") as root:
        jobs, sources = [], []
        (root / "models").mkdir()
        for row in rows:
            if row["pokemon"] not in names:
                continue
            source = row["source_archive"]
            record = write_blob(root, "inputs/" + source, colosseum.read(source))
            sources.append({"disc_file": source, **record})
            jobs.append({**row, "source": str(root / "inputs" / source),
                         "output": str(root / "models" / (row["label"] + ".glb"))})
        manifest = root / "convert.json"
        write_json(manifest, {"reader": str(reader), "models": jobs})
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        with (root / "converter.log").open("w", encoding="utf-8") as log:
            result = subprocess.run([str(blender), "-b", "--factory-startup", "--python-exit-code", "1",
                                     "--python", str(PACKAGE / "native/import_models.py"), "--", str(manifest)],
                                    stdout=log, stderr=subprocess.STDOUT, env=env, timeout=1800)
        if result.returncode:
            raise ValueError("Source-model conversion failed; see converter.log")
        outputs = []
        for row in jobs:
            path = Path(row["output"])
            actual = fingerprint(path)
            if actual["sha256"] != row["sha256"]:
                raise ValueError(f"Source model {row['pokemon']} differs from the accepted input")
            outputs.append({"path": "models/" + path.name, "pokemon": row["pokemon"], **actual})
        return receipt(root, "source-models", {"colosseum": colosseum.info(), "files": sources}, outputs)
