"""Replay the cast's accepted per-texture team palettes."""
import struct
import numpy as np
from . import recolor
from .. import datprobe

L_WEIGHT = .5          # lightness counts at half when finding a texel's zone: shading is mostly lightness
SOFT = .0015           # squared OKLab distance over which a texel's zone fades
HUE_KEEP = .5          # how much of a zone's own hue spread a texel keeps
FAR = .02              # squared distance past which a texel belongs to no zone and keeps its colour
FAR_L = .2             # lightness weight in that test: shading of a zone's own colour is never far


# --------------------------------------------------------------------------- colour
M1 = np.array([[.4122214708, .5363325363, .0514459929], [.2119034982, .6806995451, .1073969566],
               [.0883024619, .2817188376, .6299787005]])
M2 = np.array([[.2104542553, .7936177850, -.0040720468], [1.9779984951, -2.4285922050, .4505937099],
               [.0259040371, .7827717662, -.8086757660]])
M1I, M2I = np.linalg.inv(M1), np.linalg.inv(M2)


def oklab(rgb):
    rgb = np.clip(rgb, 0, 1)
    lin = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    return np.cbrt(lin @ M1.T) @ M2.T


def linear(lab):
    return ((lab @ M2I.T) ** 3) @ M1I.T


def srgb(lin):
    lin = np.clip(lin, 0, 1)
    return np.where(lin <= .0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - .055)


def from_oklab(lab):
    """Back to sRGB; a colour out of gamut loses chroma, never lightness or hue."""
    lin = linear(lab)
    bad = ((lin < -1e-4) | (lin > 1 + 1e-4)).any(1)
    if bad.any():
        lo, hi = np.zeros(bad.sum()), np.ones(bad.sum())
        part = lab[bad]
        for _ in range(14):
            mid = (lo + hi) / 2
            test = np.c_[part[:, 0], part[:, 1:] * mid[:, None]]
            t = linear(test)
            ok = ((t >= -1e-4) & (t <= 1 + 1e-4)).all(1)
            lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
        lin[bad] = linear(np.c_[part[:, 0], part[:, 1:] * lo[:, None]])
    return srgb(lin)


def hexrgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255


def rgbhex(c):
    return '#' + ''.join(f'{int(round(v * 255)):02x}' for v in np.clip(c, 0, 1))


def lch(lab):
    return lab[..., 0], np.hypot(lab[..., 1], lab[..., 2]), np.arctan2(lab[..., 2], lab[..., 1])


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


# --------------------------------------------------------------------------- the map
def move(lab, ref, target, contrast=1.0, shadow=None, light=None):
    """Texels of one zone from its reference colour to the target, offsets kept. shadow / light (OKLab colours) make
    a ramp: a texel's colour is read off the line shadow - target - light at its new lightness, so shadows and
    highlights can turn to hues of their own; its own chroma spread and half its hue spread ride on top."""
    L, C, h = lch(lab)
    L0, C0, h0 = lch(ref)
    L1, C1, h1 = lch(target)
    k = contrast * np.clip(np.sqrt(L1 / max(L0, 1e-3)), .6, 1.3)
    d = (L - L0) * k
    # pinned at black and white: an offset is squeezed into the room the target leaves on its side
    room_up, room_dn = max(1 - L1, 1e-3), max(L1, 1e-3)
    Ln = np.where(d >= 0, L1 + room_up * np.tanh(d / room_up), L1 - room_dn * np.tanh(-d / room_dn))
    ab = np.broadcast_to(target[1:], (len(L), 2)).copy()
    for stop, side in ((shadow, Ln < L1), (light, Ln > L1)):
        if stop is not None:
            t = np.clip((Ln - L1) / (stop[0] - L1 if abs(stop[0] - L1) > 1e-3 else 1e-3), 0, 1)[:, None]
            ab = np.where(side[:, None], target[1:] + (stop[1:] - target[1:]) * t, ab)
    Cs, hs = np.hypot(ab[:, 0], ab[:, 1]), np.arctan2(ab[:, 1], ab[:, 0])
    if C0 > .035:
        Cn = Cs * (C / C0)
        hn = hs + wrap(h - h0) * HUE_KEEP
    else:                       # a grey zone has no hue of its own to keep
        Cn = np.maximum(Cs + (C - C0), 0)
        hn = hs
    return np.stack([Ln, Cn * np.cos(hn), Cn * np.sin(hn)], -1)


