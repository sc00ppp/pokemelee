"""Accepted shiny and hue maps; source textures are read from the supplied disc."""
import difflib
import struct
import numpy as np
from PIL import Image
from .. import datprobe
from . import cmpr_decode as hsd_cmpr
HEADER = 0x20
TEAM = {'red': (0, 1, .95), 'blue': (218, 1, 1), 'green': (128, .85, .8)}
FEATHER = 14
GREY = .10, .22

def hsv(rgb):
    top, low = rgb.max(1), rgb.min(1)
    span = top - low
    safe = np.where(span > 1e-9, span, 1)
    r, g, b = rgb.T
    h = np.where(top == r, ((g - b) / safe) % 6, np.where(top == g, (b - r) / safe + 2, (r - g) / safe + 4)) * 60
    return np.where(span > 1e-9, h, 0), span / np.maximum(top, 1e-9), top


def rgb(h, s, v):
    h = (h % 360) / 60
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return np.select([i[..., None] == k for k in range(6)],
                     [np.stack(c, -1) for c in ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))])


def ramp(x, a, b):
    x = np.clip((x - a) / (b - a), 0, 1)
    return x * x * (3 - 2 * x)


def rules_map(rules, grey=GREY):
    """rules: [center, half width, hue it goes to, saturation x, value x (optional: lowest saturation)]."""
    def apply(c):
        h, s, v = hsv(c)
        out = c.copy()
        for rule in rules:
            center, half, to, sat, val = rule[:5]
            least = rule[5] if len(rule) > 5 else 0
            away = np.abs((h - center + 180) % 360 - 180)
            weight = (1 - ramp(away, half, half + FEATHER)) * ramp(s, *grey)
            moved = rgb(h + to - center, np.clip(np.maximum(s * sat, least), 0, 1), np.clip(v * val, 0, 1))
            out = out + (moved - out) * weight[:, None]
        return out
    return apply


def pairs_map(src, dst):
    """Nearest normal colours in the table, and their shiny ones with the difference kept, so shading survives."""
    def apply(c):
        out = np.empty_like(c)
        for start in range(0, len(c), 2000):
            part = c[start:start + 2000]
            d = ((part[:, None] - src[None]) ** 2).sum(2)
            near = np.argpartition(d, 3, axis=1)[:, :4]
            w = 1 / (np.take_along_axis(d, near, 1) + 1e-4)
            w /= w.sum(1, keepdims=True)
            out[start:start + 2000] = (w[..., None] * (dst[near] + (part[:, None] - src[near]) * .6)).sum(1)
        return np.clip(out, 0, 1)
    return apply


def hsd(name, disc):
    """The model's HSD file out of its pkx, as bytes."""
    from pokemelee.fsys import entries
    data = next(iter(entries(disc.read(f'pkx_{name}.fsys'))))[1]
    for s in range(0, 0x4000, 4):
        fs, ds, rc, roots, refs = struct.unpack('>5I', data[s:s + 20])
        if 0x1000 < fs <= len(data) - s and 0x1000 < ds < fs and 0 < roots < 64 and HEADER + ds + rc * 4 + (roots + refs) * 8 <= fs:
            return data[s:s + fs]
    raise ValueError(name)


def model_images(blob):
    """{image data offset: (offset, w, h, fmt, palette struct)} of every texture object in an HSD file, by its relocations."""
    fs, ds, rc = struct.unpack('>3I', blob[:12])
    data = blob[HEADER:HEADER + ds]
    ptrs = set(struct.unpack(f'>{rc}I', blob[HEADER + ds:HEADER + ds + rc * 4]))
    u32 = lambda o: struct.unpack('>I', data[o:o + 4])[0]
    found = {}
    for o in range(0, ds - 0x5C, 4):
        if o + 0x4C not in ptrs or u32(o + 8) > 7 or u32(o + 12) > 21 or u32(o + 0x34) > 2 or u32(o + 0x38) > 2:
            continue
        img = u32(o + 0x4C)
        if img + 16 > ds:
            continue
        at = u32(img)
        w, h = struct.unpack('>HH', data[img + 4:img + 8])
        fmt = u32(img + 8)
        if 0 < w <= 1024 and 0 < h <= 1024 and fmt <= 14:
            found[at] = (at, w, h, fmt, u32(o + 0x50) if o + 0x50 in ptrs else None)
    return data, found


def decoded(data, entry):
    at, w, h, fmt, pal = entry
    if fmt == 14:
        return hsd_cmpr.cmpr(data[at:], w, h).astype(float) / 255
    img = datprobe.Image(None, at, w, h, fmt, data[at:at + datprobe.gx_image_size(fmt, w, h)])
    tlut = None
    if pal is not None:
        table, form = struct.unpack('>2I', data[pal:pal + 8])
        count = struct.unpack('>H', data[pal + 12:pal + 14])[0]
        tlut = datprobe.Tlut(pal, table, form, count, data[table:table + count * 2])
    return np.array(datprobe.decode_image(img, tlut), float) / 255


