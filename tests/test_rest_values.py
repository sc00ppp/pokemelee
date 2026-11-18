"""Costume slots take the rest values of the vanilla colour they stand for, the model staying where it was. Synthetic
archives only: a three-joint tree with one enveloped mesh, a vertex bound to one joint and one blended between two."""
import math
from pathlib import Path
import random
import struct
import tempfile
import unittest

from pokemelee import rest_values as rv
from pokemelee.dat import Dat
from pokemelee.targets import NAMES

J0, J1, J2, DOBJ, POBJ, TABLE, IBS, ENVS, ENV0, ENV1, POSITIONS, NORMALS, LIST, SIZE = (
    0x000, 0x040, 0x080, 0x0C0, 0x0E0, 0x100, 0x180, 0x220, 0x230, 0x240, 0x260, 0x280, 0x2A0, 0x2C0)
POS_SCALE, NRM_SCALE = 10, 14


def identity():
    return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]


def costume(srt, ib_from=None, indices=(0, 1, 2)):
    """A costume archive. ``srt``: nine floats per joint; inverse binds from the rest pose of ``ib_from`` (default
    ``srt``). Vertex 0 and 2 are bound to joint 2 alone (its own space), vertex 1 is blended half and half between
    joints 1 and 2 (model space); ``indices`` are the position and normal entries the three vertices use."""
    data, pointers = bytearray(SIZE), {}

    def point(at, target):
        struct.pack_into('>I', data, at, target)
        pointers[at] = target

    flags = {J0: (1 << 1) | (1 << 3), J1: 1 | (1 << 3), J2: 1 | (1 << 3)}
    rows = [(J0, -1, flags[J0], b''), (J1, 0, flags[J1], b''), (J2, 1, flags[J2], b'')]
    raw = [struct.pack('>9f', *values) for values in srt]
    bind = rv.worlds(rows, [struct.pack('>9f', *v) for v in (ib_from or srt)])
    for k, (j, _, f, _) in enumerate(rows):
        struct.pack_into('>I', data, j + 4, f)
        data[j + 0x14:j + 0x38] = raw[k]
        struct.pack_into('>12f', data, IBS + 0x30 * k, *[x for row in rv.invert(bind[k]) for x in row])
        point(j + 0x38, IBS + 0x30 * k)
    point(J0 + 8, J1)
    point(J1 + 8, J2)
    point(J0 + 0x10, DOBJ)
    point(DOBJ + 0x0C, POBJ)
    point(POBJ + 8, TABLE)
    struct.pack_into('>HH', data, POBJ + 0x0C, 0x2000, 1)
    point(POBJ + 0x10, LIST)
    point(POBJ + 0x14, ENVS)
    for k, (name, kind, cnt, comp, scale, stride, target) in enumerate((
            (0, 1, 0, 0, 0, 0, None), (9, 3, 1, 3, POS_SCALE, 6, POSITIONS), (10, 3, 0, 3, NRM_SCALE, 6, NORMALS))):
        at = TABLE + 24 * k
        struct.pack_into('>4IBBH', data, at, name, kind, cnt, comp, scale, 0, stride)
        if target is not None:
            point(at + 20, target)
    struct.pack_into('>I', data, TABLE + 72, 0xFF)
    point(ENVS, ENV0)
    point(ENVS + 4, ENV1)
    point(ENV0, J2)
    struct.pack_into('>f', data, ENV0 + 4, 1.0)
    point(ENV1, J1)
    struct.pack_into('>f', data, ENV1 + 4, 0.5)
    point(ENV1 + 8, J2)
    struct.pack_into('>f', data, ENV1 + 12, 0.5)
    for k, (p, n) in enumerate((((0.25, 0.5, 0.0), (0.0, 1.0, 0.0)), ((0.125, 1.0, 0.0), (1.0, 0.0, 0.0)),
                                ((-0.25, 0.5, 0.125), (0.0, 0.0, 1.0)))):
        struct.pack_into('>3h', data, POSITIONS + 6 * k, *[round(x * (1 << POS_SCALE)) for x in p])
        struct.pack_into('>3h', data, NORMALS + 6 * k, *[min(32767, round(x * (1 << NRM_SCALE))) for x in n])
    listing = struct.pack('>BH', 0x90, 3)
    for pnmtx, i in zip((0, 3, 0), indices):
        listing += struct.pack('>BHH', pnmtx, i, i)
    data[LIST:LIST + len(listing)] = listing
    strings, roots = b'PlyTest5K_Share_joint\0', struct.pack('>2I', J0, 0)
    body = bytes(data) + struct.pack(f'>{len(pointers)}I', *sorted(pointers)) + roots + strings
    return struct.pack('>5I', 0x20 + len(body), len(data), len(pointers), 1, 0) + bytes(12) + body


