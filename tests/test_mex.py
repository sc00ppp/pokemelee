import unittest

from pokemelee.mex import check_result, parse_result


class MexResultTests(unittest.TestCase):
    def test_progress_then_indented_result(self):
        text = 'Saving {project}...\n{"success": true,\n "totalImported": 131}\n'
        self.assertEqual(check_result(parse_result(text))['totalImported'], 131)

    def test_partial_batch_failure_with_successful_exit_is_rejected(self):
        with self.assertRaises(ValueError):
            check_result({'success': True, 'totalImported': 130, 'totalFailed': 1})

    def test_unknown_fighter_nested_error_is_rejected(self):
        # MexCLI can report success and zero totalFailed for an unknown key.
        with self.assertRaises(ValueError):
            check_result({'success': True, 'totalFailed': 0,
                          'perFighter': {'Missing': {'error': 'fighter not found', 'removed': 0}}})

    def test_truncated_or_absent_result_is_rejected(self):
        for text in ('Saving...', '{"success": true', '{"success": true}\nunexpected error'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_result(text)
