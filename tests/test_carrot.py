import gzip
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from backend.network import FetchResult
from backend.providers import carrot

URL = 'https://shop.example.test/store?locId=2'
SEARCH = 'https://api.nevada.getcarrot.io/api/v1/store/search-products?locId=2'
LOCATIONS = 'https://api.nevada.getcarrot.io/api/v1/store/locations'
ENDPOINT = dict(url=URL, provider='carrot', provider_store_id='2', license_type='recreational')
TARGET = dict(address='20 Northwest Hwy', city='Cary')
RECORDS = [dict(id=1, name='Los Lunas, NM', addressLine1='3513 HW-47', enabled='StaffAndCustomers'),
           dict(id=2, name='Cary, IL', addressLine1='20 NW HWY', enabled='StaffAndCustomers')]


def document(identity, price=30.0, location=2, **extra):
    return dict(id=str(identity), locationId=location, name=f'Flower {identity}', brand='Brand', masterCategoryName='Flower', carrotSubcategory='Flower',
                option1Name='3.5g', option1Price=price, qty=5, unitWeight=3.5, thcPercentage=21.5, strain='SATIVA', embedding=[0.1], **extra)


def results(total, documents):
    return dict(results=[dict(found=total, out_of=total, hits=[dict(document=d) for d in documents])])


def request(page, per_page=carrot.PAGE, filter_by=None):
    search = dict(q='*', per_page=per_page, page=page, query_by='name')
    if filter_by:
        search['filter_by'] = filter_by
    return json.dumps(dict(searches=[search]))


def write_render(folder, calls, locations=RECORDS):
    root = Path(folder)
    for part in ('browser', 'manifests', 'bodies'):
        (root / part).mkdir(parents=True, exist_ok=True)
    entries = []

    def add(index, method, url, value, body=None):
        evidence = f'call{index}'
        (root / 'bodies' / f'{evidence}.gz').write_bytes(gzip.compress(json.dumps(value).encode()))
        (root / 'manifests' / f'{evidence}.json').write_text(json.dumps(dict(body_path=f'bodies/{evidence}.gz')), encoding='utf-8')
        entries.append(dict(evidence_id=evidence, url=url, method=method, status=200, request_body=body))

    add(0, 'GET', LOCATIONS, dict(locations=locations))
    for index, (page, value, *extra) in enumerate(calls, start=1):
        add(index, 'POST', SEARCH, value, request(page, *extra))
    (root / 'browser' / 'render1.json').write_text(json.dumps(dict(network_json=entries)), encoding='utf-8')


class Storefront:
    def __init__(self, folder, calls, **kwargs):
        self.evidence_dir, self.renders = Path(folder), []
        self.browser_options = dict(target_store=TARGET)
        write_render(folder, calls, **kwargs)

    def render(self, url, *, license_type=None):
        self.renders.append(dict(self.browser_options))
        return FetchResult(url, 200, b'<html></html>', {}, 'render1', '2026-10-26T00:00:00+00:00')


def two_passes(pages):
    return [(page, value) for _ in range(2) for page, value in pages]


