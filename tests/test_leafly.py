"""Leafly-hosted dispensary menus: read as a native paged menu, recreational variants only, tax-inclusive prices never compared."""
import copy
import json
import re
import unittest
from pathlib import Path

from backend import adapters
from backend.network import FetchResult
from backend.providers import leafly

FIXTURES = Path(__file__).parent / 'fixtures' / 'provider_leafly'
ITEMS = json.loads((FIXTURES / 'items.json').read_text(encoding='utf-8'))
MILAN = json.loads((FIXTURES / 'milan-dispensary.json').read_text(encoding='utf-8'))
SLUG = 'nature-s-treatment-of-illinois'
ENDPOINT = dict(url=f'https://www.leafly.com/dispensary-info/{SLUG}/menu', provider='leafly', provider_store_id='174378', license_type='recreational')
STORE = dict(id='s1', name='Natures Treatment of Illinois - Milan', address='973 Tech Dr', city='Milan', state='IL', latitude=41.4423, longitude=-90.5427)


def next_page(props):
    return ('<html><body><script id="__NEXT_DATA__" type="application/json">' + json.dumps(dict(props=dict(pageProps=props))) + '</script></body></html>').encode()


def product(number, source=ITEMS['flower']):
    item = copy.deepcopy(source)
    item['menuItemId'] = 1000 + number
    item['name'] = f'Product {number}'
    item['id'], item['variants'][0]['id'], item['variants'][1]['id'] = 5000 + 2 * number, 5000 + 2 * number, 5001 + 2 * number
    item['dispensaryId'] = 174378
    return item


class LeafletFetcher:
    """Serves the listing page and the paged /menu pages; `mode` perturbs the read the way live inventory does."""
    def __init__(self, count=60, mode=None, dispensary=None, page_size=18):
        self.count, self.mode, self.page_size, self.calls = count, mode, page_size, 0
        self.dispensary = {**MILAN, 'menuTaxPricing': 'tax_exclusive_pricing', **(dispensary or {})}
        self.products = [product(n) for n in range(count)]

    def get(self, url, headers=None):
        self.calls += 1
        number = f'leafly-{self.calls}'
        if url.endswith('/dispensary-info/' + SLUG):
            return FetchResult(url, 200, next_page(dict(dispensary=self.dispensary)), {}, number, '2026-10-22T00:00:00Z')
        page = int(re.search(r'page=(\d+)', url)[1])
        rows = self.products[(page - 1) * self.page_size: page * self.page_size]
        rows = copy.deepcopy(rows)
        if self.mode == 'repeat' and page == 2:
            rows[0] = copy.deepcopy(self.products[0])
        if self.mode == 'short' and page == 2:
            rows.pop()
        if self.mode == 'other-store' and page == 1:
            rows[0]['dispensaryId'] = 999
        return FetchResult(url, 200, next_page(dict(menuData=dict(menuItems=rows, totalItems=self.count))), {}, number, '2026-10-22T00:00:00Z')


class NormalizeTests(unittest.TestCase):
    def test_only_recreational_variants_become_offers(self):
        items = leafly.normalize(ITEMS['flower'], ENDPOINT, True)
        self.assertEqual(1, len(items))
        item = items[0]
        recreational = next(v for v in ITEMS['flower']['variants'] if not v['medical'])
        self.assertEqual(str(recreational['id']), item['variant_id'])
        self.assertEqual(str(ITEMS['flower']['menuItemId']), item['source_id'])
        self.assertEqual('70', item['regular_price'])
        self.assertEqual('3.5', item['weight_grams'])
        self.assertEqual('flower', item['category'])
        self.assertIs(False, item['conditional'])

    def test_a_sale_does_not_lower_the_shelf_price(self):
        item = leafly.normalize(ITEMS['deal'], ENDPOINT, True)[0]
        self.assertEqual('65', item['effective_price'])
        self.assertIs(False, item['conditional'])

    def test_a_per_piece_product_has_no_invented_mass(self):
        item = leafly.normalize(ITEMS['each'], ENDPOINT, True)[0]
        self.assertIsNone(item['weight_grams'])

    def test_tax_inclusive_prices_are_not_comparable(self):
        self.assertIs(True, leafly.normalize(ITEMS['flower'], ENDPOINT, False)[0]['conditional'])