OURS = [(0, 0, 0, 1, 1, 1, 0, 0, 0), (0, 0, 0, 1, 1, 1, 0, 1, 0), (0, 0, 0.3, 1, 1, 1, 0, 1, 0)]
THEIRS = [(0, 0, 0, 1, 1, 1, 0, 0, 0), (0, 0, 0, 1, 1, 1, 0.2, 1.1, 0), (0.1, 0, 0.5, 1, 1, 1, 0, 0.9, 0.05)]


def drawn(raw):
    """Every vertex's position and normal in the rest pose, drawn as the game draws an envelope mesh: one joint's
    matrix alone for a one-joint envelope, the weighted sum of matrix times inverse bind otherwise."""
    d = Dat(raw)
    rows = rv.skeleton(d)
    worlds = rv.worlds(rows, [r[3] for r in rows])

    def ib(k):
        m = struct.unpack_from('>12f', d.data, d.ptr(rows[k][0] + 0x38))
        return [list(m[0:4]), list(m[4:8]), list(m[8:12])]
    out = []
    for k, (pnmtx, i) in enumerate(zip((0, 3, 0), struct.unpack_from('>xxxBHHBHHBHH', d.data, LIST)[1::3])):
        p = [v / (1 << POS_SCALE) for v in struct.unpack_from('>3h', d.data, POSITIONS + 6 * i)]
        n = [v / (1 << NRM_SCALE) for v in struct.unpack_from('>3h', d.data, NORMALS + 6 * i)]
        if pnmtx == 0:
            m = worlds[2]
        else:
            a, b = rv.compose(worlds[1], ib(1)), rv.compose(worlds[2], ib(2))
            m = [[0.5 * x + 0.5 * y for x, y in zip(r, s)] for r, s in zip(a, b)]
        out.append((rv.point(m, p), rv.normal(m, n)))
    return out


