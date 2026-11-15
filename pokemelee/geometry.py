"""Configure an isolated, pinned offline interpreter for the character recipes."""
import json
import os
from pathlib import Path

from .catalog import PACKAGE
from .runtime import fetch, lock


def location(runtime, name):
    return Path(runtime).resolve() / name / "win-x64"


def setup_geometry(runtime, *, github_auth=False):
    pinned = lock()
    geometry = pinned["geometry"]
    names = [geometry["python"], *geometry["libraries"], geometry["helpers"]]
    for name in names:
        target = location(runtime, name)
        spec = pinned["tools"][name]["platforms"]["win-x64"]
        if not target.exists():
            fetch(name, "win-x64", target, github_auth=github_auth)
        else:
            record = json.loads((target / "receipt.json").read_text(encoding="utf-8"))
            if record.get("inputs", {}).get("sha256") != spec["sha256"]:
                raise ValueError(f"Installed {name} does not have the pinned receipt")
            if any(not (target / n).is_file() for n in spec["required"]):
                raise ValueError(f"Installed {name} is incomplete")
    return configure_geometry(runtime)


def configure_geometry(runtime):
    pinned = lock()
    geometry = pinned["geometry"]
    python = location(runtime, geometry["python"])
    paths = ["python313.zip", "."]
    for name in geometry["libraries"]:
        library = location(runtime, name)
        spec = pinned["tools"][name]["platforms"]["win-x64"]
        if any(not (library / n).is_file() for n in spec["required"]):
            raise ValueError(f"Install {name} before configuring the geometry interpreter")
        paths.append(os.path.relpath(library, python).replace("\\", "/"))
    # Relative entries keep the runtime movable. The workers add only the
    # explicit builder and helper locations passed by their parent process.
    (python / "python313._pth").write_text("\n".join(paths) + "\n", encoding="utf-8")
    return {"python": str(python / "python.exe"), "libraries": geometry["libraries"]}


def worker_command(runtime, script, *arguments):
    pinned = lock()
    python = location(runtime, pinned["geometry"]["python"]) / "python.exe"
    helper_tool = pinned["geometry"]["helpers"]
    entry = pinned["tools"][helper_tool]["platforms"]["win-x64"]["entrypoint"]
    helper = (location(runtime, helper_tool) / entry).parents[3]
    bootstrap = ("import sys;sys.path.insert(0,sys.argv[1]);"
                 "from pokemelee.native.offline_worker import main;main()")
    if not python.is_file() or not (helper / "rigswap").is_dir():
        raise ValueError("Run setup-geometry to install the pinned character runtime")
    return [str(python), "-X", "utf8", "-c", bootstrap, str(PACKAGE.parent), str(helper),
            str(Path(script).resolve()), *map(str, arguments)]
