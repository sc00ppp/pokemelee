"""Render the saved portrait composition using rebuilt costumes and pinned HSDRaw."""
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess

import numpy as np
from PIL import Image, ImageFilter
import yaml

from .cast import MELEE_FILES, checked_component
from .catalog import PACKAGE, load
from .export import fingerprint
from .datprobe import DatFile
from .parallel import run_all
from .workspace import output_directory, receipt

CODES = dict(zip(
    ('Mario DrMario Luigi Bowser Peach CaptainFalcon Ganondorf DonkeyKong Fox Falco Ness Kirby Samus Zelda '
     'Sheik Link YoungLink Pichu Pikachu Mewtwo Jigglypuff Marth Roy Yoshi GameAndWatch Popo Nana').split(),
    'Mr Dr Lg Kp Pe Ca Gn Dk Fx Fc Ns Kb Ss Zd Sk Lk Cl Pc Pk Mt Pr Ms Fe Ys Gw Pp Nn'.split()))


def scene_files(fighter, folder, pokemon, camera_back=1.0):
    """The saved portrait scene (and pose) files; camera_back > 1 pulls the camera straight back (icon renders)."""
    spec = load('portraits/' + fighter + '.json')
    scene = copy.deepcopy(spec['scene'])
    if pokemon == 'unownx':
        scene['camera'].update(x=4.5, y=7.5, z=-105)
    if pokemon in ('jynx', 'smoochum'):
        scene['camera'].update(y=9, z=-180)
    if camera_back != 1.0:
        scene['camera']['z'] *= camera_back
    scene['animation'] = {**spec['animation_settings'], 'nodes': []}
    for row in spec['pose']:
        scene['animation']['nodes'].append({'tracks': [
            {'trackType': kind, 'ptclBank': 0, 'ptclId': 0, 'frameCount': 5,
             'keys': [{'frame': frame, 'value': value, 'tan': 0, 'interpolationType': interp}
                      for frame, interp in ((0, 'HSD_A_OP_SPL0'), (5, 'HSD_A_OP_SPL'))]}
            for kind, value in row]})
    path = folder / spec['scene_name']
    path.write_text(yaml.safe_dump(scene, sort_keys=False), encoding='utf-8')
    if not spec.get('maya_pose'):
        return [str(path)]
    anim = folder / 'pose.anim'
    text = ('animVersion 1.1;\nmayaVersion 2018;\ntimeUnit ntscf;\nlinearUnit cm;\n'
            f'angularUnit {spec["angular_unit"]};\nstartTime 0;\nendTime 5;\n')
    for track in spec['maya_pose']:
        text += (f'anim {track["channel"]};\nanimData {{\n input time;\n output {track["output"]};\n'
                 ' weighted 0;\n preInfinity constant;\n postInfinity constant;\n keys {\n'
                 f' 0 {track["value"]} fixed fixed 1 0 0 0 1 0 1;\n'
                 f' 5 {track["value"]} auto auto 1 0 0;\n }}\n}}\n')
    anim.write_text(text, encoding='utf-8')
    return [str(anim), str(path)]


def body_root(dat):
    return next(at for name, at in dat.roots if name.endswith('_joint') and
                'matanim' not in name and 'shapeanim' not in name)


def render_copy(source, vanilla, output):
    """Apply the accepted renderer-only cutout/pass normalization to a copy."""
    dat, base = DatFile(source), DatFile(vanilla)
    raw = bytearray(dat.raw)
    root, original = body_root(dat), body_root(base)
    flags = dat.u32(root + 4)
    extra = (flags & 0x80000) & ~(base.u32(original + 4) & 0x80000)
    struct.pack_into('>I', raw, 32 + root + 4, flags & ~extra)
    seen = set()
    for joint in dat._iter_tree(root, 8, 12):
        dobj = dat.ptr(joint + 16)
        while dobj is not None:
            mobj = dat.ptr(dobj + 8)
            tobj = dat.ptr(mobj + 8) if mobj is not None else None
            while tobj is not None and tobj not in seen:
                seen.add(tobj)
                flags = dat.u32(tobj + 0x40)
                if flags & 0xF == 0 and flags & 0x1F0 == 0x80:
                    flags = (flags & ~0x1F0) | 0x10
                    if flags & 0xF00000 == 0x400000:
                        flags = (flags & ~0xF00000) | 0x300000
                    struct.pack_into('>I', raw, 32 + tobj + 0x40, flags)
                tobj = dat.ptr(tobj + 4)
            dobj = dat.ptr(dobj + 4)
    output.write_bytes(raw)


