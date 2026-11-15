"""Moving flames: a looping flipbook on a mon's flame texture, the way the Lavalval Chain skin did its fire.

The game runs every joint's material animation each frame (ftAnim_8006E7B8 -> HSD_JObjAnim -> HSD_TObjAnim) and only holds
the TObjs ftData lists for the eyes at rate 0. So a TexAnim with the loop flag on any other material plays by itself, in
every action, and stops for hitlag with the rest of the fighter. The frames sit in the matanim tree the port already has for
its blink, so recolor.py and anime_flat.py take them like blink frames.

usage (rigswap venv or app venv): python anim_fire.py <in.dat> <out.dat> <width> <height> [--ripple] [--preview <png>]
    the texture of that size is the flame; every DObj wearing it gets the same loop
"""
import argparse
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from pokemelee.anime_flat import cmpr_read, cmpr_write  # noqa: E402
from rigswap.plugins.melee.dat import Dat, joint_dobjs, joints  # noqa: E402

CMPR = 14
LOOP = 0x20000000       # AObj flag
TIMG = 1                # texture track: image number
U8 = 0x80               # a key's value is a whole byte
FRAMES = 8
HOLD = 3                # game frames per image: a loop of 24, as Lavalval's
RAMP = np.array([[176, 28, 10], [236, 66, 14], [250, 128, 22], [255, 196, 44], [255, 240, 130]]) / 255
STEPS = (.24, .46, .68, .9)
SEED = 7


def noise(rng, wide, tall, cells_x, cells_y):
    """Value noise that wraps in both directions, 0 to 1."""
    grid = rng.random((cells_y, cells_x))
    x, y = np.arange(wide) / wide * cells_x, np.arange(tall) / tall * cells_y
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = (1 - np.cos((x - x0) * np.pi)) / 2, (1 - np.cos((y - y0) * np.pi)) / 2
    top = grid[y0][:, x0] * (1 - fx) + grid[y0][:, (x0 + 1) % cells_x] * fx
    low = grid[(y0 + 1) % cells_y][:, x0] * (1 - fx) + grid[(y0 + 1) % cells_y][:, (x0 + 1) % cells_x] * fx
    return top * (1 - fy[:, None]) + low * fy[:, None]


def flame_frames(wide, tall, count=FRAMES):
    """Colour bands that lick up the image: row 0 is the flame's tip, the middle column its heart, as the ports paint it.
    Two layers of noise rise a whole number of heights over the loop, so the last frame runs into the first."""
    rng = np.random.default_rng(SEED)
    big, fine = noise(rng, wide, tall, 3, 2), noise(rng, wide, tall, 6, 4)
    up = np.arange(tall)[:, None] / (tall - 1)
    side = np.abs(np.arange(wide)[None] / (wide - 1) * 2 - 1)
    frames = []
    for k in range(count):
        a, b = round(tall * k / count), round(tall * 2 * k / count)
        heat = .08 + up ** .8 * 1.02 - side * .3 + (np.roll(big, -a, 0) - .5) * .85 + (np.roll(fine, -b, 0) - .5) * .4
        frames.append(np.digitize(heat, STEPS))
    return frames


def ripple_frames(picture, count=FRAMES, reach=(.03, .09), colours=32):
    """(labels per frame, palette): a painted flame's own picture, rippled by noise that rises through it over the loop.
    Flat paint stays still and only the paint's edges lick. Reach is a share of the image, sideways and upward."""
    tall, wide = picture.shape[:2]
    rng = np.random.default_rng(SEED)
    a, b = noise(rng, wide, tall, 5, 2) - .5, noise(rng, wide, tall, 4, 3) - .5
    yy, xx = np.mgrid[0:tall, 0:wide]
    made = []
    for k in range(count):
        lift = round(tall * k / count)
        x = (xx + np.roll(a, -lift, 0) * 2 * reach[0] * wide) % (wide - 1)
        y = np.clip(yy + np.roll(b, -lift, 0) * 2 * reach[1] * tall, 0, tall - 1.001)
        x0, y0 = x.astype(int), y.astype(int)
        fx, fy = (x - x0)[..., None], (y - y0)[..., None]
        made.append(picture[y0, x0] * (1 - fx) * (1 - fy) + picture[y0, x0 + 1] * fx * (1 - fy)
                    + picture[y0 + 1, x0] * (1 - fx) * fy + picture[y0 + 1, x0 + 1] * fx * fy)
    sheet = Image.fromarray(np.rint(np.vstack(made) * 255).astype('u1'), 'RGB').quantize(colours, method=Image.MEDIANCUT, dither=Image.NONE)
    labels = np.array(sheet).reshape(count, tall, wide)
    palette = np.array(sheet.getpalette()[:colours * 3], float).reshape(-1, 3) / 255
    return list(labels), palette


