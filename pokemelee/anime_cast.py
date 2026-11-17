"""Apply the accepted AniMelee character outline to a generated costume."""
import collections
import struct
import numpy as np
from .display_list import *
from .anime_stage import S16, packed
from .fighter_tables import fighter_tables, joints, joint_dobjs

def with_colour(d, p, table, normals=True):
    """A new display list with a colour index after the normal: every vertex takes entry 0 of the colour table.
    Without ``normals`` the normal's index is left out too."""
    keep = [normals or a['name'] != NRM for a in table]
    slot = sum(a['name'] <= NRM for a, k in zip(table, keep) if k)
    out = bytearray()
    for op, rows in strips(d, p, table):
        out += struct.pack('>BH', op, len(rows))
        for raw, _ in rows:
            raw = [r for r, k in zip(raw, keep) if k]
            out += b''.join(raw[:slot]) + b'\0' + b''.join(raw[slot:])
    out += bytes(-len(out) % 32)
    return bytes(out), slot


def attr_table(d, table, slot, colour, positions=None):
    """A copy of these attribute rows with a colour row in GX order, as (bytes, pointers) for Store.put.
    ``positions``: (table, first entry, fraction) of a 16-bit slice the rows read their positions from instead."""
    rows, pointers = [], []
    for a in table:
        row = bytearray(d.data[a['at']:a['at'] + ATTR_SIZE])
        row[20:24] = bytes(4)
        if positions is not None and a['name'] == POS:
            struct.pack_into('>I', row, 12, S16)
            row[16] = positions[2]
            struct.pack_into('>H', row, 18, 6)
            pointers.append((len(rows) * ATTR_SIZE + 20, positions[0], positions[1] * 6))
        elif a['data'] is not None:
            pointers.append((len(rows) * ATTR_SIZE + 20, a['data'], 0))
        rows.append(bytes(row))
    pointers = [(at + (at >= slot * ATTR_SIZE) * ATTR_SIZE, target, back) for at, target, back in pointers]
    rows.insert(slot, struct.pack('>5I', CLR0, 2, 1, 5, 0) + bytes(4))
    pointers.append((slot * ATTR_SIZE + 20, colour, 0))
    end = bytearray(ATTR_SIZE)
    end[:4] = struct.pack('>I', END)
    return b''.join(rows) + bytes(end), pointers


class Store:
    """Each piece the outline adds, once. A high- and a low-detail PObj share one display list, and meshes share
    materials and tables: a copy each was memory a four-player match did not have."""

    def __init__(self, d):
        self.d, self.copies, self.virtual = d, {}, {}

    def put(self, payload, pointers=(), align=32):
        """``payload`` with (field, target, back) pointers in it: a pointer ``back`` bytes before its target is where
        entry 0 of a slice would be, so the file's drop can move it with the slice."""
        key = bytes(payload), tuple(pointers)
        if key not in self.copies:
            at = self.copies[key] = self.d.add(payload, align)
            for field, target, back in pointers:
                struct.pack_into('>I', self.d.data, at + field, (target - back) & 0xFFFFFFFF)
                self.d.relocations.add(at + field)
                if back:
                    self.virtual[at + field] = target
        return self.copies[key]


SIXTEEN_BIT_BODIES = {'PlyKoopa5K_Share_joint'}   # Blastoise on Bowser: its body came in as floats, the only one; the
                                                 # owner's call (2026-11-16) to store it as every other costume's is
STEP = .0005        # the most a point stored as 16-bit fixed point may move
NORMAL_COORDS = {1, 2, 4, 6}    # TObj coordinates placed by normals: reflection, highlight, toon, back light
NORMAL_SOURCES = {1, 2, 3}      # GX texgen sources: normal, binormal, tangent
LIT, BUMP = 0b1100, 1 << 24     # render mode: diffuse and specular lights; TObj flag: a bump map


def reads_normals(d, m):
    """Does a material still read normals once it is off the lights: a light left on, or a texture they place."""
    if d.u32(m + 4) & LIT:
        return True
    t = d.ptr(m + 8)
    while t is not None:
        flags = d.u32(t + 0x40)
        if (flags & 0xF) in NORMAL_COORDS or d.u32(t + 0xC) in NORMAL_SOURCES or flags & BUMP:
            return True
        t = d.ptr(t + 4)
    return False


def span(d, p, table, name, whole=False):
    """The bytes of an attribute's array a PObj indexes: from its first entry used, or ``whole`` from the array's own
    start, which is what must stay put while anything still reads it (an index reaches across what lies between)."""
    a = next((a for a in table if a['name'] == name and a['data'] is not None), None)
    if a is None:
        return None
    used = [index[name] for _, rows in strips(d, p, table) for _, index in rows]
    if not used:
        return None
    return a['data'] + (0 if whole else min(used) * a['stride']), a['data'] + (max(used) + 1) * a['stride']


def without(ranges, keep):
    """``ranges`` less every range in ``keep``."""
    out, keep = [], sorted(keep)
    for a, b in ranges:
        for x, y in keep:
            if x < b and a < y:
                if x > a:
                    out.append((a, x))
                a = max(a, y)
        if b > a:
            out.append((a, b))
    return out


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


