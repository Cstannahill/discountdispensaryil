"""An endpoint bound to the wrong store is retired only when the same platform store is bound to another registry store."""
import tempfile
import unittest
from pathlib import Path

from backend.storage import Store
from test_storage import item, observation, snapshot


class MisboundEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.db.import_registry([observation('one', name='Shop One'), observation('two', name='Shop Two')], 'source')
        region = self.db.create_region(40.9844, -89.0388, 'ZIP', 50)
        self.region = region
        self.one, self.two = [s for s in self.db.stores_in_region(region['id'])]

    def tearDown(self):
        self.tmp.cleanup()

    def accepted(self, store, url, tenant, items):
        e = self.db.save_endpoint(store['id'], dict(url=url, provider='fixture', provider_store_id=tenant, license_type='recreational', resolution_evidence=[]))
        self.db.apply_snapshot(e['id'], snapshot(items), now='2026-10-17T08:00:00+00:00')
        return e

    def test_a_menu_whose_platform_store_belongs_to_another_registry_store_is_retired(self):
        own = self.accepted(self.one, 'https://x.example/menu/one', 'tenant-1', [item('a', name='A')])
        stray = self.accepted(self.one, 'https://x.example/menu/two', 'tenant-2', [item('b', name='B')])
        self.accepted(self.two, 'https://x.example/menu/two', 'tenant-2', [item('b', name='B')])
        self.db.retire_misbound_endpoint(stray['id'], 'wrong branch')
        self.assertEqual([own['id']], [e['id'] for e in self.db.endpoints(self.one['id'])])

    def test_a_menu_a_checked_page_names_as_another_branch_is_retired_with_its_proof(self):
        own = self.accepted(self.one, 'https://x.example/menu/one', 'tenant-1', [item('a', name='A')])
        stray = self.accepted(self.one, 'https://x.example/menu/mi', 'tenant-9', [item('b', name='B')])
        self.db.retire_wrong_branch_endpoint(stray['id'], 'page title names the Grand Haven, MI branch', 'https://x.example/menu/mi/product/1')
        self.assertEqual('superseded', self.db.endpoint(stray['id'])['status'])
        self.assertIn('Grand Haven', self.db.endpoint(stray['id'])['last_error'])
        self.assertEqual('complete', self.db.endpoint(own['id'])['status'])
        names = {o['name'] for o in self.db.query_offers(self.region['id'], include_stale=True)['items']}
        self.assertEqual({'A'}, names)

    def test_retiring_a_wrong_branch_menu_needs_a_reason_and_a_page(self):
        stray = self.accepted(self.one, 'https://x.example/menu/mi', 'tenant-9', [item('b', name='B')])
        for reason, proof in (('', 'https://x.example/'), ('wrong', ''), ('wrong', 'not a url')):
            with self.assertRaises(ValueError):
                self.db.retire_wrong_branch_endpoint(stray['id'], reason, proof)

    def test_a_menu_with_no_other_owner_is_refused(self):
        only = self.accepted(self.one, 'https://x.example/menu/one', 'tenant-1', [item('a', name='A')])
        with self.assertRaises(ValueError):
            self.db.retire_misbound_endpoint(only['id'], 'no proof')


if __name__ == '__main__':
    unittest.main()
