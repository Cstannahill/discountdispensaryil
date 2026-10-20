import copy
import json
from pathlib import Path
import unittest

from backend.network import FetchResult
from backend.providers.joint import fetch, normalize, observe

ROOT = Path('tests/fixtures/provider_joint')
SEARCH = json.loads((ROOT / 'search.json').read_text(encoding='utf-8'))
COOKIES = dict(url='https://bloomington.cookies.co/products/', provider='joint', provider_store_id='5449', license_type='recreational')
TERRABIS_MED = dict(url='https://terrabis.co/menu/dixon-il-med/', provider='joint', provider_store_id='6460', license_type='medicinal')


class JointFixture:
    """Serves the recorded storefront page and search responses; `count` products, one variant set each."""
    def __init__(self, page='page_cookies.html', count=2, mode=None):
        self.page, self.count, self.mode, self.calls = (ROOT / page).read_bytes(), count, mode, 0
        self.sorts = []

    def get(self, url, headers=None):
        self.calls += 1
        return FetchResult(url, 200, self.page, {}, f'page-{self.calls}', '2026-10-18T09:00:00Z')

    def post(self, url, *, json, headers=None):
        self.calls += 1
        offset, size = json['from'], json['size']
        self.sorts.append(json.get('sort'))
        base = SEARCH['hits']['hits']
        hits = []
        for index in range(offset, min(offset + size, self.count)):
            hit = copy.deepcopy(base[index % len(base)])
            hit['_source']['jointId'] = f"p{index}"
            hits.append(hit)
        if self.mode == 'repeat' and offset:
            hits = [copy.deepcopy(base[0])] * len(hits)
        if self.mode == 'drop' and offset:
            hits = hits[:-1]
        if self.mode == 'other_business' and offset == 0:
            hits[0]['_source']['businessId'] = 1
        total = dict(value=self.count, relation='eq')
        return FetchResult(url, 200, json_bytes(dict(hits=dict(total=total, hits=hits))), {}, f'search-{self.calls}', '2026-10-18T09:00:00Z')


def json_bytes(value):
    return json.dumps(value).encode()


class JointTests(unittest.TestCase):
    def page_response(self, name):
        return FetchResult('https://example.com/menu/', 200, (ROOT / name).read_bytes(), {}, 'ev-1', '2026-10-18T09:00:00Z')

    def test_observed_terrabis_currentstore_identifies_the_branch_business(self):
        endpoint = observe('https://terrabis.co/menu/dixon-il-med/', self.page_response('page_terrabis.html'))
        self.assertEqual(endpoint['provider'], 'joint')
        self.assertEqual(endpoint['provider_store_id'], '6460')
        self.assertEqual(endpoint['license_type'], 'medicinal')
        self.assertIn('Dixon', endpoint['resolution_evidence']['retailer_name'])

    def test_observed_cookies_store_schema_identifies_the_single_business(self):
        endpoint = observe('https://bloomington.cookies.co/products/', self.page_response('page_cookies.html'))
        self.assertEqual(endpoint['provider_store_id'], '5449')
        self.assertEqual(endpoint['resolution_evidence']['retailer_address'], '1006 Jc Pkwy Ste 108')

    def test_a_page_without_a_joint_store_is_not_a_joint_endpoint(self):
        self.assertIsNone(observe('https://example.com/', FetchResult('https://example.com/', 200, b'<html>plain</html>', {}, 'e', 't')))

    def test_a_medicinal_endpoint_takes_only_medical_variants(self):
        product = SEARCH['hits']['hits'][0]['_source']
        items = normalize(product, COOKIES, 'RECREATIONAL')
        self.assertTrue(items)
        self.assertTrue(all(item['variant_id'] in {v['jointId'] for v in product['variants'] if v['menuType'] == 'RECREATIONAL'} for item in items))
        medical = normalize(product, TERRABIS_MED, 'MEDICAL')
        self.assertTrue(all(item['variant_id'] in {v['jointId'] for v in product['variants'] if v['menuType'] == 'MEDICAL'} for item in medical))

    def test_price_stock_and_dose_are_read_from_the_variant(self):
        product = SEARCH['hits']['hits'][0]['_source']
        variant = next(v for v in product['variants'] if v['menuType'] == 'RECREATIONAL')
        item = normalize(product, COOKIES, 'RECREATIONAL')[0]
        self.assertEqual(float(item['regular_price']), float(variant['price']))
        self.assertEqual(item['weight_label'], variant['option'])
        self.assertEqual(item['available'], int(variant['quantity']) > 0)
        self.assertEqual(item['weight_grams'], '3.5' if variant['option'].replace(' ', '') == '3.5g' else None)
        dose = copy.deepcopy(product)
        for v in dose['variants']:
            v['option'] = '100 mg'
        self.assertTrue(all(i['weight_grams'] is None for i in normalize(dose, COOKIES, 'RECREATIONAL')))

    def test_a_capped_read_keeps_the_products_it_already_read(self):
        result = fetch(dict(COOKIES, max_pages=2), JointFixture(count=300))
        self.assertFalse(result['complete'])
        self.assertEqual(result['errors'][0]['code'], 'incomplete_joint_menu')
        self.assertEqual(len(result['pages']), 2)
        self.assertGreater(len(result['items']), 0)

    def test_full_menu_reconciles_to_its_exact_total_over_two_traversals(self):
        fixture = JointFixture(count=250)
        result = fetch(COOKIES, fixture)
        self.assertTrue(result['complete'], result['errors'])
        # itemsSold alone has ties, so pages overlap; a unique product id must break them.
        self.assertTrue(all({'jointId': 'asc'} in sort for sort in fixture.sorts))
        self.assertEqual(len(result['pages']), 6)
        self.assertEqual(result['source_product_count'], 250)

    def test_business_mismatch_repeated_dropped_and_wrong_business_never_complete(self):
        self.assertFalse(fetch(COOKIES, JointFixture(page='page_terrabis.html'))['complete'])
        for mode in ('repeat', 'drop', 'other_business'):
            result = fetch(COOKIES, JointFixture(count=250, mode=mode))
            self.assertFalse(result['complete'], mode)
            self.assertTrue(result['errors'], mode)


if __name__ == '__main__':
    unittest.main()
