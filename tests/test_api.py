import csv
import io
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from backend.main import create_app
from test_service import FixtureFetcher
from test_storage import item, observation, snapshot


class ApiTests(unittest.TestCase):
    def test_queued_run_pins_the_current_region_before_another_tab_changes_it(self):
        region,_=self.seed()
        queued=self.client.post('/api/v1/sync/runs',json={'discover':False,'resolve_sources':True}).json()
        self.client.post('/api/v1/regions',json=dict(latitude=42,longitude=-88,label='Other tab',radius_miles=1))
        job=self.app.state.store.job(queued['id'])
        self.assertEqual(job['payload']['region_id'],region['id'])
        self.assertTrue(job['payload']['pipeline_version'])

    def test_health_revision_changes_after_catalog_and_job_updates(self):
        before=self.client.get('/api/v1/health').json()['data_revision']
        job=self.app.state.store.enqueue({})
        queued=self.client.get('/api/v1/health').json()['data_revision']
        self.assertNotEqual(before,queued)
        self.app.state.store.update_job(job['id'],'running',[{'stage':'resolution','status':'blocked'}])
        self.assertNotEqual(queued,self.client.get('/api/v1/health').json()['data_revision'])

    def test_imported_store_remains_in_directory_and_menu_after_resolution_failure(self):
        region,endpoint=self.seed()
        store_id=self.app.state.store.endpoint(endpoint['id'])['store_id']
        self.app.state.store.record_resolution(store_id,'failed','New discovery failed')
        directory=self.client.get('/api/v1/dispensaries',params={'region_id':region['id'],'license_type':'recreational'}).json()
        self.assertEqual(len(directory['items']),1)
        self.assertEqual(directory['items'][0]['product_count'],2)
        self.assertEqual(self.client.get(f"/api/v1/menus/{endpoint['id']}/products").json()['total'],2)

    def test_browser_age_confirmation_requires_explicit_persisted_setting(self):
        initial=self.client.get('/api/v1/settings/browser').json()
        self.assertFalse(initial['age_confirmed'])
        changed=self.client.patch('/api/v1/settings/browser',json={'enabled':True,'age_confirmed':True,'terms_accepted':False})
        self.assertEqual(changed.status_code,200)
        self.assertTrue(self.app.state.store.setting('browser_options')['age_confirmed'])

    def test_stage_report_attempts_and_unverified_deals_routes(self):
        region,endpoint=self.seed()
        store=self.app.state.store
        store_id=store.endpoint(endpoint['id'])['store_id']
        store.record_attempt(store_id=store_id,endpoint_id=endpoint['id'],pipeline_version='old',stage='menu',tier='structured',status='partial',code='RENDER_BLANK',items=0)
        stages=self.client.get('/api/v1/pipeline/stages',params={'region_id':region['id'],'all_versions':True}).json()
        self.assertEqual(stages['total_stores'],1)
        self.assertEqual(sum(stages['by_stage'].values()),1)
        current=self.client.get('/api/v1/pipeline/stages',params={'region_id':region['id']}).json()
        self.assertEqual(current['stores'][0]['current'],False)
        attempts=self.client.get(f'/api/v1/stores/{store_id}/attempts').json()
        self.assertEqual(attempts['items'][0]['code'],'RENDER_BLANK')
        self.assertEqual(self.client.get('/api/v1/deals',params={'include_unverified':True}).status_code,200)

    def test_browser_settings_accept_platform_reads_and_honest_token_but_never_diagnostic_posts(self):
        base={'enabled':True,'age_confirmed':True,'terms_accepted':False}
        ok=self.client.patch('/api/v1/settings/browser',json=dict(base,post_policy='platform_reads',user_agent_token='TerpScout/1.0',scroll_menu=True))
        self.assertEqual(ok.status_code,200)
        self.assertEqual(self.client.get('/api/v1/settings/browser').json()['post_policy'],'platform_reads')
        self.assertEqual(self.client.get('/api/v1/settings/browser').json()['user_agent_token'],'TerpScout/1.0')
        for bad in (dict(post_policy='diagnostic_posts'),dict(user_agent_token='Mozilla/5.0 (X11) bot'),dict(user_agent_token='x'*80)):
            self.assertEqual(self.client.patch('/api/v1/settings/browser',json=dict(base,**bad)).status_code,422,bad)
        self.assertEqual(self.client.get('/api/v1/settings/browser').json()['post_policy'],'platform_reads')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name)
        self.app = create_app(db_path=path/'test.db', evidence_dir=path/'evidence',
                              fetcher=FixtureFetcher(), enable_scheduler=False, execute_jobs=False)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def seed(self):
        store = self.app.state.store
        store.import_registry([observation()], 'test')
        region = self.client.post('/api/v1/regions', json=dict(latitude=40.9844, longitude=-89.0388,
                                  label='61358', radius_miles=50)).json()
        shop = store.stores_in_region(region['id'])[0]
        endpoint = store.save_endpoint(shop['id'], dict(url='https://example.com/menu', provider='fixture',
                                       provider_store_id='tenant', license_type='recreational', resolution_evidence=['e']))
        store.apply_snapshot(endpoint['id'], snapshot([item(), item('edible', name='=SUM(1,2)', category='edibles', weight_grams=None)]))
        return region, endpoint

    def test_sync_enqueues_real_run_instead_of_reporting_completed(self):
        response = self.client.post('/api/v1/sync/runs', json={'discover': True})
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data['status'], 'queued')
        self.assertEqual(self.client.get(data['status_url']).json()['status'], 'queued')

    def test_run_history_is_paged_without_a_hundred_run_ceiling(self):
        for number in range(103):
            self.app.state.store.enqueue({'sequence': number})
        response = self.client.get('/api/v1/sync/runs?page=6&page_size=20').json()
        self.assertEqual(response['total'], 103)
        self.assertEqual(len(response['items']), 3)
        self.assertEqual(response['page'], 6)

    def test_catalog_keeps_items_ineligible_for_deal_ranking(self):
        self.seed()
        self.assertEqual(self.client.get('/api/v1/deals').json()['total'], 1)
        self.assertEqual(self.client.get('/api/v1/catalog').json()['total'], 2)
        self.assertEqual(self.client.get('/api/v1/catalog?category=edibles').json()['total'], 1)

    def test_invalid_data_version_requires_explicit_refresh(self):
        self.seed()
        response = self.client.get('/api/v1/deals?data_version=obsolete')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['code'], 'refresh_required')

    def test_schedule_is_validated_and_persisted(self):
        response = self.client.patch('/api/v1/settings/schedule', json={'frequency_per_day': 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slots'], ['07:00', '15:00', '23:00'])
        self.assertEqual(self.app.state.store.setting('frequency_per_day'), 3)
        self.assertEqual(self.client.patch('/api/v1/settings/schedule', json={'frequency_per_day': 9}).status_code, 422)

    def test_unknown_location_does_not_change_selected_region(self):
        region, _ = self.seed()
        response = self.client.post('/api/v1/locations/resolve', json={'query': 'unknown-location'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/v1/regions').json()['active_region_id'], region['id'])

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        self.seed()
        response = self.client.get('/api/v1/catalog/export')
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=SUM(1,2)", response.text)

    def test_csv_export_respects_catalog_search_and_category_filters(self):
        self.seed()
        response = self.client.get('/api/v1/catalog/export', params={'category':'edibles','q':'SUM'})
        rows = list(csv.DictReader(io.StringIO(response.text)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['category'], 'edibles')

    def test_foreign_origin_cannot_start_jobs(self):
        response = self.client.post('/api/v1/sync/runs', json={}, headers={'Origin': 'https://unrelated.example'})
        self.assertEqual(response.status_code, 403)

    def test_no_region_is_clear_empty_setup_state(self):
        cover = self.client.get('/api/v1/coverage').json()
        self.assertIsNone(cover['region'])
        self.assertEqual(cover['counts']['known_stores'], 0)
        self.assertEqual(self.client.get('/api/v1/deals').json()['items'], [])

    def test_watchlist_can_resolve_exact_offer_without_page_truncation(self):
        _, endpoint = self.seed()
        first = self.client.get('/api/v1/deals').json()['items'][0]
        response = self.client.get(f"/api/v1/menus/{endpoint['id']}/products", params={'offer_id': first['id'], 'include_removed': True})
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(response.json()['items'][0]['id'], first['id'])

    def test_benchmark_uses_whole_catalog_beyond_first_hundred_ranked_offers(self):
        _, endpoint = self.seed()
        self.app.state.store.apply_snapshot(endpoint['id'],snapshot(
            [item(str(i),weight_grams='1',effective_price='10') for i in range(101)] +
            [item('concentrate',category='concentrate',weight_grams='1',effective_price='99')]))
        response = self.client.get('/api/v1/benchmark').json()
        self.assertEqual(response['total_offers'],102)
        self.assertEqual(len(response['items']),2)
        concentrate = next(r for r in response['items'] if r['category']=='concentrate')
        self.assertEqual(concentrate['price_per_gram'],'99.00')


if __name__ == '__main__':
    unittest.main()
