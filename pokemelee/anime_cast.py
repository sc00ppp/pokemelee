"""Apply the accepted AniMelee character outline to a generated costume."""
import collections
import struct
import numpy as np
from .display_list import *
from .fighter_tables import fighter_tables, joints, joint_dobjs

def with_colour(d, p, table):
    """A new display list with a colour index after the normal: every vertex takes entry 0 of the colour table."""
    slot = sum(a['name'] <= NRM for a in table)
    out = bytearray()
    for op, rows in strips(d, p, table):
        out += struct.pack('>BH', op, len(rows))
        for raw, _ in rows:
            out += b''.join(raw[:slot]) + b'\0' + b''.join(raw[slot:])
    out += bytes(-len(out) % 32)
    return bytes(out), slot


def attr_table(d, p, table, slot, colour):
    """A copy of the PObj's attribute table with a colour row in GX order; its offset."""
    rows = [bytes(d.data[a['at']:a['at'] + ATTR_SIZE]) for a in table]
    row = struct.pack('>5I', CLR0, 2, 1, 5, 0) + bytes(4)
    rows.insert(slot, row)
    end = bytearray(ATTR_SIZE)
    end[:4] = struct.pack('>I', END)
    at = d.add(b''.join(rows) + bytes(end), 32)
    for i, a in enumerate(table):
        if a['data'] is not None:
            d.point(at + (i + (i >= slot)) * ATTR_SIZE + 20, a['data'])
    d.point(at + slot * ATTR_SIZE + 20, colour)
    return at


def world_scales(d, symbol):
    """Each joint's world scale, for meshes bound to one joint in its local space."""
    out = {}

    def walk(j, parent):
        while j is not None:
            world = parent * np.array(struct.unpack_from('>3f', d.data, j + 0x20))
            out[j] = float(np.mean(np.abs(world)))
            if not d.u32(j + 4) & (1 << 12):
                walk(d.ptr(j + 8), world)
            j = d.ptr(j + 0xc)

    walk(d.root(symbol), np.ones(3))
    return out