def target_of(spec):
    """A team's zone target: "#hex", ["#hex", contrast], or {"base": "#hex", "shadow": "#hex", "light": "#hex",
    "contrast": 1}. -> (base, contrast, shadow, light) in OKLab (None where not given)."""
    lab = lambda h: oklab(hexrgb(h)[None])[0]
    if isinstance(spec, str):
        return lab(spec), 1.0, None, None
    if isinstance(spec, list):
        return lab(spec[0]), spec[1], None, None
    return (lab(spec['base']), spec.get('contrast', 1.0),
            lab(spec['shadow']) if 'shadow' in spec else None, lab(spec['light']) if 'light' in spec else None)


class Palette:
    """zones: {name: [colours]} or {name: {"colours": [...], "in": [texture ids], "out": [texture ids], "bias": 0}}.
    A texture id is an image's data offset in hex ("0x17d20"), "blink" for an eye's blink frame, "fire" for a frame
    of a looping flipbook (anim_fire), "flat" for an untextured material, "stock" for the stock icon and the mapped
    portraits. A zone with "in" only works there; "out" keeps it off those. "bias" is taken off the zone's distances,
    so it wins a tie with a zone of the same colour (.01) or takes every texel of its textures (1)."""

    def __init__(self, zones):
        self.names = list(zones)
        self.where, self.bias = [], []
        samples, owner = [], []
        for i, name in enumerate(self.names):
            z = zones[name] if isinstance(zones[name], dict) else {'colours': zones[name]}
            self.where.append((set(z.get('in', ())), set(z.get('out', ()))))
            self.bias.append(float(z.get('bias', 0)))
            for colour in z['colours']:
                samples.append(oklab(hexrgb(colour)[None])[0])
                owner.append(i)
        self.samples, self.owner = np.array(samples), np.array(owner)
        self.refs = {name: self.samples[self.owner == i][0] for i, name in enumerate(self.names)}

    def allowed(self, ids):
        ids = set(ids or ('stock',))
        return np.array([(not inside or ids & inside) and not (ids & outside) for inside, outside in self.where], bool)

    def weights(self, lab, ids=None):
        """Texel x zone weights, each row summing to 1; zones that don't work in this texture weigh nothing."""
        ok = self.allowed(ids)
        scale = np.array([L_WEIGHT, 1, 1])
        d = (((lab[:, None] - self.samples[None]) * scale) ** 2).sum(2)
        d -= np.array(self.bias)[self.owner]
        d[:, ~ok[self.owner]] = np.inf
        least = d.min(1, keepdims=True)
        w = np.exp(-(d - least) / SOFT)
        out = np.zeros((len(lab), len(self.names) + 1))
        for i in range(len(self.names)):
            if ok[i]:
                out[:, i] = w[:, self.owner == i].max(1)
        # far from every zone: stays as it is. Judged mostly on hue and chroma, so a zone's own shading never counts
        # as far; a colour of another hue or chroma that no zone lists does.
        sat = lambda c: np.c_[c[:, :1] * FAR_L, c[:, 1:] / np.maximum(c[:, :1], .25) * .6]
        far = ((sat(lab)[:, None] - sat(self.samples)[None]) ** 2).sum(2)
        far -= np.array(self.bias)[self.owner]
        far[:, ~ok[self.owner]] = np.inf
        near = far.min(1)
        out[:, :-1] *= np.exp(-np.maximum(near - FAR, 0) / SOFT)[:, None]
        out[:, -1] = np.exp(-(FAR - np.minimum(near, FAR)) / SOFT)
        return out / out.sum(1, keepdims=True)

    def map(self, team):
        """team: {zone: target (see target_of)} -> fn(Nx3 RGB, texture ids)."""
        moves = []
        for name, target in team.items():
            if name.startswith('_'):
                continue
            moves.append((self.names.index(name), target_of(target)))

        def apply(rgb, ids=None):
            out = np.empty_like(rgb)
            for start in range(0, len(rgb), 4000):
                part = rgb[start:start + 4000]
                lab = oklab(part)
                w = self.weights(lab, ids)
                res = lab * (1 - sum(w[:, i] for i, _ in moves))[:, None] if moves else lab.copy()
                for i, (target, contrast, shadow, light) in moves:
                    res += move(lab, self.refs[self.names[i]], target, contrast, shadow, light) * w[:, i][:, None]
                out[start:start + 4000] = from_oklab(res)
            return out
        return apply

    def labels(self, colours):
        """Each zone in a false colour, for a render that shows the split."""
        def apply(rgb, ids=None):
            lab = oklab(rgb)
            w = self.weights(lab, ids)
            shade = np.clip(lab[:, :1] / .75, .35, 1.15)
            return np.clip((w @ np.r_[colours, hexrgb('#00ff80')[None]]) * shade, 0, 1)
        return apply


