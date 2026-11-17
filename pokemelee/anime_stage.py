"""AniMelee's black outline on a stage, after anime_flat.stage (animelee/RESEARCH.md).

anime_stage.py <in.dat> <out.dat> [--line 0.14] [--behind z]

The inverted hull again, as on the fighters (anime_out.py), with three differences. A stage has no place tables, so a
shell is a DObj of its own after its joint's others: one shared black unlit material, PObjs on the body's display lists
and skin weights. Stage meshes often have no normals, so points move along the faces' own direction, welded in world
space so a shell stays closed across meshes and joints. And a stage reaches far from the camera, so the line gets thicker
with distance and a far mountain keeps one.
A shell only shows at silhouettes, and a stage's lines are mostly elsewhere: where two faces it can see meet, and along the
open edges of meshes with no back. Those edges get real lines, thin black tubes on the same joints, in the same DObj.
Neither goes on translucent meshes, alpha cut-outs or anything drawn outside the depth buffer. A mesh drawn two-sided gets
lines but no shell: its winding means nothing, and the far side of a sheet would show as a black patch.
--behind leaves alone every mesh standing wholly behind that world z: a background that stays as it was rendered.

What a line is not. Where a mesh has normals, they are the model's own word on its edges: a fold they shade smoothly
across is a bump in a rock face, not an edge, unless it is sharp enough to be one whatever the shading says; and they,
not the camera, say which way a two-sided face looks. A seam is no border: where two open edges lie along each other
and their faces look the same way, the surface simply carries on in another mesh (a wall built in strips whose points
do not meet). And a stage can name meshes that get no lines at all (plain=):
the body of a bush under its translucent sheets of leaves, whose lines showed through the gaps like a basket.
"""
import argparse
import collections
import struct
import sys

import numpy as np

from .display_list import ATTR_SIZE, CULLS, END, ENVELOPE, NRM, OUTSIDE_IN, POS, SHAPE_ANIM, XLU, Dat, attrs, read_vector, strips

GROUP_SIZE = 0x34
PARTICLE_JOINTS = (1 << 14) | (1 << 5)
ALWAYS_ON_TOP, NO_DEPTH_WRITE = 1 << 27, 1 << 29       # render mode
DEPTH_ON = 0x30                                        # PE flags: compare and update
ALPHA_ALWAYS = 7
CONST = 1
CAMERA = 170.      # how far the game's camera sits from the fighters, roughly
EYE = np.array((0., 15., CAMERA))
HARD, STRAIGHT = np.cos(np.radians(40)), np.cos(np.radians(3))
SHARP, SMOOTH = np.cos(np.radians(75)), np.cos(np.radians(15))     # an edge whatever its normals say; one normal across an edge
SEAM, SEAM_OFF = .9, .05      # the share of an open edge others have to lie along, and how far off its line they may be
STAGE_LINE = .11     # a tube's radius, in world units before distance
TUBE_SIDES = 3
S16 = 3              # GX component type
TRIANGLES, STRIP, FAN, QUADS = 0x90, 0x98, 0xa0, 0x80
BLOCK = 32


def local_matrix(d, j):
    (rx, ry, rz), scale, move = (struct.unpack_from('>3f', d.data, j + at) for at in (0x14, 0x20, 0x2c))
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    out = np.eye(4)
    out[:3, :3] = np.array(((cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz),
                            (cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz),
                            (-sy, sx * cy, cx * cy))) @ np.diag(scale)
    out[:3, 3] = move
    return out


def world_matrices(d, roots=()):
    """Every joint of every group, at rest, and of any other tree given (a stage item's model)."""
    head = dict(d.roots)['map_head']
    groups, count, out = d.ptr(head + 8), d.u32(head + 12), {}

    def walk(j, parent):
        while j is not None and j not in out:
            out[j] = parent @ local_matrix(d, j)
            walk(d.ptr(j + 8), out[j])
            j = d.ptr(j + 0xc)

    for g in range(count):
        walk(d.ptr(groups + GROUP_SIZE * g), np.eye(4))
    for root in roots:
        walk(root, np.eye(4))
    return out