CULL_BACK = 0x8000      # a shell over an inside-out mesh: its inside faces are the ones GX counts as front
INSIDE_OUT = .75        # share of a mesh's triangles wound the wrong way round its normals that makes it inside out
QUADS, TRIANGLES, STRIP, FAN = 0x80, 0x90, 0x98, 0xA0


def mirrored(d, symbol):
    """Joints whose world matrix mirrors: an odd count of negative scale components down the chain."""
    out = set()

    def walk(j, flip):
        while j is not None:
            here = flip ^ bool(np.prod(struct.unpack_from('>3f', d.data, j + 0x20)) < 0)
            if here:
                out.add(j)
            if not d.u32(j + 4) & (1 << 12):
                walk(d.ptr(j + 8), here)
            j = d.ptr(j + 0xc)

    walk(d.root(symbol), False)
    return out


def wrong_way(d, p, table, mirror):
    """(wound the wrong way, all) triangles of a mesh. GX fronts run clockwise, so a front's cross product points against
    its normals; a costume baked through a mirror keeps its normals but turns every triangle round."""
    pos = next(x for x in table if x['name'] == POS)
    nrm = next((x for x in table if x['name'] == NRM), None)
    wrong = total = 0
    if nrm is None:
        return 0, 0
    for op, rows in strips(d, p, table):
        n, kind = len(rows), op & 0xF8
        tris = ([(i + i % 2, i + 1 - i % 2, i + 2) for i in range(n - 2)] if kind == STRIP else
                [(i, i + 1, i + 2) for i in range(0, n - 2, 3)] if kind == TRIANGLES else
                [(0, i + 1, i + 2) for i in range(n - 2)] if kind == FAN else
                [t for i in range(0, n - 3, 4) for t in ((i, i + 1, i + 2), (i, i + 2, i + 3))] if kind == QUADS else [])
        for a, b, c in tris:
            pa, pb, pc = (np.array(read_vector(d, pos, rows[x][1][POS])) for x in (a, b, c))
            normal = sum(np.array(read_vector(d, nrm, rows[x][1][NRM])) for x in (a, b, c))
            side = np.cross(pb - pa, pc - pa) @ normal
            if side:
                total += 1
                wrong += (side > 0) != mirror
    return wrong, total


