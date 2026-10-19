import copy
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from backend.network import FetchResult
from backend.providers.jane import api_key, fetch, slices

ROOT = Path('tests/fixtures/provider_jane')
PRODUCTS = json.loads((ROOT / 'products.json').read_text(encoding='utf-8'))
TEMPLATES = {p['search_attributes']['kind']: p for p in PRODUCTS}
ENDPOINT = dict(url='https://www.iheartjane.com/stores/3050/nuera-pekin-rec/menu', provider='jane', provider_store_id='3050', license_type='recreational')
TARGET = dict(name='NuEra Pekin', address='3249 Court St', city='Pekin', state='IL', latitude=40.5478, longitude=-89.6031)


def result(url, value, n):
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    return FetchResult(url, 200, body, {}, f'ev-{n}', '2026-10-18T09:00:00Z')


class JaneFixture:
    """Recorded store detail, page key and product records; counts drive the platform's paging rules
    (1000 ids per slice, attributes for the first 60, 60 per hydration call)."""
    def __init__(self, counts, brands=None, mode=None):
        self.counts, self.brands, self.mode, self.calls = counts, brands or {}, mode, 0
        self.browser_options = {'target_store': TARGET}

    def record(self, kind, index, brand=None):
        record = copy.deepcopy(TEMPLATES.get(kind, PRODUCTS[0]))
        product_id = abs(hash((kind, brand, index))) % 10**9
        record.update(object_id=f'{kind}-{brand}-{index}', product_id=product_id)
        record['search_attributes'].update(product_id=product_id, objectID=record['object_id'], name=f'{kind} {brand} {index}', kind=kind)
        if self.mode == 'other_store' and index == 3:
            record['store_id'] = 9999
        if self.mode == 'other_location':
            record['search_attributes']['_geoloc'] = {'lat': 41.88, 'lng': -87.63}
        if self.mode == 'near_location':
            record['search_attributes']['_geoloc'] = {'lat': 40.5644, 'lng': -89.6288}
        if self.mode == 'medical_only':
            record['search_attributes']['store_types'] = ['medical']
        return record

    def get(self, url, headers=None):
        self.calls += 1
        return result(url, (ROOT / 'page.html').read_bytes(), self.calls)

    def post(self, url, *, json, headers=None):
        self.calls += 1
        path = urlsplit(url).path
        if path == '/v2/facets':
            wanted = json['searchFacets'][0]
            if wanted == 'kind':
                return result(url, {'searchFacets': {'kind': dict(self.counts)}}, self.calls)
            kind = json['searchFilter'].split('"')[1]
            return result(url, {'searchFacets': {'brand': dict(self.brands.get(kind, {}))}}, self.calls)
        if path == '/v2/multi':
            placement = json['placements'][0]
            parts = placement['search_filter'].split('"')
            kind, brand = parts[1], (parts[3] if len(parts) > 3 else None)
            count = self.brands[kind][brand] if brand else self.counts[kind]
            ids = [self.record(kind, i, brand) for i in range(min(count, 1000))]
            stubs = [r if i < placement['page_size'] else {k: r[k] for k in ('object_id', 'product_id', 'store_id')} for i, r in enumerate(ids)]
            return result(url, {'placements': [{'nb_hits': count, 'placement': 'menu_inline_table', 'products': stubs}]}, self.calls)
        if path == '/v2/smartpage':
            wanted = json['object_ids'][:60]
            if self.mode == 'hydrate_short':
                wanted = wanted[:-1]
            out = []
            for object_id in wanted:
                kind, brand, index = object_id.split('-', 2)
                record = self.record(kind, int(index), None if brand == 'None' else brand)
                out.append({'object_id': object_id, 'search_attributes': record['search_attributes']})
            return result(url, {'products': out}, self.calls)
        raise AssertionError('unexpected POST ' + url)


