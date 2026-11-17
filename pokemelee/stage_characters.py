"""The background characters of a built stage: the people and Pokemon standing or flying behind the fight.

A character is a model with a skeleton: a branch straight under a model group's root that holds a skinned mesh. The
scenery around it never has one (a map's own skinned props are baked rigid when the stage is built). A stage item's
model counts too where a recipe hangs a Colosseum model in one (the garden's Castform, in the Shy Guy's place).

Three things follow from being one:

light   A Colosseum character's materials ask for a constant colour AND the lights. Melee reads that as constant
        (HSD_SetupChannelMode lights a material only when it asks for nothing else), so the character is drawn with
        no shading at all: its plain colour swatches at full brightness, a flat glowing cut-out. Melee's own stage
        props carry their shading in their vertex colours, and so does the character from here on: worked out once,
        from the sky and a sun high on the left, and stored per point. Not in AniMelee, whose style is the flat colour.
edges   AniMelee's stage lines draw every fold of a mesh, which on a small far character is a black scribble over its
        face and clothes: it keeps its outline and loses the lines inside it (anime_stage's edge_visible).
depth   AniMelee's outline is as wide as its distance asks. A character on a flight path rests at the path's origin,
        in the middle of the stage, and flies far behind it: its outline goes by where the path is.
"""
import bisect
import collections
import struct

import numpy as np

from . import anime_stage
from .display_list import ATTR_SIZE, CLR0, END, ENVELOPE, NRM, POS, attrs, read_vector, strips
from .dat import Dat

DIFFUSE, SPECULAR, COLOUR_SOURCE, FROM_VERTEX = 1 << 2, 1 << 3, 0b11, 0b10     # render mode
SKELETON, SKELETON_ROOT = 1, 2                                                 # joint flags
INDEX8, RGB, RGB8 = 2, 0, 1
BLOCK = 32
AMBIENT, SKY = .5, .22                          # everywhere, and more the further a face looks up
SUNS = ((np.array((-.45, .75, .5)), .33),       # high on the left, in front
        (np.array((.6, -.1, .8)), .1))          # a weak fill from the right
UP = np.array((0., 1., 0.))
ITEM_MODEL = (0, 4, 0x10, 0)                    # from itemdata: its table, the Shy Guy's article, its model, the root joint


def item_roots(d, spec):
    """The stage item models a recipe puts a character in: the Shy Guy's, where native/ys hangs the garden's Castform."""
    if 'heiho' not in spec:
        return ()
    at = d.root('itemdata')
    for field in ITEM_MODEL:
        at = d.ptr(at + field) if at is not None else None
    if at is None:
        raise ValueError('The stage has no Shy Guy item model')
    return (at,)


def tops(d, roots=()):
    """The joints straight under each model group's root, and under any other root given."""
    head = dict(d.roots)['map_head']
    groups, count = d.ptr(head + 8), d.u32(head + 12)
    for root in [d.ptr(groups + anime_stage.GROUP_SIZE * g) for g in range(count)] + list(roots):
        top = d.ptr(root + 8) if root is not None else None
        while top is not None:
            yield top
            top = d.ptr(top + 0xc)


def branch(d, j, up=None):
    """A joint and everything under it, in order (and each one's parent, into ``up``)."""
    out = [j]
    child = d.ptr(j + 8)
    while child is not None:
        if up is not None:
            up[child] = j
        out += branch(d, child, up)
        child = d.ptr(child + 0xc)
    return out


def meshes(d, joints):
    """(joint, DObj, PObj) of every mesh on these joints."""
    for j in joints:
        if d.u32(j + 4) & anime_stage.PARTICLE_JOINTS or d.ptr(j + 0x10) is None:
            continue
        for o in d.chain(d.ptr(j + 0x10), 4):
            if d.ptr(o + 8) is not None and d.ptr(o + 12) is not None:
                for p in d.chain(d.ptr(o + 12), 4):
                    yield j, o, p


def characters(d, roots=(), up=None):
    """Each character's joints."""
    return [joints for joints in (branch(d, top, up) for top in tops(d, roots))
            if any(d.u16(p + 12) & ENVELOPE for _, _, p in meshes(d, joints))]


def space(d, j, p, worlds):
    """A mesh's rest matrix, as the outline reads it."""
    return anime_stage.skinned_matrix(d, p, worlds) if d.u16(p + 12) & ENVELOPE else worlds[d.ptr(p + 20) or j]


