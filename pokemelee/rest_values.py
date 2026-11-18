"""Each colour slot carries the joint rest values of the vanilla colour it stands for online.

Online, each Slippi client loads the costume file its own disc has for the colour a player picked. A fighter's vanilla
colours share one joint tree, but some colours have their own rest values (Captain Falcon's colours 1-5 at the arms and
hands). A channel an animation leaves unkeyed sits at the costume's rest value, and Falcon's hands are ECB points and
carry hitboxes, so a costume whose slot k has colour 0's tree is simulated differently on a vanilla opponent's client:
Slippi's "Desync Risk", or a hard desync when a landing comes a frame apart. The fix is that slot k of every fighter
carries vanilla colour k's rest values bit for bit (recipes/rest-values.json names the colours); in Teams, the team
indices must also land on vanilla's team colour (``team_indices``, checked at assembly).

``fit`` copies the donor's rotation, scale and translation (JObj +0x14..+0x37) into every joint and keeps the model's
rest pose where it was: for each joint whose world matrix changed, C = inverse(new world) . old world, its inverse bind
becomes C . IB, and every vertex bound to it alone (stored in the joint's own space: a one-joint envelope, or a mesh the
joint owns) is carried by C, its normal by C's inverse transpose. Flags, envelopes and everything else stay as they are.

Plain Python float arithmetic in a fixed order (+, -, *, /, sqrt and round only; sine and cosine by a fixed series), so
every machine writes the same bytes.
"""
import math
import struct

from .catalog import load
from .display_list import ENVELOPE, NRM, POS, SHAPE_ANIM, attrs, strips
from .fighter_tables import joint_dobjs
from .mesh import costume_root, tree

SRT = slice(0x14, 0x38)                 # rotation, scale, translation: nine floats
SKELETON_ROOT, CLASSICAL_SCALING = 1 << 1, 1 << 3
BILLBOARDS, USE_QUATERNION = (0x7 << 9) | (1 << 13), 1 << 17
SINGLE = 1.0 - 2.0 ** -23               # HSD: an envelope's first weight >= 1.0f - FLT_EPSILON draws with that joint alone
PNMTXIDX = 0
INTS = {0: ('B', 0, 255), 1: ('b', -128, 127), 2: ('H', 0, 65535), 3: ('h', -32768, 32767)}


def donors(fighter, mon=None):
    """The vanilla costume files whose rest values the slots of ``fighter`` carry, slot 0 first; () for a fighter the
    recipe does not name, or for ``mon`` when it is an m-ex clone a vanilla client cannot load."""
    spec = load('rest-values.json')
    if mon in spec['clones']:
        return ()
    return tuple(spec['fighters'].get(fighter, ()))


def team_indices(fighter):
    """Vanilla's red/blue/green costume index for ``fighter`` where this disc must match it ({} when unchecked)."""
    return dict(load('rest-values.json')['teams'].get(fighter, {}))


def donor_for(files, slot):
    """The vanilla file for a slot. A slot past vanilla's colours is one a vanilla client draws as colour 0 (the game
    turns a colour it has no costume for into 0), so it takes colour 0's values."""
    return files[slot] if slot < len(files) else files[0]


# ---- fixed-order math ---------------------------------------------------------------------------------------------------
PIO2_HI, PIO2_LO = 1.57079632673412561417e+00, 6.07710050650619224932e-11    # pi/2 split (fdlibm's pio2_1, pio2_1t)
SIN = [(-1) ** n / math.factorial(2 * n + 1) for n in range(11)]
COS = [(-1) ** n / math.factorial(2 * n) for n in range(11)]


def sincos(x):
    """(sin x, cos x) by Cody-Waite reduction and Taylor series, the same bits on every machine."""
    k = round(x / (PIO2_HI + PIO2_LO))
    r = (x - k * PIO2_HI) - k * PIO2_LO
    r2 = r * r
    s = c = 0.0
    for a, b in zip(reversed(SIN), reversed(COS)):
        s = s * r2 + a
        c = c * r2 + b
    s *= r
    return ((s, c), (c, -s), (-s, -c), (-c, s))[k % 4]


def srt_matrix(values):
    """HSD_MtxSRT with classical scaling: T . Rz . Ry . Rx . S, as three rows of four."""
    rx, ry, rz, sx, sy, sz, tx, ty, tz = values
    sinx, cosx = sincos(rx)
    siny, cosy = sincos(ry)
    sinz, cosz = sincos(rz)
    return [[sx * (cosy * cosz), sy * (sinx * siny * cosz - cosx * sinz), sz * (cosx * siny * cosz + sinx * sinz), tx],
            [sx * (cosy * sinz), sy * (sinx * siny * sinz + cosx * cosz), sz * (cosx * siny * sinz - sinx * cosz), ty],
            [sx * -siny, sy * (sinx * cosy), sz * (cosx * cosy), tz]]