class CarrotTests(unittest.TestCase):
    def test_a_storefront_page_that_selects_one_location_is_a_carrot_endpoint(self):
        page = '<div class="carrot-store-root"></div><script src="https://api.nevada.getcarrot.io/api/v1/x"></script>'
        response = SimpleNamespace(url=URL, body=page.encode(), evidence_id='e', fetched_at='t')
        endpoint = carrot.observe(URL, response)
        self.assertEqual(('carrot', '2', 'recreational'), (endpoint['provider'], endpoint['provider_store_id'], endpoint['license_type']))
        self.assertIsNone(carrot.observe('https://shop.example.test/store', SimpleNamespace(url='https://shop.example.test/store', body=page.encode(), evidence_id='e', fetched_at='t')))
        self.assertIsNone(carrot.observe(URL, SimpleNamespace(url=URL, body=b'<html></html>', evidence_id='e', fetched_at='t')))

    def test_two_agreeing_traversals_that_reconcile_to_the_exact_total_make_the_menu_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            docs = [document(n) for n in range(carrot.PAGE + 3)]
            pages = [(1, results(len(docs), docs[:carrot.PAGE])), (2, results(len(docs), docs[carrot.PAGE:]))]
            storefront = Storefront(folder, two_passes(pages))
            outcome = carrot.fetch(ENDPOINT, storefront)
            self.assertEqual([], outcome['errors'])
            self.assertTrue(outcome['complete'])
            self.assertEqual((len(docs), len(docs)), (outcome['expected_count'], outcome['source_product_count']))
            self.assertEqual(dict(carrot_search=True, carrot_loc='2', await_menu=False, scroll_menu=False), {k: v for k, v in storefront.renders[0].items() if k != 'target_store'})
            first = outcome['items'][0]
            self.assertEqual(('3.5', '30', True), (str(first['weight_grams']), str(first['regular_price']), first['conditional']))

    def test_a_missing_page_or_a_total_that_does_not_reconcile_stays_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            docs = [document(n) for n in range(carrot.PAGE + 3)]
            calls = two_passes([(1, results(len(docs), docs[:carrot.PAGE]))])
            outcome = carrot.fetch(ENDPOINT, Storefront(folder, calls))
            self.assertFalse(outcome['complete'])
            self.assertIn('pages are not', outcome['errors'][0]['message'])
        with tempfile.TemporaryDirectory() as folder:
            calls = two_passes([(1, results(5, [document(1), document(2)]))])
            outcome = carrot.fetch(ENDPOINT, Storefront(folder, calls))
            self.assertFalse(outcome['complete'])
            self.assertIn('did not reconcile', outcome['errors'][0]['message'])

    def test_one_traversal_alone_or_a_category_scoped_search_does_not_count(self):
        with tempfile.TemporaryDirectory() as folder:
            outcome = carrot.fetch(ENDPOINT, Storefront(folder, [(1, results(1, [document(1)]))]))
            self.assertFalse(outcome['complete'])
            self.assertIn('two independent traversals', outcome['errors'][0]['message'])
        with tempfile.TemporaryDirectory() as folder:
            calls = two_passes([(1, results(1, [document(1)]))]) + [(1, results(1, [document(9)]), carrot.PAGE, '`masterCategoryName`:=[`Flower`]')]
            outcome = carrot.fetch(ENDPOINT, Storefront(folder, calls))
            self.assertTrue(outcome['complete'], outcome['errors'])
            self.assertEqual(['1'], sorted({item['source_id'] for item in outcome['items']}))

    def test_stock_or_price_churn_between_traversals_is_graded_converged_not_discarded(self):
        with tempfile.TemporaryDirectory() as folder:
            docs = [document(n) for n in range(40)]
            changed = [document(n, price=31.0 if n == 0 else 30.0) for n in range(40)]
            calls = [(1, results(40, docs)), (1, results(40, changed))]
            outcome = carrot.fetch(ENDPOINT, Storefront(folder, calls))
            self.assertFalse(outcome['errors'] and outcome['errors'][0]['message'].startswith('Carrot catalog did not'))
            self.assertFalse(outcome['complete'])

    def test_a_product_from_another_location_or_a_wrong_street_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = two_passes([(1, results(1, [document(1, location=1)]))])
            self.assertIn('another location', carrot.fetch(ENDPOINT, Storefront(folder, calls))['errors'][0]['message'])
        with tempfile.TemporaryDirectory() as folder:
            storefront = Storefront(folder, two_passes([(1, results(1, [document(1)]))]))
            storefront.browser_options = dict(target_store=dict(address='500 Main St', city='Cary'))
            outcome = carrot.fetch(ENDPOINT, storefront)
            self.assertFalse(outcome['complete'])
            self.assertIn('different street address', outcome['errors'][0]['message'])

    def test_each_priced_option_is_its_own_offer(self):
        endpoint = dict(url=URL)
        doc = document(7, option2Name='7g', option2Price=55.0)
        items = carrot.normalize(doc, endpoint)
        self.assertEqual([('7:1', '3.5', '30'), ('7:2', '7', '55')], [(i['variant_id'], str(i['weight_grams']), str(i['regular_price'])) for i in items])
        self.assertNotIn('embedding', items[0]['raw']['product'])


if __name__ == '__main__':
    unittest.main()
