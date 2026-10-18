"""Sibling branches listed on a chain's pages must prove themselves; they never inherit the requested store's identity."""
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


if __name__ == '__main__':
    unittest.main()
