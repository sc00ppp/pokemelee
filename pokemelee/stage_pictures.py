"""Stage-select pictures: each built stage file rendered by the pinned HSDRawViewer from the select screen's camera.

The pictures show at thumbnail size on the stage select screen, so the renderer's take is enough (owner, 11-15): no
game run, no Dolphin. What the game spawns while it runs (Ho-Oh, the stands' people, the big screen's picture) is not
in them, and the light is the renderer's."""
import collections
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image

from .cast import checked_component
from .export import fingerprint
from .parallel import run_all
from .runtime import lock
from .workspace import output_directory, receipt

# stage: (its file, camera eye, camera target), in world units
FRAMING = {
    'battlefield': ('GrNBa.dat', (0, 35.7, 189.5), (0, 29.7, 0)),
    'finaldestination': ('GrNLa.dat', (0, 14, 237.1), (0, 8, 0)),
    'dreamland': ('GrOp.dat', (0, 34.2, 214.1), (0, 28.2, 0)),
    'yoshisstory': ('GrSt.dat', (0, 29.5, 201.7), (0, 23.5, 0)),
    'fountainofdreams': ('GrIz.dat', (0, 29.9, 175.3), (0, 23.9, 0)),
    'pokemonstadium': ('GrPs.dat', (0, 65, 310), (0, 8, 0)),
}
FOV = 49            # the game's 40 degree camera as HSDRawViewer counts it: fitted to the old in-game captures (11-15)
SIZE = (1280, 960)


def render_copy(source, target):
    """A copy HSDRaw can read. HSDRaw sizes each struct up to the next pointer target, and reads no further. An AniMelee
    shell's position table keeps its pointer where entry 0 would sit, which can land inside older data: HSDRaw then
    cuts that struct short (an animation's keys: it throws) and reads the table as the few bytes up to the next struct
    (black spikes). The copy gives every vertex table its meshes read past that point a block of its own; the game file
    stays as built."""
    import bisect
    from .anime_stage import places, world_matrices
    from .display_list import Dat, attrs, strips
    d = Dat.read(source)
    starts = sorted({d.u32(r) for r in d.relocations} | {o for _, o in d.roots} | {len(d.data)})
    users = collections.defaultdict(list)       # table: (field, bytes the mesh reads from it)
    for _, o in places(d, world_matrices(d)):
        for p in d.chain(d.ptr(o + 12), 4):
            table = attrs(d, p)
            for a in table:
                if a['data'] is not None:
                    last = max(index[a['name']] for _, rows in strips(d, p, table) for _, index in rows)
                    users[a['data']].append((a['at'] + 20, (last + 1) * a['stride']))
    moved = 0
    for at, fields in users.items():
        size = max(n for _, n in fields)
        if at + size > starts[bisect.bisect_right(starts, at)]:
            block = d.add(bytes(d.data[at:at + size]), 32)
            for field, _ in fields:
                d.point(field, block)
            moved += 1
    d.save(target)
    return moved


def stage_files(stages):
    """Each built stage file by name; a later component wins, as in the project."""
    out = {}
    for component in stages:
        component = checked_component(component, 'stages')
        for row in json.loads((component / 'receipt.json').read_text())['outputs']:
            out[Path(row['path']).name] = component / row['path']
    return out


def render(viewer, source, folder, stage):
    name, eye, interest = FRAMING[stage]
    folder.mkdir(parents=True, exist_ok=True)
    dat = folder / name                 # its own copy: HSDRaw opens a file for itself, and renders run side by side
    moved = render_copy(source, dat)
    (folder / 'render-copy.txt').write_text(f'{moved} vertex tables moved', encoding='utf-8')
    out = folder / 'render.png'
    command = [str(viewer), '--stage-render', str(dat), str(out), '--eye', ','.join(map(str, eye)),
               '--interest', ','.join(map(str, interest)), '--fov', str(FOV), '--size', '%dx%d' % SIZE]
    with (folder / 'render.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    with Image.open(out) as im:
        if im.size != SIZE:
            raise ValueError(f'Unexpected stage render size: {im.size}')
    return out


def build_stage_pictures(melee, stages, output, runtime, profile='normal', selected=None):
    names = list(selected or FRAMING)
    if not names or len(set(names)) != len(names) or set(names) - FRAMING.keys():
        raise ValueError('Unknown or duplicate stage picture selection')
    runtime = Path(runtime).resolve()
    viewer = runtime / 'hsdlib/win-x64' / lock()['tools']['hsdlib']['platforms']['win-x64']['entrypoint']
    if not viewer.is_file():
        raise ValueError('Install the pinned HSDRawViewer runtime')
    built = stage_files(stages)
    missing = [FRAMING[stage][0] for stage in names if FRAMING[stage][0] not in built]
    if missing:
        raise ValueError('The stages are missing ' + ', '.join(missing))
    with output_directory(output, 'stage-pictures') as root:
        renders = run_all(lambda stage: render(viewer, built[FRAMING[stage][0]], root / 'renders' / stage, stage),
                          names, tries=3)
        outputs = []
        for stage, path in zip(names, renders):
            target = root / (stage + '.png')
            with Image.open(path) as im:        # where no model drew, black, as the game clears its screen
                Image.alpha_composite(Image.new('RGBA', SIZE, (0, 0, 0, 255)), im.convert('RGBA')).convert('RGB').save(target)
            outputs.append({'stage': stage, 'path': target.name, **fingerprint(target)})
        return receipt(root, 'stage-pictures', {'melee': melee.info(), 'stages': [str(p) for p in stages],
                                                'renderer': 'hsdrawviewer stage render', 'fov': FOV},
                       outputs, profile=profile)
