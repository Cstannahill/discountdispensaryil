"""A chain site lists every branch in its navigation, so a sibling branch's page names the requested town too. Its embed is not this store's menu."""
import unittest
from unittest.mock import patch

from backend import adapters
from backend.network import FetchResult

NAV = '<nav><a href="/store/grandhaven/">Grand Haven</a><a href="/store/supergood-des-plaines/">Des Plaines</a></nav>'


def page(name, embed):
    return f'<html><body>{NAV}<h1>{name}</h1><script src="https://dutchie.com/api/v2/embedded-menu/{embed}.js"></script></body></html>'


class Fetcher:
    pages = {'https://chain.example/': f'<html><body>{NAV}<h1>Supergood Store</h1></body></html>',
             'https://chain.example/store/grandhaven/': page('Supergood Store Grand Haven', 'aaaaaaaaaaaaaaaaaaaaaaaa'),
             'https://chain.example/store/supergood-des-plaines/': page('Supergood Store Des Plaines', 'bbbbbbbbbbbbbbbbbbbbbbbb')}

    def get(self, url, headers=None):
        if url not in self.pages:
            raise RuntimeError('unexpected ' + url)
        return FetchResult(url, 200, self.pages[url].encode(), {}, 'ev', '2026-10-22T00:00:00Z')


class SiblingBranchTests(unittest.TestCase):
    def test_only_the_requested_branchs_own_embed_becomes_a_menu(self):
        store = dict(name='Supergood Store', city='Des Plaines', state='IL', address='660 N. Wolf Rd.', website='https://chain.example/')
        with patch('backend.site_discovery.search_websites', return_value=[]), patch('backend.locators.discover_menu_candidates', return_value=[]):
            found = adapters.resolve_menu(store, Fetcher())
        ids = [x['provider_store_id'] for x in found if x['provider'] == 'dutchie' and not x.get('status')]
        self.assertEqual(['bbbbbbbbbbbbbbbbbbbbbbbb'], ids)


if __name__ == '__main__':
    unittest.main()
