import struct
import unittest

try:
    from pokemelee.art import decode, stock_icon
except ImportError:
    decode = None


@unittest.skipIf(decode is None, "install the art extra for image tests")
class ArtTests(unittest.TestCase):
    def test_rgba8_tile_channels_and_crop(self):
        data = bytearray(0x80)
        struct.pack_into(">HHB", data, 0, 2, 3, 32)
        data += bytes([255, 10] * 16 + [20, 30] * 16)
        image = decode(data)
        self.assertEqual(image.size, (2, 3))
        self.assertEqual(image.getpixel((1, 2)), (10, 20, 30, 255))

    def test_rgb5a3_channels(self):
        data = bytearray(0x80)
        struct.pack_into(">HHB", data, 0, 4, 4, 16)
        data += struct.pack(">16H", *([0xFC00] * 16))
        self.assertEqual(decode(data).getpixel((0, 0)), (255, 0, 0, 255))

    def test_truncated_texture_rejected(self):
        data = bytearray(0x80)
        struct.pack_into(">HHB", data, 0, 4, 4, 32)
        with self.assertRaisesRegex(ValueError, "Truncated"):
            decode(data)

    def test_stock_crop_and_palette(self):
        from PIL import Image
        image = Image.new("RGBA", (8, 8))
        image.paste((200, 30, 10, 255), (3, 1, 5, 7))
        result = stock_icon(image)
        self.assertEqual(result.size, (6, 6))
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((2, 0)), (200, 30, 10, 255))
