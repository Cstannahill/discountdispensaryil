from pathlib import Path
import tempfile
import unittest

from backend.storage import Store
from tests.test_storage import observation, item, snapshot

NOW = '2026-10-17T07:00:00+00:00'
SOON = '2026-10-17T08:00:00+00:00'


def many(prefix, n=30):
    return [item(f'{prefix}{i}', name=f'Filler {prefix} {i}', brand='Filler') for i in range(n)]


class MatchedDealsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name)
        self.db = Store(path / 't.db', path / 'evidence')
        self.db.import_registry([observation(k, k.title(), 40.98 + i * 0.01) for i, k in enumerate(('alpha', 'bravo', 'charlie'))],
                                'source-evidence', '2026-10-08', now='2026-10-17T06:00:00+00:00')
        self.region = self.db.create_region(40.9844, -89.0388, 'ZIP 61358', 50)
        self.endpoints = {}
        for s in self.db.stores_in_region(self.region['id']):
            self.endpoints[s['name'].lower()] = self.db.save_endpoint(s['id'], dict(url=f"https://example.com/{s['name']}", provider='fixture', provider_store_id=s['name'], license_type='recreational', resolution_evidence=['e']))

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, store, products, now=NOW):
        items = [item(f'{store}-{n}', name=n, brand='Superflux', effective_price=str(p), regular_price=str(p)) for n, p in products] + many(store)
        return self.db.apply_snapshot(self.endpoints[store]['id'], snapshot(items), now=now)

    def deals(self, **kw):
        return self.db.query_offers(self.region['id'], 'recreational', now=SOON, **kw)['items']

    def test_a_price_far_below_other_stores_stays_out_of_deals_unless_asked(self):
        self.load('alpha', [('Velvet Ropes', 7.2)])
        self.load('bravo', [('Velvet Ropes', 55)])
        self.load('charlie', [('Velvet Ropes', 50)])
        names = [(r['store_name'], r['name']) for r in self.deals(q='Velvet')]
        self.assertEqual(sorted(names), [('Bravo', 'Velvet Ropes'), ('Charlie', 'Velvet Ropes')])
        self.assertEqual(len(self.deals(q='Velvet', include_unverified=True)), 3)

    def test_matched_groups_the_same_product_across_stores_with_the_cheapest_first(self):
        self.load('alpha', [('Velvet Ropes', 40), ('Only Here', 20)])
        self.load('bravo', [('Velvet Ropes', 35)])
        result = self.db.query_matched(self.region['id'], 'recreational', now=SOON)
        velvet = [g for g in result['items'] if g['name'] == 'Velvet Ropes']
        self.assertEqual(len(velvet), 1)
        self.assertEqual((velvet[0]['store_count'], velvet[0]['best']['store_name']), (2, 'Bravo'))
        self.assertFalse([g for g in result['items'] if g['name'] == 'Only Here'])
        self.assertTrue(self.db.query_matched(self.region['id'], 'recreational', min_stores=1, now=SOON)['total'] > result['total'])

    def test_coverage_names_the_stores_whose_menus_are_too_old_to_rank(self):
        self.load('alpha', [('Velvet Ropes', 40)], now='2026-10-16T06:00:00+00:00')
        self.load('bravo', [('Velvet Ropes', 35)], now=NOW)
        cover = self.db.coverage(self.region['id'], now=SOON)
        stale = {s['store_name']: s for s in cover['stale_stores']}
        self.assertEqual(set(stale), {'Alpha'})
        self.assertEqual(stale['Alpha']['age_hours'], 26.0)
        self.assertGreater(stale['Alpha']['hidden_offers'], 0)


if __name__ == "__main__":
    unittest.main()
