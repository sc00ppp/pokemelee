"""HSD archive editing, adapted from the original authored costume converter."""
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

    def save(self, path):
        relocations = sorted(self.relocations)
        body = bytes(self.data) + struct.pack(f'>{len(relocations)}I', *relocations) + self.tail
        header = struct.pack('>5I', 0x20 + len(body), len(self.data), len(relocations), *self.counts)
        Path(path).write_bytes(header + self.raw[0x14:0x20] + body)


