"""Sibling branches listed on a chain's pages must prove themselves; they never inherit the requested store's identity."""
import json
import unittest

from backend.adapters import resolve_menu
from backend.network import FetchResult
from backend.site_discovery import branch_slug_conflict


def page(url, text):
    return FetchResult(url, 200, text.encode(), {}, 'e-' + url[-20:], '2026-10-18T09:00:00Z')


DIXON = dict(name='Terrabis - Dixon', address='123 First St', city='Dixon', state='IL')


class SlugConflictTests(unittest.TestCase):
    def test_other_localities_and_states_conflict(self):
        for url in ('https://terrabis.co/menu/ofallon-mo/', 'https://terrabis.co/menu/plainfield-il-rec/',
                    'https://zenleafdispensaries.com/locations/st-charles/menu/recreational/menu',
                    'https://dutchie.com/api/v3/embedded-menu/x/carousels/y.js?routeRoot=https%3A%2F%2Fnoxx.com%2Fstores%2Fnoxx-28th-st',
                    'https://example.com/locations/cookiesmd'):
            self.assertTrue(branch_slug_conflict(DIXON, url), url)

    def test_own_locality_or_no_slug_is_not_a_conflict(self):
        for url in ('https://terrabis.co/menu/dixon-il-rec/', 'https://terrabis.co/menu/dixon-il-med/', 'https://terrabis.co/menu/',
                    'https://terrabis.co/', 'https://example.com/locations/dixon/menu',
                    'https://dutchie.com/embedded-menu/65772a69ac53410009424572'):
            self.assertFalse(branch_slug_conflict(DIXON, url), url)

    def test_city_words_may_be_split_or_prefixed_by_direction(self):
        peoria = dict(name='Noxx - East Peoria', address='300 S Main St', city='East Peoria', state='IL')
        self.assertFalse(branch_slug_conflict(peoria, 'https://noxx.com/stores/noxx-peoria'))
        self.assertTrue(branch_slug_conflict(peoria, 'https://noxx.com/stores/noxx-plainfield-ave'))


class SiblingLinkTests(unittest.TestCase):
    def resolve(self):
        hub = '<h1>Terrabis Dixon Cannabis Dispensary</h1>' + ''.join(
            f'<a href="/menu/{slug}/">Menu {slug}</a>' for slug in ('dixon-il-rec', 'ofallon-mo', 'plainfield-il-rec', 'grayville-il-rec'))

        class Fetcher:
            browser_options = {'enabled': False}

            def get(self, url, headers=None):
                if url.rstrip('/').endswith('/menu'):
                    return page(url, hub)
                slug = url.rstrip('/').rsplit('/', 1)[-1]
                return page(url, f'<h1>Terrabis {slug}</h1><p>Shop our menu</p>')
        return resolve_menu(dict(DIXON, website='https://terrabis.co/menu/'), Fetcher())

    def test_only_the_requested_branch_menu_is_returned(self):
        found = [r['url'] for r in self.resolve() if r['provider'] == 'generic' and not r.get('status')]
        self.assertEqual(found, ['https://terrabis.co/menu/dixon-il-rec/'])

    def test_embeds_whose_route_root_names_another_branch_are_dropped(self):
        text = ('<h1>Noxx East Peoria</h1> 300 S Main St East Peoria '
                '<script src="https://dutchie.com/api/v3/embedded-menu/627458da5d75a3008f52fc56/carousels/a.js?routeRoot=https%3A%2F%2Fnoxx.com%2Fstores%2Fnoxx-28th-st"></script>'
                '<script src="https://dutchie.com/api/v3/embedded-menu/65772a69ac53410009424572/carousels/b.js?routeRoot=https%3A%2F%2Fnoxx.com%2Fstores%2Fnoxx-peoria"></script>')

        class Fetcher:
            browser_options = {'enabled': False}

            def get(self, url, headers=None):
                return page(url, text)
        store = dict(name='Noxx - East Peoria', address='300 S Main St', city='East Peoria', state='IL', website='https://noxx.com/location/noxx-peoria/')
        found = [r['provider_store_id'] for r in resolve_menu(store, Fetcher()) if r['provider'] == 'dutchie' and not r.get('status')]
        self.assertEqual(found, ['65772a69ac53410009424572'])


