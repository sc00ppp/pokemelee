"""The metal and cloak draw of a fighter file: set 3 takes set 0's lookup, set 2 and the metal model are unhooked, and
nothing else moves. AniMelee's PlCo.dat: the shared metal material becomes unlit vertex colour times a flat grey by four
checked value edits, made on the EXPORTED disc (MexCLI writes PlCo.dat anew). Synthetic archives and discs only."""
import hashlib
import json
import os
import stat
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pokemelee import builder
from pokemelee.dat import Dat
from pokemelee.fighter_metal import METAL_MODEL, metal_draws_costume, patch_exported_common, steel_metal

FTDATA, X8, TABLE, BODY0, LOW0, PARTS0, METAL0, BODY1, MODEL, AFTER = (
    0x000, 0x080, 0x0A0, 0x100, 0x120, 0x140, 0x160, 0x180, 0x200, 0x240)


def archive(data, pointers, roots=()):
    """A Dat from a data block, its {field: target} pointers and [(name, offset)] roots."""
    data = bytearray(data)
    for at, target in pointers.items():
        struct.pack_into('>I', data, at, target)
    strings, table = b'', b''
    for name, offset in roots:
        table += struct.pack('>2I', offset, len(strings))
        strings += name.encode() + b'\0'
    body = bytes(data) + struct.pack(f'>{len(pointers)}I', *sorted(pointers)) + table + strings
    return Dat(struct.pack('>5I', 0x20 + len(body), len(data), len(pointers), len(roots), 0) + bytes(12) + body)


def fighter(second_row_body=True):
    """ftData with a metal model, and a two-costume table: costume 0 has all four sets, costume 1 its own set 0 (or
    nothing). The table is followed by the lookups it names."""
    data = bytearray(0x260)
    struct.pack_into('>I', data, X8, 1)                 # one model
    pointers = {FTDATA + 0x08: X8, X8 + 4: TABLE, FTDATA + METAL_MODEL: MODEL, AFTER: MODEL,
                TABLE + 0: BODY0, TABLE + 4: LOW0, TABLE + 8: PARTS0, TABLE + 12: METAL0}
    if second_row_body:
        pointers[TABLE + 16] = BODY1
    return archive(data, pointers, [('ftDataTest', FTDATA), ('other', AFTER)])


class MetalDrawsCostume(unittest.TestCase):
    def test_set_three_shows_set_zero_and_the_metal_model_goes(self):
        d = fighter()
        before = {at: d.ptr(at) for at in d.relocations}
        self.assertEqual(metal_draws_costume(d), 2)
        self.assertEqual(d.ptr(TABLE + 12), BODY0)
        self.assertEqual(d.ptr(TABLE + 16 + 12), BODY1)
        for field in (TABLE + 8, TABLE + 16 + 8, FTDATA + METAL_MODEL):
            self.assertIsNone(d.ptr(field))
            self.assertEqual(d.u32(field), 0)
        kept = {at: v for at, v in before.items() if at not in (TABLE + 8, TABLE + 12, FTDATA + METAL_MODEL)}
        self.assertEqual({at: d.ptr(at) for at in kept}, kept)    # the normal, low and other lookups stay
        self.assertEqual(d.ptr(AFTER), MODEL)                       # data past the table is not a row

    def test_a_row_without_its_own_body_falls_back_like_the_game(self):
        d = fighter(second_row_body=False)
        self.assertEqual(metal_draws_costume(d), 1)
        self.assertIsNone(d.ptr(TABLE + 16 + 12))          # empty, so the game takes costume 0's: set 0 there

    def test_the_file_never_grows(self):
        d = fighter()
        size = len(d.raw)
        metal_draws_costume(d)
        relocations = sorted(d.relocations)
        saved = len(bytes(d.data)) + 4 * len(relocations) + len(d.tail) + 0x20
        # set 2 and the metal model lose their relocations; costume 1's set 3 gains one (it had none of its own)
        self.assertEqual(saved, size - 4)

    def test_a_file_without_ftdata_is_refused(self):
        with self.assertRaises(ValueError):
            metal_draws_costume(archive(bytes(64), {}, [('other', 0)]))


COMMON, JOINT, DOBJ, MOBJ, TOBJ, TOBJ2, TEV = 0x000, 0x080, 0x0C0, 0x0E0, 0x100, 0x200, 0x180
STEEL_FIELDS = set(range(MOBJ + 4, MOBJ + 8)) | set(range(TEV + 8, TEV + 0x14)) | set(range(TEV + 0x1C, TEV + 0x20))


