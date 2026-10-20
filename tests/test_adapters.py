import copy
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

from backend import adapters

FIXTURES = Path(__file__).parent / 'fixtures' / 'provider_blaze'


class Response:
    def __init__(self, url, data, number=0, status=200):
        self.url, self.status_code = url, status
        self.body = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        self.evidence_id, self.fetched_at, self.headers = f'evidence-{number}', '2026-10-17T08:00:00Z', {}

    def json(self):
        return json.loads(self.body)


class BlazeFetcher:
    def __init__(self, count=1103, mode=None):
        self.fixture = json.loads((FIXTURES / 'blaze.json').read_text(encoding='utf-8'))
        self.count, self.mode, self.calls = count, mode, []

    def get(self, url, headers=None):
        self.calls.append((url, headers))
        if 'api/v1/products/' not in url:
            return Response(url, (FIXTURES / 'storefront.html').read_text(), len(self.calls))
        query = parse_qs(urlparse(url).query)
        offset, limit = int(query['offset'][0]), int(query['limit'][0])
        if self.mode == 'failure' and offset >= 100:
            return Response(url, '<html>Unavailable</html>', len(self.calls), 503)
        data = []
        for n in range(offset, min(offset + limit, self.count)):
            item = copy.deepcopy(self.fixture['data'][0])
            item['id'] = item['attributes']['id'] = n if self.mode != 'repeat' else n % 100
            if self.mode=='metadata':item['attributes']['sourceUpdateDate']=len(self.calls)
            data.append(item)
        if self.mode == 'drift' and len(self.calls) > (self.count + 99) // 100 + 1 and data:
            data[0]['attributes']['name'] += ' changed'
        return Response(url, {'data': data, 'included': self.fixture['included'], 'meta': {'offset': offset + (1 if self.mode == 'offset' else 0), 'limit': limit, 'total_count': self.count}}, len(self.calls))


ENDPOINT = {'url': 'https://snapcanna.com/menu/pontiac/', 'provider': 'blaze', 'provider_store_id': 'b4b51085-7010-41fa-9f81-4929feff5630', 'license_type': 'recreational'}
SWEED_FIXTURES = FIXTURES.parent / 'provider_sweed'
SWEED_ENDPOINT = {'url': 'https://shop.treehausil.com/morris/menu', 'provider': 'sweed', 'provider_store_id': '405', 'license_type': 'recreational'}


class SweedFetcher:
    def __init__(self, count=1103, mode=None):
        self.context = json.loads((SWEED_FIXTURES / 'tree-context.json').read_text())
        self.page = json.loads((SWEED_FIXTURES / 'treemenu.json').read_text())
        self.count, self.mode, self.calls = count, mode, 0

    def get(self, url, headers=None):
        self.calls += 1
        page = int(parse_qs(urlparse(url).query).get('page', ['1'])[0])
        context = copy.deepcopy(self.context)
        query = copy.deepcopy(self.page)
        query['queryKey'][1]['page'] = page
        data = query['state']['data']
        data['page'], data['total'] = page, self.count
        data['list'] = []
        for n in range((page-1)*24, min(page*24, self.count)):
            item = copy.deepcopy(self.page['state']['data']['list'][0])
            item['id'], item['variants'][0]['id'] = n, n
            if self.mode=='metadata':item['sourceUpdateDate']=self.calls
            data['list'].append(item)
        if self.mode == 'repeat' and page > 1:
            data['list'][0]['id'] = 0
            data['list'][0]['variants'][0]['id'] = 0
        if self.mode == 'missing' and page > 1:
            data['list'].pop()
        if self.mode == 'tenant':
            context['queries'][1]['state']['data']['storeInfo']['id'] = 999
        context['queries'].append(query)
        return Response(url, '<script>var state = {"__sw_qc": '+json.dumps(context)+'};</script>', self.calls)


