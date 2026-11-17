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
        # the character select's size is all the budget check reads (synthetic: the release fix's 3,751,594 bytes)
        self.select = SimpleNamespace(offset=0, size=3751594)
        self.disc = SimpleNamespace(path=self.built_path, read=self.files.__getitem__,
                                    entries={**dict.fromkeys(self.files), 'MvOmake15.mth': entry,
                                             'MnSlChr.usd': self.select})
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

    def test_select_screen_within_budget_is_recorded(self):
        result = self.check()['select_screen_memory']
        self.assertEqual(result['file'], 'MnSlChr.usd')
        self.assertEqual(result['bytes'], 3751594)
        self.assertGreaterEqual(result['online_css_free_estimate'], 150 * 1024)

    def test_select_screen_over_budget_is_rejected(self):
        # release-13's file: 1,600 bytes free in Slippi's online character select, the code screen asserted
        self.select.size = 3904394
        with self.assertRaisesRegex(ValueError, r'MnSlChr\.usd is 3,904,394 bytes, over its budget of 3,752,394'):
            self.check()

    def test_select_screen_budget_edge(self):
        self.select.size = 3752394
        self.assertEqual(self.check()['select_screen_memory']['online_css_free_estimate'], 153600)
        self.select.size = 3752395
        with self.assertRaisesRegex(ValueError, r'over its budget of 3,752,394 by 1\.'):
            self.check()

    def test_missing_select_screen_is_rejected(self):
        del self.disc.entries['MnSlChr.usd']
        with self.assertRaisesRegex(ValueError, 'omitted the character select'):
            self.check()


class SelectScreenBudgetTests(unittest.TestCase):
    def test_budget_comes_from_the_recipe_with_its_reason(self):
        from pokemelee.builder import select_screen_budget
        name, budget, spec = select_screen_budget()
        self.assertEqual(name, 'MnSlChr.usd')
        self.assertEqual(budget, spec['online_css_free_plus_file_bytes'] - spec['min_free_bytes'])
        self.assertGreaterEqual(spec['min_free_bytes'], 150 * 1024)
        self.assertTrue(spec['reason'])

    def test_message_names_the_overrun_and_the_cause(self):
        from pokemelee.builder import check_select_screen
        with self.assertRaises(ValueError) as caught:
            check_select_screen(3_800_000)
        text = str(caught.exception)
        self.assertIn('over its budget of 3,752,394 by 47,606', text)
        self.assertIn('online character select', text)
        self.assertIn('recipes/menus.json', text)
