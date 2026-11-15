"""GX display list reader shared by the approved outline operations."""
import struct
from .dat import Dat

POS, NRM, CLR0 = 9, 10, 11
ENVELOPE, SHAPE_ANIM = 0x2000, 0x1000
CULLS, OUTSIDE_IN = 0xc000, 0x4000       # the body keeps 0x8000; the opposite flag shows the shell's inside
FROM_VERTEX, COLOUR_BITS = 2, 0b1111     # render mode: colour source and lights
XLU = 1 << 30
ATTR_SIZE, END = 24, 0xff
COLOUR_BYTES = (2, 3, 4, 2, 3, 4)      # by GX colour format, for colours written straight in a display list
CANCELLED = .25      # a point's normals add up to less than this share of their length: two layers, back to back


def attrs(d, p):
    at, out = d.ptr(p + 8), []
    while d.u32(at) != END:
        out.append(dict(at=at, name=d.u32(at), kind=d.u32(at + 4), comp=d.u32(at + 12), scale=d.data[at + 16],
                        stride=d.u16(at + 18), data=d.ptr(at + 20)))
        at += ATTR_SIZE
    return out


def read_vector(d, a, index):
    at = a['data'] + index * a['stride']
    if a['comp'] == 4:
        return struct.unpack_from('>3f', d.data, at)
    code = {1: 'b', 3: 'h'}[a['comp']]
    return tuple(v / (1 << a['scale']) for v in struct.unpack_from(f'>3{code}', d.data, at))


def attr_size(a):
    """An attribute's bytes in a display list."""
    if a['kind'] != 1:
        return 2 if a['kind'] == 3 else 1
    if a['name'] == CLR0:
        return COLOUR_BYTES[a['comp']]
    if a['name'] <= 8:
        return 1
    raise SystemExit(f'direct attribute {a["name"]}')


def strips(d, p, table):
    """The display list as (primitive, [vertex as raw bytes per attribute], {attribute: index})."""
    at, end = d.ptr(p + 16), d.ptr(p + 16) + d.u16(p + 14) * 32
    while at < end and d.data[at]:
        op, n = d.data[at], struct.unpack_from('>H', d.data, at + 1)[0]
        at += 3
        rows = []
        for _ in range(n):
            raw, index = [], {}
            for a in table:
                size = attr_size(a)
                raw.append(bytes(d.data[at:at + size]))
                index[a['name']] = int.from_bytes(raw[-1], 'big')
                at += size
            rows.append((raw, index))
        yield op, rows


