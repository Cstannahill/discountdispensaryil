from pathlib import Path
import tempfile
import unittest

from backend.failures import FailureCode
from backend.storage import Store
from tests.test_storage import observation, item, snapshot

NOW = '2026-10-17T07:00:00+00:00'
LATER = '2026-10-17T08:00:00+00:00'


def converged(items, **changes):
    return snapshot(items, complete=False, convergence=dict(kind='visible_counter', passes=2, agreement=True,
                    observed=len(items), source_total=len(items)), **changes)


def many(n, prefix='p', **changes):
    return [item(f'{prefix}{i}', **changes) for i in range(n)]


class GradedStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.db = Store(self.path / 't.db', self.path / 'evidence')
        self.db.import_registry([observation()], 'source-evidence', '2026-10-08', now='2026-10-17T06:00:00+00:00')
        self.region = self.db.create_region(40.9844, -89.0388, 'ZIP 61358', 50)
        self.shop = self.db.stores_in_region(self.region['id'])[0]
        self.endpoint = self.db.save_endpoint(self.shop['id'], dict(url='https://example.com/menu', provider='fixture',
                                              provider_store_id='t', license_type='recreational', resolution_evidence=['e']))

    def tearDown(self):
        self.tmp.cleanup()

    def apply(self, snap, now=NOW):
        return self.db.apply_snapshot(self.endpoint['id'], snap, now=now)

    def test_reopening_a_pre_existing_database_adds_new_objects(self):
        again = Store(self.path / 't.db', self.path / 'evidence')
        with again.connection() as conn:
            names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
            columns = {r[1] for r in conn.execute('pragma table_info(live_endpoints)')}
        self.assertTrue({'live_attempts', 'live_leads'} <= names)
        self.assertIn('last_converged_at', columns)

    def test_full_proof_is_grade_a(self):
        result = self.apply(snapshot(many(30)))
        self.assertEqual((result['status'], result['grade']), ('complete', 'A'))

    def test_valid_convergence_is_grade_b_and_not_an_accepted_snapshot(self):
        result = self.apply(converged(many(40)))
        self.assertEqual((result['status'], result['grade']), ('converged', 'B'))
        row = self.db.endpoint(self.endpoint['id'])
        self.assertIsNone(row['last_success_at'])
        self.assertEqual(row['last_converged_at'], NOW)
        counts = self.db.coverage(self.region['id'], now=LATER)['counts']
        self.assertEqual(counts['stores_with_accepted_menus'], 0)
        self.assertEqual(counts['stores_with_converged_menus'], 1)

    def test_malformed_convergence_stays_partial_grade_c(self):
        bad = converged(many(40))
        bad['convergence']['agreement'] = False
        result = self.apply(bad)
        self.assertEqual((result['status'], result['grade']), ('partial', 'C'))
        self.assertIsNone(self.db.endpoint(self.endpoint['id'])['last_converged_at'])

    def test_provider_errors_block_convergence(self):
        result = self.apply(converged(many(40), errors=[dict(code='incomplete_generic_menu', message='x')]))
        self.assertEqual((result['status'], result['grade']), ('partial', 'C'))

    def test_converged_offers_are_labeled_and_hidden_from_default_rankings(self):
        self.apply(converged(many(40)))
        default = self.db.query_offers(self.region['id'], now=NOW)
        shown = self.db.query_offers(self.region['id'], include_unverified=True, now=NOW)
        self.assertEqual(default['total'], 0)
        self.assertEqual(shown['total'], 40)
        self.assertEqual({o['completeness'] for o in shown['items']}, {'B'})

    def test_converged_freshness_uses_converged_time(self):
        self.apply(converged(many(40)))
        fresh = self.db.query_offers(self.region['id'], include_unverified=True, now='2026-10-17T08:00:00+00:00')
        stale = self.db.query_offers(self.region['id'], include_unverified=True, now='2026-10-18T08:00:00+00:00')
        self.assertEqual(fresh['total'], 40)
        self.assertEqual(stale['total'], 0)

    def test_converged_never_overwrites_or_removes_accepted_catalog(self):
        self.apply(snapshot(many(40)))
        result = self.apply(converged(many(40, prefix='other')), now=LATER)
        self.assertEqual(result['status'], 'converged')
        accepted = self.db.menu_products(self.endpoint['id'])
        self.assertEqual(accepted['total_variants'], 40)
        self.assertTrue(all(i['source_id'].startswith('p') for i in accepted['items']))
        self.assertEqual(result['removed'], 0)

    def test_converged_refresh_replaces_only_converged_origin_offers(self):
        self.apply(converged(many(40)))
        result = self.apply(converged(many(40, prefix='q')), now=LATER)
        self.assertEqual(result['status'], 'converged')
        rows = self.db.query_offers(self.region['id'], include_unverified=True, now=LATER, page_size=200)
        self.assertEqual({o['source_id'][0] for o in rows['items']}, {'q'})

    def test_converged_large_drop_is_not_trusted(self):
        self.apply(converged(many(100)))
        result = self.apply(converged(many(30)), now=LATER)
        self.assertEqual((result['status'], result['grade']), ('partial', 'C'))
        self.assertEqual(self.db.query_offers(self.region['id'], include_unverified=True, now=LATER)['total'], 100)

    def test_a_later_accepted_snapshot_supersedes_converged_offers(self):
        self.apply(converged(many(40)))
        self.apply(snapshot(many(40, prefix='a')), now=LATER)
        rows = self.db.query_offers(self.region['id'], include_unverified=True, now=LATER, page_size=200)
        self.assertEqual({o['completeness'] for o in rows['items']}, {'A'})
        self.assertEqual(rows['total'], 40)

    def test_snapshot_manifest_and_result_carry_the_grade(self):
        self.apply(converged(many(40)))
        self.assertEqual(self.db.menu_products(self.endpoint['id'])['snapshot']['manifest']['grade'], 'B')

    def test_attempts_are_recorded_and_classified(self):
        self.db.record_attempt(store_id=self.shop['id'], endpoint_id=self.endpoint['id'], pipeline_version='v1', stage='menu',
                               tier='generic', provider='fixture', status='failed', code=FailureCode.RENDER_BLANK,
                               items=0, seconds=1.5, detail='No structured products extracted', job_id='j1')
        rows = self.db.attempts(store_id=self.shop['id'])
        self.assertEqual(rows[0]['code'], 'RENDER_BLANK')
        self.assertEqual(rows[0]['grade'], 'D')

    def test_leads_are_stored_apart_from_endpoints(self):
        self.db.record_lead(self.shop['id'], 'https://www.jointcommerce.com/x', 'directory', 'Third-party directory lead')
        self.db.record_lead(self.shop['id'], 'https://www.jointcommerce.com/x', 'directory', 'again')
        self.assertEqual(len(self.db.leads(self.shop['id'])), 1)
        self.assertEqual(len(self.db.endpoints(self.shop['id'])), 1)

    def test_stage_report_attributes_every_store(self):
        other = self.db.import_registry([observation(), observation('b', 'Second Shop', 40.99, -89.05)], 'e2', None,
                                        now='2026-10-17T06:30:00+00:00')
        self.db.record_attempt(store_id=self.shop['id'], endpoint_id=self.endpoint['id'], pipeline_version='v1', stage='menu',
                               tier='generic', provider='fixture', status='partial', code=FailureCode.TOTAL_UNVERIFIABLE,
                               items=80, seconds=2, detail='no total', job_id='j')
        report = self.db.stage_report(self.region['id'], pipeline_version='v1')
        self.assertEqual(report['total_stores'], 2)
        self.assertEqual(sum(report['by_stage'].values()), 2)
        by_store = {r['store_name']: r for r in report['stores']}
        self.assertEqual(by_store['Test Shop']['stage'], 'extraction_failed')
        self.assertEqual(by_store['Test Shop']['code'], 'TOTAL_UNVERIFIABLE')
        self.assertEqual(by_store['Second Shop']['stage'], 'not_attempted')


