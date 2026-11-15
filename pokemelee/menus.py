"""Rebuild the accepted menu files without any saved image or project cache."""
import os
from pathlib import Path
import subprocess
import sys

from .cast import checked_component
from .catalog import PACKAGE, load
from .export import fingerprint
from .workspace import output_directory, receipt, write_blob

FILES = ("MnSlChr.usd", "MnSlMap.usd", "MnMaAll.usd", "GmPause.usd")


def build_menus(melee, sources, output, runtime, *, project_files=None):
    sources = checked_component(sources, "menu-sources")
    runtime = Path(runtime).resolve()
    with output_directory(output, "menus") as root:
        if project_files is None:
            project = root / "base-project"
            cli = runtime / "mex/win-x64/MexCLI.exe"
            with (root / "mex-create.log").open("w", encoding="utf-8") as log:
                subprocess.run([str(cli), "create", str(melee.path), str(project), "Pokemelee"],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
            project_files = project / "files"
        expected = load("menus.json")["mex_pristine_menu_sha256"]
        for name in FILES:
            source = Path(project_files) / name
            if fingerprint(source)["sha256"] != expected[name]:
                raise ValueError("Expected the pinned m-ex base menu: " + name)
            write_blob(root, "files/" + name, source.read_bytes())
        env = {**os.environ, "POKEMELEE_MENU_SOURCE": str(sources), "POKEMELEE_RUNTIME": str(runtime),
               "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        with (root / "menus.log").open("w", encoding="utf-8") as log:
            subprocess.run([sys.executable, str(PACKAGE / "native/menus/build_menus.py"),
                            str(root / "files"), str(root / "design")], env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
        outputs = [{"path": "files/" + name, **fingerprint(root / "files" / name)} for name in FILES]
        return receipt(root, "menus", {"melee": melee.info(), "sources": str(sources)}, outputs)
