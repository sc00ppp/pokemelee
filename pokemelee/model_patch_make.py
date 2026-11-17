"""Maintainer tool: write the model patches from the accepted costumes (the output of the Blender/rigswap cast replay).

Not part of the user build. For each accepted costume it finds the Colosseum vertex every finished vertex came from
(by UV, also through atlas repacks), fits a few bone transforms, and stores only what the user's discs cannot supply.
Each patch is rebuilt and checked byte for byte before it is written.
"""
import collections
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import model_patch as mp
from .catalog import load
from .dat import Dat
from .datprobe import DatFile
from .mesh import POS, NRM, TEX0, colo_root, costume_root


def uv_key(uv, G=8192):
    return (round(uv[0] * G), round(uv[1] * G))


def uv_grid(m, k):
    """The step a corner's UV is stored at: its array's fixed-point step, or 1/8192 for floats."""
    a = next((a for a in m.pobjs[m.cs[k][1]][3] if a['name'] == TEX0), None)
    return 8192 if a is None or a['comp'] == 4 else min(8192, 1 << a['scale'])


def source_points(src, T=None, G=8192):
    """Source points keyed by UV: ('v', corner) for a corner, ('m', corner, corner) for an edge midpoint."""
    exact, mid = collections.defaultdict(list), collections.defaultdict(list)
    for k, c in enumerate(src.cs):
        if TEX0 in c[3] and POS in c[3]:
            exact[uv_key(mp.uv_map(T, c[3][TEX0]), G)].append(('v', k))
    for t in src.tris:
        if not all(TEX0 in src.cs[i][3] and POS in src.cs[i][3] for i in t):
            continue
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ua, ub = mp.uv_map(T, src.cs[t[a]][3][TEX0]), mp.uv_map(T, src.cs[t[b]][3][TEX0])
            k = uv_key(((ua[0] + ub[0]) / 2, (ua[1] + ub[1]) / 2), G)
            for du in (-1, 0, 1):
                for dv in (-1, 0, 1):
                    mid[(k[0] + du, k[1] + dv)].append(('m', t[a], t[b]))
    return exact, mid


def find_uv_maps(out, src, src_sizes):
    """Atlas repacks: shifts and scales that land many finished UVs exactly on source UVs, found one at a time, at each
    UV array's own storage step. Returns the transforms and the keyed source points per (transform, step)."""
    S = np.unique(np.array([c[3][TEX0] for c in src.cs if TEX0 in c[3] and POS in c[3]], dtype=np.float64), axis=0)
    # an atlas keeps the source's texel size, and atlases are power-of-two wide and tall
    scales = sorted({(w / 2 ** m, h / 2 ** n) for w, h in src_sizes if min(w, h) >= 16
                     for m in range(3, 11) for n in range(3, 11)
                     if 1 / 64 <= w / 2 ** m <= 2 and 1 / 64 <= h / 2 ** n <= 2})
    points, maps = {}, []
    by_grid = collections.defaultdict(dict)
    for k, c in enumerate(out.cs):
        if TEX0 in c[3] and POS in c[3]:
            G = uv_grid(out, k)
            by_grid[G][uv_key(c[3][TEX0], G)] = c[3][TEX0]
    for G, left in sorted(by_grid.items()):
        for T in [None] + maps:
            points[(T, G)] = pts = source_points(src, T, G)
            left = {k: uv for k, uv in left.items() if k not in pts[0] and k not in pts[1]}
        while len(left) >= 12 and len(maps) < 16:
            O = np.array(list(left.values()), dtype=np.float64)
            O = O[np.linspace(0, len(O) - 1, min(len(O), 150)).astype(int)]
            best = None
            for sx, sy in scales:
                D = np.rint(O[:, None, :] * G - S[None, :, :] * (sx * G, sy * G)).astype(np.int64).reshape(-1, 2)
                keys, counts = np.unique((D[:, 0] + 2 ** 20) * 2 ** 22 + (D[:, 1] + 2 ** 20), return_counts=True)
                i = int(np.argmax(counts))
                if best is None or counts[i] > best[0]:
                    tx, ty = divmod(int(keys[i]), 2 ** 22)
                    best = (int(counts[i]), (float(sx), float(sy), (tx - 2 ** 20) / G, (ty - 2 ** 20) / G))
            if best is None or best[0] < max(6, len(O) * 0.05):
                break
            pts = source_points(src, best[1], G)
            hit = {k for k in left if k in pts[0] or k in pts[1]}
            if len(hit) < 12:
                break
            maps.append(best[1])
            points[(best[1], G)] = pts
            left = {k: uv for k, uv in left.items() if k not in hit}
    return maps, points


