"""Synthetic disc/archive fixtures only. No proprietary data in tests."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pokemelee import cli, fsys, runtime
from pokemelee.catalog import art_indices, load, plan
from pokemelee.disc import Disc, safe_name
from pokemelee.extract import extract


def disc_bytes(role="melee", name="hello.bin"):
    blob = bytearray(0x1600)
    blob[:8] = b"GALE01\0\2" if role == "melee" else b"GC6E01\0\0"
    blob[0x1C:0x20] = bytes.fromhex("c2339f3d")
    blob[0x20:0x29] = b"Synthetic"
    strings = b"\0folder\0" + name.encode() + b"\0root.bin\0"
    table = b"".join(struct.pack(">III", *row) for row in [
        (0x1000000, 0, 4), (0x1000001, 0, 3), (8, 0x1000, 5),
        (8 + len(name) + 1, 0x1010, 3)]) + strings
    struct.pack_into(">II", blob, 0x424, 0x500, len(table))
    blob[0x500:0x500 + len(table)] = table
    blob[0x1000:0x1005] = b"hello"
    blob[0x1010:0x1013] = b"bye"
    return bytes(blob)


def fsys_bytes(name="sample", payload=b"hello", compressed=False):
    raw = b"LZSS" + bytes(12) + b"\xff" + payload if compressed else payload
    data = bytearray(0x100) + raw
    data[:4] = b"FSYS"
    struct.pack_into(">I", data, 0xC, 1)
    struct.pack_into(">I", data, 0x60, 0x70)
    words = [0x1200, 0x100, len(payload), 0, 0, len(raw), 0, 0, 0, 0xB0, 0, 0]
    struct.pack_into(">12I", data, 0x70, *words)
    data[0xB0:0xB0 + len(name) + 1] = name.encode() + b"\0"
    return bytes(data)


class LocalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def disc(self, role="melee", **kwargs):
        path = self.root / (role + ".iso")
        path.write_bytes(disc_bytes(role, **kwargs))
        return Disc(path, role)


class DiscTests(LocalTest):
    def test_nested_fst_and_extraction_preserve_input(self):
        disc = self.disc()
        before = disc.path.read_bytes()
        self.assertEqual(list(disc.entries), ["folder/hello.bin", "root.bin"])
        result = extract(disc, self.root / "out", ["folder/hello.bin"])
        self.assertEqual((self.root / "out/folder/hello.bin").read_bytes(), b"hello")
        self.assertEqual(result["outputs"][0]["sha256"], hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(disc.path.read_bytes(), before)

    def test_wrong_region_and_revision(self):
        for at, value in [(3, ord("P")), (7, 1)]:
            with self.subTest(at=at):
                data = bytearray(disc_bytes())
                data[at] = value
                file = self.root / "wrong.iso"
                file.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "Unsupported"):
                    Disc(file, "melee")

    def test_truncated_file_rejected(self):
        data = bytearray(disc_bytes())
        struct.pack_into(">I", data, 0x500 + 2 * 12 + 8, 999999)
        file = self.root / "bad.iso"
        file.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Truncated"):
            Disc(file, "melee")

    def test_bad_directory_extent_rejected(self):
        data = bytearray(disc_bytes())
        struct.pack_into(">I", data, 0x500 + 12 + 8, 5)
        file = self.root / "bad.iso"
        file.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "directory"):
            Disc(file, "melee")

    def test_path_traversal_rejected(self):
        for name in ("..", "../escape", "a\\b", "C:escape", "NUL.txt", "bad.", "a?b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.disc(name=name)

    def test_existing_output_is_untouched(self):
        disc = self.disc()
        target = self.root / "out"
        target.mkdir()
        (target / "important.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            extract(disc, target, ["root.bin"])
        self.assertEqual([p.name for p in target.iterdir()], ["important.txt"])

    def test_missing_file_fails_before_output(self):
        with self.assertRaisesRegex(ValueError, "Missing"):
            extract(self.disc(), self.root / "out", ["absent"])
        self.assertFalse((self.root / "out").exists())

    def test_failed_extraction_never_writes_complete_receipt(self):
        disc = self.disc()
        with patch.object(disc, "read", side_effect=ValueError("changed")):
            with self.assertRaises(ValueError):
                extract(disc, self.root / "out", ["root.bin"])
        self.assertTrue((self.root / "out/failed.json").exists())
        self.assertFalse((self.root / "out/receipt.json").exists())


class FsysTests(unittest.TestCase):
    def test_raw_and_compressed(self):
        for compressed in (False, True):
            self.assertEqual(list(fsys.entries(fsys_bytes(compressed=compressed))), [("00_sample.t12", b"hello")])

    def test_overlapping_lzss_match(self):
        self.assertEqual(fsys.lzss(b"\x01A\xee\xf3", 7), b"AAAAAAA")

    def test_truncated_and_oversized_lzss(self):
        for data, size in [(b"", 2), (b"\xff", 2), (b"\0\0", 2), (b"\x01A\xee\xf3", 3)]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                fsys.lzss(data, size)

    def test_unsafe_name_and_payload_bounds(self):
        for data in (fsys_bytes(name="../bad"), fsys_bytes()[:-1]):
            with self.assertRaises(ValueError):
                list(fsys.entries(data))


class RuntimeTests(LocalTest):
    def archive(self, entries=None, sha=None):
        path = self.root / "runtime.zip"
        with zipfile.ZipFile(path, "w") as dest:
            for name, data in entries or [("tool.exe", b"synthetic-tool")]:
                dest.writestr(name, data)
        self.pin = {"tools": {"test": {"repo": "example/fork", "tag": "v1", "platforms": {
            "win-x64": {"asset": "runtime.zip", "sha256": sha or hashlib.sha256(path.read_bytes()).hexdigest(), "required": ["tool.exe"]}}}}}
        self.addCleanup(patch.stopall)
        patch("pokemelee.runtime.lock", return_value=self.pin).start()
        return path

    def test_valid_install_receipt(self):
        path = self.archive()
        result = runtime.install("test", "win-x64", path, self.root / "out")
        self.assertTrue(result["complete"])
        self.assertEqual((self.root / "out/tool.exe").read_bytes(), b"synthetic-tool")

    def test_mismatch_writes_nothing(self):
        path = self.archive(sha="0" * 64)
        with self.assertRaisesRegex(ValueError, "checksum"):
            runtime.install("test", "win-x64", path, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_missing_required_file(self):
        path = self.archive([("other.txt", b"x")])
        with self.assertRaisesRegex(ValueError, "missing required"):
            runtime.install("test", "win-x64", path, self.root / "out")

    def test_traversal_rejected_before_unpack(self):
        path = self.archive([("../escape.txt", b"x"), ("tool.exe", b"x")])
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            runtime.install("test", "win-x64", path, self.root / "out")
        self.assertFalse((self.root / "escape.txt").exists())
        self.assertFalse((self.root / "out").exists())

    def test_symlink_rejected(self):
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        path = self.archive([(link, b"elsewhere"), ("tool.exe", b"x")])
        with self.assertRaisesRegex(ValueError, "special file"):
            runtime.install("test", "win-x64", path, self.root / "out")

    def test_public_fetch_uses_exact_release_and_verifies(self):
        path = self.archive()
        with patch("urllib.request.urlopen", return_value=io.BytesIO(path.read_bytes())) as request:
            runtime.fetch("test", "win-x64", self.root / "out")
        url = request.call_args.args[0].full_url
        self.assertEqual(url, "https://github.com/example/fork/releases/download/v1/runtime.zip")
        self.assertTrue((self.root / "out/receipt.json").exists())


class ReadinessTests(LocalTest):
    def test_build_refuses_partial_iso(self):
        melee, colo = self.disc(), self.disc("colosseum")
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            code = cli.main(["build", "--melee", str(melee.path), "--colosseum", str(colo.path), "--out", str(self.root / "out.iso")])
        self.assertEqual(code, 2)
        self.assertIn("No output written", errors.getvalue())
        self.assertFalse((self.root / "out.iso").exists())

    def test_accepted_roster_and_stages_recorded(self):
        self.assertEqual(len(art_indices()), 29)
        self.assertEqual(len(load("stages.json")["stages"]), 6)
        self.assertFalse(plan()["iso_build_ready"])
        self.assertIn("cast-models", plan()["blocking_steps"])


if __name__ == "__main__":
    unittest.main()