class JaneTests(unittest.TestCase):
    def test_a_nearby_platform_location_needs_the_retailer_page_identity(self):
        # NuEra Pekin: the same street address in both sources, but the registry point is 1.8 mi off.
        unproven = fetch(ENDPOINT, JaneFixture({'flower': 1}, mode='near_location'))
        self.assertFalse(unproven['complete'])
        proven = fetch(dict(ENDPOINT, identity_confidence='name_locality'), JaneFixture({'flower': 1}, mode='near_location'))
        self.assertTrue(proven['complete'], proven['errors'])
        self.assertEqual(proven['branch_proof']['method'], 'retailer_page_identity')
        self.assertEqual(fetch(ENDPOINT, JaneFixture({'flower': 1}))['branch_proof']['method'], 'platform_location')

    def test_a_store_without_registry_coordinates_is_not_proven(self):
        fixture = JaneFixture({'flower': 1})
        fixture.browser_options = {'target_store': dict(TARGET, latitude=None)}
        self.assertIn('cannot be proven', fetch(ENDPOINT, fixture)['errors'][0]['message'])

    def test_public_sdk_key_is_read_from_the_storefront_page(self):
        evidence = []
        self.assertEqual(api_key(ENDPOINT, JaneFixture({}), evidence), 'ce5f15c9-3d09-441d-9bfd-26e87aff5925')
        self.assertTrue(evidence)

    def test_full_menu_reconciles_to_the_kind_facet_total_over_two_traversals(self):
        result = fetch(ENDPOINT, JaneFixture({'flower': 130, 'vape': 70, 'edible': 25}))
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(result['source_product_count'], 225)
        # Flower carries eighth and quarter prices; vape a half gram; edibles one "each" price.
        self.assertEqual(len(result['items']), 130 * 2 + 70 + 25)

    def test_a_kind_above_the_search_window_is_split_by_brand(self):
        fixture = JaneFixture({'flower': 1200}, brands={'flower': {'a': 700, 'b': 500}})
        self.assertEqual([s['filter'] for s in slices(fixture.counts, lambda kind: fixture.brands[kind])],
                         ['kind:"flower" AND brand:"a"', 'kind:"flower" AND brand:"b"'])
        result = fetch(ENDPOINT, fixture)
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(result['source_product_count'], 1200)

    def test_flower_weights_prices_and_specials_come_from_the_record(self):
        result = fetch(ENDPOINT, JaneFixture({'flower': 1}))
        by_weight = {item['variant_id']: item for item in result['items']}
        self.assertEqual(set(by_weight), {'eighth_ounce', 'quarter_ounce'})
        self.assertEqual(by_weight['eighth_ounce']['weight_grams'], '3.5')
        self.assertEqual(float(by_weight['eighth_ounce']['regular_price']), 50)
        self.assertEqual(float(by_weight['eighth_ounce']['effective_price']), 30)

    def test_wrong_branch_wrong_license_foreign_records_and_short_hydration_never_complete(self):
        for mode in ('other_location', 'medical_only', 'other_store', 'hydrate_short'):
            result = fetch(ENDPOINT, JaneFixture({'flower': 130}, mode=mode))
            self.assertFalse(result['complete'], mode)
            self.assertTrue(result['errors'], mode)



