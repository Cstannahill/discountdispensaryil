import json
from pathlib import Path
import tempfile
import unittest

from backend.service import SyncService
from backend.storage import Store, REGISTRY_URL
from backend.network import FetchResult
from test_storage import item, observation, snapshot


class FixtureFetcher:
    def get(self, url, headers=None):
        if url == REGISTRY_URL:
            body = Path('docs/evidence/2026-10-17-illinois-dispensary-map.csv').read_bytes()
        elif 'locations.html' in url:
            body = b'<p>Dispensaries updated as of 10/8/2026</p>'
        elif 'zippopotam' in url:
            body = json.dumps({'post code': '61358', 'country abbreviation': 'US', 'places': [
                {'latitude': '40.9844', 'longitude': '-89.0388', 'place name': 'Rutland', 'state abbreviation': 'IL'}]}).encode()
        else:
            raise RuntimeError('Fixture does not provide this public URL')
        return FetchResult(url, 200, body, {}, 'fixture-evidence', '2026-10-17T07:00:00+00:00')


class ServiceTests(unittest.TestCase):
    def test_unresolved_native_provider_hint_is_not_persisted_or_sent_to_menu_import(self):
        self.db.import_registry([observation()],'source');region=self.db.create_region(40.9844,-89.0388,'61358',50)
        def import_menu(*args):raise AssertionError('A provider hint must not enter extraction')
        service=SyncService(self.db,FixtureFetcher(),resolver=lambda s,f:[dict(url='https://example.com/',provider='sweed',provider_store_id=None,license_type='recreational')],menu_fetcher=import_menu)
        try:
            job=self.db.enqueue(dict(region_id=region['id'],discover=False))
            service.run(job['id']);result=self.db.job(job['id'])
            self.assertEqual(result['status'],'partial')
            self.assertEqual(self.db.endpoints(),[])
            self.assertTrue(any('contract' in str(event.get('error','')).lower() for event in result['results']))
        finally:
            if not service.stop_requested.is_set():service.close()

    def test_verifier_leads_reach_the_resolver_and_resolver_failures_do_not(self):
        self.db.import_registry([observation()],'source');region=self.db.create_region(40.9844,-89.0388,'61358',50)
        shop=self.db.stores_in_region(region['id'])[0]
        self.db.record_lead(shop['id'],'https://chain.example/il/rutland/','verifier','Store verifier website',[])
        self.db.record_lead(shop['id'],'https://wrong.example/','resolver','Candidate website found; branch still needs matching',[])
        seen=[]
        service=SyncService(self.db,FixtureFetcher(),resolver=lambda s,f:seen.append(s.get('lead_urls')) or [])
        job=self.db.enqueue(dict(region_id=region['id'],discover=False))
        service.run(job['id']);service.close()
        self.assertEqual(seen,[['https://chain.example/il/rutland/']])

    def test_targeted_retry_only_visits_requested_stores(self):
        self.db.import_registry([observation('a'),observation('b',name='Other Store')],'source')
        region=self.db.create_region(40.9844,-89.0388,'61358',50)
        first=self.db.stores_in_region(region['id'])[0]['id']
        visited=[]
        service=SyncService(self.db,FixtureFetcher(),resolver=lambda s,f:visited.append(s['id']) or [])
        job=self.db.enqueue({'region_id':region['id'],'discover':False,'store_ids':[first]})
        service.run(job['id']);service.close()
        self.assertEqual(visited,[first])
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name)/'test.db', Path(self.tmp.name)/'evidence')

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_sync_discovers_entire_region_without_custom_seeds(self):
        service = SyncService(self.db, FixtureFetcher(), resolver=lambda store, fetcher: [], menu_fetcher=None)
        job = self.db.enqueue({'discover': True})
        service.run(job['id'])
        self.assertEqual(self.db.source()['row_count'], 287)
        shops = self.db.stores_in_region()
        self.assertEqual(len(shops), 23)
        self.assertTrue(any(s['name'] == 'Stash - Peru' for s in shops))
        self.assertEqual(self.db.job(job['id'])['status'], 'partial')
        self.assertEqual(self.db.coverage()['counts']['unresolved_menus'], 23)

    def test_source_error_preserves_known_candidates_and_records_failure(self):
        self.db.import_registry([observation()], 'original')
        self.db.create_region(40.9844, -89.0388, 'ZIP 61358', 50)
        class Broken:
            def get(self, url, headers=None):
                raise RuntimeError('source unavailable')
        service = SyncService(self.db, Broken(), resolver=lambda s, f: [])
        job = self.db.enqueue({'discover': True})
        service.run(job['id'])
        self.assertEqual(self.db.source()['status'], 'failed')
        self.assertEqual(len(self.db.stores_in_region()), 1)
        self.assertIn(self.db.job(job['id'])['status'], ('failed', 'partial'))

    def test_menu_the_platform_places_at_another_branch_is_retired(self):
        self.db.import_registry([observation()], 'original')
        self.db.create_region(40.9844, -89.0388, 'ZIP 61358', 50)
        sibling = dict(url='https://example.com/shop/store/9', provider='fixture', provider_store_id='9', license_type='recreational', resolution_evidence=['e'])
        wrong = dict(snapshot([]), complete=False, expected_count=None, errors=[dict(code='incomplete_jane_menu', message='Menu source belongs to a different location: 42.85 mi from the registry address')])
        service = SyncService(self.db, FixtureFetcher(), resolver=lambda s, f: [sibling], menu_fetcher=lambda e, f: wrong)
        job = self.db.enqueue({'discover': False}); service.run(job['id'])
        unsure = dict(wrong, errors=[dict(code='incomplete_jane_menu', message='Jane slice returned 3 of 4 products')])
        service.menu_fetcher = lambda e, f: unsure
        other = dict(sibling, url='https://example.com/shop/store/10', provider_store_id='10')
        service.resolver = lambda s, f: [other]
        job = self.db.enqueue({'discover': False, 'resolve_sources': True}); service.run(job['id']); service.close()
        with self.db.connection() as conn:
            status = dict(conn.execute('SELECT url,status FROM live_endpoints').fetchall())
        self.assertEqual(status['https://example.com/shop/store/9'], 'superseded')
        self.assertNotEqual(status['https://example.com/shop/store/10'], 'superseded')

    def test_live_ingestion_path_seeds_and_repeated_run_is_idempotent(self):
        self.db.import_registry([observation()], 'original')
        self.db.create_region(40.9844, -89.0388, 'ZIP 61358', 50)
        endpoint = dict(url='https://example.com/menu', provider='fixture', provider_store_id='tenant',
                        license_type='recreational', resolution_evidence=['evidence'])
        service = SyncService(self.db, FixtureFetcher(), resolver=lambda s, f: [endpoint],
                              menu_fetcher=lambda e, f: snapshot([item('a'), item('b')]))
        for _ in range(2):
            job = self.db.enqueue({'discover': False})
            service.run(job['id'])
            self.assertEqual(self.db.job(job['id'])['status'], 'succeeded')
        self.assertEqual(self.db.query_offers()['total'], 2)
        self.assertEqual(self.db.diffs()['total'], 2)

    def test_registry_publication_date_uses_visible_body_not_stale_metadata(self):
        class StaleMetadata(FixtureFetcher):
            def get(self,url,headers=None):
                if 'locations.html' in url:
                    return FetchResult(url,200,b'<head><meta content="Dispensaries updated as of 10/14/2022"></head><body><script>var old="Dispensaries updated as of 10/14/2022";</script><p>Dispensaries updated as of 10/8/2026</p></body>',{},'page-evidence','2026-10-17T07:00:00Z')
                return super().get(url,headers)
        SyncService(self.db,StaleMetadata(),resolver=lambda s,f:[]).refresh_registry()
        self.assertEqual(self.db.source()['published_at'],'2026-10-08')


if __name__ == '__main__':
    unittest.main()
