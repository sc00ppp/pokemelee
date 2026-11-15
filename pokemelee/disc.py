"""Bounded, read-only GameCube ISO filesystem reader. No game data included."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import struct

SUPPORTED = {"melee": ("GALE01", 0, 2), "colosseum": ("GC6E01", 0, 0)}


def safe_name(value):
    if not value or value in (".", "..") or any(ord(c) < 32 or c in '/\\:<>"|?*' for c in value):
        raise ValueError(f"Unsafe disc/archive name: {value!r}")
    if value.endswith((" ", ".")):
        raise ValueError(f"Ambiguous disc/archive name: {value!r}")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise ValueError(f"Reserved disc/archive name: {value!r}")
    return value


@dataclass(frozen=True)
class Entry:
    offset: int
    size: int


class Disc:
    def __init__(self, filename, role):
        if role not in SUPPORTED:
            raise ValueError(f"Unknown disc role: {role}")
        self.path = Path(filename).expanduser().resolve()
        self.role = role
        self.size = self.path.stat().st_size
        with self.path.open("rb") as stream:
            header = stream.read(0x440)
            if len(header) != 0x440 or header[0x1C:0x20] != bytes.fromhex("c2339f3d"):
                raise ValueError("Expected an uncompressed GameCube ISO/GCM")
            self.game_id = header[:6].decode("ascii")
            self.disc, self.revision = header[6], header[7]
            if (self.game_id, self.disc, self.revision) != SUPPORTED[role]:
                raise ValueError(f"Unsupported {role} disc: {self.game_id}, disc {self.disc}, revision {self.revision}; expected {SUPPORTED[role]}")
            self.title = header[0x20:0x420].split(b"\0", 1)[0].decode("utf-8", errors="replace")
            start, size = struct.unpack_from(">II", header, 0x424)
            if start < 0x440 or not 12 <= size <= 32 * 1024 * 1024 or start + size > self.size:
                raise ValueError("Invalid filesystem table bounds")
            stream.seek(start)
            table = stream.read(size)
        self.entries = self._entries(table)

    def _entries(self, table):
        kind, parent, count = struct.unpack_from(">III", table)
        if kind >> 24 != 1 or parent or count < 1 or count * 12 > len(table):
            raise ValueError("Invalid filesystem root")
        rows, stack, seen = {}, [(count, "", 0)], set()
        for i in range(1, count):
            while stack and i >= stack[-1][0]:
                stack.pop()
            if not stack:
                raise ValueError("Entry outside root directory")
            word, a, b = struct.unpack_from(">III", table, i * 12)
            name_at = count * 12 + (word & 0xFFFFFF)
            if name_at >= len(table):
                raise ValueError("Invalid filename offset")
            end = table.find(b"\0", name_at)
            if end < 0:
                raise ValueError("Unterminated filename")
            name = safe_name(table[name_at:end].decode("latin1"))
            full = str(PurePosixPath(stack[-1][1]) / name)
            if full.casefold() in seen:
                raise ValueError(f"Duplicate filesystem path: {full}")
            seen.add(full.casefold())
            if word >> 24 == 1:
                if a != stack[-1][2] or not i < b <= stack[-1][0]:
                    raise ValueError("Invalid directory extent or parent")
                stack.append((b, full, i))
            elif word >> 24 == 0:
                if a < 0x440 or a + b > self.size:
                    raise ValueError(f"Truncated disc file: {full}")
                rows[full] = Entry(a, b)
            else:
                raise ValueError("Unknown filesystem entry type")
        return rows

    def read(self, name, *, limit=512 * 1024 * 1024):
        row = self.entries[name]
        if row.size > limit:
            raise ValueError(f"File exceeds read limit: {name}")
        with self.path.open("rb") as stream:
            stream.seek(row.offset)
            result = stream.read(row.size)
        if len(result) != row.size:
            raise ValueError(f"Disc changed or was truncated: {name}")
        return result

    def info(self, hash_disc=False):
        result = dict(game=self.role, game_id=self.game_id, disc=self.disc, revision=self.revision,
                      title=self.title, bytes=self.size, files=len(self.entries),
                      validation="header and filesystem bounds; not a clean-disc checksum assertion")
        if hash_disc:
            with self.path.open("rb") as stream:
                result["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        return result
