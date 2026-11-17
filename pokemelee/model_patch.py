"""Rebuild the accepted base costumes from the user's own discs plus small model patches.

A model patch holds only our edits: the finished costume's structure as an xdelta against Melee's own costume (with its
vertex arrays and textures blanked), which Colosseum vertex each finished vertex comes from, a few bone transforms, and
exact integer leftovers; textures are the user's Colosseum textures re-encoded, plus XOR leftovers. Every Pokemon
position, normal, UV and pixel comes from the user's Colosseum disc. The rebuild is plain Python float arithmetic in a
fixed order (+, -, *, /, sqrt only), so every machine gets the same bytes, and each result is checked by SHA-256.
"""
import hashlib
import json
import lzma
import math
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from .catalog import PACKAGE, load
from .dat import Dat
from .datprobe import DatFile
from .export import fingerprint
from .fsys import entries as fsys_entries
from .mesh import POS, NRM, TEX0, colo_root, corners, costume_root, envelopes, invbind, tree
from .runtime import lock
from .workspace import output_directory, receipt

MAGIC = b'PMMP1\n'
PATCHES = PACKAGE / 'recipes/model-patches'
CODES = dict(zip(
    ('Mario DrMario Luigi Bowser Peach CaptainFalcon Ganondorf DonkeyKong Fox Falco Ness Kirby Samus Zelda '
     'Sheik Link YoungLink Pichu Pikachu Mewtwo Jigglypuff Marth Roy Yoshi GameAndWatch Popo Nana').split(),
    'Mr Dr Lg Kp Pe Ca Gn Dk Fx Fc Ns Kb Ss Zd Sk Lk Cl Pc Pk Mt Pr Ms Fe Ys Gw Pp Nn'.split()))


# ---- fixed-order float math ------------------------------------------------------------------------------------------
def inv34(m):
    """Inverse of a 3x4 affine (rows), by cofactors."""
    a, b, c, tx = m[0]
    d, e, f, ty = m[1]
    g, h, i, tz = m[2]
    A = e * i - f * h
    B = -(d * i - f * g)
    C = d * h - e * g
    det = a * A + b * B + c * C
    r = [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
         [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
         [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]]
    return [[r[k][0], r[k][1], r[k][2], -(r[k][0] * tx + r[k][1] * ty + r[k][2] * tz)] for k in range(3)]


def apply(m, p):
    return (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
            m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
            m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3])


def rotate(m, n):
    return (m[0][0] * n[0] + m[0][1] * n[1] + m[0][2] * n[2],
            m[1][0] * n[0] + m[1][1] * n[1] + m[1][2] * n[2],
            m[2][0] * n[0] + m[2][1] * n[1] + m[2][2] * n[2])


def unit(n):
    s = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    return (n[0] / s, n[1] / s, n[2] / s) if s > 0 else (0.0, 0.0, 0.0)


