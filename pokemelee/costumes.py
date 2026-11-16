"""Package regenerated costumes and presentation for standalone m-ex assembly."""
from concurrent.futures import ProcessPoolExecutor
import io
import json
from pathlib import Path
import zipfile

from PIL import Image

from . import anime_cast, anime_flat
from .cast import MELEE_FILES, checked_component
from .catalog import load
from .export import fingerprint
from .parallel import workers
from .portraits import CODES
from .workspace import output_directory, receipt


def png_bytes(im):
    out = io.BytesIO()
    im.save(out, 'PNG')
    return out.getvalue()


def pair_portrait(leader, partner):
    canvas = Image.new('RGBA', (204, 188))
    for picture, dx in ((partner, -26), (leader, 14)):
        im = Image.open(picture).convert('RGBA')
        if im.size != (136, 188):
            raise ValueError('Pair portraits must retain their accepted 136x188 size')
        canvas.alpha_composite(im, (34 + dx, 0))
    return canvas.crop((34, 0, 170, 188))


def anime_costume(source, target, fighter):
    """The AniMelee costume: flat colours, then the outline. Pure Python, so each runs in a process of its own."""
    Path(target).write_bytes(anime_flat.flatten(source))
    anime_cast.convert(target, target, fighter)


def package_costumes(cast, colors, portraits, color_portraits, art, targets, output, profile='normal'):
    if profile not in ('normal', 'animelee'):
        raise ValueError('Unknown costume profile')
    paths = {key: checked_component(path, operation) for key, path, operation in (
        ('cast', cast, 'cast'), ('colors', colors, 'costume-colors'), ('portraits', portraits, 'portraits'),
        ('color_portraits', color_portraits, 'color-portraits'), ('art', art, 'menu-art'),
        ('targets', targets, MELEE_FILES))}
    records = {key: json.loads((path / 'receipt.json').read_text()) for key, path in paths.items()}
    base = {r['pokemon']: r for r in records['cast']['outputs']}
    specs = load('recolors.json')
    images = {(r['pokemon'], 'default'): paths['portraits'] / r['path'] for r in records['portraits']['outputs']}
    images.update({(r['pokemon'], r['color']): paths['color_portraits'] / r['path']
                   for r in records['color_portraits']['outputs']})
    with output_directory(output, 'costume-packages') as root:
        jobs = []
        for mon, row in base.items():
            code = CODES[row['fighter']]
            choices = [{'color': 'default', 'dat': paths['cast'] / row['path'],
                        'stock': paths['art'] / ('stock-' + specs[mon]['idx'] + '.png'),
                        'gaw': {'fill': '#FF000000', 'outline': '#80FFFFFF'} if code == 'Gw' else None}]
            choices += [{**r, 'dat': paths['colors'] / r['dat'], 'stock': paths['colors'] / r['stock']}
                        for r in records['colors']['costumes'][mon]]
            for choice in choices:
                folder = root / mon.lower() / choice['color']
                folder.mkdir(parents=True)
                jobs.append((mon, row, code, choice, folder))
        anime = profile == 'animelee'
        outlined = [(choice['dat'], folder / 'costume.dat', paths['targets'] / 'files' / f'Pl{code}.dat')
                    for _, _, code, choice, folder in jobs if anime and code != 'Gw']
        if outlined:
            with ProcessPoolExecutor(workers(len(outlined))) as pool:
                list(pool.map(anime_costume, *zip(*outlined)))
        outputs, costumes = [], {}
        for mon, row, code, choice, folder in jobs:
            key = choice['color']
            picture = images['Jynx & Smoochum' if mon == 'Jynx' and key == 'default' else mon, key]
            csp = pair_portrait(picture, images['Minun', key]) if mon == 'Plusle' else Image.open(picture).convert('RGBA')
            data = choice['dat'].read_bytes()
            if anime and code != 'Gw':
                data = (folder / 'costume.dat').read_bytes()
                csp = anime_flat.portrait(csp)
            target = folder / 'costume.zip'
            filename = f'Pl{code}Nr' + ('' if code in ('Pp', 'Nn') else 'Mod') + '.dat'
            with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr(filename, data)
                z.writestr('csp.png', png_bytes(csp))
                z.write(choice['stock'], 'stc.png')
                if choice['gaw']:
                    z.writestr('gaw.json', json.dumps(choice['gaw']))
            outputs.append({'path': target.relative_to(root).as_posix(), **fingerprint(target)})
            costumes.setdefault(mon, []).append({'color': key, 'path': outputs[-1]['path'], 'fighter': row['fighter']})
        return receipt(root, 'costume-packages', {key: str(path) for key, path in paths.items()},
                       outputs, profile=profile, costumes=costumes)