def skinned_matrix(d, p, worlds):
    """What a skinned mesh's points go through: its first joint at rest, on that joint's inverse bind."""
    joint = d.ptr(d.ptr(d.ptr(p + 20)))
    bind = d.ptr(joint + 0x38)
    if bind is None:
        return worlds[joint]
    out = np.eye(4)
    out[:3] = np.array(struct.unpack_from('>12f', d.data, bind)).reshape(3, 4)
    return worlds[joint] @ out


def faces(op, n):
    if op == STRIP:
        return [(i + i % 2, i + 1 - i % 2, i + 2) for i in range(n - 2)]
    if op == TRIANGLES:
        return [(i, i + 1, i + 2) for i in range(0, n - 2, 3)]
    if op == FAN:
        return [(0, i + 1, i + 2) for i in range(n - 2)]
    if op == QUADS:
        return [t for i in range(0, n - 3, 4) for t in ((i, i + 1, i + 2), (i, i + 2, i + 3))]
    return []


def why_not(d, m, p, table):
    """Why a mesh gets no shell, or None."""
    mode, pe = d.u32(m + 4), d.ptr(m + 20)
    if mode & XLU:
        return 'translucent'
    if mode & (ALWAYS_ON_TOP | NO_DEPTH_WRITE):
        return 'outside depth'
    if pe is not None and d.data[pe] & DEPTH_ON != DEPTH_ON:
        return 'outside depth'
    if pe is not None and (d.data[pe + 9], d.data[pe + 11]) != (ALPHA_ALWAYS, ALPHA_ALWAYS):
        return 'cut-out'
    if d.u16(p + 12) & SHAPE_ANIM:
        return 'shape anim'
    pos = next((a for a in table if a['name'] == POS), None)
    if pos is None or pos['data'] is None:
        return 'no positions'
    return None


def places(d, worlds):
    """(joint, DObj) of every drawn mesh."""
    for j in worlds:
        if d.u32(j + 4) & PARTICLE_JOINTS or d.ptr(j + 0x10) is None:
            continue
        for o in d.chain(d.ptr(j + 0x10), 4):
            if d.ptr(o + 8) is not None and d.ptr(o + 12) is not None:
                yield j, o


def unit(v):
    return v / (np.linalg.norm(v) + 1e-9)


def distance(z):
    return (CAMERA + max(0., -z)) / CAMERA


def hard(sides):
    """Is an edge between these unit normals a line: open, or a real fold? A sheet drawn twice, back to back, is no fold."""
    sheets = []
    for n in sides:
        for sheet in sheets:
            if sheet[0] @ n > HARD:
                sheet.append(n)
                break
        else:
            sheets.append([n])
    return any(len(sheet) == 1 for sheet in sheets) or any(abs(a[0] @ b[0]) < HARD for a in sheets for b in sheets)


def crease(rows):
    """Is this edge a line? ``rows`` are its faces: (unit normal, mesh, a, a's matrix, b, b's, the model's normals at a and b)."""
    sides = [row[0] for row in rows]
    if not hard(sides):
        return False
    if len(rows) == 1 or any(row[6] is None for row in rows):
        return True
    first = rows[0]
    return (any(a @ b < SHARP for i, a in enumerate(sides) for b in sides[i + 1:])
            or any(first[6] @ row[6] < SMOOTH or first[7] @ row[7] < SMOOTH for row in rows[1:]))


def seams(edges):
    """The open edges that are seams: most of their length lies along other open edges whose faces look the same way."""
    keys = [key for key, rows in edges.items() if len(rows) == 1]
    if not keys:
        return set()
    a, b = (np.array([key[i] for key in keys]) for i in (0, 1))
    n = np.array([edges[key][0][0] for key in keys])
    out = set()
    for i, key in enumerate(keys):
        along = b[i] - a[i]
        length = np.linalg.norm(along)
        along /= length
        ends = [(q - a[i]) @ along for q in (a, b)]
        off = [np.linalg.norm(q - a[i] - t[:, None] * along, axis=1) for q, t in zip((a, b), ends)]
        lying = (off[0] < SEAM_OFF) & (off[1] < SEAM_OFF) & (n @ n[i] > HARD)
        lying[i] = False
        covered, at = 0., 0.
        for low, high in sorted(zip(np.minimum(*ends)[lying], np.maximum(*ends)[lying])):
            low, high = max(low, at), min(high, length)
            if high > low:
                covered, at = covered + high - low, high
        if covered >= SEAM * length:
            out.add(key)
    return out


