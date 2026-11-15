"""Exercise export read-back failures with synthetic files, never game data."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokemelee.builder import verify_export


class ExportReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'assembled/project/project.mexproj'
        self.project.parent.mkdir(parents=True)
        self.music = self.root / 'music'
        self.music.mkdir()
        self.stage = b'synthetic-stage'
        self.song = b'synthetic-song'
        self.body = b'synthetic-costume'
        self.movie = b'synthetic-bonus-movie'
        self.base_path = self.root / 'base.iso'
        self.built_path = self.root / 'built.iso'
        self.base_path.write_bytes(self.movie)
        self.built_path.write_bytes(self.movie)
        entry = SimpleNamespace(offset=0, size=len(self.movie))
        self.files = {'stage.dat': self.stage, 'audio/song.hps': self.song,
                      'PlMrNrMod.dat': self.body}
        self.disc = SimpleNamespace(path=self.built_path, read=self.files.__getitem__,
                                    entries={**dict.fromkeys(self.files), 'MvOmake15.mth': entry})
        self.base = SimpleNamespace(path=self.base_path, entries={'MvOmake15.mth': entry})
        self.write('assembled/installed-components.json', [self.record('stage.dat', self.stage)])
        self.write('music/receipt.json', {'outputs': [self.record('files/audio/song.hps', self.song)]})
        self.write('assembled/receipt.json', {'inputs': {'components': {'music': str(self.music)}}})
        self.write('assembled/project/project.mexproj', {'fighterSaveMap': {'filePaths': ['fighter.json']}})
        self.write('assembled/project/data/fighters/fighter.json',
                   {'costumes': [{'file': {'fileName': 'PlMrNrMod.dat'}}]})
        costume = self.project.parent / 'files/PlMrNrMod.dat'
        costume.parent.mkdir()
        costume.write_bytes(self.body)
        self.mock = patch('pokemelee.builder.Disc', return_value=self.disc)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    @staticmethod
    def record(name, data):
        return {'path': name, 'sha256': hashlib.sha256(data).hexdigest()}

    def check(self):
        return verify_export(self.project, self.built_path, self.base)

    def test_valid_export_checks_installed_music_and_preserved_movie(self):
        result = self.check()
        self.assertEqual(result['installed_components'], ['stage.dat', 'audio/song.hps'])
        self.assertTrue(result['bonus_movie_preserved'])

    def test_export_with_replaced_music_is_rejected(self):
        self.files['audio/song.hps'] = b'wrong-track'
        with self.assertRaisesRegex(ValueError, 'music track'):
            self.check()

    def test_export_with_missing_costume_is_rejected(self):
        del self.disc.entries['PlMrNrMod.dat']
        with self.assertRaisesRegex(ValueError, 'omitted a costume'):
            self.check()

    def test_export_with_changed_body_is_rejected(self):
        self.files['PlMrNrMod.dat'] = b'wrong-body'
        with self.assertRaisesRegex(ValueError, 'changed a costume'):
            self.check()

    def test_export_with_movie_replacement_is_rejected(self):
        self.built_path.write_bytes(b'X' * len(self.movie))
        with self.assertRaisesRegex(ValueError, 'bonus movie'):
            self.check()
