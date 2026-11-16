"""Raw HSD meshes, read straight from a costume or a Colosseum model DAT: joints, triangle corners, envelopes and
inverse-bind matrices. No Blender, no numpy math."""
import struct

from .display_list import attrs, strips
from .fighter_tables import joint_dobjs

POS, NRM, TEX0 = 9, 10, 13


def tree(d, root):
    """Every joint under `root`, depth first, children before siblings (instanced children skipped)."""
    js = []

    def walk(j):
        while j is not None:
            js.append(j)
            if not d.u32(j + 4) & (1 << 12):
                walk(d.ptr(j + 8))
            j = d.ptr(j + 0x0C)

    walk(root)
    return js


def value(d, a, i):
    n = 2 if a['name'] == TEX0 else 3
    at = a['data'] + i * a['stride']
    if a['comp'] == 4:
        return struct.unpack_from(f'>{n}f', d.data, at)
    code = {0: 'B', 1: 'b', 2: 'H', 3: 'h'}[a['comp']]
    return tuple(v / (1 << a['scale']) for v in struct.unpack_from(f'>{n}{code}', d.data, at))


def corners(d, root):
    """(corners, triangles, pobjs): every display-list corner as (joint #, pobj #, {attr: index}, {attr: value}),
    triangles as corner index triples, and each pobj as (joint #, offset, flags, attribute table)."""
    out, tris, pobjs = [], [], []
    for ji, j in enumerate(tree(d, root)):
        for dobj in joint_dobjs(d, j):
            p = d.ptr(dobj + 0x0C)
            while p is not None:
                table = attrs(d, p)
                pi = len(pobjs)
                pobjs.append((ji, p, d.u16(p + 0x0C), table))
                byname = {a['name']: a for a in table if a['data'] is not None}
                for op, rows in strips(d, p, table):
                    base = len(out)
                    for raw, idx in rows:
                        out.append((ji, pi, idx, {k: value(d, byname[k], v) for k, v in idx.items() if k in byname}))
                    n = len(rows)
                    if op == 0x98:
                        for k in range(n - 2):
                            t = (base + k, base + k + 1, base + k + 2)
                            tris.append(t if k % 2 == 0 else (t[1], t[0], t[2]))
                    elif op == 0x90:
                        for k in range(0, n - 2, 3):
                            tris.append((base + k, base + k + 1, base + k + 2))
                    elif op == 0x80:
                        for k in range(0, n - 3, 4):
                            tris.append((base + k, base + k + 1, base + k + 2))
                            tris.append((base + k, base + k + 2, base + k + 3))
                    elif op == 0xA0:
                        for k in range(1, n - 1):
                            tris.append((base, base + k, base + k + 1))
                    else:
                        raise ValueError(f'Unknown display-list primitive {op:#x}')
                p = d.ptr(p + 4)
    return out, tris, pobjs


def costume_root(d):
    return d.root(next(n for n, o in d.roots if n.endswith('_joint') and 'matanim' not in n and 'shapeanim' not in n))


def colo_root(d):
    """A Colosseum model's top joint: scene_data -> models -> first model -> joint."""
    return d.ptr(d.ptr(d.ptr(d.root('scene_data'))))


def invbind(d, j):
    """The joint's inverse-bind matrix as three rows of four floats, or None."""
    m = d.ptr(j + 0x38)
    if m is None:
        return None
    v = struct.unpack_from('>12f', d.data, m)
    return [list(v[0:4]), list(v[4:8]), list(v[8:12])]


def envelopes(d, p):
    """The PObj's envelope list, [[(joint offset, weight)]], or None when the PObj is not enveloped."""
    if not d.u16(p + 0x0C) & 0x2000:
        return None
    arr = d.ptr(p + 0x14)
    out = []
    while arr is not None and d.ptr(arr) is not None:
        e = d.ptr(arr)
        rows = []
        while d.ptr(e) is not None:
            rows.append((d.ptr(e), struct.unpack_from('>f', d.data, e + 4)[0]))
            e += 8
        out.append(rows)
        arr += 4
    return out


def unique_positions(d, p):
    """How many distinct positions a PObj's display list uses."""
    table = attrs(d, p)
    return len({idx.get(POS) for op, rows in strips(d, p, table) for raw, idx in rows})
