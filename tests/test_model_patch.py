import unittest

from pokemelee import model_patch as mp
from pokemelee.catalog import load
from pokemelee.runtime import lock


class ModelPatchTests(unittest.TestCase):
    def test_every_accepted_costume_has_a_readable_patch(self):
        finishing = load("cast-finishing.json")["recipes"]
        names = sorted(p.stem for p in mp.PATCHES.glob("*.mpatch"))
        if not names:
            self.skipTest("model patches are local only (see tools/package_builder.py)")
        self.assertEqual(names, sorted(finishing))
        for name in names:
            header, delta, rows, pictures = mp.read_patch(mp.PATCHES / (name + ".mpatch"))
            self.assertEqual(header["sha256"], finishing[name]["sha256"], name)
            self.assertTrue(header["vanilla"].startswith("Pl") and header["vanilla"].endswith("Nr.dat"), name)
            self.assertTrue(delta and rows and header["arrays"], name)
            self.assertTrue(header["source_archive"].startswith("pkx_"), name)
            self.assertFalse(mp.delta_has_appheader(delta), name + ": template delta carries file paths")

    def test_appheader_is_detected(self):
        self.assertTrue(mp.delta_has_appheader(b"\xd6\xc3\xc4\x00\x05rest"))
        self.assertFalse(mp.delta_has_appheader(b"\xd6\xc3\xc4\x00\x01rest"))
        self.assertFalse(mp.delta_has_appheader(b"\xd6\xc3\xc4\x00\x00rest"))

    def test_residuals_restore_exact_values(self):
        for b in ({"comp": 4, "scale": 0}, {"comp": 3, "scale": 7}, {"comp": 1, "scale": 0}):
            for actual, pred in (((1.5, -2.25, 0.0), (1.4999, -2.3, 1e-6)), ((3.0, 0.5, -1.0), (2.0, 0.75, -0.5))):
                exact = mp.quantize(b, actual)
                self.assertEqual(mp.add(b, mp.quantize(b, pred), mp.residual(b, exact, mp.quantize(b, pred))), exact)

    def test_user_build_skips_maintainer_tools(self):
        tools = lock()["tools"]
        maintainer = {name for name, tool in tools.items() if tool.get("maintainer")}
        self.assertIn("blender-converter", maintainer)
        self.assertIn("blender-target-reader", maintainer)
        self.assertIn("cast-helpers", maintainer)
        self.assertTrue({name for name in tools if name.startswith("geometry-")} <= maintainer)
        self.assertFalse({"hsdlib", "mex", "xdelta", "musyx"} & maintainer)


if __name__ == "__main__":
    unittest.main()
