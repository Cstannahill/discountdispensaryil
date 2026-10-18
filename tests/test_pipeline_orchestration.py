"""Mixed-stage invariants for the production runner, not individual retailers."""
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import Mock

from backend.service import SyncService
from backend.storage import Store
from test_service import FixtureFetcher
from test_storage import item, observation, snapshot


class PipelineOrchestrationTests(unittest.TestCase):
    def test_legacy_job_menu_events_get_the_immutable_endpoint_license(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint())
        job=self.store.enqueue({'discover':False})
        self.store.update_job(job['id'],'partial',[dict(stage='menu',endpoint_id=endpoint['id'],status='partial')])
        result=self.store.job(job['id'])['results'][0]
        self.assertEqual(result['license_type'],'recreational')

    def test_unexpected_store_failure_is_checkpointed_and_does_not_abort_other_stores(self):
        self.store.import_registry([observation(),observation('second',name='Second Shop')],'two')
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[])
        process=self.service._process_store
        visited=[]
        def fail_one(shop,results,force=False):
            visited.append(shop['id'])
            if len(visited)==1:raise ValueError('Malformed store source context')
            return process(shop,results,force)
        self.service._process_store=fail_one
        job=self.run_job()
        self.assertEqual(job['status'],'partial')
        self.assertEqual(len(visited),2)
        summaries=[r for r in job['results'] if r['stage']=='store_summary']
        self.assertEqual(len(summaries),2)
        self.assertIn('Malformed store source context',summaries[0]['error'])

    def test_targeted_job_can_run_while_a_different_store_blocks_a_regional_job(self):
        second=observation('second',name='Second Shop',lat=40.99,lon=-89.04)
        self.store.import_registry([observation(),second],'registry-2')
        shops=self.store.stores_in_region(self.region['id'])
        first_id=shops[0]['id'];second_id=shops[1]['id']
        for shop in shops:
            endpoint=self.store.save_endpoint(shop['id'],self.endpoint('https://example.com/'+shop['id']))
            self.store.apply_snapshot(endpoint['id'],snapshot([item('accepted')]))
        blocked=threading.Event();release=threading.Event();target_done=threading.Event()
        def fetch(endpoint,fetcher):
            if endpoint['store_id']==first_id:
                blocked.set();release.wait(4)
            else:target_done.set()
            return snapshot([item('accepted')])
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[],menu_fetcher=fetch)
        try:
            regional=self.service.submit(dict(region_id=self.region['id'],discover=False))
            self.assertTrue(blocked.wait(2))
            duplicate=self.service.submit(dict(region_id=self.region['id'],discover=False))
            self.assertEqual(duplicate['id'],regional['id'])
            self.service.submit(dict(region_id=self.region['id'],discover=False,store_ids=[second_id]))
            self.assertTrue(target_done.wait(2),'Targeted work was trapped behind the regional run')
        finally:release.set()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.store=Store(root/'db.sqlite',root/'evidence')
        self.store.import_registry([observation()],'registry')
        self.region=self.store.create_region(40.9844,-89.0388,'Initial region',50)
        self.shop=self.store.stores_in_region()[0]
        self.service=None

    def tearDown(self):
        if self.service:self.service.close()
        self.temp.cleanup()

    def endpoint(self,url='https://example.com/menu',provider='fixture'):
        return dict(url=url,provider=provider,license_type='recreational',resolution_evidence=['source'])

    def run_job(self,**payload):
        job=self.store.enqueue(dict(region_id=self.region['id'],discover=False,**payload))
        self.service.run(job['id'])
        return self.store.job(job['id'])

    def test_retained_accepted_menu_refresh_does_not_depend_on_rediscovery(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint())
        self.store.apply_snapshot(endpoint['id'],snapshot([item('old')]))
        resolver=Mock(side_effect=RuntimeError('Locator unavailable'))
        self.service=SyncService(self.store,FixtureFetcher(),resolver=resolver,menu_fetcher=lambda e,f:snapshot([item('old'),item('new')]))
        job=self.run_job()
        self.assertEqual(job['status'],'succeeded')
        self.assertEqual(self.store.menu_products(endpoint['id'])['total'],2)
        resolver.assert_not_called()
        summary=next(result for result in job['results'] if result['stage']=='store_summary')
        self.assertTrue(summary['pipeline_version'])
        self.assertEqual(summary['menu_targets_attempted'],1)
        menu=next(result for result in job['results'] if result['stage']=='menu')
        self.assertEqual(menu['license_type'],'recreational')
        self.assertEqual(menu['url'],endpoint['url'])
        report=self.store.pipeline_report(self.region['id'])
        self.assertEqual(report['counts']['accepted'],1)
        self.assertEqual(sum(report['counts'].values()),report['total_stores'])

    def test_historic_accepted_snapshot_is_distinct_from_a_current_pipeline_attempt(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint())
        self.store.apply_snapshot(endpoint['id'],snapshot([item('accepted')]))
        report=self.store.pipeline_report(self.region['id'])
        self.assertEqual(report['counts']['not_attempted_current_pipeline'],1)
        self.assertTrue(report['stores'][0]['accepted_menu_available'])


    def test_forced_discovery_failure_retains_and_refreshes_the_accepted_menu(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint())
        self.store.apply_snapshot(endpoint['id'],snapshot([item('old')]))
        self.service=SyncService(self.store,FixtureFetcher(),resolver=Mock(side_effect=RuntimeError('Search failed')),menu_fetcher=lambda e,f:snapshot([item('old'),item('new')]))
        job=self.run_job(resolve_sources=True)
        self.assertEqual(job['status'],'partial')
        self.assertEqual(self.store.menu_products(endpoint['id'])['total'],2)
        self.assertTrue(any(result['stage']=='resolution' and result['status']=='failed' for result in job['results']))

    def test_runner_dispatches_pagination_aliases_only_once(self):
        targets=[self.endpoint('https://example.com/shop'+query,'generic') for query in ['', '?page=1','?page=97']]
        fetch=Mock(return_value=snapshot([item()],provider='generic'))
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:targets,menu_fetcher=fetch)
        job=self.run_job()
        self.assertEqual(job['status'],'succeeded')
        self.assertEqual(fetch.call_count,1)

    def test_prepared_scope_survives_active_region_change(self):
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[])
        payload=self.service.prepare_payload({'discover':False})
        self.store.create_region(42,-88,'Other tab',1)
        self.assertEqual(payload['region_id'],self.region['id'])
        self.assertTrue(payload['pipeline_version'])

    def test_interruption_after_acquisition_cannot_replace_the_accepted_snapshot(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint())
        self.store.apply_snapshot(endpoint['id'],snapshot([item('accepted')]))
        def interrupt(e,f):
            self.service.stop_requested.set()
            return snapshot([item('uncommitted')])
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[],menu_fetcher=interrupt)
        job=self.run_job()
        self.assertEqual(job['status'],'interrupted')
        self.assertEqual(self.store.menu_products(endpoint['id'])['items'][0]['source_id'],'accepted')


