import json
from urllib.parse import parse_qs, urlsplit
import unittest

from backend.adapters import _detect_endpoint, fetch_menu
from backend.network import FetchResult
from backend.providers import cresco
from backend.providers.cresco import CATEGORIES
from backend.site_discovery import provider_address_matches

MENU = 'https://www.sunnyside.shop/menu/champaign-il/store/champaign-il'
KEY = 'K' * 40
APP = '9ha3c289-1260-4he2-nm62-4598bca34naa'
STORE = dict(id=86, store_slug='champaign-il', name='Sunnyside', address='1704 S Neil St', city='Champaign', state='IL', zip='61820',
             lat=40.0988, lng=-88.2636, hidden=False, deleted=None)


def response(url, body):
    text = body if isinstance(body, str) else json.dumps(body)
    return FetchResult(url, 200, text.encode(), {}, 'evidence-' + str(abs(hash(url)) % 10**6), '2026-10-19T00:00:00Z')


class Storefront:
    """A Cresco storefront: the home page, its bundle, the ordering-app and store lookups, and paged inventory."""

    def __init__(self, flower=2, other=0, store=STORE):
        self.flower, self.other, self.store, self.calls = flower, other, store, []

    def get(self, url, headers=None):
        self.calls.append((url, dict(headers or {})))
        if url == 'https://www.sunnyside.shop/':
            return response(url, '<script src="/static/js/main.abc123.js"></script>')
        if url.endswith('/static/js/main.abc123.js'):
            return response(url, f'var c={{API_URL:"x",API_KEY:"{KEY}"}}')
        if 'store-inventory-breakdown' in url:
            return response(url, {'type': 'ordering_apps', 'rows': 1, 'data': [{'id': APP, 'stores': [self.store['id']]}]})
        if '/p/stores' in url:
            return response(url, {'type': 'stores', 'rows': 1, 'data': [self.store]})
        if 'fifo-inventory' in url:
            query = parse_qs(urlsplit(url).query)
            category, offset = query['category'][0], int(query.get('offset', ['0'])[0])
            total = self.flower if category == 'flower' else self.other
            base = 100 * CATEGORIES.index(category)
            rows = [dict(id=1000 + base + i, product_id=500 + base + i, name=f'{category} {i}', brand='Cresco',
                         price_rec=40 if i % 2 else 25.5, discounted_price=None, bt_weight=3.5, remaining_sellable_qty=4 if i % 3 else 0,
                         applied_special=None, bt_product_name=f'{category} {i}')
                    for i in range(offset, min(total, offset + 50))]
            return response(url, {'type': 'inventory', 'rows': len(rows), 'total_rows': total, 'data': rows})
        raise AssertionError('unexpected ' + url)


class CrescoTests(unittest.TestCase):
    def test_storefront_menu_page_is_a_cresco_endpoint_without_claiming_a_store_id(self):
        endpoint = _detect_endpoint(MENU, response(MENU, '<html></html>'))
        self.assertEqual((endpoint['provider'], endpoint['provider_store_id'], endpoint['license_type']), ('cresco', None, 'recreational'))

    def test_other_hosts_are_not_cresco(self):
        other = 'https://example.com/menu/champaign-il/store/champaign-il'
        self.assertNotEqual(_detect_endpoint(other, response(other, '<html></html>'))['provider'], 'cresco')

    def test_store_record_proves_the_branch_against_the_registry_address(self):
        details = cresco.store_details(Storefront(), MENU)
        endpoint = dict(resolution_evidence=details)
        registry = dict(address='1704 South Neil Street', latitude=40.0988, longitude=-88.2636)
        self.assertTrue(provider_address_matches(registry, endpoint))
        self.assertFalse(provider_address_matches(dict(address='9 Other Rd', latitude=41.9, longitude=-87.6), endpoint))

    def test_fetch_reads_every_category_and_stays_partial(self):
        site = Storefront(flower=2, other=1)
        result = fetch_menu(dict(url=MENU, provider='cresco', provider_store_id=None, license_type='recreational'), site)
        self.assertFalse(result['complete'])
        # Two flower items plus one item in each of the four other categories.
        self.assertEqual(len(result['items']), 6)
        self.assertTrue(all(i['effective_price'] is not None for i in result['items']))
        self.assertEqual({i['category'] for i in result['items']}, {'flower', 'vapes', 'other', 'concentrate'})
        self.assertTrue(all(i['source_url'] == MENU for i in result['items']))
        self.assertTrue(result['errors'])

    def test_requests_carry_the_key_store_app_and_storefront_origin(self):
        site = Storefront()
        fetch_menu(dict(url=MENU, provider='cresco', provider_store_id=None, license_type='recreational'), site)
        inventory = [h for url, h in site.calls if 'fifo-inventory' in url]
        self.assertTrue(inventory)
        self.assertEqual(inventory[0]['store_id'], '86')
        self.assertEqual(inventory[0]['ordering_app_id'], APP)
        self.assertEqual(inventory[0]['origin'], 'https://www.sunnyside.shop')

    def test_store_mismatch_with_the_endpoint_fails(self):
        result = fetch_menu(dict(url=MENU, provider='cresco', provider_store_id='999', license_type='recreational'), Storefront())
        self.assertEqual(result['items'], [])
        self.assertIn('identity changed', result['errors'][0]['message'])

    def test_ambiguous_store_lookup_fails_closed(self):
        site = Storefront(store=dict(STORE, store_slug='other-il'))
        result = fetch_menu(dict(url=MENU, provider='cresco', provider_store_id=None, license_type='recreational'), site)
        self.assertEqual(result['items'], [])
        self.assertTrue(result['errors'])


if __name__ == '__main__':
    unittest.main()