class AdapterTests(unittest.TestCase):
    def test_raw_metadata_churn_does_not_invalidate_stable_blaze_or_sweed_inventory(self):
        for endpoint,fetcher in ((ENDPOINT,BlazeFetcher(50,'metadata')),(SWEED_ENDPOINT,SweedFetcher(50,'metadata'))):
            with self.subTest(provider=endpoint['provider']):
                result=adapters.fetch_menu(endpoint,fetcher)
                self.assertTrue(result['complete'],result['errors'])

    def test_wrong_provider_branch_is_not_accepted_because_city_appears_in_navigation(self):
        fetcher=SweedFetcher(1)
        original=fetcher.get
        def get(url,headers=None):
            result=original(url,headers)
            result.body+=b'<h1>Tree Haus</h1><nav>Diamond Morris</nav>'
            return result
        fetcher.get=get
        results=adapters.resolve_menu(dict(name='Tree Haus - Diamond',city='Diamond',state='IL',address='2910 E Division St',menu_url=SWEED_ENDPOINT['url']),fetcher)
        self.assertFalse(any(r['provider']=='sweed' and not r.get('status') for r in results))
    def test_noxx_resolved_provider_evidence_is_json_serializable(self):
        text=Path('tests/fixtures/sites/noxx-peoria.html').read_text(encoding='utf-8')
        class Fetcher:
            def get(self,url):return Response('https://noxx.com/location/noxx-peoria/',text)
        results=adapters.resolve_menu(dict(name='Noxx - East Peoria',address='300 S Main St',city='East Peoria',state='IL',menu_url='https://noxx.com/location/noxx-peoria/'),Fetcher())
        self.assertTrue(any(r['provider']=='dutchie' for r in results))
        json.dumps(results)
    def test_a_spent_discovery_budget_starts_no_crawl_and_says_so(self):
        class Fetcher:
            def get(self,url):raise AssertionError('a spent discovery budget must not fetch')
        results=adapters.resolve_menu(dict(name='Budget Cannabis',city='Rutland',state='IL',menu_url='https://budget.example/menu/',discovery_seconds=0),Fetcher())
        self.assertEqual(results[0]['status'],'unresolved')
        self.assertIn('budget',results[0]['reason'])
    def test_omitted_platform_license_defaults_to_recreational(self):
        response=Response('https://example.com/menu','<h1>Public menu</h1>')
        endpoint=adapters._observed_endpoint(response.url,response)
        self.assertEqual(endpoint['license_type'],'recreational')
        self.assertEqual(endpoint['license_basis'],'default')

    def test_filtered_sweed_page_resolves_observed_full_menu_link(self):
        fetcher = SweedFetcher(1)
        query = copy.deepcopy(fetcher.page)
        query['queryKey'][1]['filters'] = [{'category': 'flower'}]
        fetcher.context['queries'].append(query)
        text = '<script>{"__sw_qc": '+json.dumps(fetcher.context)+'}</script><a href="/morris/menu">All products</a>'
        response = Response('https://shop.treehausil.com/morris/menu/flower-123', text)
        endpoint = adapters._observed_endpoint(response.url, response)
        self.assertEqual(endpoint['url'], SWEED_ENDPOINT['url'])

    def test_dual_context_sweed_uses_observed_full_menu_link_not_landing_page(self):
        text = (FIXTURES.parent/'provider_probe/ivy.txt').read_text(encoding='utf-8')
        response = Response('https://ivyhalldispensary.com/locations/peoria/menu/recreational', text)
        endpoint = adapters._observed_endpoint(response.url, response)
        self.assertEqual(endpoint['url'], 'https://ivyhalldispensary.com/locations/peoria/menu/recreational/menu')
        self.assertEqual(endpoint['license_type'], 'recreational')

    def test_sweed_observed_pagination_over_thousand_expands_variants(self):
        result = adapters.fetch_menu(SWEED_ENDPOINT, SweedFetcher())
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(1103, len(result['items']))
        self.assertEqual(1103, result['source_product_count'])
        self.assertEqual(92, len(result['pages']))

    def test_sweed_missing_repeated_and_context_changes_fail(self):
        for mode in ['repeat', 'missing', 'tenant']:
            with self.subTest(mode=mode):
                result = adapters.fetch_menu(SWEED_ENDPOINT, SweedFetcher(50, mode))
                self.assertFalse(result['complete'])
                self.assertTrue(result['errors'])

    def test_sweed_partial_traversal_preserves_observed_products_and_explains_failed_page(self):
        result=adapters.fetch_menu(SWEED_ENDPOINT,SweedFetcher(50,'missing'))
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']),24)
        self.assertIn('page 2',result['errors'][0]['message'])
        self.assertIn('received',result['errors'][0]['message'])

    def test_sweed_multi_variant_keeps_package_identity_and_conditional_prices(self):
        from backend.providers.sweed import normalize_product
        product = json.loads((SWEED_FIXTURES / 'treemenu.json').read_text())['state']['data']['list'][0]
        second = copy.deepcopy(product['variants'][0])
        second.update(id=999, name='7g', unitSize={'value':7, 'unitAbbr':'G'})
        product['variants'].append(second)
        result = normalize_product(product, SWEED_ENDPOINT)
        self.assertEqual(2, len(result))
        self.assertEqual('7', result[1]['weight_grams'])
        self.assertFalse(result[0]['conditional'])

    def test_sweed_plain_promo_price_is_not_conditional_beside_multi_buy_tags(self):
        from backend.providers.sweed import normalize_product
        product = json.loads((SWEED_FIXTURES / 'treemenu.json').read_text())['state']['data']['list'][0]
        item = normalize_product(product, SWEED_ENDPOINT)[0]
        self.assertFalse(item['conditional'])
        self.assertEqual('7', item['effective_price'])

        def variant_with(price, promo, promos):
            changed = copy.deepcopy(product)
            changed['variants'][0].update(price=price, promoPrice=promo, promos=promos)
            return normalize_product(changed, SWEED_ENDPOINT)[0]
        plain = [p for p in product['variants'][0]['promos'] if '30%' in (p.get('shortName') or '')][0]
        self.assertTrue(variant_with(10, 6.65, product['variants'][0]['promos'])['conditional'])
        self.assertTrue(variant_with(10, 5, [{'name': 'BOGO', 'isConditional': False, 'isBogo': True}])['conditional'])
        segment = dict(plain, matchedUserSegmentIds=[12])
        self.assertTrue(variant_with(10, 7, [segment, {'name': 'Buy & Save More', 'isConditional': True}])['conditional'])
        only = variant_with(10, 6, [{'name': 'Only $6.00', 'isConditional': False}, {'name': 'Stackable 5% Off', 'isConditional': True}])
        self.assertFalse(only['conditional'])
        self.assertEqual('6', only['effective_price'])

    def test_sweed_same_parent_in_distinct_listing_variants_is_valid(self):
        fetcher = SweedFetcher(50)
        original = fetcher.get
        def get(url, headers=None):
            response = original(url, headers)
            text = response.body.decode()
            text = text.replace('"id": 1, "name": "Bluenana', '"id": 0, "name": "Bluenana')
            response.body = text.encode()
            return response
        fetcher.get = get
        result = adapters.fetch_menu(SWEED_ENDPOINT, fetcher)
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(50, len(result['items']))
        self.assertEqual(49, result['source_product_count'])

    def test_observed_blaze_full_menu_over_one_thousand_and_stable_second_pass(self):
        fetcher = BlazeFetcher()
        result = adapters.fetch_menu(ENDPOINT, fetcher)
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(1103, len(result['items']))
        self.assertEqual(1103, result['expected_count'])
        self.assertGreaterEqual(len(result['pages']), 12)
        self.assertTrue(all(headers['X-Store'] == ENDPOINT['provider_store_id'] for url, headers in fetcher.calls if 'api/v1/products/' in url))

    def test_missing_page_repeated_ids_wrong_offset_and_changed_boundaries_fail(self):
        for mode in ['failure', 'repeat', 'offset', 'drift']:
            with self.subTest(mode=mode):
                result = adapters.fetch_menu(ENDPOINT, BlazeFetcher(205, mode))
                self.assertFalse(result['complete'])
                self.assertTrue(result['errors'])

    def test_fixture_categories_prices_mass_and_dose(self):
        fixture = json.loads((FIXTURES / 'blaze.json').read_text(encoding='utf-8'))
        objects = fixture['data']
        records = [adapters.normalize_blaze(x, fixture['included'], ENDPOINT) for x in objects]
        self.assertEqual('accessories', records[0]['source_category'].lower())
        self.assertIsNone(records[0]['weight_grams'])
        flower = next(x for x in records if x['category'] == 'flower')
        self.assertGreater(float(flower['weight_grams']), 0)
        edible = next(x for x in objects if x['attributes'].get('size', {}).get('units') == 'milligram')
        self.assertIsNone(adapters.normalize_blaze(edible, fixture['included'], ENDPOINT)['weight_grams'])

    def test_retail_ounce_fractions_use_28_grams(self):
        # Menus sell 1/8 oz as 3.5 g; the avoirdupois factor would price an eighth as 3.544 g.
        fixture = json.loads((FIXTURES / 'blaze.json').read_text(encoding='utf-8'))
        flower = copy.deepcopy(next(x for x in fixture['data'] if x['attributes'].get('size', {}).get('units') in ('grams', 'gram', 'g')))
        for amount, grams in (('0.125', '3.5'), ('0.25', '7'), ('0.5', '14'), ('1', '28')):
            flower['attributes']['size'] = dict(amount=amount, units='ounces', display_text='oz')
            record = adapters.normalize_blaze(flower, fixture['included'], ENDPOINT)
            self.assertEqual(float(grams), float(record['weight_grams']))

    def test_unknown_provider_is_explicitly_incomplete(self):
        result = adapters.fetch_menu({'url':'https://example.com', 'provider':'unsupported'}, BlazeFetcher())
        self.assertFalse(result['complete'])
        self.assertFalse(result['authoritative_zero'])
        self.assertTrue(result['errors'])

    def test_resolution_uses_live_structured_tenant_not_name_as_id(self):
        result = adapters.resolve_menu({'name':'Snap Canna','city':'Pontiac','menu_url':ENDPOINT['url']}, BlazeFetcher())
        self.assertEqual('blaze', result[0]['provider'])
        self.assertEqual(ENDPOINT['provider_store_id'], result[0]['provider_store_id'])
        self.assertTrue(result[0]['resolution_evidence'])

    def test_tenant_change_rejected(self):
        result = adapters.fetch_menu(dict(ENDPOINT, provider_store_id='wrong'), BlazeFetcher(1))
        self.assertFalse(result['complete'])
        self.assertEqual([], result['items'])

    def test_page_limit_fails_safely(self):
        result = adapters.fetch_menu(dict(ENDPOINT, max_pages=1), BlazeFetcher(205))
        self.assertFalse(result['complete'])


if __name__ == '__main__':
    unittest.main()