# ---- a model's corners and the space each is stored in -----------------------------------------------------------------
class Model:
    def __init__(self, d, root):
        self.d = d
        self.js = tree(d, root)
        self.jindex = {j: i for i, j in enumerate(self.js)}
        self.cs, self.tris, self.pobjs = corners(d, root)
        envs = {pi: envelopes(d, p) for pi, (ji, p, flags, table) in enumerate(self.pobjs)}
        self.space = []          # per corner: ('one'|'rigid', joint #) or ('skin', ((joint #, weight), ...))
        for ji, pi, idx, val in self.cs:
            e = envs[pi]
            if e is None:
                self.space.append(('rigid', ji))
            else:
                env = e[idx.get(0, 0) // 3]
                if len(env) == 1:
                    self.space.append(('one', self.jindex[env[0][0]]))
                else:
                    self.space.append(('skin', tuple((self.jindex[j], w) for j, w in env)))
        self.ib = {i: invbind(d, j) for i, j in enumerate(self.js)}
        self.wm = {i: (inv34(m) if m is not None else None) for i, m in self.ib.items()}

    def dominant(self, k):
        s = self.space[k]
        return s[1] if s[0] != 'skin' else max(s[1], key=lambda x: x[1])[0]

    def _matrix(self, k, table):
        s = self.space[k]
        return None if s[0] == 'skin' else table.get(s[1])

    def to_world(self, k, v):
        m = self._matrix(k, self.wm)
        return v if m is None else apply(m, v)

    def from_world(self, k, v):
        m = self._matrix(k, self.ib)
        return v if m is None else apply(m, v)

    def nrm_to_world(self, k, n):
        m = self._matrix(k, self.wm)
        return n if m is None else rotate(m, n)

    def nrm_from_world(self, k, n):
        m = self._matrix(k, self.ib)
        return n if m is None else rotate(m, n)

    def world(self, k):
        v = self.cs[k][3].get(POS)
        return None if v is None else self.to_world(k, v)


# ---- the finished costume's vertex arrays ------------------------------------------------------------------------------
def buffers(m):
    """{(attribute, data offset): dict(comp, scale, stride, count, first)} for POS/NRM/TEX0, in display-list order;
    `first` maps each array entry to the first corner that uses it."""
    out = {}
    for k, (ji, pi, idx, val) in enumerate(m.cs):
        for a in m.pobjs[pi][3]:
            if a['name'] not in (POS, NRM, TEX0) or a['data'] is None:
                continue
            b = out.setdefault((a['name'], a['data']), dict(comp=a['comp'], scale=a['scale'], stride=a['stride'], first={}))
            b['first'].setdefault(idx[a['name']], k)
    for b in out.values():
        b['count'] = max(b['first']) + 1
    return out


def components(name):
    return 2 if name == TEX0 else 3


INTS = {0: ('B', 0, 255), 1: ('b', -128, 127), 2: ('H', 0, 65535), 3: ('h', -32768, 32767)}


def read_raw(data, key, b, i):
    name, at = key
    n = components(name)
    at += i * b['stride']
    if b['comp'] == 4:
        return struct.unpack_from(f'>{n}I', data, at)       # float bits, as integers
    return struct.unpack_from(f'>{n}{INTS[b["comp"]][0]}', data, at)


def write_raw(data, key, b, i, raw):
    name, at = key
    n = components(name)
    at += i * b['stride']
    if b['comp'] == 4:
        struct.pack_into(f'>{n}I', data, at, *[x & 0xFFFFFFFF for x in raw])
    else:
        struct.pack_into(f'>{n}{INTS[b["comp"]][0]}', data, at, *raw)


def quantize(b, v):
    if b['comp'] == 4:
        return tuple(struct.unpack('>I', struct.pack('>f', x))[0] for x in v)
    q = 1 << b['scale']
    _, lo, hi = INTS[b['comp']]
    return tuple(min(hi, max(lo, int(round(x * q)))) for x in v)


def residual(b, actual, pred):
    if b['comp'] == 4:
        return tuple(((a - p + 2 ** 31) % 2 ** 32) - 2 ** 31 for a, p in zip(actual, pred))
    return tuple(a - p for a, p in zip(actual, pred))


def add(b, pred, r):
    if b['comp'] == 4:
        return tuple((p + x) % 2 ** 32 for p, x in zip(pred, r))
    return tuple(p + x for p, x in zip(pred, r))


# ---- where a finished value comes from in the Colosseum model -------------------------------------------------------------
def uv_map(T, uv):
    """An atlas repack: (scale u, scale v, shift u, shift v)."""
    return uv if T is None else (T[0] * uv[0] + T[2], T[1] * uv[1] + T[3])


def ref_value(src, ref, attr):
    """The source value a reference stands for: ('v', corner) or the midpoint ('m', corner, corner); POS/NRM in the
    model's world space."""
    vals = []
    for k in ref[1:]:
        v = src.cs[k][3].get(attr)
        if v is None:
            return None
        if attr == POS:
            v = src.to_world(k, v)
        elif attr == NRM:
            v = src.nrm_to_world(k, v)
        vals.append(v)
    if len(vals) == 1:
        return tuple(vals[0])
    return tuple((x + y) / 2 for x, y in zip(*vals))


def predict(out, src, affines, uvmaps, k, ref, name, b, key):
    """The stored integers the finished entry would hold if it were exactly its source value carried over: through
    the bone transform `key` for POS/NRM, through the atlas repack `key` for UVs."""
    v = ref_value(src, ref, name)
    if v is None:
        return None
    if name == TEX0:
        return quantize(b, uv_map(None if key is None else uvmaps[key], v))
    if key is None:
        return None
    a = affines[key]
    if name == POS:
        return quantize(b, out.from_world(k, apply(a, v)))
    return quantize(b, unit(out.nrm_from_world(k, unit(rotate(a, v)))))


# ---- textures ---------------------------------------------------------------------------------------------------------------
def images(f, roots):
    seen = {}
    for kind, o in roots:
        items = f.matanim_texanims(o) if kind == 'mat' else f.jobj_textures(o)
        for t in items:
            pairs = list(zip(t.images, t.tluts or [None] * len(t.images))) if kind == 'mat' else [(t.image, t.tlut)]
            for img, tl in pairs:
                seen.setdefault(img.data_offset, (img, tl))
    return list(seen.values())


def costume_images(f):
    return images(f, [('mat' if 'matanim' in n else 'j', o) for n, o in f.roots
                      if n.endswith('_joint') and 'shapeanim' not in n])


class Codec:
    """HSDRaw's own GX texture decoder/encoder (the texenc helper compiled against the pinned HSDRaw.dll)."""

    def __init__(self, runtime, work):
        self.tool = Path(runtime) / 'stagegraft/texenc/stagegraft-texenc.dll'
        if not self.tool.is_file():
            raise ValueError('Run compile-stages before building (texenc helper missing)')
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)

    def run(self, lines):
        job = self.work / 'job.txt'
        job.write_text('\n'.join('\t'.join(map(str, line)) for line in lines), encoding='utf-8')
        result = subprocess.run(['dotnet', str(self.tool), str(job)], capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise ValueError('Texture codec failed: ' + result.stdout[-2000:] + result.stderr[-2000:])

    def decode(self, tag, pictures):
        lines = []
        for k, (img, tl) in enumerate(pictures):
            base = self.work / f'{tag}{k}'
            base.with_suffix('.bin').write_bytes(img.data)
            if tl:
                base.with_suffix('.pal').write_bytes(tl.data)
            lines.append(('decode', img.format, img.width, img.height, base.with_suffix('.bin'), tl.format if tl else 0,
                          tl.count if tl else 0, base.with_suffix('.pal') if tl else '-', base.with_suffix('.rgba')))
        self.run(lines)
        return [np.frombuffer((self.work / f'{tag}{k}.rgba').read_bytes(), np.uint8).reshape(img.height, img.width, 4)
                for k, (img, _) in enumerate(pictures)]

    def encode(self, rows, sources):
        """rows: (source #, format, palette format, width, height); the source picture resized if needed."""
        lines = []
        for n, (j, fmt, pf, w, h) in enumerate(rows):
            px = sources[j]
            if px.shape[:2] != (h, w):
                px = np.asarray(Image.fromarray(np.ascontiguousarray(px), 'RGBA').resize((w, h), Image.BILINEAR))
            (self.work / f'q{n}.rgba').write_bytes(np.ascontiguousarray(px).tobytes())
            lines.append(('encode', fmt, pf, w, h, self.work / f'q{n}.rgba', self.work / f'q{n}.bin', self.work / f'q{n}.pal'))
        self.run(lines)
        return [((self.work / f'q{n}.bin').read_bytes(), (self.work / f'q{n}.pal').read_bytes()) for n in range(len(rows))]


def source_pictures(codec, model):
    path = codec.work / 'source.dat'
    path.write_bytes(model)
    return codec.decode('s', images(DatFile(path), [('j', colo_root(Dat(model)))]))


def xor(a, b):
    return (np.frombuffer(a, np.uint8) ^ np.frombuffer(b, np.uint8)).tobytes()


def fit(blob, n):
    return blob[:n].ljust(n, b'\0')


# ---- the patch file -------------------------------------------------------------------------------------------------------
def write_patch(path, header, template_delta, entries, textures):
    """header: JSON-able; entries: per array, per entry None or (ref, key, leftovers); textures: per picture
    (data XOR, palette XOR)."""
    rows = bytearray()
    for array in entries:
        for row in array:
            if row is None:
                rows += b'\0'
                continue
            ref, key, left = row
            rows += bytes([1 if ref[0] == 'v' else 2]) + struct.pack(f'<{len(ref) - 1}I', *ref[1:])
            rows += struct.pack('<h', -1 if key is None else key) + struct.pack(f'<{len(left)}i', *left)
    pictures = b''.join(x + p for x, p in textures)
    body = lzma.compress(template_delta + bytes(rows) + pictures, preset=9 | lzma.PRESET_EXTREME)
    header = dict(header, template_bytes=len(template_delta), rows_bytes=len(rows))
    text = json.dumps(header, separators=(',', ':')).encode('utf-8')
    Path(path).write_bytes(MAGIC + struct.pack('<I', len(text)) + text + body)


def read_patch(path):
    raw = Path(path).read_bytes()
    if not raw.startswith(MAGIC):
        raise ValueError('Not a model patch: ' + str(path))
    n = struct.unpack_from('<I', raw, len(MAGIC))[0]
    header = json.loads(raw[len(MAGIC) + 4:len(MAGIC) + 4 + n])
    body = lzma.decompress(raw[len(MAGIC) + 4 + n:])
    t, r = header['template_bytes'], header['rows_bytes']
    return header, body[:t], body[t:t + r], body[t + r:]


def delta_has_appheader(delta):
    """True when a VCDIFF delta carries an application header (xdelta3 writes the source and target paths there)."""
    return delta[:4] == b'\xd6\xc3\xc4\x00' and bool(delta[4] & 0x04)


def parse_rows(blob, arrays):
    """The entry rows again, given each array's (name, count)."""
    at, out = 0, []
    for name, count in arrays:
        rows = []
        for _ in range(count):
            kind = blob[at]
            at += 1
            if kind == 0:
                rows.append(None)
                continue
            n = 1 if kind == 1 else 2
            ref = ('v' if kind == 1 else 'm',) + struct.unpack_from(f'<{n}I', blob, at)
            at += 4 * n
            key = struct.unpack_from('<h', blob, at)[0]
            at += 2
            left = struct.unpack_from(f'<{components(name)}i', blob, at)
            at += 4 * components(name)
            rows.append((ref, None if key < 0 else key, left))
        out.append(rows)
    if at != len(blob):
        raise ValueError('Model patch rows are damaged')
    return out


# ---- rebuild ------------------------------------------------------------------------------------------------------------------
def xdelta_tool(runtime):
    return Path(runtime) / 'xdelta/win-x64' / lock()['tools']['xdelta']['platforms']['win-x64']['entrypoint']


def colo_model(colosseum, archive):
    """The model DAT inside a Colosseum pkx archive (Colosseum's PKX header is 0x40 bytes)."""
    (_, data), = list(fsys_entries(colosseum.read(archive)))
    size = struct.unpack_from('>I', data, 0x40)[0]
    return data[0x40:0x40 + size]


def rebuild(patch_path, model, vanilla, runtime, work):
    """The finished costume bytes, from the patch, the Colosseum model DAT and Melee's own costume DAT."""
    header, delta, rows, pictures = read_patch(patch_path)
    for blob, key in ((model, 'source_sha256'), (vanilla, 'vanilla_sha256')):
        if hashlib.sha256(blob).hexdigest() != header[key]:
            raise ValueError(f'{header["pokemon"]}: an input differs from the expected disc file ({key})')
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / 'vanilla.dat').write_bytes(vanilla)
    (work / 'template.xd').write_bytes(delta)
    result = subprocess.run([str(xdelta_tool(runtime)), '-d', '-f', '-s', str(work / 'vanilla.dat'),
                             str(work / 'template.xd'), str(work / 'template.dat')], capture_output=True, timeout=300)
    if result.returncode:
        raise ValueError(f'{header["pokemon"]}: template patch failed')
    raw = (work / 'template.dat').read_bytes()
    out_d = Dat(raw)
    data = bytearray(out_d.data)
    out = Model(out_d, costume_root(out_d))
    src = Model(Dat(model), colo_root(Dat(model)))
    bufs = buffers(out)
    keys = [tuple(k) for k in header['arrays']]
    if keys != list(bufs):
        raise ValueError(f'{header["pokemon"]}: vertex arrays differ from the patch')
    affines, uvmaps = header['affines'], [tuple(t) for t in header['uvmaps']]
    for key, array in zip(keys, parse_rows(rows, [(k[0], bufs[k]['count']) for k in keys])):
        b = bufs[key]
        for i, row in enumerate(array):
            if row is None:
                continue
            ref, akey, left = row
            pred = predict(out, src, affines, uvmaps, b['first'][i], ref, key[0], b, akey)
            write_raw(data, key, b, i, add(b, pred, left))
    codec = Codec(runtime, work / 'textures')
    sources = source_pictures(codec, model)
    recs = header['textures']
    preds = codec.encode([(r['source'], r['fmt'], r['palfmt'], r['w'], r['h']) for r in recs], sources)
    at = 0
    for r, (pdata, ppal) in zip(recs, preds):
        x = pictures[at:at + r['data_len']]
        at += r['data_len']
        data[r['data_at']:r['data_at'] + r['data_len']] = xor(fit(pdata, r['data_len']), x)
        if r.get('pal_len'):
            x = pictures[at:at + r['pal_len']]
            at += r['pal_len']
            data[r['pal_at']:r['pal_at'] + r['pal_len']] = xor(fit(ppal, r['pal_len']), x)
    built = raw[:0x20] + bytes(data) + raw[0x20 + len(data):]
    if hashlib.sha256(built).hexdigest() != header['sha256']:
        raise ValueError(f'{header["pokemon"]}: rebuilt costume differs from the accepted one')
    return built


