"""slippi_patch.py: Slippi Dolphin patches some menu files as the game loads them, and edits must be made to what the
game actually runs.

Slippi Dolphin applies Sys/GameFiles/GALE01/<file>.diff (VCDIFF, xdelta3 without secondary compression) to the disc's
file when the game reads it (MnMaAll.usd: Online Play and its submenus). The game runs that TARGET, which differs in
layout from the disc file, and only the disc bytes the patch COPIES reach it; the patch copies by content, so one disc
byte can feed several target bytes and a target struct can take its fields from unrelated disc offsets.

So an edit is made on the target, and each changed target byte is traced back through the patch to the disc byte it is
copied from (`back`). Reported, never written: target bytes the patch writes itself (literal), and disc bytes that also
feed target bytes which are not meant to change (shared).

The patch used is pinned in tools/slippi/ (the copy in Slippi Launcher's netplay folder as of 2026-11-12).
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT, RUNTIME
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np

DIFFS = RUNTIME / 'slippi-menu-map/win-x64'


# ------------------------------------------------------------------------------------------------------------ VCDIFF
def _code_table():
    NOOP, ADD, RUN, COPY = 0, 1, 2, 3
    t = [((RUN, 0, 0), (NOOP, 0, 0))]
    t += [((ADD, s, 0), (NOOP, 0, 0)) for s in range(18)]
    for m in range(9):
        t.append(((COPY, 0, m), (NOOP, 0, 0)))
        t += [((COPY, s, m), (NOOP, 0, 0)) for s in range(4, 19)]
    t += [((ADD, a, 0), (COPY, c, m)) for m in range(6) for a in range(1, 5) for c in range(4, 7)]
    t += [((ADD, a, 0), (COPY, 4, m)) for m in range(6, 9) for a in range(1, 5)]
    t += [((COPY, 4, m), (ADD, 1, 0)) for m in range(9)]
    assert len(t) == 256
    return t


TABLE = _code_table()


class _R:
    def __init__(self, b):
        self.b, self.p = b, 0

    def byte(self):
        self.p += 1
        return self.b[self.p - 1]

    def var(self):
        v = 0
        while True:
            c = self.byte()
            v = (v << 7) | (c & 0x7F)
            if not c & 0x80:
                return v

    def take(self, n):
        self.p += n
        return self.b[self.p - n:self.p]


def apply(diff, source):
    """(target bytes, provenance): prov[i] = the source offset target byte i is copied from, -1 if literal"""
    r = _R(diff)
    if r.take(3) != b'\xd6\xc3\xc4':
        raise ValueError('not a VCDIFF patch')
    r.byte()
    hi = r.byte()
    if hi & 3:
        raise ValueError('compressed VCDIFF / custom code table not supported')
    if hi & 4:
        r.take(r.var())
    out, prov = bytearray(), []
    while r.p < len(diff):
        wi = r.byte()
        seg_len = seg_pos = 0
        if wi & 3:
            seg_len, seg_pos = r.var(), r.var()
        from_src = bool(wi & 1)
        r.var()
        tlen = r.var()
        if r.byte():
            raise ValueError('compressed VCDIFF sections')
        dlen, ilen, alen = r.var(), r.var(), r.var()
        if wi & 4:
            r.take(4)
        data, inst, addr = _R(r.take(dlen)), _R(r.take(ilen)), _R(r.take(alen))
        near, nslot, same = [0] * 4, 0, [0] * 768
        w0 = len(out)
        while inst.p < len(inst.b):
            for typ, size, mode in TABLE[inst.byte()]:
                if typ == 0:
                    continue
                if size == 0:
                    size = inst.var()
                if typ == 1:
                    out += data.take(size)
                    prov += [-1] * size
                elif typ == 2:
                    out += bytes([data.byte()]) * size
                    prov += [-1] * size
                else:
                    here = seg_len + len(out) - w0
                    if mode == 0:
                        a = addr.var()
                    elif mode == 1:
                        a = here - addr.var()
                    elif mode < 6:
                        a = near[mode - 2] + addr.var()
                    else:
                        a = same[(mode - 6) * 256 + addr.byte()]
                    near[nslot], nslot = a, (nslot + 1) % 4
                    same[a % 768] = a
                    if a < seg_len and from_src:
                        out += source[seg_pos + a:seg_pos + a + size]
                        prov += range(seg_pos + a, seg_pos + a + size)
                    else:
                        t = seg_pos + a if a < seg_len else w0 + a - seg_len
                        for k in range(size):
                            out.append(out[t + k])
                            prov.append(prov[t + k])
        if len(out) - w0 != tlen:
            raise ValueError('VCDIFF window length mismatch')
    return bytes(out), np.array(prov, dtype=np.int64)


def diff_for(name):
    p = DIFFS / f'{name}.diff'
    return p.read_bytes()


def live_matches(name):
    """True if Slippi Launcher's own patch is the one pinned here (None if Slippi Launcher's copy is not found)"""
    # Builds use only the installed, checksummed version; never inspect or
    # depend on a user's Slippi installation.
    return None


def target(name, disc):
    return apply(diff_for(name), disc)


def back(name, disc, want):
    """disc bytes that make the target `want` wherever the disc can; returns (new disc, report)"""
    tgt, prov = target(name, disc)
    w = np.frombuffer(want, np.uint8)
    t = np.frombuffer(tgt, np.uint8)
    if len(w) != len(t):
        raise ValueError('the edited target changed size')
    changed = np.nonzero(w != t)[0]
    literal = [int(i) for i in changed if prov[i] < 0]
    edits, clash = {}, []
    for i in changed:
        s = int(prov[i])
        if s < 0:
            continue
        if s in edits and edits[s] != int(w[i]):
            clash.append(int(i))
        edits.setdefault(s, int(w[i]))
    order = np.argsort(prov, kind='stable')
    sp = prov[order]
    shared = defaultdict(list)
    for s, v in edits.items():
        lo, hi = np.searchsorted(sp, s), np.searchsorted(sp, s, 'right')
        for j in order[lo:hi]:
            if w[j] != v:
                shared[s].append(int(j))
    new = bytearray(disc)
    for s, v in edits.items():
        if s not in shared:
            new[s] = v
    got, _ = target(name, bytes(new))
    miss = np.nonzero(np.frombuffer(got, np.uint8) != w)[0]
    rep = {'changed': len(changed), 'written': len(edits) - len(shared), 'literal': literal, 'clash': clash,
           'shared': dict(shared), 'miss': [int(i) for i in miss]}
    return bytes(new), rep


# --------------------------------------------------------------------------------------------- HSD navigation (target)
class Hsd:
    """a mutable HSD archive: data-offset reads/writes, root symbols, joints in menugraft's order"""

    def __init__(self, b):
        self.b = bytearray(b)
        fs, ds, rc, rtc, refc = struct.unpack('>5I', self.b[:20])
        ro = 0x20 + ds + 4 * rc
        strs = ro + 8 * rtc + 8 * refc
        self.roots = {}
        for i in range(rtc):
            off, so = struct.unpack('>II', self.b[ro + 8 * i:ro + 8 * i + 8])
            self.roots[self.b[strs + so:self.b.index(b'\0', strs + so)].decode()] = off

    def get(self, o, n):
        return bytes(self.b[0x20 + o:0x20 + o + n])

    def put(self, o, data):
        self.b[0x20 + o:0x20 + o + len(data)] = data

    def u32(self, o):
        return struct.unpack('>I', self.get(o, 4))[0]

    def joints(self, model):
        out = []

        def walk(o):
            while o:
                out.append(o)
                walk(self.u32(o + 8))
                o = self.u32(o + 12)
        walk(self.roots[model + '_Top_joint'])
        return out

    def dobjs(self, jo):
        o, res = self.u32(jo + 0x10), []
        while o:
            res.append(o)
            o = self.u32(o + 4)
        return res

    def mobj(self, model, j, d=0):
        return self.u32(self.dobjs(self.joints(model)[j])[d] + 8)

    def tobj(self, model, j, d=0, t=0):
        to = self.u32(self.mobj(model, j, d) + 8)
        for _ in range(t):
            to = self.u32(to + 4)
        return to

    def image(self, model, j, d=0, t=0):
        im = self.u32(self.tobj(model, j, d, t) + 0x4C)
        return struct.unpack('>IHHI', self.get(im, 12))

    def hide(self, model, js):
        jo = self.joints(model)
        for j in js:
            self.put(jo[j] + 4, struct.pack('>I', self.u32(jo[j] + 4) | 0x10))