def common(extra_tobj=False, rendermode=0x1C, root='ftLoadCommonData', filler=0):
    """ftLoadCommonData whose entry 20 is the metal joint -> DObj -> MObj (lit) -> one TObj -> its TEV block (off).
    ``filler`` changes bytes the steel edit must not care about, as an exporter's rewrite would."""
    data = bytearray(0x260)
    struct.pack_into('>I', data, MOBJ + 4, rendermode)
    data[TEV + 8:TEV + 12] = bytes.fromhex('8580080f')
    struct.pack_into('>I', data, TEV + 0x14, 0x11223344)       # tev0, not ours to touch
    struct.pack_into('>I', data, 0x240, filler)
    pointers = {COMMON + 4 * 20: JOINT, COMMON + 4 * 3: JOINT, JOINT + 0x10: DOBJ, DOBJ + 8: MOBJ, MOBJ + 8: TOBJ,
                TOBJ + 0x58: TEV}
    if extra_tobj:
        pointers[TOBJ + 4] = TOBJ2
    raw = bytearray(archive(data, pointers, [(root, COMMON)]).raw)
    table = 0x20 + len(data)                          # relocation table out of order, as PlCo.dat's is
    raw[table:table + 4], raw[table + 4:table + 8] = raw[table + 4:table + 8], raw[table:table + 4]
    return Dat(bytes(raw))