class FetchTests(unittest.TestCase):
    def fetch(self, fetcher, endpoint=ENDPOINT, store=STORE):
        fetcher.browser_options = dict(target_store=store)
        return leafly.fetch(endpoint, fetcher)

    def test_a_reconciled_menu_read_twice_is_complete(self):
        result = self.fetch(LeafletFetcher(60))
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(60, len(result['items']))
        self.assertEqual(60, result['expected_count'])
        self.assertEqual(60, result['source_product_count'])

    def test_a_full_last_page_needs_no_extra_request(self):
        fetcher = LeafletFetcher(36)
        result = self.fetch(fetcher)
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(1 + 2 * 2, fetcher.calls)

    def test_a_repeated_product_means_the_listing_moved_so_it_is_converged_never_complete(self):
        result = self.fetch(LeafletFetcher(600, 'repeat'))
        self.assertFalse(result['complete'])
        self.assertFalse(result['errors'], result['errors'])
        self.assertEqual('churn_tolerant', result['convergence']['kind'])
        self.assertTrue(result['convergence']['page_drift'])

    def test_a_short_middle_page_fails_and_keeps_what_was_read(self):
        result = self.fetch(LeafletFetcher(60, 'short'))
        self.assertFalse(result['complete'])
        self.assertTrue(result['errors'])
        self.assertTrue(result['items'])

    def test_products_of_another_dispensary_fail(self):
        result = self.fetch(LeafletFetcher(60, 'other-store'))
        self.assertFalse(result['complete'])
        self.assertTrue(result['errors'])

    def test_a_listing_at_a_different_street_address_fails(self):
        result = self.fetch(LeafletFetcher(60), store=dict(STORE, address='735 W. Main St.'))
        self.assertFalse(result['complete'])
        self.assertIn('different street address', result['errors'][0]['message'])

    def test_a_tax_inclusive_menu_is_read_but_every_price_is_conditional(self):
        result = self.fetch(LeafletFetcher(60, dispensary=dict(menuTaxPricing='tax_inclusive_pricing')))
        self.assertTrue(result['complete'], result['errors'])
        self.assertTrue(all(item['conditional'] is True for item in result['items']))

    def test_a_listing_for_another_dispensary_id_fails(self):
        result = self.fetch(LeafletFetcher(60, dispensary=dict(id=1)))
        self.assertFalse(result['complete'])
        self.assertTrue(result['errors'])

    def test_the_provider_is_dispatched_and_native(self):
        self.assertTrue(adapters.provider_capabilities('leafly')['native_full_menu'])
        result = adapters.fetch_menu(ENDPOINT, LeafletFetcher(30))
        self.assertEqual('leafly', result['provider'])


class ObserveTests(unittest.TestCase):
    def test_slug_and_links(self):
        self.assertEqual(SLUG, leafly.slug_from(f'https://www.leafly.com/dispensary-info/{SLUG}/menu?page=3'))
        self.assertIsNone(leafly.slug_from('https://www.leafly.com/strains/blue-dream'))
        self.assertIsNone(leafly.slug_from('https://example.com/dispensary-info/x'))
        text = f'<a href="https://www.leafly.com/dispensary-info/{SLUG}">a</a><a href="https://www.leafly.com/dispensary-info/{SLUG}/deals">b</a><a href="https://www.leafly.com/dispensary-info/{SLUG}---galesburg/menu">c</a>'
        self.assertEqual([f'https://www.leafly.com/dispensary-info/{SLUG}', f'https://www.leafly.com/dispensary-info/{SLUG}---galesburg'], leafly.listing_links(text))

    def test_the_listing_page_gives_a_menu_endpoint_with_its_street_address_and_pin(self):
        url = f'https://www.leafly.com/dispensary-info/{SLUG}'
        found = leafly.observe(url, FetchResult(url, 200, next_page(dict(dispensary=MILAN)), {}, 'ev', '2026-10-22T00:00:00Z'))
        self.assertEqual(('leafly', '174378', 'recreational'), (found['provider'], found['provider_store_id'], found['license_type']))
        self.assertEqual(f'https://www.leafly.com/dispensary-info/{SLUG}/menu', found['url'])
        details = found['resolution_evidence']
        self.assertEqual('973 Tech Drive', details['retailer_address'])
        self.assertEqual(dict(lat=41.4422671, lng=-90.5426505), details['platform_location'])

    def test_a_page_without_a_dispensary_is_not_an_endpoint(self):
        url = f'https://www.leafly.com/dispensary-info/{SLUG}'
        self.assertIsNone(leafly.observe(url, FetchResult(url, 200, next_page({}), {}, 'ev', '2026-10-22T00:00:00Z')))


if __name__ == '__main__':
    unittest.main()


