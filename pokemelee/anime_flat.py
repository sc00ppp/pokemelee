"""anime_flat.py <in.dat> <out.dat> [--colours 14]: a costume's textures cut to a few flat colours, where they sit.

Colosseum paints soft shading into its textures. With the lights off that reads as blur, and AniMelee's look is colour
regions with hard edges. One palette serves the whole costume, so a colour crossing two textures stays one colour and
the blink frames match the face they sit on. It is read from the costume itself, so run this after recolor.

Same sizes and same offsets, so geometry, weights and every pointer stay byte for byte. A CMPR image is re-encoded, a
palette moves entry by entry, an RGB5A3 image texel by texel. I4 images are masks and stay as they are."""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from .texture_ops import HEADER, datprobe, rgb565, rgb5a3, rgba8, textures, to565

CMPR, RGB565, RGB5A3, RGBA8 = 14, 4, 5, 6
TLUT_565, TLUT_5A3 = 1, 2
MON_COSTUME = re.compile(r'Pl..Nr(Mod.*|_\d+)\.dat')   # m-ex's name for an imported costume; Popo's and Nana's keep Nr and get a number
COLOURS = 14
LANDS = 8              # rounds of moving the palette to the middle of what it took
SOLID = .5
ENTRY_AREA = 8.         # texels a palette entry stands for, about right for the cast's 64x32 CI8 images
PORTRAIT_LINE = 2       # texels
STAGE_COLOURS = 48
STAGE_BLUR = 64         # texels of image width per blur pass: noisy ground would otherwise band into camouflage
GROUP_SIZE = 0x34       # one map_head group: joints, then their animations
LIT = 0b1100            # the DIFF and SPEC bits of a render mode


