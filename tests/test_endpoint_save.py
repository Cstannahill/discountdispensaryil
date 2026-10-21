"""Saving an endpoint whose tenant is already saved under another URL must not collide with an endpoint already at the new URL."""
import tempfile
import unittest
from pathlib import Path

from backend.storage import Store
from test_storage import observation


class SaveEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.db.import_registry([observation()], 'source')
        region = self.db.create_region(40.9844, -89.0388, 'ZIP', 50)
        self.shop = self.db.stores_in_region(region['id'])[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_tenant_saved_elsewhere_does_not_collide_with_the_endpoint_at_the_new_url(self):
        base = dict(provider='generic', license_type='recreational', resolution_evidence=[])
        self.db.save_endpoint(self.shop['id'], dict(base, url='https://x.example/stores/a/', provider_store_id='t1'))
        self.db.save_endpoint(self.shop['id'], dict(base, url='https://x.example/menu/', provider_store_id=None))
        saved = self.db.save_endpoint(self.shop['id'], dict(base, url='https://x.example/menu/', provider_store_id='t1'))
        self.assertEqual('https://x.example/menu/', saved['url'])


if __name__ == '__main__':
    unittest.main()
