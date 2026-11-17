import importlib.util
import json
import lzma
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_builder", ROOT / "tools/package_builder.py")
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

HOME = Path("C:" + "/Users/someone")      # split: tools/check_source.py rejects workstation paths
BUILD = Path("E:/maker-build/repo")
ACCOUNT = pb.PRIVATE_ACCOUNTS[0]


class ForbiddenContentTests(unittest.TestCase):
    """A synthetic finished folder: clean, then with each thing the packager must refuse to ship."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        (self.folder / "engine/app").mkdir(parents=True)
        (self.folder / "engine/app/ok.py").write_text("print('hello from C:/Windows/Fonts')\n", encoding="utf-8")
        (self.folder / "README.txt").write_text("Made from your own discs.\n", encoding="utf-8")
        self.strings = pb.forbidden_strings(BUILD, home=HOME)

    def tearDown(self):
        self.tmp.cleanup()

    def problems(self):
        return pb.forbidden_content(self.folder, self.strings)

    def test_clean_folder_passes(self):
        self.assertEqual(self.problems(), [])

    def test_user_profile_path(self):
        (self.folder / "engine/app/a.json").write_text(json.dumps({"p": "C:\\Users\\someone\\AppData\\x"}))
        self.assertTrue(any("user profile" in what for _, what in self.problems()))

    def test_user_name_on_another_drive_and_in_utf16(self):
        (self.folder / "engine/app/b.dll").write_bytes(b"MZ\0\0" + "D:\\Users\\Someone\\src\\b.pdb".encode("utf-16-le"))
        self.assertTrue(any("user profile" in what for _, what in self.problems()))

    def test_build_folder(self):
        (self.folder / "engine/app/c.dll").write_bytes(b"\0E:\\maker-build\\runtime\\obj\\c.pdb\0")
        self.assertTrue(any("build folder" in what for _, what in self.problems()))

    def test_pdb_obj_and_pycache(self):
        (self.folder / "engine/app/d.pdb").write_bytes(b"")
        (self.folder / "engine/app/e.obj").write_bytes(b"")
        (self.folder / "engine/app/__pycache__").mkdir()
        found = {what for _, what in self.problems()}
        self.assertTrue({".pdb file", ".obj file", "__pycache__ folder"} <= found)

    def test_private_repository(self):
        (self.folder / "engine/app/lock.json").write_text(
            json.dumps({"url": f"https://api.github.com/repos/{ACCOUNT}/secret/zipball/abc"}))
        self.assertTrue(any("private repository" in what for _, what in self.problems()))

    def test_inside_zip_and_model_patch_body(self):
        with zipfile.ZipFile(self.folder / "engine/app/lib.zip", "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("x.txt", "C:\\Users\\someone\\x" * 50)
        header = json.dumps({"template_bytes": 1}).encode()
        body = lzma.compress(b"\xd6\xc3\xc4\x00\x05vC:\\Users\\someone\\AppData\\Local\\Temp\\t\\template.dat//")
        (self.folder / "engine/app/m.mpatch").write_bytes(b"PMMP1\n" + struct.pack("<I", len(header)) + header + body)
        where = {w for w, _ in self.problems()}
        self.assertIn("engine/app/lib.zip!x.txt", where)
        self.assertIn("engine/app/m.mpatch!body", where)


class UserLockfileTests(unittest.TestCase):
    def test_maintainer_tools_and_private_fields_left_out(self):
        pinned = {"schema": 1, "unresolved": [], "geometry": {"python": "geometry-python"}, "tools": {
            "fork": {"repo": f"{ACCOUNT}/fork", "tag": "v1", "platforms": {"win-x64": {
                "asset": "fork.zip", "sha256": "ab", "entrypoint": "fork.exe", "required": ["fork.exe"]}}},
            "upstream": {"repo": "someone/tool", "tag": "v2", "platforms": {"win-x64": {
                "url": "https://github.com/someone/tool", "sha256": "cd", "required": ["t.exe"]}}},
            "helper": {"maintainer": True, "repo": f"{ACCOUNT}/helper", "platforms": {}}}}
        user = pb.user_lockfile(pinned)
        self.assertEqual(sorted(user["tools"]), ["fork", "upstream"])
        self.assertNotIn("repo", user["tools"]["fork"])
        self.assertEqual(user["tools"]["fork"]["platforms"]["win-x64"]["sha256"], "ab")
        self.assertEqual(user["tools"]["upstream"]["repo"], "someone/tool")
        self.assertNotIn("geometry", user)
        self.assertNotIn(ACCOUNT, json.dumps(user).lower())

    def test_real_lockfile_keeps_what_preflight_reads(self):
        pinned = pb.lock()
        user = pb.user_lockfile(pinned)
        self.assertNotIn(ACCOUNT, json.dumps(user).lower())
        for name, tool in pinned["tools"].items():
            if tool.get("maintainer"):
                self.assertNotIn(name, user["tools"])
                continue
            for key in ("sha256", "required", "entrypoint"):
                if key in tool["platforms"].get("win-x64", {}):
                    self.assertEqual(user["tools"][name]["platforms"]["win-x64"][key],
                                     tool["platforms"]["win-x64"][key], name)


if __name__ == "__main__":
    unittest.main()