class RestValueTests(unittest.TestCase):
    def test_every_joint_takes_the_donors_rest_values_and_the_model_stays_put(self):
        ours, theirs = costume(OURS), costume(THEIRS)
        fitted, summary = rv.fit(ours, theirs)
        d, v, before = Dat(fitted), Dat(theirs), Dat(ours)
        self.assertEqual([r[3] for r in rv.skeleton(d)], [r[3] for r in rv.skeleton(v)])
        self.assertEqual([r[2] for r in rv.skeleton(d)], [r[2] for r in rv.skeleton(before)])
        self.assertEqual(summary['rest_values_copied'], 2)
        self.assertEqual(summary['joints_moved'], 2)
        self.assertEqual(summary['inverse_binds'], 2)
        self.assertEqual((summary['positions'], summary['normals']), (2, 2))     # the blended vertex stays as stored
        step = 1 / (1 << POS_SCALE)
        for (p, n), (q, m) in zip(drawn(ours), drawn(fitted)):
            self.assertLess(max(abs(a - b) for a, b in zip(p, q)), step)
            na, nb = math.sqrt(sum(x * x for x in n)), math.sqrt(sum(x * x for x in m))
            self.assertGreater(sum(a * b for a, b in zip(n, m)) / (na * nb), 0.99999)
        # nothing but rest values, the moved joints' inverse binds and the single-joint vertices changed
        changed = {i for i, (a, b) in enumerate(zip(Dat(ours).data, d.data)) if a != b}
        allowed = set()
        for j in (J1, J2):
            allowed |= set(range(j + 0x14, j + 0x38))
        allowed |= set(range(IBS + 0x30, IBS + 0x90))
        for k in (0, 2):
            allowed |= set(range(POSITIONS + 6 * k, POSITIONS + 6 * k + 6)) | set(range(NORMALS + 6 * k, NORMALS + 6 * k + 6))
        self.assertTrue(changed <= allowed, sorted(changed - allowed))
        self.assertEqual(len(fitted), len(ours))

    def test_the_bind_pose_is_kept_even_where_the_inverse_binds_were_not_the_rest_pose(self):
        posed = [(0, 0, 0, 1, 1, 1, 0, 0, 0), (0.2, 0, 0, 1, 1, 1, 0, 1, 0), (0, 0, 0.3, 1, 1, 1, 0, 1, 0)]
        ours = costume(posed, ib_from=OURS)
        fitted, _ = rv.fit(ours, costume(THEIRS))
        for (p, _), (q, _) in zip(drawn(ours), drawn(fitted)):
            self.assertLess(max(abs(a - b) for a, b in zip(p, q)), 1 / (1 << POS_SCALE))

    def test_a_costume_with_the_donors_values_comes_back_unchanged(self):
        ours = costume(OURS)
        fitted, summary = rv.fit(ours, costume(OURS, ib_from=THEIRS))
        self.assertEqual(fitted, ours)
        self.assertEqual(summary['joints_moved'], 0)

    def test_an_entry_drawn_under_two_bindings_cannot_follow_a_joint(self):
        shared = costume(OURS, indices=(0, 0, 2))      # vertex 1 (blended) reuses vertex 0's (joint 2) entries
        with self.assertRaisesRegex(ValueError, 'several joints'):
            rv.fit(shared, costume(THEIRS))
        # where no joint moves, sharing is harmless
        self.assertEqual(rv.fit(shared, costume(OURS, ib_from=THEIRS))[0], shared)

    def test_another_tree_is_refused(self):
        ours = bytearray(costume(OURS))
        d = Dat(ours)
        flat = bytearray(d.raw)
        struct.pack_into('>I', flat, 0x20 + J1 + 8, 0)       # J2 no longer under J1 ...
        struct.pack_into('>I', flat, 0x20 + J1 + 0x0C, J2)   # ... but its sibling (both relocated fields)
        relocs = sorted((d.relocations - {J1 + 8}) | {J1 + 0x0C})
        body = bytes(flat[0x20:0x20 + len(d.data)]) + struct.pack(f'>{len(relocs)}I', *relocs) + d.tail
        other = struct.pack('>5I', 0x20 + len(body), len(d.data), len(relocs), 1, 0) + bytes(12) + body
        with self.assertRaisesRegex(ValueError, 'another joint tree'):
            rv.fit(bytes(ours), other)

    def test_sine_and_cosine_match_the_library_to_the_last_bit_or_so(self):
        rng = random.Random(7)
        for x in [rng.uniform(-40, 40) for _ in range(2000)] + [0.0, -0.0, math.pi, -math.pi / 2, 1e-9]:
            s, c = rv.sincos(x)
            self.assertLess(abs(s - math.sin(x)), 4e-16)
            self.assertLess(abs(c - math.cos(x)), 4e-16)

    def test_captain_falcons_slots_follow_vanillas_colour_order(self):
        files = rv.donors('CaptainFalcon')
        self.assertEqual(files, ('PlCaNr.dat', 'PlCaGy.dat', 'PlCaRe.usd', 'PlCaWh.dat', 'PlCaGr.dat', 'PlCaBu.dat'))
        self.assertEqual([rv.donor_for(files, k) for k in (0, 3, 5, 6)],
                         ['PlCaNr.dat', 'PlCaWh.dat', 'PlCaBu.dat', 'PlCaNr.dat'])
        self.assertTrue(set(files) <= set(NAMES))

    def test_every_fighter_has_its_vanilla_colours_and_clones_none(self):
        from pokemelee.portraits import CODES
        for fighter, code in CODES.items():
            files = rv.donors(fighter)
            self.assertGreaterEqual(len(files), 4, fighter)
            self.assertTrue(all(f[2:4] == code for f in files), fighter)
            self.assertTrue(set(files) <= set(NAMES), fighter)
        self.assertEqual(len(rv.donors('Pichu', 'Pichu')), 4)
        self.assertEqual(rv.donors('Pichu', 'Plusle'), ())
        self.assertEqual(rv.donors('Pichu', 'Minun'), ())

    def test_blazikens_slots_and_team_indices_are_vanillas(self):
        from pokemelee.assembly import team_slots
        from pokemelee.catalog import load
        spec = load('recolors.json')['Blaziken']
        colours = ['default', *spec['colours']]
        self.assertEqual(len(colours), len(rv.donors('CaptainFalcon')))
        self.assertEqual(team_slots(spec, colours, 'CaptainFalcon'), {'red': 2, 'blue': 5, 'green': 4})
        self.assertEqual(rv.team_indices('CaptainFalcon'), {'red': 2, 'blue': 5, 'green': 4})
        self.assertEqual(spec['colours']['red'], 'keep')                     # red team: the default look
        self.assertEqual(spec['colours']['green-team'], {'as': 'green'})
        with self.assertRaisesRegex(ValueError, 'Teams costume indices'):
            team_slots({**spec, 'teams': {}}, colours, 'CaptainFalcon')    # by colour name: green would be 3
        self.assertEqual(team_slots({}, ['default', 'shiny', 'red', 'blue', 'green'], 'Fox'),
                         {'red': 2, 'blue': 3, 'green': 4})                # not checked: no entry for Fox

    def test_packaging_fits_each_falcon_slot_to_its_colour_and_leaves_others(self):
        from pokemelee.costumes import fit_rest_values
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            files = tmp / 'files'
            files.mkdir()
            colours = {'PlCaNr.dat': OURS, 'PlCaGy.dat': THEIRS, 'PlCaRe.usd': [OURS[0], THEIRS[1], OURS[2]],
                       'PlCaWh.dat': [OURS[0], OURS[1], THEIRS[2]]}
            for name, srt in colours.items():
                (files / name).write_bytes(costume(srt))
            for name in ('PlFxNr.dat', 'PlFxOr.dat'):              # Fox's colours: colour 0's values, nothing moves
                (files / name).write_bytes(costume(OURS))
            jobs = []
            for mon, fighter, slots in (('Blaziken', 'CaptainFalcon', 4), ('Quilava', 'Fox', 2), ('Plusle', 'Pichu', 2)):
                for k in range(slots):
                    folder = tmp / mon / str(k)
                    folder.mkdir(parents=True)
                    (folder / 'in.dat').write_bytes(costume(OURS))
                    jobs.append((mon, {'fighter': fighter}, None, {'dat': folder / 'in.dat'}, folder))
            fit_rest_values(jobs, files)                             # Plusle, a clone, reads no Pichu file
            for (mon, row, _, choice, folder), name in zip(jobs, list(colours) + [None] * 4):
                rows = rv.skeleton(Dat(choice['dat'].read_bytes()))
                if name is None or colours[name] == OURS:            # nothing to move: the source stays the slot's
                    self.assertEqual(choice['dat'], folder / 'in.dat')
                    self.assertFalse((folder / 'rest.dat').exists())
                    continue
                self.assertEqual(choice['dat'], folder / 'rest.dat')
                self.assertEqual([r[3] for r in rows], [r[3] for r in rv.skeleton(Dat((files / name).read_bytes()))])
            (files / 'PlCaWh.dat').unlink()
            for job in jobs[:4]:
                job[3]['dat'] = job[4] / 'in.dat'
            with self.assertRaisesRegex(ValueError, 'lack PlCaWh.dat'):
                fit_rest_values(jobs[:4], files)


if __name__ == '__main__':
    unittest.main()
