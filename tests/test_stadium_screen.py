"""AniMelee leaves Stadium's big screen as it is: the type announcements are pictures, not scenery."""
import struct
import unittest
from types import SimpleNamespace
from unittest import mock

from pokemelee import anime_flat, stages
from pokemelee.datprobe import Image, TexAnimInfo, Tlut, TobjInfo

RGB5A3, TLUT_565 = 5, 1


def rgb5a3(r, g, b):
    return 0x8000 | r << 10 | g << 5 | b


def picture(seed):
    """A 4x4 RGB5A3 picture of sixteen different colours."""
    return struct.pack('>16H', *(rgb5a3((seed + 7 * i) % 32, (3 * seed + 5 * i) % 32, (11 * i + seed) % 32) for i in range(16)))


class KeepTests(unittest.TestCase):
    def setUp(self):
        # data block: picture A at 0, picture B at 32, a 4-entry RGB565 palette at 64
        palette = struct.pack('>4H', 0xF800, 0x07E0, 0x001F, 0xFFFF)
        self.raw = bytes(0x20) + picture(1) + picture(9) + palette
        self.dat = SimpleNamespace(raw=self.raw)
        self.images = {0: Image(0, 0, 4, 4, RGB5A3, None), 32: Image(0, 32, 4, 4, RGB5A3, None)}
        self.tables = {64: Tlut(0, 64, TLUT_565, 4, None)}

    def flat(self, keep=((), ())):
        return bytes(anime_flat.flattened(self.dat, self.images, self.tables, 3, keep=keep))

    def test_kept_pictures_and_palettes_stay_byte_for_byte(self):
        out = self.flat(keep=([32], [64]))
        self.assertEqual(out[0x20 + 32:0x20 + 72], self.raw[0x20 + 32:0x20 + 72])

    def test_the_rest_flattens_as_if_nothing_were_kept(self):
        everything, kept = self.flat(), self.flat(keep=([32], [64]))
        self.assertNotEqual(everything[0x20 + 32:0x20 + 72], self.raw[0x20 + 32:0x20 + 72])      # flattening does move them
        self.assertNotEqual(everything[0x20:0x20 + 32], self.raw[0x20:0x20 + 32])
        self.assertEqual(kept[0x20:0x20 + 32], everything[0x20:0x20 + 32])                     # same palette for the rest


class FakeStage:
    """map_head at 0x100 with two groups; group 1 draws two textures and animates one of them against a third."""
    roots = [('map_head', 0x100)]
    words = {0x108: 0x200, 0x200: 0x400, 0x234: 0x500, 0x23C: 0x600, 0x600: 0x700}

    def ptr(self, off):
        return self.words.get(off)

    def jobj_textures(self, root):
        image = lambda at: Image(0, at, 64, 64, 14, None)
        return {0x400: [TobjInfo(0, 0, image(0x900), None)],
                0x500: [TobjInfo(3, 0, image(0x1000), Tlut(0, 0x2000, 1, 20, None)), TobjInfo(3, 1, image(0x1100), None)]}[root]

    def matanim_texanims(self, root):
        frames = [Image(0, 0x1100, 256, 256, 9, None), Image(0, 0x1200, 256, 256, 9, None), Image(0, None, 0, 0, 0, None)]
        return [TexAnimInfo(3, 1, 0, frames, [Tlut(0, 0x2100, 1, 256, None)])]


class ScreenTests(unittest.TestCase):
    def test_a_group_gives_what_it_draws_and_what_its_animation_swaps_in(self):
        self.assertEqual(anime_flat.group_textures(FakeStage(), 1), ({0x1000, 0x1100, 0x1200}, {0x2000, 0x2100}))
        self.assertEqual(anime_flat.group_textures(FakeStage(), 0), ({0x900}, set()))

    def test_stadium_keeps_its_screen_and_the_wide_picture(self):
        images = {0x40: Image(0, 0x40, 768, 168, 14, None), 0x80: Image(0, 0x80, 64, 64, 14, None)}
        with mock.patch.object(anime_flat, 'stage_parts', return_value=('dat', images, {}, set())), \
                mock.patch.object(anime_flat, 'group_textures', return_value=({0x1000}, {0x2000})) as screen:
            self.assertEqual(stages.stadium_pictures('GrPs.usd'), ([0x40, 0x1000], [0x2000]))
        screen.assert_called_once_with('dat', stages.STADIUM_SCREEN)


if __name__ == '__main__':
    unittest.main()