def convert(source, target, fighter, line=0.14):
    d = Dat.read(source)
    symbol = next(n for n, _ in d.roots if n.endswith('_Share_joint'))
    tables = fighter_tables(fighter)
    f = Dat.read(fighter)
    scale = struct.unpack_from('>f', f.data, f.ptr(next(o for n, o in f.roots if n.startswith('ftData'))) + 0x8c)[0]
    thick = line / scale
    low, scales, mirror = set(tables.low), world_scales(d, symbol), mirrored(d, symbol)
    places = [(j, o) for j in joints(d, symbol) for o in joint_dobjs(d, j)]

    shaped = {d.ptr(o + 8) for _, o in places if d.ptr(o + 12) is not None
              and any(d.u16(p + 12) & SHAPE_ANIM for p in d.chain(d.ptr(o + 12), 4))}
    store = Store(d)
    colours, black = {}, store.put(struct.pack('>4B', 0, 0, 0, 255))

    def colour_of(m):
        if m not in colours:
            mat = d.ptr(m + 12)
            r, g, b = (d.data[mat + 4 + i] for i in range(3)) if mat is not None else (255, 255, 255)
            alpha = struct.unpack_from('>f', d.data, mat + 12)[0] if mat is not None else 1
            colours[m] = store.put(struct.pack('>4B', r, g, b, round(min(alpha, 1) * 255)))
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
        # a mesh wound inside out (Blastoise's tucked-in body on Bowser) would show its shell's outside: black all over
        wrong, total = wrong_way(d, p, table, not mesh['env'] and mesh['j'] in mirror) if mesh['shell'] else (0, 0)
        mesh['inside_out'] = bool(wrong >= 4 and wrong >= INSIDE_OUT * total)
        stats['inside out'] += int(mesh['inside_out'])
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

    # the shell's positions, one table per source table and space. Only the slice its shells use, as 16-bit fixed point
    # (as a stage's shells): its pointer stays where entry 0 would be, so the display lists keep their indices
    wanted = collections.defaultdict(set)
    for mesh in meshes.values():
        if mesh['shell']:
            pos = next(x for x in mesh['table'] if x['name'] == POS)
            wanted[pos['data'], pos['stride'], pos['comp'], pos['scale'], mesh['space'], mesh['j'] if not mesh['env'] else None] |= \
                {index[POS] for _, index in mesh['rows']}
    shells = {}
    for (data, stride, comp, sc, space, j), indices in wanted.items():
        first = min(indices) & ~15
        out = np.zeros((max(indices) + 1 - first, 3))
        here = 1.0 if j is None else scales.get(j, 1.0)
        for i in indices:
            x = read_vector(d, dict(data=data, stride=stride, comp=comp, scale=sc), i)
            key = space, tuple(np.round(x, 3))
            both = layers(key)
            n = normals[key].sum(0) if both is None else both[0]
            out[i - first] = np.array(x) + n / (np.linalg.norm(n) + 1e-9) * thick / here
        raw, fraction = packed(out)
        shells[data, space] = store.put(raw), first, fraction

    # meshes on one display list are rewritten as one: they keep their normals if any of them still reads them
    lists = collections.defaultdict(list)
    for mesh in meshes.values():
        lists[d.ptr(mesh['p'] + 16)].append(mesh)
    for users in lists.values():
        keep = any(reads_normals(d, mesh['m']) for mesh in users)
        stats['normals kept' if keep else 'normals dropped'] += len(users)
        for mesh in users:
            mesh['normals'] = keep

    # a body that came in as floats, as 16-bit fixed point like every other costume's: a slice per array, its pointer
    # where entry 0 would be, wherever 16 bits hold every point within STEP
    bodies = {}
    if symbol in SIXTEEN_BIT_BODIES:
        arrays = collections.defaultdict(set)
        for mesh in meshes.values():
            pos = next(x for x in mesh['table'] if x['name'] == POS)
            if pos['comp'] == 4 and pos['data'] is not None:
                arrays[pos['data'], pos['stride']] |= {index[POS] for _, index in mesh['rows']}
        for (data, stride), indices in arrays.items():
            first = min(indices) & ~15
            out = np.zeros((max(indices) + 1 - first, 3))
            for i in indices:
                out[i - first] = read_vector(d, dict(data=data, stride=stride, comp=4, scale=0), i)
            raw, fraction = packed(out)
            if .5 / (1 << fraction) <= STEP:
                bodies[data] = store.put(raw), first, fraction
                stats['16-bit body arrays'] += 1

    # what the rewrite leaves unread: the old lists and tables, the normals no mesh reads any more and the float
    # positions the 16-bit ones replace. What any row left still indexes stays, from its array's own start
    dead, read = [], []
    for p, mesh in meshes.items():
        table = mesh['table']
        dead += [(d.ptr(p + 16), d.ptr(p + 16) + d.u16(p + 14) * 32), (d.ptr(p + 8), d.ptr(p + 8) + (len(table) + 1) * ATTR_SIZE)]
        for a in table:
            gone = (a['name'] == NRM and not mesh['normals']) or (a['name'] == POS and a['data'] in bodies)
            if a['data'] is not None:
                (dead if gone else read).append(span(d, p, table, a['name'], not gone))
    for _, o in places:         # meshes the rewrite leaves alone (a shape animation) still read all of theirs
        for p in d.chain(d.ptr(o + 12), 4) if d.ptr(o + 12) is not None else ():
            if p not in meshes:
                table = attrs(d, p)
                read += [(d.ptr(p + 16), d.ptr(p + 16) + d.u16(p + 14) * 32), (d.ptr(p + 8), d.ptr(p + 8) + (len(table) + 1) * ATTR_SIZE)]
                read += [span(d, p, table, a['name'], True) for a in table if a['data'] is not None]
    dead = without([x for x in dead if x], [x for x in read if x])

    last, rewritten = {}, {}
    for mesh in meshes.values():
        p, m, table = mesh['p'], mesh['m'], mesh['table']
        kept = [a for a in table if mesh['normals'] or a['name'] != NRM]
        key = d.ptr(p + 16), mesh['normals']
        if key not in rewritten:
            listing, slot = with_colour(d, p, table, mesh['normals'])
            rewritten[key] = store.put(listing), len(listing) // 32, slot
        at, units, slot = rewritten[key]
        pos = next(x for x in table if x['name'] == POS)
        body_table = store.put(*attr_table(d, kept, slot, colour_of(m), bodies.get(pos['data'])))
        flags = d.u16(p + 12)
        old_env = d.ptr(p + 20)
        d.point(p + 8, body_table)
        d.point(p + 16, at)
        struct.pack_into('>H', d.data, p + 14, units)
        if not mesh['shell']:
            continue
        struct.pack_into('>H', d.data, p + 12, flags & ~CULLS)      # both faces: a one-sided panel's back must hide the shell
        shell_table = store.put(*attr_table(d, kept, slot, black, shells[pos['data'], mesh['space']]))
        shell = d.add(bytes(0x18), 4)
        d.point(shell + 8, shell_table)
        struct.pack_into('>HH', d.data, shell + 12, (flags & ~CULLS) | (CULL_BACK if mesh['inside_out'] else OUTSIDE_IN),
                         units)
        d.point(shell + 16, at)
        d.point(shell + 20, old_env)
        head = d.ptr(mesh['o'] + 12)
        tail = last.get(head, d.chain(head, 4)[-1])
        d.point(tail + 4, shell)
        last[head] = shell
    grown = len(d.data)
    freed = d.drop(dead, store.virtual)
    d.save(target)
    return (f'{symbol}: {len(places)} places, {len(done)} materials off the lights, scale {scale:.3f}, shell {thick:.3f} units, '
            f'{dict(stats)}, {grown} bytes, {freed} unread dropped, {len(d.data)} bytes')
