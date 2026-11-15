"""Export failure cases plus an opt-in real xdelta round trip on synthetic ISOs."""
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from pokemelee.export import export_artifacts, find_xdelta, fingerprint
from test_builder import LocalTest, disc_bytes


class ExportTests(LocalTest):
    def setUp(self):
        super().setUp()
        self.base = self.root / "original Melee.iso"
        self.built = self.root / "built Pokemelee.iso"
        self.base.write_bytes(disc_bytes())
        data = bytearray(disc_bytes())
        data[0x1000:0x1005] = b"world"
        self.built.write_bytes(data)
        self.output = self.root / "export"
        self.fake = self.root / "fake-tool"
        self.fake.write_bytes(b"synthetic fake executable")

    def fake_run(self, executable, args):
        if args[0] == "-V":
            return "Xdelta synthetic test double"
        shutil.copyfile(args[-2], args[-1])
        return ""

    def export(self):
        return export_artifacts(self.base, self.built, self.output, xdelta=self.fake)

    def test_export_keeps_both_outputs_and_base_fingerprint(self):
        before = fingerprint(self.base), fingerprint(self.built)
        with patch("pokemelee.export._run", side_effect=self.fake_run):
            result = self.export()
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ["pokemelee.iso", "pokemelee.xdelta", "receipt.json"])
        self.assertEqual(result["inputs"]["melee"]["sha256"], before[0]["sha256"])
        self.assertEqual(fingerprint(self.output / "pokemelee.iso"), before[1])
        self.assertEqual((fingerprint(self.base), fingerprint(self.built)), before)
        self.assertTrue(result["patch_verified"])

    def test_decode_mismatch_does_not_publish_pair(self):
        def corrupt(executable, args):
            if args[0] == "-d":
                Path(args[-1]).write_bytes(b"bad decoded output")
                return ""
            return self.fake_run(executable, args)
        with patch("pokemelee.export._run", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "verification failed"):
                self.export()
        self.assertEqual([p.name for p in self.output.iterdir()], ["failed.json"])

    def test_failed_encoder_does_not_publish_pair(self):
        with patch("pokemelee.export._run", side_effect=["Xdelta test", ValueError("encoder failure")]):
            with self.assertRaisesRegex(ValueError, "encoder failure"):
                self.export()
        self.assertEqual([p.name for p in self.output.iterdir()], ["failed.json"])

    def test_never_overwrites_existing_output(self):
        self.output.mkdir()
        keep = self.output / "pokemelee.iso"
        keep.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.export()
        self.assertEqual(keep.read_bytes(), b"keep")

    def test_base_and_built_cannot_be_same_file(self):
        with self.assertRaisesRegex(ValueError, "different"):
            export_artifacts(self.base, self.base, self.output, xdelta=self.fake)
        self.assertFalse(self.output.exists())

    def test_unchanged_base_is_not_a_build(self):
        shutil.copyfile(self.base, self.built)
        with patch("pokemelee.export._run", return_value="Xdelta test"):
            with self.assertRaisesRegex(ValueError, "identical"):
                self.export()
        self.assertFalse(self.output.exists())

    def test_wrong_base_version_rejected(self):
        data = bytearray(self.base.read_bytes())
        data[7] = 1
        self.base.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.export()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(os.environ.get("POKEMELEE_TEST_XDELTA") == "1", "set POKEMELEE_TEST_XDELTA=1 with xdelta available")
    def test_real_xdelta_round_trip(self):
        result = export_artifacts(self.base, self.built, self.output, xdelta=find_xdelta())
        self.assertTrue(result["patch_verified"])
        self.assertEqual((self.output / "pokemelee.xdelta").read_bytes()[:3], bytes.fromhex("d6c3c4"))
        self.assertEqual(fingerprint(self.output / "pokemelee.iso"), fingerprint(self.built))
        self.assertTrue(json.loads((self.output / "receipt.json").read_text())["complete"])