def fit_affine(pairs):
    S = np.array([s for s, _ in pairs], dtype=np.float64)
    P = np.array([p for _, p in pairs], dtype=np.float64)
    A, *_ = np.linalg.lstsq(np.c_[S, np.ones(len(S))], P, rcond=None)
    return [[float(A[0][r]), float(A[1][r]), float(A[2][r]), float(A[3][r])] for r in range(3)]


def texture_sizes(f, roots):
    return {(img.width, img.height) for img, _ in mp.images(f, roots)}


def generate(costume, model, vanilla, work, runtime):
    """(header pieces, template DAT, entry rows, texture records, texture XORs) for one finished costume."""
    work = Path(work)
    out_d = Dat(costume)
    out = mp.Model(out_d, costume_root(out_d))
    src_d = Dat(model)
    src = mp.Model(src_d, colo_root(src_d))
    (work / 'source.dat').write_bytes(model)
    (work / 'costume.dat').write_bytes(costume)
    sizes = texture_sizes(DatFile(work / 'source.dat'), [('j', colo_root(src_d))])
    uvmaps, points = find_uv_maps(out, src, sizes)

    # 1. candidate source points for every corner with a UV match, and the atlas repack it went through
    cand, uvt = {}, {}
    for k, c in enumerate(out.cs):
        if TEX0 in c[3] and POS in c[3]:
            G = uv_grid(out, k)
            key = uv_key(c[3][TEX0], G)
            for t in [None] + list(range(len(uvmaps))):
                T = None if t is None else uvmaps[t]
                pts = points.get((T, G)) or points.setdefault((T, G), source_points(src, T, G))
                refs = pts[0].get(key) or pts[1].get(key)
                if refs:
                    cand[k], uvt[k] = refs, t
                    break

    # 2. bone transforms per (finished joint, source joint), from the unambiguous matches
    def group_of(k, ref):
        return (out.dominant(k), src.dominant(ref[1]))

    pairs = collections.defaultdict(list)
    for k, refs in cand.items():
        if len(refs) == 1:
            pairs[group_of(k, refs[0])].append((mp.ref_value(src, refs[0], POS), out.world(k)))
    by_out = collections.defaultdict(list)
    for (oj, sj), items in pairs.items():
        by_out[oj].extend(items)
    everything = [x for items in pairs.values() for x in items]
    named = {}
    if len(everything) >= 12:
        named['all'] = fit_affine(everything)
    for oj, items in by_out.items():
        if len(items) >= 12:
            named[('o', oj)] = fit_affine(items)
    for g, items in pairs.items():
        if len(items) >= 8:
            named[('g',) + g] = fit_affine(items)
    order = list(named)
    index = {k: i for i, k in enumerate(order)}
    affines = [named[k] for k in order]

    def affine_for(k, ref):
        g = group_of(k, ref)
        for key in (('g',) + g, ('o', g[0]), 'all'):
            if key in index:
                return index[key]

    # 3. each array entry: the reference and transform that predict it best, and the exact leftover
    bufs = mp.buffers(out)
    all_refs = [('v', k) for k, c in enumerate(src.cs) if POS in c[3]]
    SW = np.array([mp.ref_value(src, r, POS) for r in all_refs]) if all_refs else np.zeros((0, 3))
    rows = []
    template = bytearray(out_d.data)
    for key, b in bufs.items():
        name = key[0]
        array = []
        for i in range(b['count']):
            k = b['first'].get(i)
            actual = mp.read_raw(out_d.data, key, b, i)
            best = None
            if k is not None:
                refs = cand.get(k)
                if not refs and name in (POS, NRM) and affines:
                    # no UV match: the nearest source vertex under this joint's own transform
                    ak = index.get(('o', out.dominant(k)), index.get('all'))
                    A = np.array(affines[ak])
                    moved = SW @ A[:, :3].T + A[:, 3]
                    refs = [all_refs[int(np.argmin(((moved - np.array(out.world(k))) ** 2).sum(1)))]]
                for ref in refs or []:
                    akey = uvt.get(k) if name == TEX0 else affine_for(k, ref)
                    pred = mp.predict(out, src, affines, uvmaps, k, ref, name, b, akey)
                    if pred is None:
                        continue
                    left = mp.residual(b, actual, pred)
                    cost = sum(abs(x) for x in left)
                    if best is None or cost < best[0]:
                        best = (cost, ref, akey, left)
            if best is None:
                array.append(None)
            else:
                array.append(best[1:])
                mp.write_raw(template, key, b, i, (0,) * mp.components(name))
        rows.append(array)

    # 4. textures: the source picture that looks most like each finished one, re-encoded by HSDRaw, XOR the rest
    codec = mp.Codec(runtime, work / 'textures')
    sources = mp.source_pictures(codec, model)
    pictures = mp.costume_images(DatFile(work / 'costume.dat'))
    finished = codec.decode('o', pictures)
    plan = []
    for (img, tl), a in zip(pictures, finished):
        best = None
        for j, s in enumerate(sources):
            s = s if s.shape == a.shape else np.asarray(
                Image.fromarray(np.ascontiguousarray(s), 'RGBA').resize((img.width, img.height), Image.BILINEAR))
            diff = float(np.abs(a.astype(int) - s.astype(int)).mean())
            if best is None or diff < best[0]:
                best = (diff, j)
        plan.append((best[1], img.format, tl.format if tl else 0, img.width, img.height))
    preds = codec.encode(plan, sources)
    recs, xors = [], []
    for (img, tl), (j, fmt, pf, w, h), (pdata, ppal) in zip(pictures, plan, preds):
        rec = dict(source=j, fmt=fmt, palfmt=pf, w=w, h=h, data_at=img.data_offset, data_len=len(img.data))
        x = mp.xor(mp.fit(pdata, len(img.data)), img.data)
        template[img.data_offset:img.data_offset + len(img.data)] = bytes(len(img.data))
        p = b''
        if tl:
            rec.update(pal_at=tl.data_offset, pal_len=len(tl.data))
            p = mp.xor(mp.fit(ppal, len(tl.data)), tl.data)
            template[tl.data_offset:tl.data_offset + len(tl.data)] = bytes(len(tl.data))
        recs.append(rec)
        xors.append((x, p))
    whole = out_d.raw[:0x20] + bytes(template) + out_d.raw[0x20 + len(template):]
    header = dict(affines=affines, uvmaps=[list(t) for t in uvmaps], arrays=[list(k) for k in bufs], textures=recs)
    return header, whole, rows, xors



