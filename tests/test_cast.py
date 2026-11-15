import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pokemelee.cast import checked_component, selection
from pokemelee.native.offline_worker import NoAuthoring, no_network
from pokemelee.workspace import digest


class CastTests(unittest.TestCase):
    def test_incomplete_cast_cannot_silently_skip(self):
        complete = selection()
        self.assertEqual(len(complete), 29)
        from pokemelee.catalog import load
        recipes = load("cast-finishing.json")
        recipes["recipes"].pop("pichu")
        with patch("pokemelee.cast.load", side_effect=lambda name: recipes if name == "cast-finishing.json" else load(name)):
            with self.assertRaisesRegex(ValueError, "awaiting verification: pichu"):
                selection()
        with self.assertRaises(ValueError):
            selection(["Pichu", "pichu"])

    def test_worker_forbids_authoring_and_network(self):
        for module in ("rigswap.ai", "rigswap.ai.client", "rigswap.core.run", "rigswap.pipeline"):
            with self.assertRaises(ImportError):
                NoAuthoring().find_spec(module)
        for event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
            with self.assertRaises(RuntimeError):
                no_network(event, ())

    def test_component_receipt_detects_changed_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "model.glb").write_bytes(b"synthetic model fixture")
            (root / "receipt.json").write_text(json.dumps({"operation": "source-models", "complete": True,
                "outputs": [{"path": "model.glb", "sha256": digest(b"synthetic model fixture")}]}))
            self.assertEqual(checked_component(root, "source-models"), root.resolve())
            (root / "model.glb").write_bytes(b"changed fixture")
            with self.assertRaisesRegex(ValueError, "changed"):
                checked_component(root, "source-models")
