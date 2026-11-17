"""How the AniMelee outline is stored: dropping what nothing reads, one copy of each piece, lists without normals,
16-bit position slices, and a stage shell's own small list. Synthetic archives only."""
import struct
import unittest

from pokemelee import anime_cast, anime_stage
from pokemelee.dat import Dat
from pokemelee.display_list import ATTR_SIZE, END, NRM, POS, attrs

TEX0 = 13
INDEX16, DIRECT = 3, 1


def archive(data, pointers, roots=()):
    """A Dat from a data block, its {field: target} pointers and [(name, offset)] roots."""
    data = bytearray(data)
    for at, target in pointers.items():
        struct.pack_into('>I', data, at, target & 0xFFFFFFFF)
    strings, table = b'', b''
    for name, offset in roots:
        table += struct.pack('>2I', offset, len(strings))
        strings += name.encode() + b'\0'
    body = bytes(data) + struct.pack(f'>{len(pointers)}I', *sorted(pointers)) + table + strings
    return Dat(struct.pack('>5I', 0x20 + len(body), len(data), len(pointers), len(roots), 0) + bytes(12) + body)


def row(name, kind, comp=INDEX16, scale=0, stride=0):
    return struct.pack('>4IBBHI', name, kind, 1, comp, scale, 0, stride, 0)