def lab(c):
    """Nx3 RGB in 0..1 to CIE Lab, where distance is near what the eye sees."""
    linear = np.where(c > .04045, ((c + .055) / 1.055) ** 2.4, c / 12.92)
    xyz = linear @ np.array([[.4124, .3576, .1805], [.2126, .7152, .0722], [.0193, .1192, .9505]]).T
    t = xyz / [.9505, 1, 1.089]
    f = np.where(t > .008856, np.cbrt(t), 7.787 * t + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def choose(colours, counts, size=COLOURS):
    """The palette. Seeds go to whatever is farthest from what's already picked, so a small red iris gets its own colour;
    the square root of a colour's area stops the big body colours from taking every slot."""
    key = (colours * 31).round().astype(np.int64) @ [1, 32, 1024]
    unique, inverse = np.unique(key, return_inverse=True)
    weight = np.bincount(inverse, counts, len(unique))
    mean = np.stack([np.bincount(inverse, colours[:, i] * counts, len(unique)) for i in range(3)], 1) / weight[:, None]
    points, weight = lab(mean), np.sqrt(weight)
    if len(points) <= size:
        return mean
    picked = [int(np.argmax(weight))]
    gap = ((points - points[picked[0]]) ** 2).sum(1)
    for _ in range(size - 1):
        picked.append(int(np.argmax(gap)))
        gap = np.minimum(gap, ((points - points[picked[-1]]) ** 2).sum(1))
    centres = points[picked]
    for _ in range(LANDS):
        near = ((points[:, None] - centres[None]) ** 2).sum(2).argmin(1)
        for k in range(size):
            mine = near == k
            if mine.any():
                centres[k] = (points[mine] * weight[mine, None]).sum(0) / weight[mine].sum()
    near = ((points[:, None] - centres[None]) ** 2).sum(2).argmin(1)
    return np.array([(mean[near == k] * weight[near == k, None]).sum(0) / weight[near == k].sum() for k in range(size) if (near == k).any()])


def nearest(c, palette):
    centres = lab(palette)
    unique, inverse = np.unique((c * 255).round().astype(np.int64) @ [1, 256, 65536], return_inverse=True)
    rgb = np.stack([unique & 255, (unique >> 8) & 255, unique >> 16], 1) / 255
    return ((lab(rgb)[:, None] - centres[None]) ** 2).sum(2).argmin(1)[inverse]


def cmpr_read(raw, w, h):
    """RGBA, padded to whole tiles. Blocks run in 8x8 tiles of four, indices from the top bit down."""
    pw, ph = (w + 7) // 8 * 8, (h + 7) // 8 * 8
    count = pw * ph // 16
    words = np.frombuffer(raw[:count * 8], '>u2').reshape(-1, 4).astype(np.uint32)
    a, b, four = rgb565(words[:, 0]), rgb565(words[:, 1]), words[:, 0] > words[:, 1]
    bits = (words[:, 2] << 16) | words[:, 3]
    pal = np.ones((count, 4, 4))
    pal[:, 0, :3], pal[:, 1, :3] = a, b
    pal[:, 2, :3] = np.where(four[:, None], (2 * a + b) / 3, (a + b) / 2)
    pal[:, 3, :3] = np.where(four[:, None], (a + 2 * b) / 3, 0)
    pal[:, 3, 3] = four
    index = (bits[:, None] >> (30 - 2 * np.arange(16))) & 3
    texels = pal[np.arange(count)[:, None], index].reshape(ph // 8, pw // 8, 2, 2, 4, 4, 4)
    return texels.transpose(0, 2, 4, 1, 3, 5, 6).reshape(ph, pw, 4)


def block(row, palette, codes):
    """One 4x4 block of palette numbers (-1 clear) as (c0, c1, bits). Two colours is the common case and needs no mixes.
    With more, the pair whose ramp lands closest wins, and any third colour takes the nearest step on it."""
    solid = row[row >= 0]
    if not len(solid):
        return 0, 0, 0xFFFFFFFF
    clear = len(solid) < 16
    used, counts = np.unique(solid, return_counts=True)
    if len(used) == 1:
        used = np.r_[used, used]
    order = used[np.argsort(-counts)][:4] if len(used) > 2 else used
    best = None
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a, b = int(codes[order[i]]), int(codes[order[j]])
            c0, c1 = (min(a, b), max(a, b)) if clear or len(used) == 2 or a == b else (max(a, b), min(a, b))
            x, y = rgb565(np.array([c0, c1], np.uint32))
            steps = np.stack([x, y, (2 * x + y) / 3, (x + 2 * y) / 3]) if c0 > c1 else np.stack([x, y, (x + y) / 2])
            cost = ((palette[used][:, None] - steps[None]) ** 2).sum(2)
            error = (cost.min(1) * (counts if len(counts) == len(used) else 8)).sum()
            if best is None or error < best[0]:
                best = error, c0, c1, steps, cost.argmin(1)
    _, c0, c1, _, picks = best
    lookup = dict(zip(used.tolist(), picks.tolist()))
    bits = 0
    for texel in row.tolist():
        bits = bits << 2 | (lookup[texel] if texel >= 0 else 3)
    return c0, c1, bits


def cmpr_write(buf, at, labels, palette):
    """The picture back into the blocks, each distinct block worked out once."""
    ph, pw = labels.shape
    blocks = labels.reshape(ph // 8, 2, 4, pw // 8, 2, 4).transpose(0, 3, 1, 4, 2, 5).reshape(-1, 16)
    rows, inverse = np.unique(blocks, axis=0, return_inverse=True)
    codes = to565(palette)
    worked = np.array([block(row, palette, codes) for row in rows], np.uint32)[inverse.ravel()]
    out = np.empty(len(blocks) * 2, '>u4')
    out[0::2] = (worked[:, 0] << 16) | worked[:, 1]
    out[1::2] = worked[:, 2]
    buf[at:at + len(blocks) * 8] = out.tobytes()


def soft(picture, passes=1):
    """A one texel blur before the colours are picked, so a band's edge follows the shading and not CMPR's blocks."""
    weight = picture[..., 3:]
    layers = np.concatenate([picture[..., :3] * weight, weight], -1)
    for _ in range(passes):
        pad = np.pad(layers, ((1, 1), (1, 1), (0, 0)), mode='edge')
        row = pad[:, :-2] + 2 * pad[:, 1:-1] + pad[:, 2:]
        layers = (row[:-2] + 2 * row[1:-1] + row[2:]) / 16
    return layers[..., :3] / np.maximum(layers[..., 3:], 1 / 16)


def calm(labels):
    """A lone speck takes its neighbours' colour; a line one texel wide keeps its own, since it has neighbours along it."""
    h, w = labels.shape
    pad = np.pad(labels, 1, mode='edge')
    around = np.stack([pad[y:y + h, x:x + w] for y in range(3) for x in range(3) if (x, y) != (1, 1)], -1)
    lone = (labels >= 0) & ~(around == labels[..., None]).any(-1)
    out = labels.copy()
    for y, x in zip(*np.nonzero(lone)):
        near = around[y, x][around[y, x] >= 0]
        if len(near):
            out[y, x] = np.bincount(near).argmax()
    return out


def rgb5a3_rgb(words):
    v = words.astype(np.uint32)
    return np.where(((v >> 15) == 1)[:, None], np.stack([(v >> 10) & 31, (v >> 5) & 31, v & 31], 1) / 31,
                    np.stack([(v >> 8) & 15, (v >> 4) & 15, v & 15], 1) / 15)


def flatten(path, colours=COLOURS):
    dat, images, tables, _ = textures(path)
    return bytes(flattened(dat, images, tables, colours))


def flattened(dat, images, tables, colours, passes=lambda picture: 1):
    buf = bytearray(dat.raw)
    size = lambda img: datprobe.gx_image_size(img.format, img.width, img.height)
    samples, areas = [], []
    pictures = {}
    for at, img in images.items():
        where = HEADER + at
        if img.format == CMPR:
            pictures[at] = cmpr_read(bytes(buf[where:where + size(img)]), img.width, img.height)
            solid = pictures[at][pictures[at][..., 3] > SOLID][:, :3]
            samples.append(solid)
            areas.append(np.ones(len(solid)))
        elif img.format == RGB5A3:
            c = rgb5a3_rgb(np.frombuffer(bytes(buf[where:where + size(img)]), '>u2'))
            samples.append(c)
            areas.append(np.ones(len(c)))
        elif img.format == RGB565:
            c = rgb565(np.frombuffer(bytes(buf[where:where + size(img)]), '>u2').astype(np.uint32))
            samples.append(c)
            areas.append(np.ones(len(c)))
        elif img.format == RGBA8:
            tiles = np.frombuffer(bytes(buf[where:where + size(img)]), 'u1').reshape(-1, 64)
            c = np.stack([tiles[:, 1:32:2], tiles[:, 32::2], tiles[:, 33::2]], -1).reshape(-1, 3) / 255
            samples.append(c)
            areas.append(np.ones(len(c)))
    for at, table in tables.items():
        words = np.frombuffer(bytes(buf[HEADER + at:HEADER + at + table.count * 2]), '>u2')
        samples.append(rgb565(words.astype(np.uint32)) if table.format == TLUT_565 else rgb5a3_rgb(words))
        areas.append(np.full(table.count, ENTRY_AREA))
    if not samples:
        return buf
    palette = choose(np.concatenate(samples), np.concatenate(areas), colours)
    moved = lambda c: palette[nearest(c, palette)]
    for at, picture in pictures.items():
        labels = nearest(soft(picture, passes(picture)).reshape(-1, 3), palette).reshape(picture.shape[:2])
        labels[picture[..., 3] <= SOLID] = -1
        cmpr_write(buf, HEADER + at, calm(labels), palette)
    for at, img in images.items():
        where = HEADER + at
        if img.format == RGB5A3:
            rgb5a3(buf, where, size(img) // 2, moved)
        elif img.format == RGB565:
            words = np.frombuffer(bytes(buf[where:where + size(img)]), '>u2').astype(np.uint32)
            buf[where:where + size(img)] = to565(moved(rgb565(words))).astype('>u2').tobytes()
        elif img.format == RGBA8:
            rgba8(buf, where, size(img), moved)
    for at, table in tables.items():
        where, count = HEADER + at, table.count * 2
        if table.format == TLUT_565:
            buf[where:where + count] = to565(moved(rgb565(np.frombuffer(bytes(buf[where:where + count]), '>u2').astype(np.uint32)))) \
                .astype('>u2').tobytes()
        elif table.format == TLUT_5A3:
            rgb5a3(buf, where, table.count, moved)
    return buf


def stage_parts(path):
    """(dat, images, palettes, materials) of a stage file: what its map_head groups draw, animated frames too."""
    dat = datprobe.DatFile(path)
    head = dict(dat.roots)['map_head']
    groups, count = dat.ptr(head + 8), dat.u32(head + 12)
    images, tables, mobjs = {}, {}, set()
    for group in range(groups, groups + GROUP_SIZE * count, GROUP_SIZE):
        root, frames = dat.ptr(group), dat.ptr(group + 8)
        while frames is not None and dat.ptr(frames) is not None:       # a null-ended list of material animation trees
            for anim in dat.matanim_texanims(dat.ptr(frames)):
                images.update({i.data_offset: i for i in anim.images if i.data_offset is not None})
                tables.update({t.data_offset: t for t in anim.tluts if t.data_offset is not None})
            frames += 4
        for j in dat._iter_tree(root, 0x08, 0x0C) if root is not None else ():
            if dat.u32(j + 0x04) & ((1 << 14) | (1 << 5)):
                continue
            dobj = dat.ptr(j + 0x10)
            while dobj is not None:
                mobj = dat.ptr(dobj + 0x08)
                if mobj is not None:
                    mobjs.add(mobj)
                dobj = dat.ptr(dobj + 0x04)
    for mobj in mobjs:
        tobj = dat.ptr(mobj + 0x08)
        while tobj is not None:
            off = dat.ptr(tobj + 0x4C)
            img = dat.image_at(off) if off is not None else None
            if img is not None and img.data_offset is not None:
                images[img.data_offset] = img
                if dat.ptr(tobj + 0x50) is not None:
                    table = dat.tlut_at(dat.ptr(tobj + 0x50))
                    tables[table.data_offset] = table
            tobj = dat.ptr(tobj + 0x04)
    return dat, images, tables, mobjs


def stage(path, colours=STAGE_COLOURS):
    """A stage to match, in place: flat colours, and the lights off. Baked vertex shading stays, as on AniMelee's own."""
    dat, images, tables, mobjs = stage_parts(path)
    buf = flattened(dat, images, tables, colours, lambda picture: max(picture.shape[:2]) // STAGE_BLUR + 1)
    for mobj in mobjs:
        mode = dat.u32(mobj + 4) & ~LIT
        struct.pack_into('>I', buf, HEADER + mobj + 4, mode if mode & 3 else mode | 1)
    return bytes(buf)


def portrait(picture):
    """A costume's portrait to match: the render as it is, with a black line around the figure, as the in-game outline.
    Works on the picture, so the two-fighter portraits come out the same way. (Through AniMelee Test 12 the render was
    also cut to 12 flat colours; the owner, 2026-11-11: "the animelee css portraits look weird af". The renderer lights
    the model whatever its materials say, so the flattened DAT gives no flatter picture: the light stays.)"""
    c = np.asarray(picture.convert('RGBA'), float) / 255
    figure = c[..., 3] > SOLID
    out = c.copy()
    line = figure
    for _ in range(PORTRAIT_LINE):
        pad = np.pad(line, 1)
        line = pad[1:-1, 1:-1] | pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
    out[line & ~figure] = [0, 0, 0, 1]
    return Image.fromarray((out * 255).round().astype('u1'), 'RGBA')


def portraits(proj_dir, log=print):
    """Every portrait a mon costume shows, in an m-ex project. Game & Watch keeps his own black figure, as in anime_out."""
    done = set()
    for fj in sorted((proj_dir / 'data' / 'fighters').glob('*.json')):
        for costume in json.loads(fj.read_text(encoding='utf-8')).get('costumes') or []:
            name = (costume.get('file') or {}).get('fileName') or ''
            art = proj_dir / 'assets' / ((costume.get('csp') or '').replace('\\', '/') + '.png')
            if MON_COSTUME.fullmatch(name) and name[2:4] != 'Gw' and art.is_file() and art not in done:
                portrait(Image.open(art)).save(art)
                done.add(art)
    log(f'anime: {len(done)} portraits done')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source')
    ap.add_argument('target')
    ap.add_argument('--colours', type=int, default=COLOURS)
    a = ap.parse_args()
    Path(a.target).write_bytes(flatten(a.source, a.colours))


if __name__ == '__main__':
    main()