def gcm(files):
    """A minimal Melee GCM holding ``files`` {name: bytes}, each at a 32-byte boundary."""
    names = list(files)
    strings = b''.join(n.encode() + b'\0' for n in names)
    fst_at, fst_size = 0x440, 12 * (len(names) + 1) + len(strings)
    at, entries, body = -(-(fst_at + fst_size) // 32) * 32, [struct.pack('>III', 1 << 24, 0, len(names) + 1)], {}
    name_at = 0
    for n in names:
        entries.append(struct.pack('>III', name_at, at, len(files[n])))
        body[at], at, name_at = files[n], -(-(at + len(files[n])) // 32) * 32, name_at + len(n) + 1
    disc = bytearray(at + 32)
    disc[0:8] = b'GALE01' + bytes([0, 2])
    disc[0x1C:0x20] = bytes.fromhex('c2339f3d')
    struct.pack_into('>II', disc, 0x424, fst_at, fst_size)
    disc[fst_at:fst_at + fst_size] = b''.join(entries) + strings
    for offset, data in body.items():
        disc[offset:offset + len(data)] = data
    return bytes(disc)


def plco_bytes(**kw):
    return common(**kw).raw


class SteelMetal(unittest.TestCase):
    def test_four_values_change_and_nothing_else(self):
        d = common()
        before, relocations = bytes(d.data), set(d.relocations)
        steel_metal(d, bytes.fromhex('a0b0c0'))
        self.assertEqual(d.u32(MOBJ + 4), 0x12)                                  # unlit, vertex colour
        self.assertEqual(bytes(d.data[TEV + 8:TEV + 12]).hex(), '0f0f0f80')     # colour = konst
        self.assertEqual(bytes(d.data[TEV + 0x10:TEV + 0x14]).hex(), 'a0b0c0ff')
        self.assertEqual(d.u32(TEV + 0x1C), 0x40000000)                          # colour stage on
        self.assertTrue({i for i, (a, b) in enumerate(zip(before, d.data)) if a != b} <= STEEL_FIELDS)
        self.assertEqual(d.relocations, relocations)

    def test_an_unexpected_file_is_refused_untouched(self):
        for d in (common(rendermode=0x12), common(extra_tobj=True), common(root='other')):
            before = bytes(d.data)
            with self.assertRaises(ValueError):
                steel_metal(d)
            self.assertEqual(bytes(d.data), before)
        d = common()
        steel_metal(d)
        patched = bytes(d.data)
        with self.assertRaises(ValueError):                  # a second run finds the new values, not the old
            steel_metal(d)
        self.assertEqual(bytes(d.data), patched)


class SteelOnTheExportedDisc(unittest.TestCase):
    def test_animelee_changes_only_the_four_values_on_the_disc(self):
        with tempfile.TemporaryDirectory() as folder:
            iso = Path(folder) / 'built.iso'
            iso.write_bytes(gcm({'PlCo.dat': plco_bytes(), 'other.dat': b'x' * 40}))
            before = iso.read_bytes()
            rows = patch_exported_common(iso, 'animelee')
            after = iso.read_bytes()
        start = before.index(plco_bytes())
        changed = {i - start - 0x20 for i, (a, b) in enumerate(zip(before, after)) if a != b}
        self.assertEqual(len(after), len(before))
        self.assertTrue(changed and changed <= STEEL_FIELDS)     # the relocation table keeps its own order too
        plco = after[start:start + len(plco_bytes())]
        self.assertEqual(rows[0]['sha256'], hashlib.sha256(plco).hexdigest())
        self.assertEqual(rows[0]['exported_sha256'], hashlib.sha256(plco_bytes()).hexdigest())

    def test_normal_never_opens_the_disc_for_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            iso = Path(folder) / 'built.iso'
            iso.write_bytes(gcm({'PlCo.dat': plco_bytes()}))
            os.chmod(iso, stat.S_IREAD)
            try:
                self.assertEqual(patch_exported_common(iso, 'normal'), [])
            finally:
                os.chmod(iso, stat.S_IREAD | stat.S_IWRITE)

    def write_disc(self, folder):
        """builder.write_disc with MexCLI replaced by an export that writes PlCo.dat ANEW (other bytes than the
        project's copy), as the real one does; the xdelta packaging is skipped."""
        folder = Path(folder)
        assembled, music = folder / 'animelee-project', folder / 'music'
        (assembled / 'project').mkdir(parents=True)
        music.mkdir()
        (assembled / 'project/project.mexproj').write_text(json.dumps({'fighterSaveMap': {'filePaths': []}}))
        (assembled / 'project/files').mkdir()
        (assembled / 'project/files/PlCo.dat').write_bytes(plco_bytes())
        (assembled / 'installed-components.json').write_text('[]')
        (assembled / 'receipt.json').write_text(json.dumps({'inputs': {'components': {'music': str(music)}}}))
        (music / 'receipt.json').write_text(json.dumps({'outputs': []}))
        movie = b'movie' * 20
        melee = folder / 'melee.iso'
        melee.write_bytes(gcm({'MvOmake15.mth': movie, 'PlCo.dat': plco_bytes()}))

        class Export:
            def __init__(self, *args):
                pass

            def command(self, name, built, timeout=None):
                # MnSlChr.usd: the export check reads the character select's size (its memory budget)
                Path(built).write_bytes(gcm({'MvOmake15.mth': movie, 'PlCo.dat': plco_bytes(filler=0xABCD),
                                             'MnSlChr.usd': b'synthetic-select'}))

        with mock.patch.object(builder, 'Mex', Export), mock.patch.object(builder, 'export_artifacts',
                                                                          lambda *a, **k: {}):
            builder.write_disc(assembled, builder.Disc(melee, 'melee'), folder, 'animelee', folder / 'out')
        return assembled

    def test_the_steel_metal_survives_an_export_that_rewrites_plco(self):
        with tempfile.TemporaryDirectory() as folder:
            assembled = self.write_disc(folder)
            disc = builder.Disc(assembled / 'built.iso', 'melee')
            d = Dat(disc.read('PlCo.dat'))
            checks = json.loads((assembled / 'export-checks.json').read_text())
        self.assertEqual(d.u32(MOBJ + 4), 0x12)                      # steel on the disc that ships
        self.assertEqual(d.u32(0x240), 0xABCD)                       # over the export's own file
        self.assertIn('PlCo.dat', checks['installed_components'])     # and the export check covered it
        self.assertEqual(checks['patched_after_export'][0]['path'], 'PlCo.dat')

    def test_the_export_check_catches_a_patched_file_that_did_not_land(self):
        def patch_then_spoil(iso, profile):
            rows = patch_exported_common(iso, profile)
            data = bytearray(Path(iso).read_bytes())
            data[data.index(bytes.fromhex('0f0f0f80'))] = 0x85
            Path(iso).write_bytes(data)
            return rows
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(builder.fighter_metal, 'patch_exported_common', patch_then_spoil):
                with self.assertRaisesRegex(ValueError, 'patched after the export'):
                    self.write_disc(folder)


if __name__ == '__main__':
    unittest.main()
