"""The original Colosseum logo, backdrop and panel used by the menu recipes."""
from pathlib import Path

from PIL import Image

from .art import decode
from .export import fingerprint
from .fsys import entries
from .stages import run_helper
from .workspace import output_directory, receipt, write_blob


def generate_menu_sources(colosseum, output, runtime):
    recipes = [("title.fsys", "03_logo_demo.rdat", (540, 224), "logotex/d0_j19_o0_t0_540x224.png"),
               ("topmenu.fsys", "02_menu_bg00.dat", (640, 480), "bgtex/d0_j1_o0_t0_640x480.png")]
    with output_directory(output, "menu-sources") as root:
        outputs = []
        for archive, member, size, target in recipes:
            source = dict(entries(colosseum.read(archive)))[member]
            write_blob(root, member, source)
            dump = root / (Path(member).stem + "-dump")
            run_helper(runtime, "colodump", [root / member, dump], root / (member + ".log"))
            matches = []
            for file in (dump / "tex").glob("*.png"):
                with Image.open(file) as image:
                    if image.size == size:
                        matches.append(image.convert("RGBA"))
            if len(matches) != 1:
                raise ValueError(f"Expected one {size} source texture in {archive}")
            out = root / target
            out.parent.mkdir(parents=True, exist_ok=True)
            matches[0].save(out)
            outputs.append({"path": target, **fingerprint(out)})
        target = "colosseumbattle_menu/27_menu_069.png"
        source = dict(entries(colosseum.read("colosseumbattle_menu.fsys")))["27_menu_069.t12"]
        out = root / target
        out.parent.mkdir()
        decode(source).save(out)
        outputs.append({"path": target, **fingerprint(out)})
        return receipt(root, "menu-sources", {"colosseum": colosseum.info()}, outputs)
