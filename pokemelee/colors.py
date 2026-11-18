"""Replay the final shiny and individually designed team costumes."""
import io
import json

import numpy as np
from PIL import Image

from .art import one, stock_icon
from .cast import checked_component
from .catalog import load
from .fsys import entries
from .native import palette, recolor
from .workspace import output_directory, receipt, write_blob


def image_bytes(im):
    buffer = io.BytesIO()
    im.save(buffer, 'PNG')
    return buffer.getvalue()


def build_colors(colosseum, cast, output, selected=None):
    cast = checked_component(cast, 'cast')
    rows = json.loads((cast / 'receipt.json').read_text())['outputs']
    specs = load('recolors.json')
    wanted = {n.lower() for n in selected} if selected else {r['pokemon'].lower() for r in rows}
    if not wanted or wanted - {r['pokemon'].lower() for r in rows}:
        raise ValueError('Unknown or missing color costume')
    bodies = dict(entries(colosseum.read('poke_body.fsys')))
    with output_directory(output, 'costume-colors') as root:
        outputs, costumes = [], {}
        for row in rows:
            mon = row['pokemon']
            if mon.lower() not in wanted:
                continue
            source = cast / row['path']
            base = source.read_bytes()
            spec, pal = specs[mon], load('palettes/' + mon + '.json')
            stock = stock_icon(one(bodies, 'body' + spec['idx']))
            costumes[mon] = []
            made = {}
            for key, kind in spec['colours'].items():
                folder = mon.lower() + '/' + key
                gaw = None
                if isinstance(kind, dict) and 'as' in kind:
                    # A second slot with an earlier colour's look (Captain Falcon's slots follow vanilla's colours
                    # online): the very same file and stock icon, so m-ex stores its pictures once.
                    data, icon, gaw = made[kind['as']]
                elif spec.get('gw'):
                    gaw = {'fill': '#FF000000', 'outline': '#80FFFFFF'}
                    if key in pal:
                        gaw.update({k: pal[key][k] for k in ('fill', 'outline')})
                        data = base
                        fill = np.array(list(bytes.fromhex(gaw['fill'][3:])), float) / 255
                        pixels = np.array(stock, float) / 255
                        light = pixels[..., :3].mean(2, keepdims=True)
                        pixels[..., :3] = fill * (1 - light) + light
                        icon = Image.fromarray(np.rint(pixels * 255).astype('u1'))
                    else:
                        fn = recolor.colour_map(key, kind, spec, colosseum)
                        data = recolor.recolored(source, fn)
                        icon = stock_icon(one(bodies, 'body' + spec['idx'] + '_c'))
                elif key in ('red', 'blue', 'green') and key in pal:
                    fn = palette.Palette(pal['zones']).map(pal[key])
                    data = palette.recolored_by_texture(source, fn)
                    icon = recolor.mapped_image(stock, fn)
                else:
                    fn = recolor.colour_map(key, kind, spec, colosseum)
                    data = base if kind == 'keep' else recolor.recolored(source, fn)
                    icon = (stock_icon(one(bodies, 'body' + spec['idx'] + '_c')) if key == 'shiny'
                            else recolor.mapped_image(stock, fn))
                made[key] = data, icon, gaw
                dat = write_blob(root, folder + '/costume.dat', data)
                outputs.extend([dat, write_blob(root, folder + '/stock.png', image_bytes(icon))])
                record = {'color': key, 'dat': dat['path'], 'stock': folder + '/stock.png', 'gaw': gaw}
                if gaw:
                    outputs.append(write_blob(root, folder + '/gaw.json', (json.dumps(gaw, indent=2) + '\n').encode()))
                costumes[mon].append(record)
        return receipt(root, 'costume-colors', {'colosseum': colosseum.info(), 'cast': str(cast)},
                       outputs, costumes=costumes)