if __name__ == '__main__':
    unittest.main()


class SupersedeEndpointTests(GradedStorageTests):
    def test_superseding_hides_the_endpoint_but_keeps_the_row_and_its_reason(self):
        other = self.db.save_endpoint(self.shop['id'], dict(url='https://example.com/other', provider='fixture', provider_store_id='o', license_type='recreational', resolution_evidence=['e']))
        self.db.supersede_endpoint(other['id'], 'Different branch')
        self.assertNotIn(other['id'], [e['id'] for e in self.db.endpoints(self.shop['id'])])
        row = self.db.endpoint(other['id'])
        self.assertEqual((row['status'], row['last_error']), ('superseded', 'Different branch'))

    def test_an_endpoint_with_active_accepted_offers_cannot_be_superseded(self):
        self.apply(snapshot(many(30)))
        with self.assertRaisesRegex(ValueError, 'endpoint_has_active_offers'):
            self.db.supersede_endpoint(self.endpoint['id'], 'cleanup')
        self.assertEqual(self.db.endpoint(self.endpoint['id'])['status'], 'complete')

    def test_unknown_endpoint_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'unknown_menu'):
            self.db.supersede_endpoint('nope', 'x')


class PlatformCensusTests(GradedStorageTests):
    def test_observed_platforms_and_brand_are_reported_per_store_and_stage(self):
        from backend.platforms import brand_key
        self.db.record_platforms(self.shop['id'], [dict(platform='jane', url='https://example.com/menu', evidence_id='e1', status='observed'),
                                                   dict(platform='jane', url='https://example.com/menu', evidence_id='e2', status='observed'),
                                                   dict(platform='dutchie', url='https://other.example/', evidence_id='e3', status='identity_conflict')])
        self.assertEqual(len(self.db.store_platforms(self.shop['id'])), 2)
        report = self.db.stage_report(self.region['id'])
        row = report['stores'][0]
        # A platform seen only on a page proven to be another branch does not describe this store.
        self.assertEqual(row['platforms'], ['jane'])
        self.assertEqual(row['brand'], brand_key(self.shop['name'], self.shop['city']))
        self.assertEqual(report['by_platform'], {'jane': {'not_attempted': 1}})

    def test_a_native_endpoint_provider_counts_as_the_store_platform(self):
        self.db.save_endpoint(self.shop['id'], dict(url='https://example.com/sweed', provider='sweed', provider_store_id='s1',
                                                    license_type='recreational', resolution_evidence=['e']))
        self.assertIn('sweed', self.db.stage_report(self.region['id'])['stores'][0]['platforms'])
