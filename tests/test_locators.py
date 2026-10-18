from pathlib import Path
import unittest

from backend.locators import discover_menu_candidates, addresses_match


class Response:
    status_code = 200
    evidence_id = 'captured-locator'
    fetched_at = '2026-10-17T07:00:00Z'
    def __init__(self, text, url):
        self.body, self.url = text.encode(), url


class LocatorTests(unittest.TestCase):
    def test_known_official_age_gate_is_not_replaced_by_a_directory_result(self):
        class Fetcher:
            def get(self,url):
                if 'stashdispensaries.com' in url:
                    return Response('<title>Age Gate</title>Please confirm you are at least 21', 'https://www.stashdispensaries.com/age-gate?returnUrl=/')
                return Response('<li class="b_algo"><h2><a href="https://www.jointcommerce.com/dispensaries/stash-peru/menu">Stash Peru cannabis dispensary</a></h2></li>',url)
        results=discover_menu_candidates(dict(name='Stash - Peru',city='Peru',address='1320 38th St'),Fetcher())
        self.assertEqual(results[0]['status'],'blocked')
        self.assertIn('stashdispensaries.com',results[0]['url'])

    def test_live_chain_directory_selects_branch_by_address_not_default_store(self):
        text = Path('tests/fixtures/provider_probe/tree.txt').read_text(encoding='utf-8')
        class Fetcher:
            def get(self, url):
                return Response(text, 'https://shop.treehausil.com/morris')
        results = discover_menu_candidates(dict(name='Tree Haus - Diamond', address='2910 E. Division St', city='Diamond'), Fetcher())
        self.assertEqual([r['url'] for r in results if r['status'] == 'matched'], ['https://shop.treehausil.com/diamond'])

    def test_address_conflict_is_preserved_instead_of_silently_matching_city(self):
        text = Path('tests/fixtures/provider_probe/aroma.txt').read_text(encoding='utf-8')
        class Fetcher:
            def get(self, url):
                return Response(text, 'https://shop.aromahillcannabis.com/peoria')
        results = discover_menu_candidates(dict(name='Aroma Hill - Peoria', address='1210 W Glen Ave', city='Peoria'), Fetcher())
        self.assertTrue(any(r['status'] == 'identity_conflict' for r in results))
        self.assertFalse(any(r['status'] == 'matched' for r in results))

    def test_street_abbreviations_match_but_house_numbers_do_not(self):
        self.assertTrue(addresses_match('50 Gore Rd', '50 Gore Road, Morris, Illinois'))
        self.assertTrue(addresses_match('3929 W. War Memorial Dr', '3929 West War Memorial Drive, Peoria IL'))
        self.assertFalse(addresses_match('1210 W Glen Ave', '1204 West Glen Avenue'))

    def test_new_unknown_brand_is_an_explicit_discovery_gap(self):
        class SearchUnavailable:
            def get(self,url):raise RuntimeError('Search unavailable')
        results = discover_menu_candidates(dict(name='New Independent Dispensary', address='1 Main St', city='Rutland'), SearchUnavailable())
        self.assertEqual(results[0]['status'], 'unresolved')
        self.assertIn('search', results[0]['reason'].lower())


if __name__ == '__main__':
    unittest.main()
