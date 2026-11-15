"""Colosseum FSYS/LZSS decoding, adapted from the existing stage builder."""
import struct

from .disc import safe_name

TYPES = {0x02: "rdat", 0x04: "dat", 0x06: "ccd", 0x0E: "scd", 0x1C: "rel"}
MAX_ENTRY = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024


def lzss(source, size):
    if not 0 <= size <= MAX_ENTRY:
        raise ValueError("Invalid LZSS output size")
    ring, cursor, output, i, flags = bytearray(4096), 4078, bytearray(), 0, 0
    while len(output) < size:
        flags >>= 1
        if not flags & 0x100:
            if i >= len(source):
                raise ValueError("Truncated LZSS flags")
            flags = source[i] | 0xFF00
            i += 1
        if flags & 1:
            if i >= len(source):
                raise ValueError("Truncated LZSS literal")
            values = [source[i]]
            i += 1
        else:
            if i + 2 > len(source):
                raise ValueError("Truncated LZSS reference")
            low, high = source[i:i + 2]
            i += 2
            start, length = low | ((high & 0xF0) << 4), (high & 0x0F) + 3
            values = None
        count = 1 if values else length
        if len(output) + count > size:
            raise ValueError("LZSS output exceeds declared size")
        for k in range(count):
            value = values[0] if values else ring[(start + k) & 4095]
            output.append(value)
            ring[cursor] = value
            cursor = (cursor + 1) & 4095
    return bytes(output)


def entries(blob):
    if len(blob) < 0x60 or blob[:4] != b"FSYS":
        raise ValueError("Invalid FSYS header")
    count = struct.unpack_from(">I", blob, 0xC)[0]
    if not 0 <= count <= 100000 or 0x60 + 4 * count > len(blob):
        raise ValueError("Invalid FSYS entry count")
    names, total = set(), 0
    for index in range(count):
        at = struct.unpack_from(">I", blob, 0x60 + 4 * index)[0]
        if at + 0x30 > len(blob):
            raise ValueError("Truncated FSYS entry")
        words = struct.unpack_from(">12I", blob, at)
        start, size, compressed, name_at = words[1], words[2], words[5], words[9]
        total += size
        if total > MAX_TOTAL:
            raise ValueError("FSYS archive exceeds total extraction limit")
        if size > MAX_ENTRY or name_at >= len(blob):
            raise ValueError("Invalid FSYS size or name pointer")
        end = blob.find(b"\0", name_at)
        if end < 0:
            raise ValueError("Unterminated FSYS name")
        name = safe_name(blob[name_at:end].decode("utf-8"))
        kind = (words[0] >> 8) & 255
        filename = f"{index:02d}_{name}.{TYPES.get(kind, f't{kind:02x}')}"
        if filename.casefold() in names:
            raise ValueError("Duplicate FSYS filename")
        names.add(filename.casefold())
        if start + compressed > len(blob) or start > len(blob):
            raise ValueError("Truncated FSYS payload")
        raw = blob[start:start + compressed]
        if raw.startswith(b"LZSS"):
            if len(raw) < 16:
                raise ValueError("Truncated LZSS header")
            data = lzss(raw[16:], size)
        else:
            if start + size > len(blob):
                raise ValueError("Truncated raw FSYS payload")
            data = blob[start:start + size]
        yield filename, data
