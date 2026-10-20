"""A verifier verdict backed by a kept claim changes what a store is (open, closed, renamed). The registry row is never edited."""
import tempfile
import unittest
from pathlib import Path

from backend.storage import Store
from test_storage import observation


def verdict(store_id, verdict, claims, result, status='verified'):
    return dict(store_id=store_id, version='test', status=status, verdict=verdict, result=result, claims=claims, dropped=[],
                transcript=[], evidence=[], model='test/model', steps=1, tokens=10, usd=0.0, seconds=1.0, detail=None)


class VerdictIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.db.import_registry([observation()], 'source', now='2026-10-17T06:00:00+00:00')
        self.region = self.db.create_region(40.9844, -89.0388, 'ZIP 61358', 50)
        self.shop = self.db.stores_in_region(self.region['id'])[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_closed_verdict_marks_the_store_closed_and_keeps_its_registry_row(self):
        claim = dict(field='existence', value='permanently closed', url='https://x.example/', quote='This dispensary is permanently closed', evidence_id='ev-1')
        self.db.record_verification(verdict(self.shop['id'], 'closed', [claim], dict(verdict='closed', confidence=0.9)))
        store = self.db.stores_in_region(self.region['id'])[0]
        self.assertEqual('closed', store['operating_status'])
        self.assertEqual('Test Shop', store['name'])
        self.assertEqual('closed', self.db.stage_report(self.region['id'])['stores'][0]['stage'])

    def test_existence_verdict_marks_the_store_open(self):
        claim = dict(field='existence', value='open', url='https://x.example/', quote='Open daily', evidence_id='ev-1')
        self.db.record_verification(verdict(self.shop['id'], 'exists', [claim], dict(verdict='exists', confidence=0.9)))
        self.assertEqual('open', self.db.stores_in_region(self.region['id'])[0]['operating_status'])

    def test_renamed_verdict_records_the_new_name_with_its_source(self):
        claim = dict(field='name', value='Bloom Wellness Normal', url='https://risecannabis.com/x/', quote='Bloom Wellness Normal', evidence_id='ev-2')
        self.db.record_verification(verdict(self.shop['id'], 'renamed', [claim],
                                            dict(verdict='renamed', name='Bloom Wellness Normal', website='https://risecannabis.com/x/')))
        store = self.db.stores_in_region(self.region['id'])[0]
        self.assertEqual('Test Shop', store['name'])
        self.assertEqual('rebranded', store['identity_status'])
        self.assertEqual([('Bloom Wellness Normal', 'rebrand', 'https://risecannabis.com/x/', 'ev-2')],
                         [(a['name'], a['kind'], a['source_url'], a['evidence_id']) for a in store['aliases']])

    def test_rename_without_a_kept_name_claim_records_nothing(self):
        claim = dict(field='existence', value='open', url='https://x.example/', quote='Open daily', evidence_id='ev-1')
        self.db.record_verification(verdict(self.shop['id'], 'renamed', [claim], dict(verdict='unknown', name='Guessed Name')))
        store = self.db.stores_in_region(self.region['id'])[0]
        self.assertEqual([], store['aliases'])
        self.assertEqual('registry_candidate', store['identity_status'])

    def test_backfill_applies_stored_verdicts_that_predate_identity_events(self):
        claim = dict(field='existence', value='permanently closed', url='https://x.example/', quote='This dispensary is permanently closed', evidence_id='ev-1')
        self.db.record_verification(verdict(self.shop['id'], 'closed', [claim], dict(verdict='closed', confidence=0.9)))
        with self.db.connection() as conn:
            conn.execute("DELETE FROM live_store_identity")
            conn.execute("UPDATE live_stores SET operating_status='unverified'")
        self.assertEqual('unverified', self.db.stores_in_region(self.region['id'])[0]['operating_status'])
        self.assertEqual({'verdicts': 1}, self.db.backfill_identity())
        self.assertEqual('closed', self.db.stores_in_region(self.region['id'])[0]['operating_status'])

    def test_rebrand_recorded_from_a_matched_branch_page_is_listed_with_its_source(self):
        self.db.record_identity(self.shop['id'], 'rebrand', 'The Joint Dispensary - Rutland', 'https://example.com/locations/rutland/', 'ev-3')
        store = self.db.stores_in_region(self.region['id'])[0]
        self.assertEqual(['The Joint Dispensary - Rutland'], [a['name'] for a in store['aliases']])
        self.assertEqual('rebranded', store['identity_status'])


if __name__ == '__main__':
    unittest.main()