class AttemptTelemetryTests(PipelineOrchestrationTests):
    """Reuses the orchestration fixtures; the inherited tests are re-run harmlessly."""

    def menu_attempt(self):
        return next(a for a in self.store.attempts(store_id=self.shop['id']) if a['stage']=='menu')

    def test_menu_attempts_are_recorded_with_codes_and_grades(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint(provider='generic'))
        failing=snapshot([item('a')],provider='generic',complete=False,errors=[dict(code='incomplete_generic_menu',message='Products extracted, but source advertises no independently verifiable full-menu total')])
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[],menu_fetcher=lambda e,f:failing)
        self.store.apply_snapshot(endpoint['id'],snapshot([item('a')],provider='generic'))
        self.run_job()
        attempt=self.menu_attempt()
        self.assertEqual((attempt['stage'],attempt['tier'],attempt['code'],attempt['grade']),('menu','structured','TOTAL_UNVERIFIABLE','C'))
        self.assertTrue(attempt['pipeline_version'])
        self.assertIsNotNone(attempt['job_id'])

    def test_exception_attempt_is_classified(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint(provider='generic'))
        self.store.apply_snapshot(endpoint['id'],snapshot([item('a')],provider='generic'))
        def boom(e,f):raise ValueError('Public endpoint returned HTTP 403')
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[],menu_fetcher=boom)
        self.run_job()
        attempt=self.menu_attempt()
        self.assertEqual((attempt['code'],attempt['grade']),('HTTP_REJECTED','D'))

    def test_resolution_failure_attempt_and_lead_are_recorded_without_an_endpoint(self):
        resolved=[dict(url='https://www.jointcommerce.com/x/menu',provider='generic',license_type='recreational',status='unresolved',
                       reason='Third-party directory is a discovery lead, not a retailer menu')]
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:resolved)
        self.run_job()
        self.assertEqual(self.store.endpoints(self.shop['id']),[])
        self.assertEqual([lead['url'] for lead in self.store.leads(self.shop['id'])],['https://www.jointcommerce.com/x/menu'])
        attempt=self.store.attempts(store_id=self.shop['id'])[0]
        self.assertEqual((attempt['stage'],attempt['status']),('resolution','unresolved'))

    def test_directory_target_returned_as_a_menu_is_a_lead_not_an_endpoint(self):
        resolved=[dict(url='https://www.leafly.com/dispensary-info/x',provider='generic',license_type='recreational',resolution_evidence={})]
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:resolved)
        self.run_job()
        self.assertEqual(self.store.endpoints(self.shop['id']),[])
        self.assertEqual(len(self.store.leads(self.shop['id'])),1)

    def test_converged_import_is_recorded_as_grade_b(self):
        endpoint=self.store.save_endpoint(self.shop['id'],self.endpoint(provider='generic'))
        items=[item(str(i)) for i in range(40)]
        incoming=snapshot(items,provider='generic',complete=False,convergence=dict(kind='visible_counter',passes=2,agreement=True,observed=40,source_total=40))
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[self.endpoint(provider='generic')],menu_fetcher=lambda e,f:incoming)
        job=self.run_job()
        self.assertEqual(next(r for r in job['results'] if r['stage']=='menu')['grade'],'B')
        attempt=self.menu_attempt()
        self.assertEqual((attempt['status'],attempt['grade'],attempt['code']),('converged','B',None))


class SupersededTargetTests(PipelineOrchestrationTests):
    def test_discovery_does_not_revive_or_import_a_superseded_endpoint(self):
        retired=self.store.save_endpoint(self.shop['id'],self.endpoint('https://example.com/wrong-branch','generic'))
        self.store.supersede_endpoint(retired['id'],'Different branch')
        fetch=Mock(return_value=snapshot([item()],provider='generic'))
        self.service=SyncService(self.store,FixtureFetcher(),resolver=lambda s,f:[self.endpoint('https://example.com/wrong-branch','generic'),self.endpoint('https://example.com/right','generic')],menu_fetcher=fetch)
        self.run_job()
        urls=[call.args[0]['url'] for call in fetch.call_args_list]
        self.assertEqual(urls,['https://example.com/right'])
        self.assertEqual(self.store.endpoint(retired['id'])['status'],'superseded')