def rest_matrices(d, j, p, worlds, up):
    """The matrix each vertex of a mesh goes through at rest, by its matrix index, as Melee builds them (pobj.c
    SetupEnvelopeModelMtx and its two simpler cases). One matrix for a whole skinned mesh is not it: a vertex bound to
    one bone is stored in that bone's space unless the mesh hangs outside the skeleton's root."""
    if not d.u16(p + 12) & ENVELOPE:
        other = d.ptr(p + 20)
        return [worlds[j]] + ([worlds[other]] if other is not None else [])

    def bind(joint):
        out = np.eye(4)
        if d.ptr(joint + 0x38) is not None:
            out[:3] = np.array(struct.unpack_from('>12f', d.data, d.ptr(joint + 0x38))).reshape(3, 4)
        return out

    right = None
    if not d.u32(j + 4) & SKELETON_ROOT:
        x = j
        while x in up and not d.u32(x + 4) & (SKELETON | SKELETON_ROOT):
            x = up[x]
        if x == j:
            right = np.linalg.inv(bind(j))
        elif d.u32(x + 4) & SKELETON_ROOT:
            right = np.linalg.inv(worlds[x]) @ worlds[j]
        else:
            right = np.linalg.inv(worlds[x] @ bind(x)) @ worlds[j]
    out, at = [], d.ptr(p + 20)
    while d.ptr(at) is not None:
        weights, e = [], d.ptr(at)
        while d.ptr(e) is not None:
            weights.append((d.ptr(e), struct.unpack_from('>f', d.data, e + 4)[0]))
            e += 8
        if weights[0][1] >= 1 - 1e-6:
            m = worlds[weights[0][0]] @ bind(weights[0][0]) if right is not None else worlds[weights[0][0]]
        else:
            m = sum(w * (worlds[joint] @ bind(joint)) for joint, w in weights)
        out.append(m @ right if right is not None else m)
        at += 4
    return out


def edge_filter(path, roots=()):
    """anime_stage's edge_visible for a flattened stage: no line between two points of one character."""
    d = Dat.read(path)
    worlds = anime_stage.world_matrices(d, roots)
    own = set()
    for joints in characters(d, roots):
        for j, _, p in meshes(d, joints):
            table = attrs(d, p)
            pos = next((a for a in table if a['name'] == POS), None)
            if pos is None or pos['data'] is None:
                continue
            m = space(d, j, p, worlds)
            for _, rows in strips(d, p, table):
                for _, index in rows:
                    own.add(tuple(np.round(m[:3, :3] @ np.array(read_vector(d, pos, index[POS])) + m[:3, 3], 2)))
    return lambda a, b, sides: not (tuple(np.round(a, 2)) in own and tuple(np.round(b, 2)) in own) and anime_stage.seen(a, b, sides)


def flight_depths(path, spec):
    """{mesh: the world z it is really drawn at} for the characters a recipe sends along a flight path."""
    d = Dat.read(path)
    cast = characters(d)
    donors = [x for x in spec.get('donors', ()) if 'place' in x and not x['file'].endswith('.rdat')]
    if len(cast) != len(donors):
        raise ValueError(f'The stage holds {len(cast)} characters and its recipe places {len(donors)}')
    out = {}
    for joints, donor in zip(cast, donors):
        if 'path' in donor:
            z = float(np.mean([point[2] for point in donor['path']['points']]))
            out.update({p: z for _, _, p in meshes(d, joints)})
    return out


def plain_filter(path, spec, roots=()):
    """anime_stage's plain for a flattened stage: the scenery standing wholly inside a box its recipe calls foliage."""
    boxes = [np.array(box, float) for box in spec.get('foliage', ())]
    if not boxes:
        return None
    d = Dat.read(path)
    cast = {p for joints in characters(d, roots) for _, _, p in meshes(d, joints)}
    return lambda p, points: p not in cast and any((points >= box[:3]).all() and (points <= box[3:]).all() for box in boxes)


def shade(normal):
    """How bright a face with this unit normal is. Mostly the sky, so a character that turns round or flies a loop
    never shows a black side; the sun only models it."""
    sky = SKY * (.5 + .5 * float(normal @ UP))
    return min(1., AMBIENT + sky + sum(k * max(0., float(normal @ sun / np.linalg.norm(sun))) for sun, k in SUNS))


class Room:
    """Where the rewritten lists go: the blocks the old ones leave free first, then the end of the file. A stage is
    loaded whole beside four fighters, so what a rewrite leaves behind is memory the match does not get back."""

    def __init__(self, d):
        self.d, self.holes = d, []
        self.targets = collections.Counter(d.u32(at) for at in d.relocations)
        self.sorted = sorted(self.targets)

    def free(self, at, size):
        """Give up a block, unless something else still points at or into it."""
        i = bisect.bisect_right(self.sorted, at)
        if self.targets[at] != 1 or at % BLOCK or (i < len(self.sorted) and self.sorted[i] < at + size):
            return
        self.d.data[at:at + size] = bytes(size)
        self.holes.append([at, size])
        self.holes.sort()
        merged = [self.holes[0]]
        for hole in self.holes[1:]:
            if merged[-1][0] + merged[-1][1] == hole[0]:
                merged[-1][1] += hole[1]
            else:
                merged.append(hole)
        self.holes = merged

    def put(self, payload):
        payload += bytes(-len(payload) % BLOCK)
        fits = [hole for hole in self.holes if hole[1] >= len(payload)]
        if not fits:
            return self.d.add(payload, BLOCK)
        hole = min(fits, key=lambda h: h[1])
        at = hole[0]
        self.d.data[at:at + len(payload)] = payload
        hole[0], hole[1] = at + len(payload), hole[1] - len(payload)
        self.holes = [h for h in self.holes if h[1]]
        return at