def fit(im, size=(136, 188), margin=4):
    box = im.getchannel('A').getbbox()
    if not box:
        raise ValueError('Empty portrait')
    im = im.crop(box)
    im.thumbnail((size[0] - 2 * margin, size[1] - 2 * margin), Image.Resampling.LANCZOS)
    out = Image.new('RGBA', size)
    out.alpha_composite(im, ((size[0] - im.width) // 2, size[1] - margin - im.height))
    return out


def render(pokemon, fighter, source, folder, runtime, files, *, fill=(0, 0, 0)):
    folder.mkdir(parents=True, exist_ok=True)
    dat = folder / ('Pl' + CODES[fighter] + 'Nr.dat')
    render_copy(source, files / dat.name, dat)
    arguments = scene_files(fighter, folder, pokemon)
    out = folder / 'csp.png'
    # All accepted ports preserve the donor DObj slots. Keep the authored scene's
    # hidden nodes (alternate faces, low-detail geometry and Yoshi's shield egg).
    command = [str(runtime / 'hsdlib/win-x64/HSDRawViewer.exe'), '--csp', str(dat), str(out)]
    if pokemon in ('jynx', 'smoochum'):
        command += ['--scale', '4', '--no-shadow']
    if fighter == 'GameAndWatch':
        command += ['--override-diffuse', ','.join(map(str, (*fill, 255)))]
    if fighter == 'Fox':
        gun = folder / 'PlFx.dat'       # its own copy: HSDRaw opens a file for itself, and renders run side by side
        shutil.copyfile(files / gun.name, gun)
        command += ['--gun', str(gun), '--gun-bone', '68', '--gun-view', '47,-47,-114',
                    '--gun-offset', '-0.15,-0.8,0.05', '--gun-scale', '0.85']
    with (folder / 'render.log').open('w', encoding='utf-8') as log:
        subprocess.run(command + arguments, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    im = Image.open(out).convert('RGBA')
    if fighter == 'Ness':
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if not im.getchannel('A').getbbox():
        raise ValueError('Renderer returned an empty portrait: ' + pokemon)
    if pokemon == 'unownx':
        pixels = np.array(im)
        body = pixels[..., 3] > 200
        grown = np.array(Image.fromarray((body * 255).astype('uint8')).filter(ImageFilter.MaxFilter(3))) > 128
        pixels[grown & ~body] = (115, 115, 115, 255)
        im = Image.fromarray(pixels)
    if pokemon in ('jynx', 'smoochum'):
        im.save(folder / 'layer.png')
        im = fit(im)
    im.save(out)
    return out


def build_portraits(cast, targets, output, runtime, selected=None):
    cast, targets = checked_component(cast, 'cast'), checked_component(targets, MELEE_FILES)
    rows = json.loads((cast / 'receipt.json').read_text())['outputs']
    wanted = {n.lower() for n in selected} if selected else {r['pokemon'].lower() for r in rows}
    if not wanted or wanted - {r['pokemon'].lower() for r in rows}:
        raise ValueError('Unknown or missing portrait costume')
    runtime = Path(runtime).resolve()
    with output_directory(output, 'portraits') as root:
        rows = [row for row in rows if row['pokemon'].lower() in wanted]
        paths = run_all(lambda row: render(row['pokemon'].lower(), row['fighter'], cast / row['path'],
                                           root / row['pokemon'].lower(), runtime, targets / 'files'), rows, tries=3)
        outputs = [{'pokemon': row['pokemon'], 'path': path.relative_to(root).as_posix(), **fingerprint(path)}
                   for row, path in zip(rows, paths)]
        if {'jynx', 'smoochum'} <= wanted:
            pair = Image.new('RGBA', (136, 188))
            for mon, width, at in (('jynx', 124, (12, 5)), ('smoochum', 88, (0, 83))):
                im = Image.open(root / mon / 'layer.png').convert('RGBA')
                im = im.crop(im.getchannel('A').getbbox())
                im = im.resize((width, round(width * im.height / im.width)), Image.Resampling.LANCZOS)
                pair.alpha_composite(im, at)
            path = root / 'jynx-smoochum.png'
            pair.save(path)
            outputs.append({'pokemon': 'Jynx & Smoochum', 'path': path.name, **fingerprint(path)})
        return receipt(root, 'portraits', {'cast': str(cast), 'targets': str(targets)}, outputs)


def build_color_portraits(colosseum, colors, cast, targets, portraits, output, runtime, selected=None):
    """Use the same saved scenes and color maps as the accepted alternate costumes."""
    from .native import palette, recolor
    colors = checked_component(colors, 'costume-colors')
    cast = checked_component(cast, 'cast')
    targets = checked_component(targets, MELEE_FILES)
    portraits = checked_component(portraits, 'portraits')
    costumes = json.loads((colors / 'receipt.json').read_text())['costumes']
    cast_rows = json.loads((cast / 'receipt.json').read_text())['outputs']
    fighters = {r['pokemon']: r['fighter'] for r in cast_rows}
    defaults = {r['pokemon']: cast / r['path'] for r in cast_rows}
    pictures = {r['pokemon']: portraits / r['path']
                for r in json.loads((portraits / 'receipt.json').read_text())['outputs']}
    specs = load('recolors.json')
    wanted = {n.lower() for n in selected} if selected else {n.lower() for n in costumes}
    if not wanted or wanted - {n.lower() for n in costumes}:
        raise ValueError('Unknown or missing portrait color')
    with output_directory(output, 'color-portraits') as root:
        jobs = [(mon, row) for mon, rows in costumes.items() if mon.lower() in wanted for row in rows]

        def one(job):
            mon, row = job
            spec, pal, key = specs[mon], load('palettes/' + mon + '.json'), row['color']
            folder = root / mon.lower() / key
            folder.mkdir(parents=True, exist_ok=True)
            if spec.get('art') == 'map':
                fn = (palette.Palette(pal['zones']).map(pal[key])
                      if key in ('red', 'blue', 'green') and key in pal else
                      recolor.colour_map(key, spec['colours'][key], spec, colosseum))
                base = pictures['Jynx & Smoochum' if mon == 'Jynx' else mon]
                path = folder / 'csp.png'
                recolor.mapped_image(Image.open(base), fn).save(path)
                return path
            fill = tuple(bytes.fromhex(row['gaw']['fill'][3:])) if row.get('gaw') else (0, 0, 0)
            if fill == (0, 0, 0) and (colors / row['dat']).read_bytes() == defaults[mon].read_bytes():
                # The very costume file of the default (Sceptile green, Minun blue, Plusle red): its default portrait,
                # not a second render. Two renders can differ by GPU noise, and m-ex stores a CSP once only when two
                # are identical, so MnSlChr's size (and the online character select's free memory) went by chance.
                path = folder / 'csp.png'
                shutil.copyfile(pictures[mon], path)
                return path
            return render(mon.lower(), fighters[mon], colors / row['dat'], folder,
                          Path(runtime).resolve(), targets / 'files', fill=fill)

        def same_as(mon, row):
            """The earlier colour a slot repeats (a recipe kind {"as": colour}): its portrait is copied, not rendered."""
            kind = specs[mon]['colours'][row['color']]
            return kind.get('as') if isinstance(kind, dict) else None

        rendered = [job for job in jobs if not same_as(*job)]
        paths = {(mon, row['color']): path for (mon, row), path in zip(rendered, run_all(one, rendered, tries=3))}
        for mon, row in jobs:
            if same_as(mon, row):
                folder = root / mon.lower() / row['color']
                folder.mkdir(parents=True, exist_ok=True)
                paths[mon, row['color']] = folder / 'csp.png'
                shutil.copyfile(paths[mon, same_as(mon, row)], folder / 'csp.png')
        outputs = [{'pokemon': mon, 'color': row['color'], 'path': paths[mon, row['color']].relative_to(root).as_posix(),
                    **fingerprint(paths[mon, row['color']])} for mon, row in jobs]
        return receipt(root, 'color-portraits', {'colors': str(colors), 'portraits': str(portraits),
                       'targets': str(targets), 'cast': str(cast)}, outputs)