def compose(a, b):
    """a . b for 3x4 affines."""
    return [[a[i][0] * b[0][k] + a[i][1] * b[1][k] + a[i][2] * b[2][k] + (a[i][3] if k == 3 else 0.0)
             for k in range(4)] for i in range(3)]


def invert(m):
    """Inverse of a 3x4 affine, by cofactors."""
    a, b, c, tx = m[0]
    d, e, f, ty = m[1]
    g, h, i, tz = m[2]
    A, B, C = e * i - f * h, -(d * i - f * g), d * h - e * g
    det = a * A + b * B + c * C
    if det == 0:
        raise ValueError('a joint matrix cannot be inverted')
    r = [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
         [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
         [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]]
    return [[r[k][0], r[k][1], r[k][2], -(r[k][0] * tx + r[k][1] * ty + r[k][2] * tz)] for k in range(3)]


def point(m, p):
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3))


def normal(m, n):
    """A normal through the affine ``m``: by the inverse transpose of its linear part, keeping the normal's length."""
    q = invert(m)
    out = tuple(q[0][i] * n[0] + q[1][i] * n[1] + q[2][i] * n[2] for i in range(3))
    before, after = math.sqrt(sum(x * x for x in n)), math.sqrt(sum(x * x for x in out))
    return out if after == 0 else tuple(x * (before / after) for x in out)


def f32(x):
    return struct.unpack('>f', struct.pack('>f', x))[0]


# ---- the joint tree ---------------------------------------------------------------------------------------------------------
def skeleton(d):
    """[(offset, parent #, flags, SRT bytes)] of a costume's joint tree, depth first as the game walks it."""
    js = tree(d, costume_root(d))
    index = {j: i for i, j in enumerate(js)}
    parent = [-1] * len(js)
    for j in js:
        c = d.ptr(j + 8) if not d.u32(j + 4) & (1 << 12) else None
        while c is not None:
            parent[index[c]] = index[j]
            c = d.ptr(c + 0x0C)
    return [(j, parent[i], d.u32(j + 4), bytes(d.data[j + SRT.start:j + SRT.stop])) for i, j in enumerate(js)]


def worlds(rows, srt):
    """Each joint's rest world matrix, from ``srt`` (bytes per joint) and the tree in ``rows``."""
    out = []
    for (_, parent, _, _), raw in zip(rows, srt):
        local = srt_matrix(struct.unpack('>9f', raw))
        out.append(local if parent < 0 else compose(out[parent], local))
    return out


# ---- vertex arrays ----------------------------------------------------------------------------------------------------------
def read_entry(d, a, index):
    at = a['data'] + index * a['stride']
    if a['comp'] == 4:
        return at, struct.unpack_from('>3f', d.data, at)
    if a['comp'] not in INTS:
        raise ValueError(f'unknown vertex component type {a["comp"]}')
    q = 1 << a['scale']
    return at, tuple(v / q for v in struct.unpack_from(f'>3{INTS[a["comp"]][0]}', d.data, at))


def write_entry(data, a, at, value):
    """Store a position or normal as its array stores them (rounded to the nearest step). A normal's component may sit
    at the format's end (1.0 is one step past what 16 bits with 15 fraction bits hold); a position may not."""
    if a['comp'] == 4:
        struct.pack_into('>3f', data, at, *value)
        return
    code, lo, hi = INTS[a['comp']]
    q = 1 << a['scale']
    raw = [int(round(v * q)) for v in value]
    if a['name'] == NRM:
        raw = [min(hi, max(lo, r)) for r in raw]
    elif any(not lo <= r <= hi for r in raw):
        raise ValueError('a moved vertex no longer fits its stored format')
    struct.pack_into(f'>3{code}', data, at, *raw)


