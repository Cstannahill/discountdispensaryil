import json
import sqlite3
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sample_stores import verdict, saved_targets


def saved_database(endpoints):
    database = sqlite3.connect(':memory:')
    database.row_factory = sqlite3.Row
    database.execute('CREATE TABLE live_stores(id TEXT PRIMARY KEY, name TEXT, address TEXT, city TEXT, state TEXT, latitude REAL, longitude REAL)')
    database.execute('CREATE TABLE live_endpoints(id TEXT PRIMARY KEY, store_id TEXT, url TEXT, provider TEXT, provider_store_id TEXT, '
                     'license_type TEXT, status TEXT, last_attempt_at TEXT, last_success_at TEXT, resolution_json TEXT)')
    database.execute("INSERT INTO live_stores(id,name,city,state) VALUES ('s1','Store One','Chicago','IL')")
    for endpoint in endpoints:
        database.execute('INSERT INTO live_endpoints VALUES (:id,:store_id,:url,:provider,:provider_store_id,:license_type,:status,'
                         ':last_attempt_at,:last_success_at,:resolution_json)', dict(dict(provider_store_id=None, status='active', last_success_at=None,
                                                                                       resolution_json='{}'), **endpoint))
    return database


class SavedTargetTests(unittest.TestCase):
    def test_samples_the_accepted_endpoint_not_the_most_recently_attempted_one(self):
        database = saved_database([
            dict(id='accepted', store_id='s1', url='https://a.example/menu', provider='jane', license_type='recreational',
                 last_attempt_at='2026-10-01T00:00:00', last_success_at='2026-10-01T00:00:00'),
            dict(id='rejected', store_id='s1', url='https://other.example/menu', provider='generic', license_type='recreational',
                 last_attempt_at='2026-10-19T00:00:00', status='active'),
        ])
        self.assertEqual([endpoint['id'] for _, endpoint in saved_targets(database, ['s1'])], ['accepted'])

    def test_samples_each_accepted_license_with_its_resolution_context(self):
        resolution = json.dumps(dict(identity_confidence=0.9, script_urls=['https://sdk.example/x.js']))
        database = saved_database([
            dict(id='rec', store_id='s1', url='https://a.example/rec', provider='jane', license_type='recreational',
                 last_attempt_at='2026-10-01T00:00:00', last_success_at='2026-10-01T00:00:00', resolution_json=resolution),
            dict(id='med', store_id='s1', url='https://a.example/med', provider='jane', license_type='medicinal',
                 last_attempt_at='2026-10-02T00:00:00', last_success_at='2026-10-02T00:00:00', resolution_json=resolution),
        ])
        targets = saved_targets(database, ['s1'])
        self.assertEqual(sorted(endpoint['id'] for _, endpoint in targets), ['med', 'rec'])
        for _, endpoint in targets:
            self.assertEqual(endpoint['identity_confidence'], 0.9)
            self.assertEqual(endpoint['script_urls'], ['https://sdk.example/x.js'])

    def test_superseded_endpoints_are_never_sampled(self):
        database = saved_database([
            dict(id='old', store_id='s1', url='https://old.example/menu', provider='jane', license_type='recreational',
                 last_attempt_at='2026-10-19T00:00:00', last_success_at='2026-10-01T00:00:00', status='superseded'),
        ])
        self.assertEqual(saved_targets(database, ['s1']), [])

    def test_store_without_an_accepted_endpoint_samples_its_latest_live_attempt(self):
        database = saved_database([
            dict(id='older', store_id='s1', url='https://a.example/menu', provider='generic', license_type='recreational',
                 last_attempt_at='2026-10-01T00:00:00'),
            dict(id='latest', store_id='s1', url='https://b.example/menu', provider='generic', license_type='recreational',
                 last_attempt_at='2026-10-19T00:00:00'),
        ])
        self.assertEqual([endpoint['id'] for _, endpoint in saved_targets(database, ['s1'])], ['latest'])


class SampleVerdictTests(unittest.TestCase):
    def test_proven_branch_with_products_is_sample_ok(self):
        self.assertEqual(verdict(dict(items=40, errors=[])), 'SAMPLE_PRODUCTS')

    def test_no_products_is_reported_not_guessed(self):
        self.assertEqual(verdict(dict(items=0, errors=[])), 'NO_PRODUCTS')

    def test_branch_mismatch_is_never_ok(self):
        self.assertEqual(verdict(dict(items=40, errors=['BRANCH_MISMATCH'])), 'BRANCH_UNPROVEN')

    def test_errors_win(self):
        self.assertEqual(verdict(dict(items=40, error='boom')), 'ERROR')


if __name__ == '__main__':
    unittest.main()
