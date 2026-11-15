"""Synthetic archive tests; optional full rebuild uses only user-supplied discs."""
import os
from pathlib import Path
import struct
import tempfile
import unittest

from pokemelee.hsd import sanitize_stage
from pokemelee.stages import build_stages


def archive():
    body = bytearray(0x100)
    struct.pack_into(">II", body, 8, 0x50, 1)  # map_head's model-group array
    struct.pack_into(">I", body, 0x54, 0x60)
    struct.pack_into(">I", body, 0x60, 0xFFFFFFFF)
    struct.pack_into(">I", body, 0x90, 0xFFFFFFFF)
    entries = struct.pack(">6I", 0, 0, 0x54, 9, 0x90, 17)
    strings = b"map_head\0removed\0kept\0"
    size = 0x20 + len(body) + len(entries) + len(strings)
    return struct.pack(">5I", size, len(body), 0, 1, 2) + bytes(12) + body + entries + strings


class StageTests(unittest.TestCase):
    def test_resolves_only_model_group_externs(self):
        source = archive()
        result = sanitize_stage(source)
        self.assertEqual(len(result), len(source) - 8)
        self.assertEqual(struct.unpack_from(">I", result)[0], len(result))
        self.assertEqual(struct.unpack_from(">I", result, 16)[0], 1)
        self.assertEqual(result[0x74:0x78], bytes(4))
        self.assertEqual(result[0x80:0x84], bytes(4))
        self.assertEqual(result[0xB0:0xB4], b"\xff" * 4)
        self.assertTrue(result.endswith(b"map_head\0removed\0kept\0"))
        self.assertEqual(sanitize_stage(result), result)

    def test_rejects_cyclic_external_chain(self):
        data = bytearray(archive())
        struct.pack_into(">I", data, 0x80, 0x54)
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            sanitize_stage(data)

    def test_rejects_truncated_archive(self):
        for data in (b"", archive()[:-1]):
            with self.assertRaises(ValueError):
                sanitize_stage(data)

    def test_rejects_bad_group_extent(self):
        data = bytearray(archive())
        struct.pack_into(">I", data, 0x2C, 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "model-group"):
            sanitize_stage(data)

    def test_invalid_selection_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            with self.assertRaisesRegex(ValueError, "Unknown stage recipe"):
                build_stages(None, None, out, tmp, ["missing"])
            self.assertFalse(out.exists())

    @unittest.skipUnless(os.environ.get("POKEMELEE_TEST_MELEE") and os.environ.get("POKEMELEE_TEST_COLOSSEUM"),
                         "set local disc paths to run the two-profile cold stage build")
    def test_real_cold_build_both_profiles(self):
        from pokemelee.disc import Disc
        melee = Disc(os.environ["POKEMELEE_TEST_MELEE"], "melee")
        colo = Disc(os.environ["POKEMELEE_TEST_COLOSSEUM"], "colosseum")
        runtime = os.environ.get("POKEMELEE_TEST_RUNTIME", "runtime")
        with tempfile.TemporaryDirectory() as tmp:
            for profile in ("normal", "animelee"):
                result = build_stages(melee, colo, Path(tmp) / profile, runtime, profile=profile)
                self.assertTrue(result["complete"])
                self.assertEqual(len(result["outputs"]), 11)


if __name__ == "__main__":
    unittest.main()
