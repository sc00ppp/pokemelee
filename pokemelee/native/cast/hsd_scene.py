"""hsd_scene.py: a pkx model's joints, dobjs, materials and full texture chains, read straight from the HSD data."""

from cast_paths import WORK, TARGETS
import struct
import sys
from pathlib import Path

from pokemelee.disc import Disc
from pokemelee.fsys import entries
import os


def pkx(name):
    """Largest model payload from the explicitly supplied source disc."""
    disc = Disc(os.environ["POKEMELEE_COLOSSEUM"], "colosseum")
    return max((data for _, data in entries(disc.read(f"pkx_{name}.fsys"))), key=len)


class Scene:
    def __init__(self, d, start=0x40):
        fs, ds, rc, roots, refs = struct.unpack('>5I', d[start:start + 20])
        self.base = start + 0x20
        self.data = d[self.base:self.base + ds]
        tab = self.base + ds + rc * 4
        st = tab + (roots + refs) * 8
        self.roots = {}
        for i in range(roots):
            off, name = struct.unpack('>II', d[tab + i * 8:tab + i * 8 + 8])
            s = st + name
            self.roots[d[s:d.find(b'\0', s)].decode('latin1')] = off

    def u32(self, o):
        return struct.unpack('>I', self.data[o:o + 4])[0]

    def f32(self, o):
        return struct.unpack('>f', self.data[o:o + 4])[0]

    def tobj(self, o):
        img = self.u32(o + 0x4C)
        w, h = struct.unpack('>HH', self.data[img + 4:img + 8])
        return dict(at=o, id=self.u32(o + 8), src=self.u32(o + 12), scale=(self.f32(o + 0x1C), self.f32(o + 0x20)),
                    trans=(self.f32(o + 0x28), self.f32(o + 0x2C)), wrap=(self.u32(o + 0x34), self.u32(o + 0x38)),
                    repeat=self.data[o + 0x3C:o + 0x3E].hex(), flags=self.u32(o + 0x40), blend=self.f32(o + 0x44),
                    size=(w, h), fmt=self.u32(img + 8), image=self.u32(img), tlut=self.u32(o + 0x50), tev=self.u32(o + 0x58))

    def mobj(self, o):
        m = self.u32(o + 12)
        out = dict(at=o, render=self.u32(o + 4), diffuse=self.data[m + 4:m + 8].hex(), ambient=self.data[m:m + 4].hex(),
                   specular=self.data[m + 8:m + 12].hex(), alpha=self.f32(m + 12), shiny=self.f32(m + 16),
                   pe=self.u32(o + 0x14), tobjs=[])
        t = self.u32(o + 8)
        while t:
            out['tobjs'].append(self.tobj(t))
            t = self.u32(t + 4)
        return out

    def joints(self, o, out=None):
        """Depth first, as the rip numbers meshes."""
        out = [] if out is None else out
        i = len(out)
        rec = dict(n=i, at=o, flags=self.u32(o + 4), dobjs=[])
        out.append(rec)
        d = self.u32(o + 0x10) if not (rec['flags'] & 0x4000) else 0
        while d:
            pob, p = [], self.u32(d + 12)
            while p:
                pob.append(dict(at=p, flags=struct.unpack('>H', self.data[p + 12:p + 14])[0], blocks=struct.unpack('>H', self.data[p + 14:p + 16])[0]))
                p = self.u32(p + 4)
            rec['dobjs'].append(dict(at=d, mobj=self.mobj(self.u32(d + 8)), pobjs=pob))
            d = self.u32(d + 4)
        c = self.u32(o + 8)
        if c:
            self.joints(c, out)
        s = self.u32(o + 12)
        if s:
            self.joints(s, out)
        return out


CM = ['none', 'amask', 'rgbmask', 'blend', 'mod', 'replace', 'pass', 'add', 'sub']
AM = ['none', 'amask', 'blend', 'mod', 'replace', 'pass', 'add', 'sub']
COORD = ['uv', 'refl', 'hilite', 'shadow', 'toon', 'grad']


def show(t):
    f = t['flags']
    lm = ''.join(c for b, c in ((0x10, 'D'), (0x20, 'S'), (0x40, 'A'), (0x80, 'X'), (0x100, 's')) if f & b)
    return (f"id{t['id']} src{t['src']} {COORD[f & 15]} {t['size'][0]}x{t['size'][1]} fmt{t['fmt']} img {t['image']:#x} "
            f"col={CM[(f >> 16) & 15]} a={AM[(f >> 20) & 15]} lm={lm}{' BUMP' if f & 0x1000000 else ''} blend={t['blend']:.2f} "
            f"sc={t['scale'][0]:.2f},{t['scale'][1]:.2f} tr={t['trans'][0]:.2f},{t['trans'][1]:.2f} wrap={t['wrap']} rep={t['repeat']} tev={t['tev']:#x}")


if __name__ == '__main__':
    s = Scene(pkx(sys.argv[1]))
    print(s.roots)
    root = s.roots['scene_data']
    models = s.u32(root)
    joint = s.u32(s.u32(models))
    js = s.joints(joint)
    print(len(js), 'joints')
    n = 0
    for j in js:
        for dob in j['dobjs']:
            m = dob['mobj']
            print(f"mesh_{n:02d} joint {j['n']} dobj {dob['at']:#x} mobj {m['at']:#x} render {m['render']:#x} diff {m['diffuse']} amb {m['ambient']} spec {m['specular']} alpha {m['alpha']:.2f} shiny {m['shiny']:.1f} pe {m['pe']:#x} pobjs {len(dob['pobjs'])}")
            for t in m['tobjs']:
                print('    ', show(t))
            n += 1