def pack_keys(count, hold):
    """One run of constant keys: the image number, then the frames to the next key. The last key waits for the loop."""
    n = count - 1
    head = [0x01 | (n & 7) << 4 | (0x80 if n >> 3 else 0)] + ([n >> 3] if n >> 3 else [])
    body = [v for i in range(count) for v in (i, hold if i < n else 0)]
    return bytes(head + body)


def wearing(d, wide, tall):
    """(image desc, [(joint number, DObj slot, texture number)]) for the one CMPR texture of this size."""
    found = {}
    symbol = next(n for n, _ in d.roots if n.endswith('_Share_joint'))
    for i, joint in enumerate(joints(d, symbol)):
        for slot, dobj in enumerate(joint_dobjs(d, joint)):
            tobj = d.ptr(d.ptr(dobj + 8) + 8)
            desc = d.ptr(tobj + 0x4C) if tobj is not None else None
            if desc is not None and (d.u16(desc + 4), d.u16(desc + 6), d.u32(desc + 8)) == (wide, tall, CMPR):
                found.setdefault(d.ptr(desc), (desc, []))[1].append((i, slot, d.u32(tobj + 8)))
    if len(found) != 1:
        raise SystemExit(f'{len(found)} CMPR textures are {wide}x{tall}')
    return next(iter(found.values()))


def anim_nodes(d):
    """{joint number: its node in the matanim tree}. The two trees run side by side, child for child."""
    symbol = next(n for n, _ in d.roots if n.endswith('_Share_joint'))
    matanim = next(o for n, o in d.roots if n.endswith('_matanim_joint'))
    number = {j: i for i, j in enumerate(joints(d, symbol))}
    out = {}

    def walk(j, m):
        while j is not None and m is not None:
            out[number[j]] = m
            walk(d.ptr(j + 8), d.ptr(m))
            j, m = d.ptr(j + 0x0C), d.ptr(m + 4)
    walk(d.root(symbol), matanim)
    return out


def slot_node(d, node, slot):
    """The MatAnim of a DObj: the list runs parallel to the joint's DObjs, and new empty ones are added up to it."""
    at = d.ptr(node + 8)
    if at is None:
        at = d.add(bytes(0x10))
        d.point(node + 8, at)
    for _ in range(slot):
        after = d.ptr(at)
        if after is None:
            after = d.add(bytes(0x10))
            d.point(at, after)
        at = after
    return at


def install(source, target, wide, tall, ripple=False, hold=HOLD, preview=None):
    """ripple keeps the picture that's there and moves its edges; otherwise the texture becomes flame_frames'."""
    d = Dat.read(source)
    desc, places = wearing(d, wide, tall)
    pad_y, pad_x = (8 - tall) % 8, (8 - wide) % 8
    if ripple:
        raw = bytes(d.data[d.ptr(desc):d.ptr(desc) + (wide + pad_x) * (tall + pad_y) // 2])
        frames, palette = ripple_frames(cmpr_read(raw, wide, tall)[:tall, :wide, :3])
    else:
        frames, palette = flame_frames(wide, tall), RAMP
    table = d.add(bytes(4 * len(frames)))
    for i, labels in enumerate(frames):
        raw = bytearray((wide + pad_x) * (tall + pad_y) // 2)
        cmpr_write(raw, 0, np.pad(labels, ((0, pad_y), (0, pad_x)), mode='edge'), palette)
        data = d.add(bytes(raw), 32)
        image = d.add(bytes(d.data[desc:desc + 0x18]))
        d.point(image, data)
        d.point(table + i * 4, image)
    keys = pack_keys(len(frames), hold)
    track = d.add(keys)
    fobj = d.add(struct.pack('>IIfBBBxI', 0, len(keys), 0., TIMG, U8, U8, 0))
    d.point(fobj + 0x10, track)
    aobj = d.add(struct.pack('>IfII', LOOP, float(len(frames) * hold), 0, 0))
    d.point(aobj + 8, fobj)
    nodes = anim_nodes(d)
    for joint, slot, texture in places:
        material = slot_node(d, nodes[joint], slot)
        if d.ptr(material + 8) is not None:
            raise SystemExit(f'joint {joint} slot {slot} is animated already')
        anim = d.add(struct.pack('>5I2H', 0, texture, 0, 0, 0, len(frames), 0))
        d.point(anim + 8, aobj)
        d.point(anim + 0x0C, table)
        d.point(material + 8, anim)
    d.save(target)
    if preview:
        sheet = np.hstack([palette[f] for f in frames])
        Image.fromarray(np.rint(sheet * 255).astype('u1'), 'RGB').save(preview)
    return places


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('source')
    a.add_argument('target')
    a.add_argument('wide', type=int)
    a.add_argument('tall', type=int)
    a.add_argument('--ripple', action='store_true')
    a.add_argument('--preview')
    args = a.parse_args()
    print(install(args.source, args.target, args.wide, args.tall, args.ripple, preview=args.preview))
