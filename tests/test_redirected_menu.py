"""A Dutchie embed that redirects to the retailer's own storefront is the same menu only when that page carries the same store id."""
import unittest

from backend.failures import FailureCode, classify
from backend.network import FetchResult
from backend.providers.generic import browser_error_page, same_store_host, same_store_redirect


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


class SameStoreHostTests(unittest.TestCase):
    def test_later_pages_on_a_proven_storefront_host_are_the_same_menu(self):
        hosts = set()
        first = page('https://letsascend.com/menu/?page=1', '<script>dispensaryId="684991b85f1314468afebce7"</script>')
        second = page('https://letsascend.com/menu/?page=2', '<div>a later page need not repeat the store id</div>')
        self.assertTrue(same_store_host(DUTCHIE, first, hosts))
        self.assertTrue(same_store_host(DUTCHIE, second, hosts))

    def test_a_later_page_on_an_unproven_host_is_not_accepted(self):
        hosts = set()
        other = page('https://other.example/menu/?page=2', '<div>no store id here</div>')
        self.assertFalse(same_store_host(DUTCHIE, other, hosts))


class BrowserErrorPageTests(unittest.TestCase):
    def test_chromes_error_page_is_not_the_menu_and_reports_a_refusal(self):
        response = page('chrome-error://chromewebdata/', '')
        self.assertTrue(browser_error_page(response))
        message = 'Browser navigation refused: the source refused this browser session (HTTP 403 on this menu) and Chrome showed an error page instead of the menu'
        self.assertEqual(FailureCode.HTTP_REJECTED, classify(message))

    def test_a_real_storefront_page_is_not_an_error_page(self):
        self.assertFalse(browser_error_page(page('https://dutchie.com/embedded-menu/684991b85f1314468afebce7', '')))


if __name__ == '__main__':
    unittest.main()
