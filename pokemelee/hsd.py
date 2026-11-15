"""Deterministic HSD archive preparations used by the approved Stadium recipes."""
import struct


def sanitize_stage(data):
    """Resolve external references inside the model-group array as Melee does.

    HSDRaw otherwise treats external pointer-chain links as struct boundaries.
    Adapted from the original Stadium builder's sanitize.py.
    """
    data = bytearray(data)
    if len(data) < 0x20:
        raise ValueError("Truncated HSD archive")
    size, data_size, relocations, roots, refs = struct.unpack_from(">5I", data)
    table = 0x20 + data_size + 4 * relocations
    strings_at = table + 8 * (roots + refs)
    if size != len(data) or strings_at > len(data):
        raise ValueError("Invalid HSD archive tables")
    entries = [struct.unpack_from(">2I", data, table + 8*i) for i in range(roots + refs)]
    strings = data[strings_at:]
    def name(offset):
        end = strings.find(b"\0", offset)
        if end < 0:
            raise ValueError("Invalid HSD symbol")
        return strings[offset:end]
    def read(offset):
        if not 0 <= offset <= data_size - 4:
            raise ValueError("Invalid HSD pointer")
        return struct.unpack_from(">I", data, 0x20 + offset)[0]
    head = next((o for o,s in entries[:roots] if name(s) == b"map_head"), None)
    if head is None:
        raise ValueError("Stage has no map_head symbol")
    start, count = read(head + 8), read(head + 12)
    end = start + count * 0x34
    if end > data_size:
        raise ValueError("Invalid stage model-group array")
    kept, removed = [], 0
    for index, (offset, string) in enumerate(entries):
        if index >= roots and start <= offset < end:
            seen = set()
            while offset != 0xFFFFFFFF and offset < data_size:
                if offset in seen:
                    raise ValueError("Cyclic HSD external pointer chain")
                seen.add(offset)
                nxt = read(offset)
                struct.pack_into(">I", data, 0x20 + offset, 0)
                offset = nxt
            removed += 1
        else:
            kept.append((offset, string))
    result = data[:table] + b"".join(struct.pack(">2I", *e) for e in kept) + strings
    struct.pack_into(">I", result, 0, len(result))
    struct.pack_into(">I", result, 16, refs - removed)
    return bytes(result)
