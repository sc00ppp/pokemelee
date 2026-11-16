"""Render the character-select tiles: each one is cut from its mon's portrait scene (the finished in-game costume in
its portrait pose, drawn by the pinned HSDRawViewer with the camera pulled back so nothing runs off the edge), at the
box recipes/icons.json gives, then laid on its type background by native/menu_icons."""
import json
import subprocess
from pathlib import Path

from PIL import Image

from .cast import MELEE_FILES, checked_component
from .catalog import load
from .export import fingerprint
from .native import menu_icons as art
from .parallel import run_all
from .portraits import CODES, render_copy, scene_files
from .runtime import lock
from .workspace import output_directory, receipt

TILE = (art.SIZE[0] * art.SCALE, art.SIZE[1] * art.SCALE)
KINDS = {**{name: kind for name, (_, kind, _) in art.CAST.items()},
         **{name: kind for name, (kind, *_) in art.PAIRS.items()}}


def render(mon, fighter, costume, folder, viewer, files, back, scale):
    """The mon's portrait scene, camera pulled back by `back`, no drop shadow, facing the way its portrait does."""
    folder.mkdir(parents=True, exist_ok=True)
    dat = folder / ('Pl' + CODES[fighter] + 'Nr.dat')
    render_copy(costume, files / dat.name, dat)
    arguments = scene_files(fighter, folder, mon if mon == 'unownx' else None, camera_back=back)
    out = folder / 'render.png'
    command = [str(viewer), '--csp', str(dat), str(out), '--scale', str(scale), '--no-shadow']
    if fighter == 'GameAndWatch':
        command += ['--override-diffuse', '0,0,0,255']
    with (folder / 'render.log').open('w', encoding='utf-8') as log:
        subprocess.run(command + arguments, cwd=folder, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    with Image.open(out) as im:
        im = im.convert('RGBA')
    if fighter == 'Ness':
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if not im.getchannel('A').getbbox():
        raise ValueError('Renderer returned an empty icon render: ' + mon)
    return im


def cut(parts, renders):
    """The tile: each part's box (centre and height in percent of its render, width from the space it fills) scaled
    into its `to` rectangle, painted in order."""
    margin = TILE[0]
    canvas = Image.new('RGBA', (TILE[0] + 2 * margin, TILE[1] + 2 * margin))
    for part in parts:
        im = renders[part['mon']]
        x, y, w, h = part.get('to', (0, 0, 1, 1))
        size = (round(w * TILE[0]), round(h * TILE[1]))
        cx, cy, height = (v / 100 for v in part['box'])
        bh = height * im.height
        bw = bh * size[0] / size[1]
        box = tuple(round(v) for v in (cx * im.width - bw / 2, cy * im.height - bh / 2,
                                       cx * im.width + bw / 2, cy * im.height + bh / 2))
        piece = im.crop(box).resize(size, Image.LANCZOS)
        canvas.alpha_composite(piece, (margin + round(x * TILE[0]), margin + round(y * TILE[1])))
    return canvas.crop((margin, margin, margin + TILE[0], margin + TILE[1]))


def generate_icons(cast, targets, output, runtime, profiles=("normal", "animelee")):
    cast, targets = checked_component(cast, 'cast'), checked_component(targets, MELEE_FILES)
    profiles = tuple(profiles)
    if not profiles or len(set(profiles)) != len(profiles) or set(profiles) - {"normal", "animelee"}:
        raise ValueError("Expected distinct normal/animelee icon profiles")
    runtime = Path(runtime).resolve()
    viewer = runtime / "hsdlib/win-x64" / lock()["tools"]["hsdlib"]["platforms"]["win-x64"]["entrypoint"]
    if not viewer.is_file():
        raise ValueError("Install the pinned HSDRawViewer runtime")
    recipe = load("icons.json")
    if set(recipe["tiles"]) != set(KINDS):
        raise ValueError("recipes/icons.json must cover exactly the character-select tiles")
    rows = {r["pokemon"].lower(): r for r in json.loads((cast / "receipt.json").read_text())["outputs"]}
    wanted = sorted({part["mon"] for tile in recipe["tiles"].values() for part in tile["parts"]})
    if set(wanted) - set(rows):
        raise ValueError("The cast is missing icon mons: " + ", ".join(sorted(set(wanted) - set(rows))))
    with output_directory(output, "css-icons") as root:
        def one(mon):
            row = rows[mon]
            return mon, render(mon, row["fighter"], cast / row["path"], root / "renders" / mon, viewer,
                               targets / "files", recipe["camera_back"], recipe["scale"])

        renders = dict(run_all(one, wanted, tries=3))
        names = [*art.CAST, *art.PAIRS]
        tiles = {name: cut(recipe["tiles"][name]["parts"], renders) for name in names}
        outputs = []
        for profile in profiles:
            folder = root / profile
            (folder / "raw").mkdir(parents=True)
            for name in names:
                tiles[name].save(folder / "raw" / (name + ".png"))
                target = folder / ("css-" + name + ".png")
                art.compose(tiles[name], KINDS[name], profile == "animelee").save(target)
                outputs.append({"profile": profile, "pokemon": name, "path": target.relative_to(root).as_posix(),
                                **fingerprint(target)})
            art.sheet(folder, names)
        return receipt(root, "css-icons", {"cast": str(cast), "targets": str(targets),
                                           "renderer": "hsdrawviewer portrait scenes", "profiles": list(profiles)},
                       outputs)
