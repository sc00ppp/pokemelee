import struct
import unittest

from pokemelee.cries import dsp, sound_samples


class CryTests(unittest.TestCase):
    def test_dsp_signed_nibbles_and_sample_count(self):
        frame = bytes([0, 0x17, 0x8F, 0, 0, 0, 0, 0])
        self.assertEqual(struct.unpack("<4h", dsp(frame, 4, [(0, 0)] * 8)), (1, 7, -8, -1))

    def test_dsp_history_crosses_frame_boundary(self):
        frame = bytes([0, 0x10, 0, 0, 0, 0, 0, 0])
        samples = struct.unpack("<15h", dsp(frame + bytes(8), 15, [(2048, 0)] * 8))
        self.assertEqual(samples, (1,) * 15)

    def test_dsp_saturates_instead_of_wrapping(self):
        frame = bytes([15, 0x78, 0, 0, 0, 0, 0, 0])
        self.assertEqual(struct.unpack("<2h", dsp(frame, 2, [(0, 0)] * 8)), (32767, -32768))

    def test_dsp_rejects_short_input_and_bad_predictor(self):
        for frame, count in [(bytes(7), 1), (bytes(8), 15), (bytes([0x80]) + bytes(7), 1)]:
            with self.assertRaises(ValueError):
                dsp(frame, count, [(0, 0)] * 8)

    def test_sound_lookup_reads_macro_start_sample(self):
        pool = bytearray(48)
        struct.pack_into(">I", pool, 0, 16)
        struct.pack_into(">IHH", pool, 16, 16, 23, 0)
        pool[24:28] = b"\x00\x00\x35\x10"
        struct.pack_into(">I", pool, 32, 0xFFFFFFFF)
        project = bytearray(64)
        struct.pack_into(">IHH8I", project, 0, 0xFFFFFFFF, 2, 1, 0, 0, 0, 0, 0, 40, 0, 0)
        struct.pack_into(">H", project, 40, 1)
        struct.pack_into(">HH", project, 44, 12, 23)
        self.assertEqual(sound_samples(project, pool), {12: 53})
        pool[27] = 0
        with self.assertRaisesRegex(ValueError, "exactly one sample"):
            sound_samples(project, pool)


if __name__ == "__main__":
    unittest.main()