def mesh(rows, vertices, op=0x98):
    """A PObj at 0 with its attribute table at 32 and its display list at 256: ``rows`` [(name, kind)], each vertex
    the bytes of its attributes in order. Arrays (dummy) at 512."""
    data = bytearray(1024)
    pointers = {8: 32, 16: 256}
    at = 32
    for name, kind in rows:
        data[at:at + ATTR_SIZE] = row(name, kind)
        if kind != DIRECT:
            pointers[at + 20] = 512
        at += ATTR_SIZE
    struct.pack_into('>I', data, at, END)
    listing = struct.pack('>BH', op, len(vertices)) + b''.join(vertices)
    data[256:256 + len(listing)] = listing
    struct.pack_into('>H', data, 14, -(-len(listing) // 32))
    return archive(data, pointers)


class DropTests(unittest.TestCase):
    def test_whole_blocks_go_and_every_pointer_and_root_moves_with_what_stays(self):
        d = archive(bytes(160), {0: 96, 100: 0, 4: 128}, [('top', 96)])
        freed = d.drop([(32, 96)])
        self.assertEqual(freed, 64)
        self.assertEqual(len(d.data), 96)
        self.assertEqual((d.ptr(0), d.ptr(36), d.ptr(4)), (32, 0, 64))
        self.assertEqual(d.roots, [('top', 32)])
        self.assertEqual(d.relocations, {0, 4, 36})

    def test_a_part_block_stays_but_its_fields_go(self):
        d = archive(bytes(128), {40: 0, 0: 96}, [])
        d.drop([(36, 100)])                 # only 64..96 is a whole block
        self.assertEqual(len(d.data), 96)
        self.assertNotIn(40, d.relocations)
        self.assertEqual(d.u32(40), 0)
        self.assertEqual(d.ptr(0), 64)      # what stood just past the block

    def test_a_slice_pointer_moves_with_its_slice(self):
        d = archive(bytes(192), {0: 160 - 48}, [])     # where entry 0 of a 6-byte table would be, 8 entries before 160
        d.drop([(64, 128)], {0: 160})
        self.assertEqual(d.ptr(0), 96 - 48)

    def test_a_pointer_into_dropped_data_is_an_error(self):
        d = archive(bytes(128), {0: 64}, [])
        with self.assertRaises(ValueError):
            d.drop([(32, 96)])


class CastTests(unittest.TestCase):
    def test_a_list_without_normals_keeps_the_rest_and_puts_the_colour_after_the_position(self):
        d = mesh([(0, DIRECT), (POS, INDEX16), (NRM, INDEX16), (TEX0, INDEX16)],
                 [bytes((3, 0, i, 0, 9, 0, 20 + i)) for i in range(3)])
        table = attrs(d, 0)
        listing, slot = anime_cast.with_colour(d, 0, table, normals=False)
        self.assertEqual(slot, 2)
        self.assertEqual(listing[:3], b'\x98\x00\x03')
        self.assertEqual(listing[3:9], bytes((3, 0, 0, 0, 0, 20)))       # matrix, position, colour 0, texture: no normal
        self.assertEqual(len(listing) % 32, 0)
        with_normals, slot = anime_cast.with_colour(d, 0, table)
        self.assertEqual((slot, with_normals[3:11]), (3, bytes((3, 0, 0, 0, 9, 0, 0, 20))))

    def test_a_table_reads_its_positions_from_a_slice(self):
        d = mesh([(POS, INDEX16), (TEX0, INDEX16)], [bytes(4)] * 3)
        payload, pointers = anime_cast.attr_table(d, attrs(d, 0), 1, 700, (640, 16, 10))
        position = payload[:ATTR_SIZE]
        self.assertEqual(struct.unpack_from('>I', position, 12)[0], anime_stage.S16)
        self.assertEqual((position[16], struct.unpack_from('>H', position, 18)[0]), (10, 6))
        self.assertEqual(struct.unpack_from('>I', payload, ATTR_SIZE)[0], 11)              # the colour row
        self.assertIn((20, 640, 96), pointers)
        self.assertIn((ATTR_SIZE + 20, 700, 0), pointers)
        self.assertIn((2 * ATTR_SIZE + 20, 512, 0), pointers)                             # the texture, past the colour

    def test_the_same_piece_is_stored_once_and_a_slice_pointer_is_remembered(self):
        d = archive(bytes(64), {}, [])
        store = anime_cast.Store(d)
        a = store.put(bytes(32), [(4, 0, 0)])
        self.assertEqual(store.put(bytes(32), [(4, 0, 0)]), a)
        b = store.put(bytes(32), [(8, 160, 96)])
        self.assertNotEqual(a, b)
        self.assertEqual(d.u32(b + 8), 64)
        self.assertEqual(store.virtual, {b + 8: 160})

    def test_what_still_reads_normals(self):
        data = bytearray(512)
        pointers = {}
        struct.pack_into('>I', data, 4, 2)                          # vertex colours, lights off
        self.assertFalse(anime_cast.reads_normals(archive(data, pointers), 0))
        struct.pack_into('>I', data, 4, 2 | 4)                      # a diffuse light left on
        self.assertTrue(anime_cast.reads_normals(archive(data, pointers), 0))
        struct.pack_into('>I', data, 4, 2)
        pointers[8] = 64                                            # one texture
        struct.pack_into('>I', data, 64 + 0xC, 4)                   # placed by its UVs
        self.assertFalse(anime_cast.reads_normals(archive(data, pointers), 0))
        for flags, source in ((1, 4), (2, 4), (0, 1), (1 << 24, 4)):    # reflection, highlight, by normal, bump
            struct.pack_into('>2I', data, 64 + 0x40, flags, 0)
            struct.pack_into('>I', data, 64 + 0xC, source)
            self.assertTrue(anime_cast.reads_normals(archive(data, pointers), 0))

    def test_ranges_less_what_is_kept(self):
        self.assertEqual(anime_cast.without([(0, 100)], [(10, 20), (50, 120)]), [(0, 10), (20, 50)])
        self.assertEqual(anime_cast.without([(0, 10)], [(0, 10)]), [])


class StageShellTests(unittest.TestCase):
    def test_a_shell_list_holds_its_matrix_indices_and_renumbered_points_only(self):
        vertices = [bytes((6, 0x10, 0x00, 0, 1)), bytes((9, 0x20, 0x00, 0, 2)), bytes((6, 0x10, 0x00, 0, 3))]
        d = mesh([(0, DIRECT), (POS, INDEX16), (NRM, INDEX16)], vertices)
        out = anime_stage.shell_list(d, 0, attrs(d, 0), {0x1000: 0, 0x2000: 1})
        self.assertEqual(out[:9], bytes((0x98, 0, 3, 6, 0, 9, 1, 6, 0)))
        self.assertEqual(len(out) % 32, 0)
        wide = anime_stage.shell_list(d, 0, attrs(d, 0), {0x1000: 0, 0x2000: 300})
        self.assertEqual(wide[3:9], bytes((6, 0, 0, 9, 1, 44)))


if __name__ == '__main__':
    unittest.main()
