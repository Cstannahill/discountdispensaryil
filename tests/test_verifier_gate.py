"""The weekly store check is skipped when the saved menu still loads, still proves its branch and still reads items."""
import tempfile
import unittest
from pathlib import Path

from backend.service import SyncService
from backend.storage import Store
from test_service import FixtureFetcher
from test_storage import item, observation, snapshot


class VerifierGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.db.import_registry([observation()], 'source')
        self.region = self.db.create_region(40.9844, -89.0388, '61358', 50)
        self.shop = self.db.stores_in_region(self.region['id'])[0]

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, identity, menu):
        self.db.save_endpoint(self.shop['id'], dict(url='https://x.example/menu', provider='fixture', license_type='recreational', identity_confidence=identity, resolution_evidence=[]))
        checked = []
        service = SyncService(self.db, FixtureFetcher(), resolver=lambda s, f: [], menu_fetcher=menu, verifier=lambda s, f: checked.append(s['id']))
        try:
            job = self.db.enqueue(dict(region_id=self.region['id'], discover=False))
            service.run(job['id'])
        finally:
            if not service.stop_requested.is_set():
                service.close()
        return checked

    def partial_menu(self, endpoint, fetcher):
        return snapshot([item('a', name='Flower A')], complete=False, expected_count=None)

    def test_a_saved_menu_that_reads_items_and_proves_its_branch_is_not_rechecked_by_the_llm(self):
        self.assertEqual([], self.run_sync('matched', self.partial_menu))

    def test_a_saved_menu_that_fails_to_load_is_checked(self):
        def broken(endpoint, fetcher):
            raise ValueError('menu unavailable')
        self.assertEqual([self.shop['id']], self.run_sync('matched', broken))

    def test_a_saved_menu_whose_branch_was_never_proven_is_checked(self):
        self.assertEqual([self.shop['id']], self.run_sync('candidate', self.partial_menu))


if __name__ == '__main__':
    unittest.main()