def make_patches(melee, colosseum, cast_dir, runtime, out_dir=None, selected=None, log=print):
    """Write and check a model patch for each accepted costume in `cast_dir` (a completed cast component)."""
    runtime = Path(runtime).resolve()
    out_dir = Path(out_dir or mp.PATCHES)
    out_dir.mkdir(parents=True, exist_ok=True)
    cast_dir = Path(cast_dir)
    finishing = load('cast-finishing.json')['recipes']
    sources = {m['label'] + '.glb': m['source_archive'] for m in load('source-models.json')['models']}
    record = json.loads((cast_dir / 'receipt.json').read_text(encoding='utf-8'))
    report = []
    for row in record['outputs']:
        name = row['pokemon'].lower()
        if selected and name not in {s.lower() for s in selected}:
            continue
        costume = (cast_dir / row['path']).read_bytes()
        if hashlib.sha256(costume).hexdigest() != finishing[name]['sha256']:
            raise ValueError(f'{name}: not the accepted costume')
        archive = sources[load('cast/' + name + '.json')['source_model']]
        model = mp.colo_model(colosseum, archive)
        vanilla_name = 'Pl' + mp.CODES[row['fighter']] + 'Nr.dat'
        vanilla = melee.read(vanilla_name)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            header, template, rows, xors = generate(costume, model, vanilla, tmp, runtime)
            (tmp / 'vanilla.dat').write_bytes(vanilla)
            (tmp / 'template.dat').write_bytes(template)
            # -A= writes no VCDIFF application header: without it xdelta3 stores both file paths (the maintainer's temp
            # folder, user name included) in every patch it makes
            subprocess.run([str(mp.xdelta_tool(runtime)), '-e', '-9', '-f', '-A=', '-s', str(tmp / 'vanilla.dat'),
                            str(tmp / 'template.dat'), str(tmp / 'template.xd')], check=True, capture_output=True)
            delta = (tmp / 'template.xd').read_bytes()
            if mp.delta_has_appheader(delta):
                raise ValueError(f'{name}: the template delta carries an application header (file paths)')
            header.update(pokemon=row['pokemon'], fighter=row['fighter'], source_archive=archive,
                          vanilla=vanilla_name, sha256=finishing[name]['sha256'],
                          source_sha256=hashlib.sha256(model).hexdigest(),
                          vanilla_sha256=hashlib.sha256(vanilla).hexdigest())
            path = out_dir / (name + '.mpatch')
            mp.write_patch(path, header, delta, rows, xors)
            mp.rebuild(path, model, vanilla, runtime, tmp / 'check')      # raises unless byte-identical
        report.append({'pokemon': row['pokemon'], 'bytes': path.stat().st_size})
        log(f'{row["pokemon"]}: {path.stat().st_size:,d} bytes, rebuild exact', flush=True)
    return report
