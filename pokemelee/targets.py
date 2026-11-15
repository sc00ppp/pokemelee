"""Prepare the accepted cast's Melee geometry from the original Melee disc."""
import os
from pathlib import Path
import subprocess

from .catalog import PACKAGE, load
from .export import fingerprint
from .geometry import worker_command
from .runtime import lock
from .workspace import output_directory, receipt, write_blob, write_json


def conversion_environment(runtime, files, targets, *, hsd=None, blender=None, target_reader=False):
    runtime = Path(runtime).resolve()
    tools = lock()["tools"]
    hsd = Path(hsd or runtime / "hsdlib/win-x64" /
               tools["hsdlib"]["platforms"]["win-x64"]["entrypoint"]).resolve()
    converter = "blender-target-reader" if target_reader else "blender-converter"
    blender = Path(blender or runtime / converter / "win-x64" /
                   tools[converter]["platforms"]["win-x64"]["entrypoint"]).resolve()
    if not hsd.is_file() or not blender.is_file():
        raise ValueError("Install the pinned HSDRaw and Blender converter runtimes")
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
            "RIGSWAP_MELEE_FILES": str(Path(files).resolve()),
            "RIGSWAP_MELEE_TARGETS": str(Path(targets).resolve()),
            "RIGSWAP_HSDRAW": str(hsd), "RIGSWAP_BLENDER4": str(blender)}


def prepare_targets(melee, output, runtime, *, hsd=None, blender=None):
    fighters = load("cast.json")["fighters"]
    with output_directory(output, "melee-targets") as root:
        files, targets = root / "files", root / "targets"
        env = conversion_environment(runtime, files, targets, hsd=hsd, blender=blender, target_reader=True)
        # The full set is fixed; the converter uses filenames to identify each
        # fighter. Keep neutral costumes, move tables and animation archives.
        names = {"PlCo.dat"}
        codes = ("Mr", "Dr", "Lg", "Kp", "Pe", "Ca", "Gn", "Fx", "Fc", "Ss", "Zd",
                 "Sk", "Lk", "Dk", "Cl", "Kb", "Ys", "Fe", "Ns", "Ms", "Gw", "Pk", "Pr", "Mt", "Pc")
        for code in codes:
            names.update("Pl" + code + suffix for suffix in (".dat", "Nr.dat", "AJ.dat"))
        sources = [write_blob(root, "files/" + name, melee.read(name)) for name in sorted(names)]
        write_json(root / "job.json", {"files": str(files), "targets": str(targets),
                                      "fighters": ["GameAndWatch" if f["pokemon"] == "UnownX" else
                                                   f["fighter"].replace(" ", "").replace(".", "") for f in fighters]})
        with (root / "converter.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(worker_command(runtime, PACKAGE / "native/prepare_targets.py", root / "job.json"),
                                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
        if result.returncode:
            raise ValueError("Melee target conversion failed; see converter.log")
        outputs = [{"path": p.relative_to(root).as_posix(), **fingerprint(p)}
                   for p in sorted(targets.rglob("*")) if p.is_file()]
        return receipt(root, "melee-targets", {"melee": melee.info(), "files": sources}, outputs)
