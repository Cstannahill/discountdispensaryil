import gzip
import json as jsonlib
from pathlib import Path
import tempfile
import unittest

from backend.network import FetchResult
from backend.providers import gapcommerce, treez

OAK = 'e4b5da36-cbb4-4c73-9e8d-22dff12b5397'
BLUE = 'ceb1d719-7895-4a27-acba-aae3c6766434'
ORG = 'd3082ead-fc96-4c73-9d87-30333659cfc7'
URL = 'https://menu.example.test/shop'
SEARCH = gapcommerce.SEARCH
RECORDS = [dict(name='Be. - Oak Forest', short_name='be-oak-forest', object_id=OAK, address1='5940 W 159th St', city='Oak Forest', state='IL',
                zip='60452', mso_org_id=ORG, mso_store_entity_id=OAK, customer_type_allow='ADULT'),
           dict(name='Be. - Blue Island', short_name='be-blue-island', object_id=BLUE, address1='12720 S Western Ave', city='Blue Island', state='IL',
                zip='60406', mso_org_id=ORG, mso_store_entity_id=BLUE, customer_type_allow='ADULT')]
ENDPOINT = dict(url=URL, provider='gapcommerce', provider_store_id=OAK, license_type='recreational')


def page_html(records=RECORDS):
    # The store list is serialized into a Next.js RSC string, so its quotes arrive escaped.
    escaped = jsonlib.dumps({'treezStores': records}, separators=(',', ':')).replace('"', '\\"')
    return f'<html><script>self.__next_f.push([1,"{escaped}"])</script></html>'


def variant(identity, parent, price=25):
    return dict(id=identity, catalogParentId=parent, brand='Brand', category='FLOWER', name='Flower ' + identity, slug='flower-' + identity,
                isActive=True, isAboveThreshold=True,
                productData=dict(size='3.5 g', pricing=dict(priceSell=price, discountedPrice=price, appliedDiscountIds=[]),
                                 inventory=[dict(customerType='ALL', availableUnits=10)]))


def search(total, hits, store=OAK):
    return dict(took=5, timed_out=False, _shards=dict(total=1, successful=1, failed=0, failures=None),
                hits=dict(total=dict(value=total, relation='eq'), max_score=0.1,
                          hits=[dict(_index='product_' + store, _id='doc-' + source['id'], _source=source) for source in hits]))


def request_body(direction, offset, query=None):
    return dict(**{'from': offset, 'size': 100, 'query': query or gapcommerce.QUERY, 'sort': [{'_id': direction}]})


def write_render(folder, responses):
    """Evidence of one browser render: the page's search responses with their request bodies, as the worker records them."""
    root = Path(folder)
    for part in ('browser', 'manifests', 'bodies'):
        (root / part).mkdir(parents=True, exist_ok=True)
    entries = []
    for index, (direction, offset, value, *query) in enumerate(responses):
        evidence = f'search{index}'
        (root / 'bodies' / f'{evidence}.gz').write_bytes(gzip.compress(jsonlib.dumps(value).encode()))
        (root / 'manifests' / f'{evidence}.json').write_text(jsonlib.dumps(dict(body_path=f'bodies/{evidence}.gz')), encoding='utf-8')
        entries.append(dict(evidence_id=evidence, url=SEARCH, method='POST', status=200, content_type='application/json',
                            request_body=jsonlib.dumps(request_body(direction, offset, *query))))
    (root / 'browser' / 'render1.json').write_text(jsonlib.dumps(dict(network_json=entries)), encoding='utf-8')


def result(url, body, status=200, evidence='page'):
    return FetchResult(url, status, body.encode('utf-8'), {}, evidence, '2026-10-19T00:00:00+00:00')


class Storefront:
    """Fake fetcher: the storefront page over plain HTTP, and a browser render whose evidence holds the search responses."""
    def __init__(self, folder, responses, html=None):
        self.evidence_dir = Path(folder)
        self.html, self.browser_options, self.renders = html or page_html(), {}, []
        write_render(folder, responses)

    def get(self, url, headers=None):
        return result(url, self.html if url == URL else '', 200 if url == URL else 404)

    def render(self, url, *, license_type=None):
        self.renders.append(dict(self.browser_options))
        return result(url, '<html></html>', evidence='render1')


def both_orders(pages):
    """Each id order's pages: (direction, offset, hit-count response)."""
    return [(direction, offset, value) for direction in ('asc', 'desc') for offset, value in pages.items()]


def three_variants():
    return {0: search(3, [variant('a1', 'pa'), variant('a2', 'pa')]), 2: search(3, [variant('b1', 'pb')])}