class ResolveTests(unittest.TestCase):
    """The retailer's own site links to its Leafly listing; the listing's address proves the branch."""
    SITE = 'https://retailer.example/'

    def retailer(self, links, native=''):
        body = '<h1>Natures Treatment of Illinois</h1><p>973 Tech Dr, Milan, IL</p>' + native + ''.join(f'<a href="{link}">listing</a>' for link in links)
        return body

    def resolve(self, store, links, dispensaries, native=''):
        from unittest.mock import patch
        fetched = []
        retailer = self.retailer(links, native)

        class Fetcher:
            def get(self_inner, url, headers=None):
                fetched.append(url)
                if url.startswith(ResolveTests.SITE):
                    return FetchResult(url, 200, retailer.encode(), {}, 'ev-site', '2026-10-22T00:00:00Z')
                slug = leafly.slug_from(url)
                if slug in dispensaries:
                    return FetchResult(url, 200, next_page(dict(dispensary=dispensaries[slug])), {}, 'ev-' + slug, '2026-10-22T00:00:00Z')
                raise RuntimeError('unexpected ' + url)
        with patch('backend.site_discovery.search_websites', return_value=[]), patch('backend.locators.discover_menu_candidates', return_value=[]):
            return adapters.resolve_menu(dict(store, website=self.SITE), Fetcher()), fetched

    def test_the_linked_listing_whose_address_matches_becomes_the_menu(self):
        links = [f'https://www.leafly.com/dispensary-info/{SLUG}', f'https://www.leafly.com/dispensary-info/{SLUG}---galesburg']
        galesburg = dict(MILAN, id=317358, slug=SLUG + '---galesburg', address1='735 W Main Street', city='Galesburg', locations=[dict(lat=40.94815, lon=-90.382705)])
        found, _ = self.resolve(STORE, links, {SLUG: MILAN, SLUG + '---galesburg': galesburg})
        leaflies = [x for x in found if x['provider'] == 'leafly']
        self.assertEqual(['174378'], [x['provider_store_id'] for x in leaflies])
        self.assertEqual('matched', leaflies[0]['identity_confidence'])

    def test_a_listing_at_another_street_address_is_not_this_stores_menu(self):
        galesburg = dict(MILAN, id=317358, slug=SLUG + '---galesburg', address1='735 W Main Street', city='Galesburg', locations=[dict(lat=40.94815, lon=-90.382705)])
        found, _ = self.resolve(STORE, [f'https://www.leafly.com/dispensary-info/{SLUG}---galesburg'], {SLUG + '---galesburg': galesburg})
        self.assertFalse([x for x in found if x['provider'] == 'leafly' and not x.get('status')])

    def test_a_native_menu_found_on_the_site_means_leafly_is_not_read(self):
        native = '<script src="https://dutchie.com/api/v3/embedded-menu/natures-treatment.js"></script>'
        found, fetched = self.resolve(STORE, [f'https://www.leafly.com/dispensary-info/{SLUG}'], {SLUG: MILAN}, native)
        self.assertFalse([x for x in found if x['provider'] == 'leafly'])
        self.assertFalse([url for url in fetched if 'leafly.com' in url])


class WiringTests(unittest.TestCase):
    def test_a_leafly_endpoint_survives_the_directory_cleanup(self):
        import tempfile
        from backend.storage import Store
        from test_storage import observation
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp) / 'test.db', Path(tmp) / 'evidence')
            db.import_registry([observation()], 'source')
            region = db.create_region(40.9844, -89.0388, '61358', 50)
            shop = db.stores_in_region(region['id'])[0]
            saved = db.save_endpoint(shop['id'], dict(ENDPOINT, resolution_evidence=[]))
            db.retire_discovery_only_endpoints()
            self.assertEqual('leafly', db.endpoint(saved['id'] if isinstance(saved, dict) else saved)['provider'])
            self.assertNotEqual('superseded', db.endpoint(saved['id'] if isinstance(saved, dict) else saved)['status'])

    def test_the_sync_saves_a_resolved_leafly_endpoint_rather_than_demoting_it_to_a_lead(self):
        import tempfile
        from backend.service import SyncService
        from backend.storage import Store
        from test_service import FixtureFetcher
        from test_storage import observation
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp) / 'test.db', Path(tmp) / 'evidence')
            db.import_registry([observation()], 'source')
            region = db.create_region(40.9844, -89.0388, '61358', 50)
            resolved = dict(ENDPOINT, identity_confidence='matched', resolution_evidence=dict(retailer_address='100 Main St'))
            service = SyncService(db, FixtureFetcher(), resolver=lambda s, f: [resolved], menu_fetcher=lambda e, f: dict(items=[], complete=False, expected_count=None, pages=[], errors=[dict(code='x', message='x')], evidence=[], authoritative_zero=False, provider='leafly', adapter_version='1'), verifier=lambda s, f: None)
            try:
                service.run(db.enqueue(dict(region_id=region['id'], discover=False))['id'])
            finally:
                if not service.stop_requested.is_set():
                    service.close()
            self.assertEqual(['leafly'], [e['provider'] for e in db.endpoints()])
