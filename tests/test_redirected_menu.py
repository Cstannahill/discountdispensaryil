"""A Dutchie embed that redirects to the retailer's own storefront is the same menu only when that page carries the same store id."""
import unittest

from backend.network import FetchResult
from backend.providers.generic import same_store_redirect


def page(url, text):
    return FetchResult(url, 200, text.encode(), {}, 'e-' + url[-12:], '2026-10-20T09:00:00Z')


DUTCHIE = dict(provider='dutchie', provider_store_id='684991b85f1314468afebce7', url='https://dutchie.com/embedded-menu/684991b85f1314468afebce7')


class SameStoreRedirectTests(unittest.TestCase):
    def test_a_storefront_page_carrying_the_same_store_id_is_the_same_menu(self):
        response = page('https://letsascend.com/chicago-ridge/menu/', '<script>window.dispensaryId="684991b85f1314468afebce7"</script>')
        self.assertTrue(same_store_redirect(DUTCHIE, response))

    def test_a_page_with_another_store_id_is_not_the_same_menu(self):
        response = page('https://letsascend.com/midway/menu/', '<script>window.dispensaryId="67db1a78b40c6b931564d063"</script>')
        self.assertFalse(same_store_redirect(DUTCHIE, response))

    def test_only_dutchie_embeds_qualify(self):
        response = page('https://letsascend.com/menu/', '684991b85f1314468afebce7')
        self.assertFalse(same_store_redirect(dict(DUTCHIE, provider='generic'), response))


if __name__ == '__main__':
    unittest.main()