class BranchRecordTests(unittest.TestCase):
    def test_the_branch_list_is_read_from_the_escaped_storefront_payload(self):
        self.assertEqual([record['object_id'] for record in gapcommerce.store_records(page_html())], [OAK, BLUE])
        self.assertEqual(gapcommerce.store_records('<html>no listing</html>'), [])

    def test_observe_names_the_registry_branch_by_its_street_and_not_its_sibling(self):
        response = result(URL, page_html())
        endpoint = gapcommerce.observe(URL, response, dict(address='5940 159th St', city='Oak Forest'))
        self.assertEqual((endpoint['provider'], endpoint['provider_store_id'], endpoint['license_type']), ('gapcommerce', OAK, 'recreational'))
        self.assertEqual(gapcommerce.observe(URL, response, dict(address='12720 S Western Ave', city='Blue Island'))['provider_store_id'], BLUE)
        self.assertIsNone(gapcommerce.observe(URL, response, dict(address='1 Main St', city='Oak Forest')))
        self.assertIsNone(gapcommerce.observe(URL, response))


class SearchTraversalTests(unittest.TestCase):
    def test_both_id_orders_reconcile_to_the_hit_total_and_the_menu_is_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            storefront = Storefront(folder, both_orders(three_variants()))
            outcome = gapcommerce.fetch(ENDPOINT, storefront)
            self.assertEqual(outcome['errors'], [])
            self.assertTrue(outcome['complete'])
            self.assertEqual((outcome['expected_count'], outcome['source_product_count']), (3, 2))
            self.assertEqual(sorted(item['variant_id'] for item in outcome['items']), ['a1', 'a2', 'b1'])
            self.assertEqual(storefront.renders, [dict(gap_search=True, gap_entity=OAK, await_menu=False, scroll_menu=False)])

    def test_a_category_scoped_search_is_not_mistaken_for_the_catalog(self):
        category = {'bool': {'must': [{'bool': {'should': [{'match': {'category.keyword': 'FLOWER'}}]}}]}}
        with tempfile.TemporaryDirectory() as folder:
            responses = both_orders(three_variants()) + [('asc', 0, search(1, [variant('x1', 'px')]), category)]
            outcome = gapcommerce.fetch(ENDPOINT, Storefront(folder, responses))
            self.assertTrue(outcome['complete'])
            self.assertEqual(sorted(item['variant_id'] for item in outcome['items']), ['a1', 'a2', 'b1'])

    def test_a_missing_page_in_either_order_stays_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            pages = three_variants()
            responses = [(d, o, v) for d, o, v in both_orders(pages) if not (d == 'desc' and o == 2)]
            outcome = gapcommerce.fetch(ENDPOINT, Storefront(folder, responses))
            self.assertFalse(outcome['complete'])
            self.assertIn('did not reconcile', outcome['errors'][0]['message'])

    def test_a_storefront_that_never_replayed_one_id_order_is_not_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            responses = [(d, o, v) for d, o, v in both_orders(three_variants()) if d == 'asc']
            outcome = gapcommerce.fetch(ENDPOINT, Storefront(folder, responses))
            self.assertFalse(outcome['complete'])
            self.assertIn('not replayed in desc', outcome['errors'][0]['message'])

    def test_a_hit_from_another_store_index_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            wrong = {0: search(1, [variant('a1', 'pa')], store=BLUE)}
            outcome = gapcommerce.fetch(ENDPOINT, Storefront(folder, both_orders(wrong)))
            self.assertFalse(outcome['complete'])
            self.assertIn('another store index', outcome['errors'][0]['message'])

    def test_a_registry_branch_with_a_different_street_is_refused_before_the_browser_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            storefront = Storefront(folder, both_orders(three_variants()))
            storefront.browser_options = dict(target_store=dict(address='12720 S Western Ave'))
            outcome = gapcommerce.fetch(ENDPOINT, storefront)
            self.assertFalse(outcome['complete'])
            self.assertIn('different street address', outcome['errors'][0]['message'])
            self.assertEqual(storefront.renders, [])

    def test_a_storefront_that_does_not_list_the_endpoint_store_is_not_read(self):
        with tempfile.TemporaryDirectory() as folder:
            storefront = Storefront(folder, both_orders(three_variants()), html=page_html(RECORDS[1:]))
            self.assertIsNone(gapcommerce.probe(ENDPOINT, storefront)[2])
            self.assertFalse(gapcommerce.fetch(ENDPOINT, storefront)['complete'])
            self.assertEqual(storefront.renders, [])


class TreezRoutingTests(unittest.TestCase):
    def test_a_treez_endpoint_on_a_listing_storefront_reads_the_search_api(self):
        with tempfile.TemporaryDirectory() as folder:
            outcome = treez.fetch(dict(ENDPOINT, provider='treez'), Storefront(folder, both_orders(three_variants())))
            self.assertEqual(outcome['provider'], 'treez')
            self.assertTrue(outcome['complete'])


if __name__ == '__main__':
    unittest.main()
