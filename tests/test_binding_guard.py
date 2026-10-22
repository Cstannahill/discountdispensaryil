"""A platform store already bound to one registry store is never bound to another."""
import tempfile
import unittest
from pathlib import Path

from backend.service import SyncService
from backend.storage import Store
from test_service import FixtureFetcher
from test_storage import observation


class BindingGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.db.import_registry([observation('one', name='Shop One'), observation('two', name='Shop Two')], 'source')
        self.region = self.db.create_region(40.9844, -89.0388, '61358', 50)
        self.stores = {s['name']: s for s in self.db.stores_in_region(self.region['id'])}

    def tearDown(self):
        self.tmp.cleanup()

    def run_resolution(self, provider, store_name='Shop One'):
        owner = self.stores['Shop Two']
        self.db.save_endpoint(owner['id'], dict(url='https://x.example/menu/two', provider=provider, provider_store_id='tenant-9', license_type='recreational', resolution_evidence=[]))
        stray = dict(url='https://x.example/menu/one', provider=provider, provider_store_id='tenant-9', license_type='recreational', status='matched', resolution_evidence=[])
        def no_menu(endpoint, fetcher):
            raise ValueError('fixture menu unavailable')
        service = SyncService(self.db, FixtureFetcher(), resolver=lambda s, f: [stray] if s['name'] == store_name else [], menu_fetcher=no_menu)
        try:
            job = self.db.enqueue(dict(region_id=self.region['id'], discover=False, store_ids=[self.stores[store_name]['id']]))
            service.run(job['id'])
            return self.db.job(job['id'])
        finally:
            if not service.stop_requested.is_set():
                service.close()

    def test_a_single_store_platform_id_bound_elsewhere_is_not_saved_for_another_store(self):
        result = self.run_resolution('dutchie')
        self.assertEqual([], self.db.endpoints(self.stores['Shop One']['id']))
        self.assertTrue(any(e.get('stage') == 'resolution' and e.get('status') == 'identity_conflict' for e in result['results']))

    def test_a_chain_shared_id_is_not_blocked(self):
        self.run_resolution('sweed')
        self.assertEqual(1, len(self.db.endpoints(self.stores['Shop One']['id'])))


if __name__ == '__main__':
    unittest.main()