def walk(path):
    """(dat, {image offset: (image, {tlut offset: tlut}, ids)}, flat material offsets). ids hold the image's offset in
    hex, and for a frame a matanim swaps in, "fire" (a flipbook of 6 or more frames, anim_fire.py's) or "blink"."""
    dat = datprobe.DatFile(path)
    items = {}

    def add(img, tluts, *ids):
        if img is None or img.data_offset is None:
            return
        entry = items.setdefault(img.data_offset, (img, {}, {hex(img.data_offset)}))
        entry[1].update({t.data_offset: t for t in tluts if t is not None and t.data_offset is not None})
        entry[2].update(ids)
    for name, root in dat.roots:
        if name.endswith('matanim_joint'):
            for anim in dat.matanim_texanims(root):
                kind = 'fire' if len({i.data_offset for i in anim.images}) >= 6 else 'blink'
                for img in anim.images:
                    add(img, anim.tluts, kind)
    flat = []
    for mobj in recolor.materials(dat):
        tobj = dat.ptr(mobj + 0x08)
        if tobj is None and dat.ptr(mobj + 0x0C) is not None:
            flat.append(dat.ptr(mobj + 0x0C))
        while tobj is not None:
            off = dat.ptr(tobj + 0x4C)
            if off is not None:
                table = dat.ptr(tobj + 0x50)
                add(dat.image_at(off), [dat.tlut_at(table)] if table is not None else [])
            tobj = dat.ptr(tobj + 0x04)
    return dat, items, flat


def recolored_by_texture(path, fn):
    """recolor.recolored, with each texture's ids handed to fn(rgb, ids)."""
    dat, items, flat = walk(path)
    buf = bytearray(dat.raw)
    done = set()
    for at, (img, tluts, ids) in items.items():
        f = lambda c, ids=frozenset(ids): fn(c, ids)
        where, size = recolor.HEADER + at, datprobe.gx_image_size(img.format, img.width, img.height)
        if img.format == 14:
            recolor.cmpr(buf, where, img.width, img.height, f)
        elif img.format == 4:
            buf[where:where + size] = recolor.to565(f(recolor.rgb565(
                np.frombuffer(bytes(buf[where:where + size]), '>u2').astype(np.uint32)))).astype('>u2').tobytes()
        elif img.format == 5:
            recolor.rgb5a3(buf, where, size // 2, f)
        elif img.format == 6:
            recolor.rgba8(buf, where, size, f)
        for t_at, table in tluts.items():
            if t_at in done:
                continue
            done.add(t_at)
            where, size = recolor.HEADER + t_at, table.count * 2
            if table.format == 1:
                buf[where:where + size] = recolor.to565(f(recolor.rgb565(
                    np.frombuffer(bytes(buf[where:where + size]), '>u2').astype(np.uint32)))).astype('>u2').tobytes()
            elif table.format == 2:
                recolor.rgb5a3(buf, where, table.count, f)
    for mat in flat:
        at = recolor.HEADER + mat + 0x04
        c = np.array(list(buf[at:at + 3]), float)[None] / 255
        buf[at:at + 3] = bytes(np.rint(np.clip(fn(c, frozenset({'flat'})), 0, 1) * 255).astype('u1')[0].tolist())
    return bytes(buf)