def bindings(d, rows):
    """{(attribute, entry offset): (attribute row, index, bindings)} for every position and normal entry a display list
    uses. A binding is the joint # the entry is stored in the space of (a one-joint envelope, or a mesh the joint owns),
    'blend' for a weighted envelope (model space, drawn through the inverse binds), or ('unsupported', why, joint #) for a
    mesh this fit does not model, which may not move. An entry used under two bindings is an error only where it moves."""
    index = {j: i for i, (j, *_) in enumerate(rows)}
    out = {}
    for owner, (j, _, owner_flags, _) in enumerate(rows):
        for dobj in joint_dobjs(d, j):
            p = d.ptr(dobj + 0x0C)
            while p is not None:
                flags = d.u16(p + 0x0C)
                table = attrs(d, p)
                envs = None
                if flags & ENVELOPE and not owner_flags & SKELETON_ROOT:
                    envs = [('unsupported', 'an envelope mesh under a joint that is not a skeleton root', None)]
                elif flags & ENVELOPE:
                    envs, arr = [], d.ptr(p + 0x14)
                    while arr is not None and d.ptr(arr) is not None:
                        first = d.ptr(arr)
                        envs.append(index[d.ptr(first)] if struct.unpack_from('>f', d.data, first + 4)[0] >= SINGLE
                                    else 'blend')
                        arr += 4
                elif flags & SHAPE_ANIM or d.ptr(p + 0x14) is not None:
                    kind = 'a shape-animated mesh' if flags & SHAPE_ANIM else 'a shared-vertex mesh'
                    envs = [('unsupported', kind, owner)]
                for _, batch in strips(d, p, table):
                    for _, idx in batch:
                        bind = owner if envs is None else envs[0 if len(envs) == 1 else idx.get(PNMTXIDX, 0) // 3]
                        for a in table:
                            if a['name'] in (POS, NRM) and a['data'] is not None:
                                at = a['data'] + idx[a['name']] * a['stride']
                                out.setdefault((a['name'], at), (a, idx[a['name']], set()))[2].add(bind)
                p = d.ptr(p + 4)
    return out


# ---- the fit ----------------------------------------------------------------------------------------------------------------
def fit(costume, donor):
    """``costume`` (file bytes) with every joint's rest values taken from ``donor`` (a costume of the same skeleton), the
    rest pose kept in place. Returns (bytes, summary)."""
    from .dat import Dat
    d, v = Dat(costume), Dat(donor)
    rows, theirs = skeleton(d), skeleton(v)
    if [r[1] for r in rows] != [r[1] for r in theirs]:
        raise ValueError('the donor costume has another joint tree')
    old, new = [r[3] for r in rows], [r[3] for r in theirs]
    changed = []
    for i, (_, parent, _, _) in enumerate(rows):
        changed.append(old[i] != new[i] or (parent >= 0 and changed[parent]))
    data = bytearray(d.data)
    summary = {'joints': len(rows), 'rest_values_copied': sum(a != b for a, b in zip(old, new)),
               'joints_moved': sum(changed), 'inverse_binds': 0, 'positions': 0, 'normals': 0}
    if not any(changed):
        return bytes(costume), summary
    for (j, parent, flags, _), moved in zip(rows, changed):
        if flags & USE_QUATERNION or (moved and flags & BILLBOARDS):
            raise ValueError('a joint whose matrix is not its rest values alone')
    if any(not flags & CLASSICAL_SCALING for _, _, flags, _ in rows) and any(
            struct.unpack('>3f', raw[12:24]) != (1.0, 1.0, 1.0) for raw in old + new):
        raise ValueError('scale compensation (no classical scaling) is not modelled')
    before, after = worlds(rows, old), worlds(rows, new)
    carry = {i: compose(invert(after[i]), before[i]) for i, moved in enumerate(changed) if moved}

    for (j, *_), _, raw in zip(rows, old, new):
        data[j + SRT.start:j + SRT.stop] = raw
    seen = {}
    for i, c in carry.items():
        j = rows[i][0]
        ib = d.ptr(j + 0x38)
        if ib is None:
            continue
        m = struct.unpack_from('>12f', d.data, ib)
        value = [f32(x) for row in compose(c, [list(m[0:4]), list(m[4:8]), list(m[8:12])]) for x in row]
        if seen.setdefault(ib, value) != value:
            raise ValueError('two joints share one inverse bind')
        struct.pack_into('>12f', data, ib, *value)
        summary['inverse_binds'] += 1
    for (name, at), (a, index, binds) in bindings(d, rows).items():
        moving = [b for b in binds if b in carry or (isinstance(b, tuple) and (b[2] is None or b[2] in carry))]
        if not moving:
            continue
        if isinstance(moving[0], tuple):
            raise ValueError(f'{moving[0][1]} would have to follow a joint whose rest values changed')
        if len(binds) > 1:
            raise ValueError(f'a vertex entry at {at:#x} is drawn under several joints and cannot follow one')
        if d.u32(a['at'] + 8) != (1 if name == POS else 0):
            raise ValueError('only XYZ positions and plain normals can follow a joint')
        _, value = read_entry(d, a, index)
        c = carry[moving[0]]
        write_entry(data, a, at, point(c, value) if name == POS else normal(c, value))
        summary['positions' if name == POS else 'normals'] += 1
    out = bytearray(costume)
    out[0x20:0x20 + len(data)] = data
    return bytes(out), summary