def normal(d, a, index):
    """A normal as stored: only its direction matters."""
    return np.array(struct.unpack_from('>3' + 'BbHhf'[a['comp']], d.data, a['data'] + index * a['stride']), float)


def seen(a, b, sides):
    """Can the camera see a face on this edge?"""
    return any(n @ (EYE - (a + b) / 2) > 0 for n in sides)


def packed(points):
    """Points as GX fixed point, as fine as their range allows: the bytes and the fraction bits."""
    points = np.array(points)
    fraction = max(0, min(14, int(np.log2(32767 / max(np.abs(points).max(), 1e-3)))))
    return np.round(points * (1 << fraction)).astype('>i2').tobytes(), fraction


def set_positions(d, row, at, fraction):
    """Make an attribute table row read its positions from ``at``."""
    struct.pack_into('>I', d.data, row + 12, S16)
    d.data[row + 16] = fraction
    struct.pack_into('>H', d.data, row + 18, 6)
    d.point(row + 20, at)


def straighten(segments):
    """Runs of segments that go straight on, as one segment: only where a point joins exactly two of them."""
    out, ends = dict(enumerate(segments)), collections.defaultdict(set)

    def key(x):
        return tuple(np.round(x, 2))

    for i, (a, _, b, _) in out.items():
        ends[key(a)].add(i)
        ends[key(b)].add(i)
    for point, users in ends.items():
        if len(users) != 2:
            continue
        i, j = users
        a, ma, b, mb = out[i]
        c, mc, e, me = out[j]
        if key(a) == point:
            a, ma, b, mb = b, mb, a, ma
        if key(e) == point:
            c, mc, e, me = e, me, c, mc
        if unit(b - a) @ unit(e - c) > STRAIGHT:
            out[i] = a, ma, e, me
            del out[j]
            ends[key(e)].discard(j)
            ends[key(e)].add(i)
    return list(out.values())