def light(source, target, roots=()):
    """Bake every character's shading into vertex colours; what was done, or None when the stage has no character
    (the file is then left alone)."""
    d, up = Dat.read(source), {}
    cast = characters(d, roots, up)
    if not cast:
        return None
    worlds, stats = anime_stage.world_matrices(d, roots), collections.Counter()
    jobs, materials, seen = [], set(), set()
    for joints in cast:
        stats['characters'] += 1
        for j, o, p in meshes(d, joints):
            m = d.ptr(o + 8)
            if p in seen or not d.u32(m + 4) & DIFFUSE and m not in materials:      # twice in the file, or drawn unlit as it is
                continue
            seen.add(p)
            table = attrs(d, p)
            names = [a['name'] for a in table]
            normal = next((a for a in table if a['name'] == NRM), None)
            if normal is None or normal['data'] is None or CLR0 in names or any(a['kind'] == 1 and a['name'] > 8 for a in table):
                stats['left lit'] += 1
                continue
            turns = [np.linalg.inv(rest[:3, :3]).T for rest in rest_matrices(d, j, p, worlds, up)]      # normals go through the inverse transpose
            tint = np.array(struct.unpack_from('>3B', d.data, d.ptr(m + 12) + 4)) / 255.               # the material's diffuse
            shades, lists = {}, list(strips(d, p, table))
            for _, rows in lists:
                for _, index in rows:
                    key = index[NRM], index.get(0, 0) // 3
                    if key not in shades:
                        v = turns[key[1]] @ anime_stage.normal(d, normal, key[0])
                        length = np.linalg.norm(v)
                        rgb = tint * (shade(v / length) if length > 1e-9 else AMBIENT)
                        shades[key] = tuple(int(round(c * 255)) for c in rgb)
            jobs.append((p, table, names, lists, shades))
            materials.add(m)
    # one colour table for the stage while its colours fit a byte's index, and the next one after that
    palettes, placed = [{}], []
    for job in jobs:
        need = set(job[4].values())
        palette = next((q for q in palettes if len(need | set(q)) <= 256), None)
        if palette is None:
            palette = {}
            palettes.append(palette)
        for colour in sorted(need):
            palette.setdefault(colour, len(palette))
        job[4].update({key: palette[colour] for key, colour in job[4].items()})
        placed.append(job + (palettes.index(palette),))
    jobs, room = placed, Room(d)
    for p, *_ in jobs:
        room.free(d.ptr(p + 16), d.u16(p + 14) * BLOCK)
    for p, table, names, lists, shades, _ in jobs:       # the lists first: they are what the freed blocks can hold
        at = next((i for i, n in enumerate(names) if n > CLR0), len(names))
        listing = bytearray()
        for op, rows in lists:
            listing += struct.pack('>BH', op, len(rows))
            for raw, index in rows:
                listing += b''.join(raw[:at]) + bytes((shades[index[NRM], index.get(0, 0) // 3],)) + b''.join(raw[at:])
        struct.pack_into('>H', d.data, p + 14, (len(listing) + BLOCK - 1) // BLOCK)
        d.point(p + 16, room.put(bytes(listing)))
    colours = [room.put(b''.join(bytes(c) for c in palette)) for palette in palettes]
    tables = {}
    for p, table, names, _, _, palette in jobs:
        key = d.ptr(p + 8), palette
        if key not in tables:       # meshes that shared an attribute table still share one
            at = next((i for i, n in enumerate(names) if n > CLR0), len(names))
            row = struct.pack('>4I', CLR0, INDEX8, RGB, RGB8) + struct.pack('>BBH', 0, 0, 3) + bytes(4)
            old = [bytes(d.data[a['at']:a['at'] + ATTR_SIZE]) for a in table]
            new = tables[key] = d.add(b''.join(old[:at] + [row] + old[at:]) + struct.pack('>I', END) + bytes(ATTR_SIZE - 4), 4)
            for i, a in enumerate(table[:at] + [None] + table[at:]):
                if a is None:
                    d.point(new + i * ATTR_SIZE + 20, colours[palette])
                elif a['data'] is not None:
                    d.point(new + i * ATTR_SIZE + 20, a['data'])
        d.point(p + 8, tables[key])
    for m in materials:
        struct.pack_into('>I', d.data, m + 4, d.u32(m + 4) & ~(DIFFUSE | SPECULAR | COLOUR_SOURCE) | FROM_VERTEX)
    d.save(target)
    stats.update(meshes=len(jobs), materials=len(materials), tables=len(tables), palettes=len(palettes))
    return dict(stats)