def rare_map(name, disc):
    a, b = hsd(name, disc), hsd('rare_' + name, disc)
    (da, ia), (db, ib) = model_images(a), model_images(b)
    coloured = lambda found: sorted(e for e in found.values() if e[3] > 3)     # a rare model can add a greyscale map
    na, nb = coloured(ia), coloured(ib)
    blocks = difflib.SequenceMatcher(None, [e[1:3] for e in na], [e[1:3] for e in nb], autojunk=False).get_matching_blocks()
    src, dst = [], []
    for entry, other in ((na[m.a + k], nb[m.b + k]) for m in blocks for k in range(m.size)):
        x, y = decoded(da, entry), decoded(db, other)
        keep = (x[..., 3] > .5) & (y[..., 3] > .5)
        if keep.sum() < 16 or np.corrcoef(x[keep][:, :3].mean(1), y[keep][:, :3].mean(1))[0, 1] < .6:    # not the same picture
            continue
        src.append(x[keep][:, :3])
        dst.append(y[keep][:, :3])
    src, dst = np.concatenate(src), np.concatenate(dst)
    key = (src * 31).round().astype(int) @ [1, 32, 1024]
    order = np.argsort(key)
    key, src, dst = key[order], src[order], dst[order]
    cut = np.flatnonzero(np.diff(key)) + 1
    src = np.array([p.mean(0) for p in np.split(src, cut)])
    dst = np.array([p.mean(0) for p in np.split(dst, cut)])
    print('  pairs', name, len(src), 'colours', flush=True)
    return pairs_map(src, dst)


def rgb565(values):
    v = values.astype(np.uint32)
    return np.stack([(v >> 11) & 31, (v >> 5) & 63, v & 31], 1) / np.array([31, 63, 31])


def to565(c):
    q = np.rint(c * [31, 63, 31]).astype(np.uint32)
    return (q[:, 0] << 11) | (q[:, 1] << 5) | q[:, 2]


def cmpr(buf, at, w, h, fn):
    """Every block's two end colours through fn; the mode (c0 > c1 opaque, else with transparency) stays as it was."""
    pw, ph = (w + 7) // 8 * 8, (h + 7) // 8 * 8
    count = pw * ph // 16
    words = np.frombuffer(bytes(buf[at:at + count * 8]), '>u2').reshape(-1, 4).copy()
    bits = np.frombuffer(bytes(buf[at:at + count * 8]), '>u4').reshape(-1, 2)[:, 1].copy()
    a, b = words[:, 0].astype(np.int64), words[:, 1].astype(np.int64)
    opaque = a > b
    unique, inverse = np.unique(np.r_[a, b], return_inverse=True)
    mapped = to565(fn(rgb565(unique))).astype(np.int64)[inverse]
    na, nb = mapped[:count].copy(), mapped[count:].copy()
    swap = (opaque & (na < nb)) | (~opaque & (na > nb))
    na[swap], nb[swap] = nb[swap].copy(), na[swap].copy()
    four = 0x55555555
    bits = np.where(swap & opaque, bits ^ four, bits)
    bits = np.where(swap & ~opaque, bits ^ ((~bits >> 1) & four), bits)
    same = opaque & (na == nb)       # an equal pair would read as the transparent mode
    room = (na & 31) < 31            # nudge blue's lowest bit where it has room: +1 on a full blue carries into green
    na = np.where(same & room, na + 1, na)                 # (2026-11-12: pale blues came out lemon yellow)
    nb = np.where(same & ~room, nb - 1, nb)
    out = np.empty(count * 2, '>u4')
    out[0::2] = (na.astype(np.uint32) << 16) | nb.astype(np.uint32)
    out[1::2] = bits
    buf[at:at + count * 8] = out.tobytes()


def rgb5a3(buf, at, count, fn):
    """RGB5A3 words through fn: an opaque one stays 5:5:5, a translucent one stays 3:4:4:4 with its alpha."""
    v = np.frombuffer(bytes(buf[at:at + count * 2]), '>u2').astype(np.uint32)
    opaque = (v >> 15) == 1
    c = fn(np.where(opaque[:, None], np.stack([(v >> 10) & 31, (v >> 5) & 31, v & 31], 1) / 31,
                    np.stack([(v >> 8) & 15, (v >> 4) & 15, v & 15], 1) / 15))
    five, four = np.rint(c * 31).astype(np.uint32), np.rint(c * 15).astype(np.uint32)
    out = np.where(opaque, 0x8000 | (five[:, 0] << 10) | (five[:, 1] << 5) | five[:, 2],
                   (v & 0x7000) | (four[:, 0] << 8) | (four[:, 1] << 4) | four[:, 2])
    buf[at:at + count * 2] = out.astype('>u2').tobytes()


