"""A duplicate menu is retired only when its active offers match the kept menu exactly; accepted inventory is never hidden on a guess."""
import tempfile
import unittest
from pathlib import Path

from backend.storage import Store
from test_storage import item, observation, snapshot


class DuplicateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.db.import_registry([observation()], 'source')
        region = self.db.create_region(40.9844, -89.0388, 'ZIP', 50)
        self.shop = self.db.stores_in_region(region['id'])[0]
        self.region = region

    def tearDown(self):
        self.tmp.cleanup()

    def accepted(self, url, items, now):
        endpoint = self.db.save_endpoint(self.shop['id'], dict(url=url, provider='fixture', license_type='recreational', resolution_evidence=[]))
        self.db.apply_snapshot(endpoint['id'], snapshot(items), now=now)
        return endpoint

    def test_two_endpoints_with_identical_offers_are_a_proven_duplicate(self):
        first = self.accepted('https://example.com/menu/', [item('a', name='Flower A'), item('b', name='Flower B')], '2026-10-17T08:00:00+00:00')
        second = self.accepted('https://example.com/shop/', [item('a', name='Flower A'), item('b', name='Flower B')], '2026-10-17T09:00:00+00:00')
        pairs = self.db.identical_duplicate_endpoints()
        self.assertEqual([(second['id'], first['id'])], pairs)

    def test_offers_with_a_missing_brand_still_compare(self):
        first = self.accepted('https://example.com/menu/', [item('a', name='Flower A', brand=None)], '2026-10-17T08:00:00+00:00')
        second = self.accepted('https://example.com/shop/', [item('a', name='Flower A', brand=None)], '2026-10-17T09:00:00+00:00')
        self.assertEqual([(second['id'], first['id'])], self.db.identical_duplicate_endpoints())

    def test_endpoints_with_different_offers_are_not_duplicates(self):
        self.accepted('https://example.com/menu/', [item('a', name='Flower A'), item('b', name='Flower B')], '2026-10-17T08:00:00+00:00')
        self.accepted('https://example.com/shop/', [item('a', name='Flower A'), item('c', name='Flower C')], '2026-10-17T09:00:00+00:00')
        self.assertEqual([], self.db.identical_duplicate_endpoints())

    def test_retiring_a_proven_duplicate_hides_its_offers_but_keeps_the_kept_menu(self):
        first = self.accepted('https://example.com/menu/', [item('a', name='Flower A'), item('b', name='Flower B')], '2026-10-17T08:00:00+00:00')
        second = self.accepted('https://example.com/shop/', [item('a', name='Flower A'), item('b', name='Flower B')], '2026-10-17T09:00:00+00:00')
        keep, duplicate = self.db.identical_duplicate_endpoints()[0]
        self.db.retire_duplicate_endpoint(duplicate, keep, 'Same offers as the kept menu')
        self.assertEqual([keep], [e['id'] for e in self.db.endpoints(self.shop['id'])])
        self.assertEqual(2, self.db.stores_in_region(self.region['id'])[0]['product_count'])

    def test_retiring_an_endpoint_that_is_not_identical_is_refused(self):
        first = self.accepted('https://example.com/menu/', [item('a', name='Flower A'), item('b', name='Flower B')], '2026-10-17T08:00:00+00:00')
        second = self.accepted('https://example.com/shop/', [item('a', name='Flower A'), item('c', name='Flower C')], '2026-10-17T09:00:00+00:00')
        with self.assertRaises(ValueError):
            self.db.retire_duplicate_endpoint(second['id'], first['id'], 'not proven')


if __name__ == '__main__':
    unittest.main()
