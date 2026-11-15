"""Original deterministic palette and texture operations."""
import struct
import numpy as np
from . import datprobe
HEADER = 0x20

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


