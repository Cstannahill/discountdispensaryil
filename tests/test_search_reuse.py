"""A paid website search is skipped when a saved menu vouches for the store, and what it finds is saved and crawled next time."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.service import SyncService
from backend.storage import Store
from test_service import FixtureFetcher
from test_site_discovery import response
from test_storage import item, observation, snapshot


class ResolverSearchTests(unittest.TestCase):
    shop = dict(name='Former Brand - Normal', city='Normal', state='IL', address='1609 Northbrook Dr', website='https://former.example/')

    class Fetcher:
        def get(self, url):
            return response(url, '<h1>Former Brand Schaumburg</h1>')

    def test_no_search_flag_skips_the_open_web_search(self):
        from backend.adapters import resolve_menu
        calls = []
        with patch('backend.site_discovery.search_websites', side_effect=lambda *a, **k: calls.append(1) or []):
            resolve_menu(dict(self.shop, no_search=True), self.Fetcher())
        self.assertEqual([], calls)

    def test_search_results_are_handed_to_the_sink_to_be_saved(self):
        from backend.adapters import resolve_menu
        saved = []
        lead = dict(url='https://new-owner.example/menu', status='candidate', evidence=[])
        with patch('backend.site_discovery.search_websites', return_value=[lead]):
            resolve_menu(dict(self.shop, search_sink=saved.extend), self.Fetcher())
        self.assertEqual(['https://new-owner.example/menu'], [x['url'] for x in saved][:1])


class ServiceSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.db.import_registry([observation()], 'source')
        self.region = self.db.create_region(40.9844, -89.0388, '61358', 50)
        self.shop = self.db.stores_in_region(self.region['id'])[0]

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, resolver, identity='matched'):
        self.db.save_endpoint(self.shop['id'], dict(url='https://x.example/menu', provider='fixture', license_type='recreational', identity_confidence=identity, resolution_evidence=[]))
        menu = lambda endpoint, fetcher: snapshot([item('a', name='Flower A')], complete=False, expected_count=None)
        service = SyncService(self.db, FixtureFetcher(), resolver=resolver, menu_fetcher=menu, verifier=lambda s, f: None)
        try:
            service.run(self.db.enqueue(dict(region_id=self.region['id'], discover=False))['id'])
        finally:
            if not service.stop_requested.is_set():
                service.close()

    def test_a_vouched_store_resolves_without_search(self):
        seen = []
        self.run_sync(lambda s, f: seen.append(s) or [])
        self.assertTrue(seen[0].get('no_search'))

    def test_an_unvouched_store_may_search(self):
        seen = []
        self.run_sync(lambda s, f: seen.append(s) or [], identity='candidate')
        self.assertFalse(seen[0].get('no_search'))

    def test_search_found_sites_are_saved_and_become_seeds_next_run(self):
        def first(store, fetcher):
            store['search_sink']([dict(url='https://new-owner.example/menu')])
            return []
        self.run_sync(first, identity='candidate')
        self.assertIn(('https://new-owner.example/menu', 'search'), [(l['url'], l['source']) for l in self.db.leads(self.shop['id'])])
        seen = []
        self.run_sync(lambda s, f: seen.append(s) or [], identity='candidate')
        self.assertIn('https://new-owner.example/menu', seen[0]['lead_urls'])

    def test_a_search_result_never_overwrites_a_verifier_lead(self):
        self.db.record_lead(self.shop['id'], 'https://v.example/', 'verifier', 'cited')
        def first(store, fetcher):
            store['search_sink']([dict(url='https://v.example/')])
            return []
        self.run_sync(first, identity='candidate')
        self.assertEqual('verifier', [l['source'] for l in self.db.leads(self.shop['id']) if l['url'] == 'https://v.example/'][0])


if __name__ == '__main__':
    unittest.main()
