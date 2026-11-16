"""Apply the original menu artwork passes to a fresh project file directory."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

# an embedded (._pth) Python does not put the script's folder on the path; the menu passes live beside it
sys.path.insert(0, str(Path(__file__).resolve().parent))
import menu_art  # noqa: E402
import map_art
import main_art
import colo_menus
import main_colo
import css_doors
from menu_paths import MENUGRAFT


files, work = map(lambda p: Path(p).resolve(), sys.argv[1:3])
work.mkdir(parents=True, exist_ok=True)


def helper(*args):
    subprocess.run([str(MENUGRAFT), *map(str, args)], check=True, timeout=300)


for name, module in (("MnSlChr.usd", menu_art), ("MnSlMap.usd", map_art), ("MnMaAll.usd", main_art)):
    source = files / name
    dump, art, patched = work / (name + "-original"), work / (name + "-first-art"), work / (name + "-first")
    if module is main_art:
        art.mkdir()
        spec = main_art.spec()
    else:
        helper("dump", source, dump)
        sys.argv = [module.__file__, str(dump), str(art)]
        module.main()
        spec = json.loads((art / "spec.json").read_text())
        if module is menu_art:
            spec["moves"] = css_doors.spec_moves()
    (art / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    helper("patch", source, art / "spec.json", patched)
    if module is main_art and patched.stat().st_size != source.stat().st_size:
        raise ValueError("Main menu first pass changed its size")
    shutil.copyfile(patched, source)

colo_menus.install(files, work)
main_colo.install(files, work)