def sweed_page(home, store_id, name, address, lat, lng, branches=None, menu=True):
    """A Sweed SSR store page: tenant config, the default store's info, optionally the catalog query and the branch list."""
    queries = [{'queryKey': ['/Store/GetStoreConfig', {}], 'state': {'data': {'id': store_id}}},
               {'queryKey': ['/Store/GetStoreInfoV2'], 'state': {'data': {'storeInfo': {
                   'id': store_id, 'name': name, 'contacts': {'address': address}, 'saleTypes': ['Recreational'], 'url': home,
                   'location': {'coords': {'lat': lat, 'lng': lng}, 'city': {'name': name.rsplit(' ', 1)[-1]}}}}}}]
    if menu:
        queries.append({'queryKey': ['/Products/GetProductList', {'filters': {}, 'page': 1, 'searchTerm': ''}], 'state': {'data': {}}})
    if branches is not None:
        queries.append({'queryKey': ['/Store/GetStoreShortInfoList'], 'state': {'data': {'shortStoreInfoList': branches}}})
    return (f'<title>{name} Cannabis Menu</title><a href="{home}/menu">Shop</a>'
            '<script>window.__S={"__sw_qc":' + json.dumps({'queries': queries}) + '}</script>')


class SweedDefaultBranchTests(unittest.TestCase):
    """Multi-store Sweed sites open on a default branch; the tenant's branch list leads to the requested store."""
    BRANCHES = [dict(name='Greenz - Belleville', url='https://order.example/belleville', contacts=dict(address='360 S Green Mt Rd, Belleville, IL 62221')),
                dict(name='Greenz - Decatur', url='https://order.example/decatur', contacts=dict(address='5045 Indus Dr, Decatur, IL 62522')),
                dict(name='Greenz - Lincoln', url='https://order.example/lincoln', contacts=dict(address='1120 Woodlawn Rd, Lincoln, IL 62656'))]

    def fetcher(self, pages):
        class Fetcher:
            browser_options = {'enabled': False}
            requested = []

            def get(self, url, headers=None):
                self.requested.append(url)
                return page(url, pages[url.rstrip('/')]) if url.rstrip('/') in pages else FetchResult(url, 404, b'', {}, 'e-404', '2026-10-18T09:00:00Z')
        return Fetcher()

    def pages(self, default_lists=True):
        belleville = dict(home='https://order.example/belleville', store_id=999, name='Greenz - Belleville', address='360 S Green Mt Rd, Belleville, IL 62221', lat=38.5053, lng=-89.9277)
        return {
            'https://order.example/belleville/menu': sweed_page(**belleville, branches=self.BRANCHES if default_lists else None),
            'https://order.example/belleville': sweed_page(**belleville, branches=self.BRANCHES, menu=False),
            'https://order.example/decatur': sweed_page('https://order.example/decatur', 1001, 'Greenz - Decatur', '5045 Indus Dr, Decatur, IL 62522', 39.84532, -89.03982, menu=False),
            'https://order.example/decatur/menu': sweed_page('https://order.example/decatur', 1001, 'Greenz - Decatur', '5045 Indus Dr, Decatur, IL 62522', 39.84532, -89.03982),
        }

    def sweed_ids(self, store, fetcher):
        return [r['provider_store_id'] for r in resolve_menu(store, fetcher) if r['provider'] == 'sweed' and not r.get('status')]

    def test_branch_list_on_default_page_leads_to_the_requested_store(self):
        # The registry street number is mistyped (5405 vs 5045); the branch's own map pin is at the registry point.
        store = dict(name='Greenz - Decatur', address='5405 Indus. Dr.', city='Decatur', state='IL', latitude=39.84513, longitude=-89.03858,
                     website='https://order.example/belleville/menu')
        self.assertEqual(self.sweed_ids(store, self.fetcher(self.pages())), ['1001'])

    def test_menu_page_without_the_list_reads_the_default_store_home(self):
        store = dict(name='Greenz - Lincoln', address='1120 Woodlawn Road', city='Lincoln', state='IL', latitude=40.1, longitude=-89.3,
                     website='https://order.example/belleville/menu')
        pages = self.pages(default_lists=False)
        pages['https://order.example/lincoln'] = sweed_page('https://order.example/lincoln', 1002, 'Greenz - Lincoln', '1120 Woodlawn Rd, Lincoln, IL 62656', 40.1, -89.3, menu=False)
        pages['https://order.example/lincoln/menu'] = sweed_page('https://order.example/lincoln', 1002, 'Greenz - Lincoln', '1120 Woodlawn Rd, Lincoln, IL 62656', 40.1, -89.3)
        fetcher = self.fetcher(pages)
        self.assertEqual(self.sweed_ids(store, fetcher), ['1002'])
        self.assertIn('https://order.example/belleville', fetcher.requested)

    def test_store_missing_from_the_list_is_not_given_a_sibling(self):
        store = dict(name='Greenz - Springfield', address='1 Main St', city='Springfield', state='IL', latitude=39.8, longitude=-89.6,
                     website='https://order.example/belleville/menu')
        self.assertEqual(self.sweed_ids(store, self.fetcher(self.pages())), [])


if __name__ == '__main__':
    unittest.main()
