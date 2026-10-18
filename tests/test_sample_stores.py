import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sample_stores import verdict


class SampleVerdictTests(unittest.TestCase):
    def test_proven_branch_with_products_is_sample_ok(self):
        self.assertEqual(verdict(dict(items=40, errors=[])), 'SAMPLE_PRODUCTS')

    def test_no_products_is_reported_not_guessed(self):
        self.assertEqual(verdict(dict(items=0, errors=[])), 'NO_PRODUCTS')

    def test_branch_mismatch_is_never_ok(self):
        self.assertEqual(verdict(dict(items=40, errors=['BRANCH_MISMATCH'])), 'BRANCH_UNPROVEN')

    def test_errors_win(self):
        self.assertEqual(verdict(dict(items=40, error='boom')), 'ERROR')


if __name__ == '__main__':
    unittest.main()
