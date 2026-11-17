"""HSD archive editing, adapted from the original authored costume converter."""
import bisect
import itertools
from pathlib import Path
import struct

class Dat:
    """A .dat file read for its data block, relocation table (the data's pointer fields) and root table."""

    def __init__(self, raw):
        self.raw = bytes(raw)
        _, data_size, relocations, roots, references = struct.unpack_from('>5I', self.raw, 0)
        self.data = bytearray(self.raw[0x20:0x20 + data_size])
        table = 0x20 + data_size
        self.relocations = set(struct.unpack_from(f'>{relocations}I', self.raw, table))
        self.tail = self.raw[table + relocations * 4:]       # the root and reference tables and their names
        self.counts = (roots, references)
        strings = (roots + references) * 8
        self.roots = []
        for i in range(roots):
            offset, name = struct.unpack_from('>2I', self.tail, i * 8)
            end = self.tail.index(b'\0', strings + name)
            self.roots.append((self.tail[strings + name:end].decode('ascii'), offset))

    @classmethod
    def read(cls, path):
        return cls(Path(path).read_bytes())

    def u32(self, at):
        return struct.unpack_from('>I', self.data, at)[0]

    def u16(self, at):
        return struct.unpack_from('>H', self.data, at)[0]

    def ptr(self, at):
        return self.u32(at) if at in self.relocations else None

    def bytes_at(self, at, n):
        return list(self.data[at:at + n])

    def root(self, name):
        return next((offset for n, offset in self.roots if n == name), None)

    def chain(self, head, next_at):
        out, seen = [], set()
        while head is not None:
            if head in seen:
                raise ValueError(f'a looped chain at {head:#x}')
            seen.add(head)
            out.append(head)
            head = self.ptr(head + next_at)
        return out

    def add(self, payload, align=4):
        """Append ``payload`` to the data block; its offset."""
        self.data.extend(b'\0' * (-len(self.data) % align))
        at = len(self.data)
        self.data.extend(payload)
        return at

    def point(self, at, target):
        """Make the field at ``at`` point to ``target`` (an offset in the data block), or to nothing."""
        struct.pack_into('>I', self.data, at, target or 0)
        if target is None:
            self.relocations.discard(at)
        else:
            self.relocations.add(at)

    def drop(self, ranges, virtual=None):
        """Take ``ranges`` [(start, end)] out of the data block and move every pointer, relocation and root with what
        stays. Only whole 32-byte blocks go, so everything after them keeps its alignment; a field inside a range goes
        with it even where its block stays. ``virtual``: {field: the offset its value was reckoned from}, for a pointer
        kept where entry 0 of a slice would be, which need not be data at all. A pointer left into a dropped block is an
        error: something still reads it."""
        dead = []
        for a, b in sorted(ranges):
            if dead and a <= dead[-1][1]:
                dead[-1][1] = max(dead[-1][1], b)
            elif b > a:
                dead.append([a, b])
        cuts = [(-(-a // 32) * 32, b // 32 * 32) for a, b in dead]
        cuts = [(a, b) for a, b in cuts if b > a]
        starts, before = [a for a, _ in cuts], list(itertools.accumulate((b - a for a, b in cuts), initial=0))
        dead_starts, virtual = [a for a, _ in dead], virtual or {}

        def move(x):
            i = bisect.bisect_right(starts, x)
            if i and x < cuts[i - 1][1]:
                raise ValueError(f'a pointer into dropped data at {x:#x}')
            return x - before[i]

        relocations = set()
        for at in sorted(self.relocations):
            i = bisect.bisect_right(dead_starts, at)
            if i and at < dead[i - 1][1]:
                struct.pack_into('>I', self.data, at, 0)
                continue
            value = self.u32(at)
            if at in virtual:
                value = move(virtual[at]) + value - virtual[at]
            else:
                value = move(value)
            struct.pack_into('>I', self.data, at, value & 0xFFFFFFFF)
            relocations.add(move(at))
        kept, at = bytearray(), 0
        for a, b in cuts:
            kept += self.data[at:a]
            at = b
        self.data, self.relocations = kept + self.data[at:], relocations
        tail = bytearray(self.tail)
        for i in range(sum(self.counts)):
            struct.pack_into('>I', tail, i * 8, move(struct.unpack_from('>I', tail, i * 8)[0]))
        self.tail = bytes(tail)
        self.roots = [(name, move(offset)) for name, offset in self.roots]
        return before[-1]

    def save(self, path):
        relocations = sorted(self.relocations)
        body = bytes(self.data) + struct.pack(f'>{len(relocations)}I', *relocations) + self.tail
        header = struct.pack('>5I', 0x20 + len(body), len(self.data), len(relocations), *self.counts)
        Path(path).write_bytes(header + self.raw[0x14:0x20] + body)