def rebuild_one(name, melee, colosseum, runtime, root, accepted):
    """One accepted base costume, written to hand/<mon>-<Fighter>/4-export/<Fighter>.dat (a process of its own)."""
    header = read_patch(PATCHES / (name + '.mpatch'))[0]
    if header['sha256'] != accepted:
        raise ValueError(f'{name}: model patch is not for the accepted costume')
    model = colo_model(colosseum, header['source_archive'])
    vanilla = melee.read(header['vanilla'])
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        built = rebuild(PATCHES / (name + '.mpatch'), model, vanilla, runtime, tmp)
    out = root / 'hand' / f'{name}-{header["fighter"]}' / '4-export' / (header['fighter'] + '.dat')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(built)
    return {'pokemon': header['pokemon'], 'fighter': header['fighter'],
            'path': out.relative_to(root).as_posix(), **fingerprint(out)}


def build_cast(melee, colosseum, output, runtime, selected=None, jobs=None):
    """The accepted base costumes, laid out as the replayed cast was: hand/<mon>-<Fighter>/4-export/<Fighter>.dat.
    ``jobs`` caps how many rebuild at once (default: one per core)."""
    from concurrent.futures import ProcessPoolExecutor
    from .parallel import workers
    finishing = load('cast-finishing.json')['recipes']
    names = sorted(p.stem for p in PATCHES.glob('*.mpatch'))
    if selected is not None:
        names = [n for n in names if n in {s.lower() for s in selected}]
    if not names:
        raise ValueError('No model patches in ' + str(PATCHES) + '; write them with model-patches or use the builder release')
    if set(names) != set(finishing) and selected is None:
        raise ValueError('Model patches and accepted cast recipes disagree')
    runtime = Path(runtime).resolve()
    with output_directory(output, 'cast') as root:
        count = workers(len(names) if jobs is None else min(jobs, len(names)))
        with ProcessPoolExecutor(count) as pool:
            outputs = list(pool.map(rebuild_one, names, *zip(*[(melee, colosseum, runtime, root, finishing[n]['sha256'])
                                                                   for n in names])))
        return receipt(root, 'cast', {'colosseum': colosseum.info(), 'melee': melee.info(), 'method': 'model-patches'},
                       outputs, authoring='disabled', network='disabled')
