"""LLM results are kept: a found site or an evidence-backed verdict is not paid for again, and a failed attempt is not remembered as 'nothing found'."""
import unittest

from backend.service import VERIFY_HOURS, verify_interval_hours
from backend.site_discovery import search_cache_seconds


class SearchCacheTests(unittest.TestCase):
    def test_a_found_site_is_kept_for_a_month(self):
        self.assertEqual(30 * 86400, search_cache_seconds([dict(url='https://x.example/')], []))

    def test_an_honest_empty_answer_is_kept_for_a_week(self):
        self.assertEqual(7 * 86400, search_cache_seconds([], [dict(url='https://openrouter.ai/x', status=200)]))

    def test_a_failed_search_is_retried_in_minutes(self):
        self.assertEqual(300, search_cache_seconds([], [dict(url=None, error='ConnectError: x')]))


class VerifyIntervalTests(unittest.TestCase):
    def test_an_evidence_backed_verdict_stands_for_months(self):
        for verdict in ('exists', 'renamed', 'moved'):
            self.assertEqual(90 * 24, verify_interval_hours(dict(status='verified', verdict=verdict)))

    def test_an_unknown_or_failed_answer_is_retried_weekly(self):
        self.assertEqual(VERIFY_HOURS, verify_interval_hours(dict(status='verified', verdict='unknown')))
        self.assertEqual(VERIFY_HOURS, verify_interval_hours(dict(status='failed', verdict='unknown')))
        self.assertEqual(VERIFY_HOURS, verify_interval_hours(None))


if __name__ == '__main__':
    unittest.main()