def convert(source, target, fighter, line=0.14):
    d = Dat.read(source)
    symbol = next(n for n, _ in d.roots if n.endswith('_Share_joint'))
    tables = fighter_tables(fighter)
    f = Dat.read(fighter)
    scale = struct.unpack_from('>f', f.data, f.ptr(next(o for n, o in f.roots if n.startswith('ftData'))) + 0x8c)[0]
    thick = line / scale
    low, scales = set(tables.low), world_scales(d, symbol)
    places = [(j, o) for j in joints(d, symbol) for o in joint_dobjs(d, j)]

    shaped = {d.ptr(o + 8) for _, o in places if d.ptr(o + 12) is not None
              and any(d.u16(p + 12) & SHAPE_ANIM for p in d.chain(d.ptr(o + 12), 4))}
    colours, black = {}, d.add(struct.pack('>4B', 0, 0, 0, 255), 32)

    def colour_of(m):
        if m not in colours:
            mat = d.ptr(m + 12)
            r, g, b = (d.data[mat + 4 + i] for i in range(3)) if mat is not None else (255, 255, 255)
            alpha = struct.unpack_from('>f', d.data, mat + 12)[0] if mat is not None else 1
            colours[m] = d.add(struct.pack('>4B', r, g, b, round(min(alpha, 1) * 255)), 32)
        return colours[m]

    # one normal per point in space, so a shell stays closed across hard edges and between meshes. Each point keeps two
    # sums, because a model can be two layers back to back (Ralts): those normals cancel and the shell would get no offset
    meshes, normals, stats = {}, collections.defaultdict(lambda: np.zeros((2, 3))), collections.Counter()
    for place, (j, o) in enumerate(places):      # a low-detail DObj can share its body's PObjs: each is rewritten once
        m = d.ptr(o + 8)
        if m is None or d.ptr(o + 12) is None:
            continue
        if m in shaped:
            stats['shape anim'] += 1
            continue
        kind = 'low detail' if place in low else 'translucent' if d.u32(m + 4) & XLU else 'shelled'
        for p in d.chain(d.ptr(o + 12), 4):
            if p not in meshes or (kind == 'shelled' and not meshes[p]['shell']):
                meshes[p] = dict(j=j, o=o, m=m, p=p, shell=kind == 'shelled', kind=kind, env=bool(d.u16(p + 12) & ENVELOPE))
    for p, mesh in meshes.items():
        stats[mesh['kind']] += 1
        mesh['table'] = table = attrs(d, p)
        if any(x['name'] == CLR0 for x in table):
            raise SystemExit('a mesh with vertex colours')
        mesh['rows'] = rows = [row for _, batch in strips(d, p, table) for row in batch]
        mesh['space'] = 'env' if mesh['env'] else mesh['j']
        if mesh['shell']:
            pos, nrm = (next(x for x in table if x['name'] == n) for n in (POS, NRM))
            for _, index in rows:
                n = np.array(read_vector(d, nrm, index[NRM]))
                pair = normals[mesh['space'], tuple(np.round(read_vector(d, pos, index[POS]), 3))]
                pair[0 if pair[0] @ n >= 0 else 1] += n / (np.linalg.norm(n) + 1e-9)
    middle = np.mean([x for _, x in normals], 0) * (1, 0, 1)

    def layers(key):
        """The two sums of a point, the outer one first, or None where the normals simply add up."""
        a, b = normals[key]
        if np.linalg.norm(a + b) >= CANCELLED * (np.linalg.norm(a) + np.linalg.norm(b)):
            return None
        out = (np.array(key[1]) - middle) * (1, 0, 1)
        return (a, b) if a @ out >= b @ out else (b, a)

    for mesh in meshes.values():        # the inner layer gets no shell: the outer one has the line, and an inner rim pokes through
        if mesh['shell']:
            pos, nrm = (next(x for x in mesh['table'] if x['name'] == n) for n in (POS, NRM))
            votes = 0
            for _, index in mesh['rows']:
                both = layers((mesh['space'], tuple(np.round(read_vector(d, pos, index[POS]), 3))))
                if both is not None:
                    votes += 1 if both[0] @ np.array(read_vector(d, nrm, index[NRM])) > 0 else -1
            mesh['shell'] = votes >= 0

    done = set()
    for _, o in places:
        m = d.ptr(o + 8)
        if m is not None and m not in shaped and d.ptr(o + 12) is not None:
            done.add(m)
            colour_of(m)
            struct.pack_into('>I', d.data, m + 4, (d.u32(m + 4) & ~COLOUR_BITS) | FROM_VERTEX)

    # the shell's positions, one table per source table and space
    wanted = collections.defaultdict(set)
    for mesh in meshes.values():
        if mesh['shell']:
            pos = next(x for x in mesh['table'] if x['name'] == POS)
            wanted[pos['data'], pos['stride'], pos['comp'], pos['scale'], mesh['space'], mesh['j'] if not mesh['env'] else None] |= \
                {index[POS] for _, index in mesh['rows']}
    shells = {}
    for (data, stride, comp, sc, space, j), indices in wanted.items():
        out = bytearray((max(indices) + 1) * 12)
        here = 1.0 if j is None else scales.get(j, 1.0)
        for i in indices:
            x = read_vector(d, dict(data=data, stride=stride, comp=comp, scale=sc), i)
            key = space, tuple(np.round(x, 3))
            both = layers(key)
            n = normals[key].sum(0) if both is None else both[0]
            struct.pack_into('>3f', out, i * 12, *(np.array(x) + n / (np.linalg.norm(n) + 1e-9) * thick / here))
        shells[data, space] = d.add(bytes(out), 32)

    last = {}
    for mesh in meshes.values():
        p, m, table, rows = mesh['p'], mesh['m'], mesh['table'], mesh['rows']
        listing, slot = with_colour(d, p, table)
        units = len(listing) // 32
        at = d.add(listing, 32)
        body_table = attr_table(d, p, table, slot, colour_of(m))
        flags = d.u16(p + 12)
        old_env = d.ptr(p + 20)
        d.point(p + 8, body_table)
        d.point(p + 16, at)
        struct.pack_into('>H', d.data, p + 14, units)
        if not mesh['shell']:
            continue
        struct.pack_into('>H', d.data, p + 12, flags & ~CULLS)      # both faces: a one-sided panel's back must hide the shell
        pos = next(x for x in table if x['name'] == POS)
        shell_table = attr_table(d, p, table, slot, black)
        row = shell_table + table.index(pos) * ATTR_SIZE + (table.index(pos) >= slot) * ATTR_SIZE
        struct.pack_into('>I', d.data, row + 12, 4)
        d.data[row + 16] = 0
        struct.pack_into('>H', d.data, row + 18, 12)
        d.point(row + 20, shells[pos['data'], mesh['space']])
        shell = d.add(bytes(0x18), 4)
        d.point(shell + 8, shell_table)
        struct.pack_into('>HH', d.data, shell + 12, (flags & ~CULLS) | OUTSIDE_IN, units)
        d.point(shell + 16, at)
        d.point(shell + 20, old_env)
        head = d.ptr(mesh['o'] + 12)
        tail = last.get(head, d.chain(head, 4)[-1])
        d.point(tail + 4, shell)
        last[head] = shell
    d.save(target)
    return f'{symbol}: {len(places)} places, {len(done)} materials off the lights, scale {scale:.3f}, shell {thick:.3f} units, {dict(stats)}, {len(d.data)} bytes'
