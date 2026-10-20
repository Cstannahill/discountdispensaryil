import json
from pathlib import Path
import tempfile
import threading
import time
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

    def test_sample_run_reads_capped_pages_per_endpoint_and_writes_no_menu_state(self):
        self.db.import_registry([observation()],'source');region=self.db.create_region(40.9844,-89.0388,'61358',50)
        seen=[]
        def read_menu(endpoint,fetcher):
            seen.append(endpoint.get('max_pages'))
            return dict(items=[dict(source_id='a',name='Flower')],complete=False,expected_count=None,errors=[],source_count=None,pages=[dict(page=1,items=1),dict(page=2,items=0)])
        resolved=[dict(url='https://example.com/menu',provider='jane',provider_store_id='1',license_type='recreational',status='matched',resolution_evidence=[])]
        service=SyncService(self.db,FixtureFetcher(),resolver=lambda s,f:list(resolved),menu_fetcher=read_menu)
        try:
            job=self.db.enqueue(dict(region_id=region['id'],discover=False,sample_pages=2))
            service.run(job['id']);result=self.db.job(job['id'])
        finally:
            if not service.stop_requested.is_set():service.close()
        self.assertEqual(seen,[2])
        samples=[event for event in result['results'] if event.get('stage')=='menu_sample']
        self.assertEqual(len(samples),1)
        self.assertEqual(samples[0]['items'],1);self.assertEqual(samples[0]['pages'],2)
        with self.db.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM live_snapshots').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM live_offers').fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM live_endpoints WHERE last_success_at IS NOT NULL").fetchone()[0],0)

    def test_sample_run_reads_a_saved_endpoint_before_discovery_and_budgets_discovery(self):
        self.db.import_registry([observation()],'source');region=self.db.create_region(40.9844,-89.0388,'61358',50)
        shop=self.db.stores_in_region(region['id'])[0]
        self.db.save_endpoint(shop['id'],dict(url='https://example.com/menu',provider='jane',provider_store_id='1',license_type='recreational',resolution_evidence=[]))
        budgets=[]
        def resolver(store,fetcher):budgets.append(store.get('discovery_seconds'));return []
        def read_menu(endpoint,fetcher):return dict(items=[dict(source_id='a',name='Flower')],complete=False,expected_count=None,errors=[],source_count=None,pages=[dict(page=1,items=1)])
        service=SyncService(self.db,FixtureFetcher(),resolver=resolver,menu_fetcher=read_menu)
        try:
            sample=self.db.enqueue(dict(region_id=region['id'],discover=False,sample_pages=2))
            service.run(sample['id']);sampled=self.db.job(sample['id'])
            self.assertEqual(budgets,[])
            self.assertTrue(any(event.get('stage')=='menu_sample' and event.get('items')==1 for event in sampled['results']))
            with self.db.connection() as conn:conn.execute("UPDATE live_endpoints SET status='superseded'")
            full=self.db.enqueue(dict(region_id=region['id'],discover=False))
            service.run(full['id'])
            self.assertEqual(budgets,[None])
            sample_again=self.db.enqueue(dict(region_id=region['id'],discover=False,sample_pages=2))
            service.run(sample_again['id'])
            self.assertEqual(budgets,[None,120])
        finally:
            if not service.stop_requested.is_set():service.close()

    def test_sample_run_overlaps_different_chains(self):
        self.db.import_registry([observation('a'),observation('b',name='Other Store')],'source')
        region=self.db.create_region(40.9844,-89.0388,'61358',50)
        barrier=threading.Barrier(2,timeout=5);passed=[]
        def resolver(store,fetcher):barrier.wait();passed.append(store['id']);return []
        service=SyncService(self.db,FixtureFetcher(),resolver=resolver,menu_fetcher=lambda endpoint,fetcher:None)
        try:
            job=self.db.enqueue(dict(region_id=region['id'],discover=False,sample_pages=2))
            service.run(job['id']);result=self.db.job(job['id'])
        finally:
            if not service.stop_requested.is_set():service.close()
        self.assertEqual(len(passed),2)
        self.assertEqual(len([event for event in result['results'] if event.get('stage')=='store_summary']),2)

    def test_sample_run_keeps_one_chain_to_one_store_at_a_time(self):
        self.db.import_registry([observation('a'),observation('b')],'source')
        region=self.db.create_region(40.9844,-89.0388,'61358',50)
        active=[];peak=[0];gate=threading.Lock()
        def resolver(store,fetcher):
            with gate:active.append(store['id']);peak[0]=max(peak[0],len(active))
            time.sleep(0.2)
            with gate:active.remove(store['id'])
            return []
        service=SyncService(self.db,FixtureFetcher(),resolver=resolver,menu_fetcher=lambda endpoint,fetcher:None)
        try:
            job=self.db.enqueue(dict(region_id=region['id'],discover=False,sample_pages=2))
            service.run(job['id']);result=self.db.job(job['id'])
        finally:
            if not service.stop_requested.is_set():service.close()
        self.assertEqual(peak[0],1)
        self.assertEqual(len([event for event in result['results'] if event.get('stage')=='store_summary']),2)

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