def rgba8(buf, at, size, fn):
    tiles = np.frombuffer(bytes(buf[at:at + size]), 'u1').reshape(-1, 64).copy()
    c = np.stack([tiles[:, 1:32:2], tiles[:, 32::2], tiles[:, 33::2]], -1).reshape(-1, 3) / 255
    c = np.rint(fn(c) * 255).astype('u1').reshape(-1, 16, 3)
    tiles[:, 1:32:2], tiles[:, 32::2], tiles[:, 33::2] = c[..., 0], c[..., 1], c[..., 2]
    buf[at:at + size] = tiles.tobytes()


def materials(dat):
    """Every material a joint tree draws. A port's meshes can sit on a root joint flagged ROOT_XLU, the bit
    datprobe.jobj_textures takes for a particle joint, so this walk only leaves out real spline and particle joints."""
    found = set()
    for name, root in dat.roots:
        if name.endswith('_joint') and 'matanim' not in name and 'shapeanim' not in name:
            for j in dat._iter_tree(root, 0x08, 0x0C):
                if dat.u32(j + 0x04) & ((1 << 14) | (1 << 5)):
                    continue
                dobj = dat.ptr(j + 0x10)
                while dobj is not None:
                    mobj = dat.ptr(dobj + 0x08)
                    if mobj is not None:
                        found.add(mobj)
                    dobj = dat.ptr(dobj + 0x04)
    return found


def textures(path):
    """(dat, images, palettes, plain materials): each image and palette once, the blink frames' too."""
    dat = datprobe.DatFile(path)
    images, tables, flat = {}, {}, []
    for name, root in dat.roots:
        if name.endswith('matanim_joint'):
            for anim in dat.matanim_texanims(root):
                images.update({i.data_offset: i for i in anim.images if i.data_offset is not None})
                tables.update({t.data_offset: t for t in anim.tluts if t.data_offset is not None})
    for mobj in materials(dat):
        tobj = dat.ptr(mobj + 0x08)
        if tobj is None and dat.ptr(mobj + 0x0C) is not None:
            flat.append(dat.ptr(mobj + 0x0C))
        while tobj is not None:
            off = dat.ptr(tobj + 0x4C)
            img = dat.image_at(off) if off is not None else None
            if img is not None and img.data_offset is not None:
                images[img.data_offset] = img
                if dat.ptr(tobj + 0x50) is not None:
                    table = dat.tlut_at(dat.ptr(tobj + 0x50))
                    tables[table.data_offset] = table
            tobj = dat.ptr(tobj + 0x04)
    return dat, images, tables, flat


def recolored(path, fn):
    dat, images, tables, flat = textures(path)
    buf = bytearray(dat.raw)
    for at, img in images.items():
        where, size = HEADER + at, datprobe.gx_image_size(img.format, img.width, img.height)
        if img.format == 14:
            cmpr(buf, where, img.width, img.height, fn)
        elif img.format == 4:
            count = size // 2
            buf[where:where + size] = to565(fn(rgb565(np.frombuffer(bytes(buf[where:where + size]), '>u2').astype(np.uint32)))) \
                .astype('>u2').tobytes()
        elif img.format == 5:
            rgb5a3(buf, where, size // 2, fn)
        elif img.format == 6:
            rgba8(buf, where, size, fn)
    for at, table in tables.items():
        where, size = HEADER + at, table.count * 2
        if table.format == 1:
            buf[where:where + size] = to565(fn(rgb565(np.frombuffer(bytes(buf[where:where + size]), '>u2').astype(np.uint32)))) \
                .astype('>u2').tobytes()
        elif table.format == 2:
            rgb5a3(buf, where, table.count, fn)
    for mat in flat:
        at = HEADER + mat + 0x04
        c = np.array(list(buf[at:at + 3]), float)[None] / 255
        buf[at:at + 3] = bytes(np.rint(np.clip(fn(c), 0, 1) * 255).astype('u1')[0].tolist())
    return bytes(buf)


def mapped_image(im, fn):
    px = np.array(im.convert('RGBA')).astype(float) / 255
    shape = px.shape
    px[..., :3] = fn(px[..., :3].reshape(-1, 3)).reshape(shape[0], shape[1], 3)
    return Image.fromarray(np.rint(px * 255).astype('u1'), 'RGBA')


def colour_map(key, kind, spec, disc):
    """The map a spec entry names: 'rare', 'keep', 'body' (a team), a hue number, or a rule list."""
    if kind == 'keep':
        return lambda c: c
    if kind == 'rare':
        return rare_map(spec['rare'], disc)
    if isinstance(kind, dict):
        return lambda c: c * kind['tint']
    if isinstance(kind, list):
        return rules_map(kind)
    hue, sat, val = TEAM[key] if kind == 'body' else (kind, 1, 1)
    return rules_map([[c, half, hue, s * sat, v * val, *rest] for c, half, s, v, *rest in spec['body']], spec.get('grey', GREY))