class WhiteLabelStorefrontTests(unittest.TestCase):
    """Retailer-hosted Jane storefronts (NuEra, Cannabist) render the store's own dmerch records into the page."""
    def page(self, url, ids, extra=''):
        records = ''.join('{\\"store_id\\":%d,\\"storeId\\":%d}' % (i, i) for i in ids)
        text = '<link rel="canonical" href="%s"><script>self.__next_f.push([1,"https://dmerch.iheartjane.com %s%s"])</script>' % (url, records, extra)
        return FetchResult(url, 200, text.encode(), {}, 'ev', '2026-10-18T09:00:00Z')

    def test_page_naming_one_jane_store_is_a_native_jane_endpoint(self):
        from backend.adapters import _detect_endpoint
        url = 'https://nueracannabis.com/shop/store/1517/featured'
        endpoint = _detect_endpoint(url, self.page(url, [1517, 1517]))
        self.assertEqual(('jane', '1517'), (endpoint['provider'], endpoint['provider_store_id']))

    def test_mixed_or_contradicting_store_ids_are_not_a_contract(self):
        from backend.adapters import _detect_endpoint
        url = 'https://nueracannabis.com/shop/store/1517/featured'
        self.assertNotEqual('jane', _detect_endpoint(url, self.page(url, [1517, 3057]))['provider'])
        self.assertNotEqual('jane', _detect_endpoint(url, self.page(url, [3057]))['provider'])

    def test_store_types_on_the_records_set_the_license_context(self):
        from backend.adapters import _observed_endpoint
        url = 'https://nueracannabis.com/shop/store/1518/featured'
        medical = self.page(url, [1518], ' {\\"store_types\\":[\\"medical\\"]}')
        recreational = self.page(url, [1518], ' {\\"store_types\\":[\\"medical\\",\\"recreational\\"]}')
        self.assertEqual('medicinal', _observed_endpoint(url, medical)['license_type'])
        self.assertEqual('recreational', _observed_endpoint(url, recreational)['license_type'])

    def test_page_location_rejects_sibling_storefronts_at_resolution(self):
        from backend.adapters import _detect_endpoint
        from backend.site_discovery import provider_address_matches
        store = dict(address='504 Riverside Dr', latitude=40.6809, longitude=-89.5821)
        url = 'https://nueracannabis.com/shop/store/1517/featured'
        here = self.page(url, [1517], ' {\\"_geoloc\\":{\\"lat\\":40.6809635,\\"lng\\":-89.5820017}}')
        there = self.page(url, [1517], ' {\\"_geoloc\\":{\\"lat\\":40.1164,\\"lng\\":-88.2434}}')
        self.assertTrue(provider_address_matches(store, _detect_endpoint(url, here)))
        self.assertFalse(provider_address_matches(store, _detect_endpoint(url, there)))
        self.assertIsNone(provider_address_matches(store, _detect_endpoint(url, self.page(url, [1517]))))

    def test_one_endpoint_per_jane_store_and_siblings_are_dropped(self):
        from unittest.mock import patch
        from backend.adapters import resolve_menu
        here = ' {\\"_geoloc\\":{\\"lat\\":40.6809635,\\"lng\\":-89.5820017}}'
        there = ' {\\"_geoloc\\":{\\"lat\\":40.1164,\\"lng\\":-88.2434}}'
        pages = {'https://chain.example/shop/store/1517/featured': ([1517], here, '<a href="/shop/store/1517/shop-all">x</a><a href="/shop/store/3057/featured">y</a>'),
                 'https://chain.example/shop/store/1517/shop-all': ([1517], here, ''), 'https://chain.example/shop/store/3057/featured': ([3057], there, '')}
        test = self
        class Fetcher:
            def get(self, url):
                ids, extra, links = pages[url]
                page = test.page(url, ids, extra)
                return FetchResult(url, 200, page.body + ('<h1>Chain East Peoria</h1>504 Riverside Dr' + links).encode(), {}, 'ev', page.fetched_at)
        store = dict(name='Chain - East Peoria', city='East Peoria', state='IL', address='504 Riverside Dr', latitude=40.6809, longitude=-89.5821,
                     lead_urls=['https://chain.example/shop/store/1517/featured', 'https://chain.example/shop/store/1517/shop-all', 'https://chain.example/shop/store/3057/featured'])
        with patch('backend.site_discovery.search_websites', return_value=[]), patch('backend.locators.discover_menu_candidates', return_value=[]):
            found = [(m['provider'], m.get('provider_store_id')) for m in resolve_menu(store, Fetcher()) if not m.get('status')]
        self.assertEqual(found, [('jane', '1517')])

    def test_rise_menu_urls_carry_the_jane_store_id_even_when_the_page_refuses_us(self):
        from unittest.mock import patch
        from backend.adapters import resolve_menu
        class Refused:
            def get(self, url):
                return FetchResult(url, 403, b'Forbidden', {}, 'ev', '2026-10-18T09:00:00Z')
        def resolve(store, *urls):
            with patch('backend.site_discovery.search_websites', return_value=[]), patch('backend.locators.discover_menu_candidates', return_value=[]):
                return [(m['provider'], m.get('provider_store_id'), m['license_type'], m.get('identity_confidence'))
                        for m in resolve_menu(dict(store, lead_urls=list(urls)), Refused()) if not m.get('status')]
        canton = dict(name='Rise - Canton', city='Canton', state='IL', address='3104 N Main St', latitude=40.5568, longitude=-90.0270)
        self.assertEqual(resolve(canton, 'https://risecannabis.com/dispensaries/illinois/canton/1343/recreational-menu/?refinementList%5Bbrand%5D%5B%5D=RYTHM'),
                         [('jane', '1343', 'recreational', 'name_locality')])
        colorado = dict(name='Rise - Joliet  Colorado Ave', city='Joliet', state='IL', address='2865 Colorado Ave', latitude=41.5, longitude=-88.1)
        # A sibling branch in the same city must prove itself at the platform's own coordinates.
        self.assertEqual(resolve(colorado, 'https://risecannabis.com/dispensaries/illinois/joliet-rock-creek/254/medical-menu/'),
                         [('jane', '254', 'medicinal', None)])


if __name__ == '__main__':
    unittest.main()