def add_tubes(d, mesh, segments, line):
    """A PObj of black tubes along world-space (a, a's matrix index, b, b's) segments, on the mesh's joint or skin weights."""
    space, table = mesh['space'], mesh['table']
    inverse, move = np.linalg.inv(space[:3, :3]), space[:3, 3]
    matrix = next((a for a in table if a['name'] == 0), None)
    turns = [(np.cos(t), np.sin(t)) for t in np.arange(TUBE_SIDES) * 2 * np.pi / TUBE_SIDES]
    points, listing = [], bytearray()
    for a, ma, b, mb in segments:
        along = unit(b - a)
        towards = unit(EYE - a)
        across = unit(np.cross(along, towards))
        up = np.cross(across, along)
        r = line * distance(min(a[2], b[2]))
        start = len(points)
        for end in (a - along * r / 2, b + along * r / 2):
            points += [inverse @ (end + (up * x + across * y) * r - move) for x, y in turns]
        listing += struct.pack('>BH', STRIP, 2 * TUBE_SIDES + 2)
        for i in (*range(TUBE_SIDES), 0):
            for ring, m in ((0, ma), (1, mb)):
                if matrix is not None:
                    listing.append(m)
                listing += struct.pack('>H', start + ring * TUBE_SIDES + i)
    assert len(points) < 1 << 16
    listing += bytes(-len(listing) % BLOCK)
    pos = mesh['pos']
    rows = [bytes(d.data[a['at']:a['at'] + ATTR_SIZE]) for a in (matrix, pos) if a is not None]
    at = d.add(b''.join(rows) + struct.pack('>I', END) + bytes(ATTR_SIZE - 4), BLOCK)
    row = at + (len(rows) - 1) * ATTR_SIZE
    struct.pack_into('>I', d.data, row + 4, 3)
    raw, fraction = packed(points)
    set_positions(d, row, d.add(raw, BLOCK), fraction)
    tube = d.add(bytes(0x18), 4)
    d.point(tube + 8, at)
    struct.pack_into('>HH', d.data, tube + 12, d.u16(mesh['p'] + 12) & ~CULLS, len(listing) // BLOCK)
    d.point(tube + 16, d.add(bytes(listing), BLOCK))
    d.point(tube + 20, d.ptr(mesh['p'] + 20))
    return tube


def outline(source, target, line=0.14, tube=STAGE_LINE, behind=None, edge_visible=None, roots=(), depths=None, plain=None):
    """``roots``: joint trees outside the model groups to line too (a stage item's model). ``depths``: {mesh: world z}
    for meshes that are not drawn where they rest (a character on a flight path), for the line's width. ``plain``:
    which meshes get no lines, asked with the mesh and its world points."""
    d = Dat.read(source)
    worlds, stats = world_matrices(d, roots), collections.Counter()
    meshes, normals = [], collections.defaultdict(lambda: np.zeros(3))
    edges, depths = collections.defaultdict(list), depths or {}
    for j, o in places(d, worlds):
        for p in d.chain(d.ptr(o + 12), 4):
            table = attrs(d, p)
            reason = why_not(d, d.ptr(o + 8), p, table)
            if reason is not None:
                stats[reason] += 1
                continue
            flags = d.u16(p + 12)
            space = skinned_matrix(d, p, worlds) if flags & ENVELOPE else worlds[d.ptr(p + 20) or j]
            pos = next(a for a in table if a['name'] == POS)
            if plain is not None and plain(p, np.array([space[:3, :3] @ np.array(read_vector(d, pos, index[POS])) + space[:3, 3]
                                                        for _, rows in strips(d, p, table) for _, index in rows])):
                stats['plain'] += 1
                continue
            if behind is not None and max(space[2, :3] @ np.array(read_vector(d, pos, index[POS])) + space[2, 3] for _, rows in strips(d, p, table) for _, index in rows) < behind:
                stats['behind'] += 1
                continue
            mesh = dict(o=o, p=p, table=table, pos=pos, space=space, used=set(), depth=depths.get(p))
            meshes.append(mesh)
            mesh['shell'] = bool(flags & CULLS)
            flip = -1 if flags & OUTSIDE_IN else 1      # GX fronts are clockwise, so a front's cross product points inward
            said = next((a for a in table if a['name'] == NRM and a['data'] is not None and a['kind'] != 1), None)
            turn = np.linalg.inv(space[:3, :3]).T
            for op, rows in strips(d, p, table):
                indices = [index[POS] for _, index in rows]
                mesh['used'] |= set(indices)
                points = [space[:3, :3] @ np.array(read_vector(d, pos, i)) + space[:3, 3] for i in indices]
                own = [unit(turn @ normal(d, said, index[NRM])) for _, index in rows] if said is not None else None
                for a, b, c in faces(op, len(rows)):
                    n = -flip * np.cross(points[b] - points[a], points[c] - points[a])
                    if np.linalg.norm(n) < 1e-6:
                        continue
                    if not mesh['shell'] and (n @ (own[a] + own[b] + own[c]) < 0 if own is not None else n @ (EYE - points[a]) < 0):
                        n = -n
                    for x in (a, b, c):
                        if mesh['shell']:
                            normals[tuple(np.round(points[x], 2))] += n
                    for x, y in ((a, b), (b, c), (c, a)):
                        ends = sorted(((tuple(np.round(points[z], 2)), z) for z in (x, y)), key=lambda e: e[0])
                        if ends[0][0] != ends[1][0]:
                            m, l = (rows[z][1].get(0, 0) for z in (ends[0][1], ends[1][1]))
                            edges[ends[0][0], ends[1][0]].append((unit(n), len(meshes) - 1, points[ends[0][1]], m, points[ends[1][1]], l,
                                                                  *((own[ends[0][1]], own[ends[1][1]]) if own is not None else (None, None))))

    # the shells' positions, per source table and space. Meshes share big tables and use a slice each, so a table only
    # holds its slice, and its pointer stays where entry 0 would be: the display lists keep their indices
    tables, grown = {}, len(d.data)
    for mesh in meshes:
        if not mesh['shell']:
            continue
        pos, space = mesh['pos'], mesh['space']
        mesh['key'] = key = pos['data'], np.round(space, 3).tobytes()
        tables.setdefault(key, [pos, space, set(), mesh['depth']])[2] |= mesh['used']
    for key, (pos, space, used, depth) in tables.items():
        first = min(used) & ~15
        out = np.zeros((max(used) + 1 - first, 3))
        inverse = np.linalg.inv(space[:3, :3])
        for i in used:
            x = np.array(read_vector(d, pos, i))
            world = space[:3, :3] @ x + space[:3, 3]
            n = normals[tuple(np.round(world, 2))]
            thick = line * distance(world[2] if depth is None else depth)
            out[i - first] = x + inverse @ (unit(n) * thick)
        raw, fraction = packed(out)
        tables[key] = d.add(raw, BLOCK) - first * 6, fraction

    black = d.add(struct.pack('>12B2f', *(0, 0, 0, 255) * 3, 1., 1.), 4)
    mobj = d.add(bytes(0x18), 4)
    struct.pack_into('>I', d.data, mobj + 4, CONST)
    d.point(mobj + 12, black)

    shells = collections.defaultdict(list)
    for mesh in meshes:
        if not mesh['shell']:
            continue
        p, table, pos = mesh['p'], mesh['table'], mesh['pos']
        flags = d.u16(p + 12)
        rows = [bytes(d.data[a['at']:a['at'] + ATTR_SIZE]) for a in table]
        at = d.add(b''.join(rows) + struct.pack('>I', END) + bytes(ATTR_SIZE - 4), BLOCK)
        for i, a in enumerate(table):
            if a['data'] is not None:
                d.point(at + i * ATTR_SIZE + 20, a['data'])
        set_positions(d, at + table.index(pos) * ATTR_SIZE, *tables[mesh['key']])
        shell = d.add(bytes(0x18), 4)
        d.point(shell + 8, at)
        struct.pack_into('>HH', d.data, shell + 12, (flags & ~CULLS) | OUTSIDE_IN, d.u16(p + 14))
        d.point(shell + 16, d.ptr(p + 16))
        d.point(shell + 20, d.ptr(p + 20))
        struct.pack_into('>H', d.data, p + 12, flags & ~CULLS)      # both faces: a one-sided panel's back must hide the shell
        shells[mesh['o']].append(shell)
    segments, seam = collections.defaultdict(list), seams(edges)
    stats['seams'] = len(seam)
    for key, rows in edges.items():
        if key in seam:
            continue
        sides = [row[0] for row in rows]
        _, at, a, ma, b, mb = rows[0][:6]
        if crease(rows) and (edge_visible or seen)(a, b, sides):
            segments[at].append((a, ma, b, mb))
    for at, batch in segments.items():
        mesh = meshes[at]
        batch = straighten(batch)
        stats['lines'] += len(batch)
        shells[mesh['o']].append(add_tubes(d, mesh, batch, tube))
    stats['edges'] = len(edges)
    for o, chain in shells.items():
        for a, b in zip(chain, chain[1:]):
            d.point(a + 4, b)
        dobj = d.add(bytes(0x10), 4)
        d.point(dobj + 8, mobj)
        d.point(dobj + 12, chain[0])
        d.point(d.chain(o, 4)[-1] + 4, dobj)
    d.save(target)
    stats['shelled'] = sum(mesh['shell'] for mesh in meshes)
    stats['two-sided'] = len(meshes) - stats['shelled']
    return f'{dict(stats)}, {grown} -> {len(d.data)} bytes'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source')
    ap.add_argument('target')
    ap.add_argument('--line', type=float, default=0.14)
    ap.add_argument('--tube', type=float, default=STAGE_LINE)
    ap.add_argument('--behind', type=float)
    a = ap.parse_args()
    print(outline(a.source, a.target, a.line, a.tube, a.behind))


if __name__ == '__main__':
    main()
