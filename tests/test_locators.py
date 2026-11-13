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

    def test_embedded_store_list_binds_branch_menus_by_street_address(self):
        text = Path('tests/fixtures/provider_probe/beyond-locator.html').read_text(encoding='utf-8')
        class Fetcher:
            def get(self, url):
                return Response(text, 'https://beyond-hello.com/illinois-dispensaries/')
        results = discover_menu_candidates(dict(name='Beyond/Hello  Sauget', address='2021 Goose Lake Rd', city='Sauget'), Fetcher())
        self.assertEqual(sorted(r['url'] for r in results if r['status'] == 'matched'),
                         ['https://beyond-hello.com/illinois-dispensaries/goose-lake/adult-use-menu/',
                          'https://beyond-hello.com/illinois-dispensaries/goose-lake/medical-menu/'])
        self.assertEqual('2021 Goose Lake Road, Sauget, IL 62206', results[0]['retailer_address'])
        # Same city, other branch: the suite-number form still matches its own street address only.
        results = discover_menu_candidates(dict(name='Beyond Hello  Sauget Mississippi Ave', address='1401 Mississippi Ave. Ste. 17', city='Sauget'), Fetcher())
        self.assertEqual(sorted(r['url'] for r in results if r['status'] == 'matched'),
                         ['https://beyond-hello.com/illinois-dispensaries/st-louis-metro-east/adult-use-menu/',
                          'https://beyond-hello.com/illinois-dispensaries/st-louis-metro-east/medical-menu/'])

    def test_branch_absent_from_embedded_store_list_is_not_bound_to_a_sibling(self):
        from backend.locators import _known_menu_candidates
        text = Path('tests/fixtures/provider_probe/beyond-locator.html').read_text(encoding='utf-8')
        class Fetcher:
            def get(self, url):
                return Response(text, 'https://beyond-hello.com/illinois-dispensaries/')
        results = _known_menu_candidates(dict(name='Beyond/Hello - Peoria', address='7620 N IL Rt 91', city='Peoria'), Fetcher())
        self.assertEqual(['unresolved'], [r['status'] for r in results])
        self.assertIn('absent', results[0]['reason'])
        class SearchFindsNothing(Fetcher):
            def get(self, url):
                if 'beyond-hello.com' in url:return Response(text, 'https://beyond-hello.com/illinois-dispensaries/')
                return Response('<html>no results</html>', url)
        results = discover_menu_candidates(dict(name='Beyond/Hello - Peoria', address='7620 N IL Rt 91', city='Peoria'), SearchFindsNothing())
        self.assertEqual(['unresolved'], [r['status'] for r in results])
        self.assertIn('absent', results[0]['reason'])

    def test_street_abbreviations_match_but_house_numbers_do_not(self):
        self.assertTrue(addresses_match('50 Gore Rd', '50 Gore Road, Morris, Illinois'))
        self.assertTrue(addresses_match('3929 W. War Memorial Dr', '3929 West War Memorial Drive, Peoria IL'))
        self.assertTrue(addresses_match('20 Northwest Hwy', '20 NW HWY'))
        self.assertFalse(addresses_match('20 Northwest Hwy', '20 NE HWY'))
        self.assertFalse(addresses_match('1210 W Glen Ave', '1204 West Glen Avenue'))

    def test_new_unknown_brand_is_an_explicit_discovery_gap(self):
        class SearchUnavailable:
            def get(self,url):raise RuntimeError('Search unavailable')
        results = discover_menu_candidates(dict(name='New Independent Dispensary', address='1 Main St', city='Rutland'), SearchUnavailable())
        self.assertEqual(results[0]['status'], 'unresolved')
        self.assertIn('search', results[0]['reason'].lower())

    def test_verilife_menus_are_located_on_the_rise_site(self):
        from backend.locators import CONNECTORS
        import re
        root = next(url for pattern, url in CONNECTORS if re.search(pattern, 'Verilife Ottawa', re.I))
        self.assertEqual('https://risecannabis.com/dispensaries/illinois/', root)

    def test_street_aliases_platforms_write_differently_still_match(self):
        for registry, platform in (('1225 N State Route 121', '1225 IL-121'), ('5539 Miller Circle Dr', '5539 Miller Cir Dr'),
                                   ('13352 Cicero Ave', '13352 S Cicero Ave'), ('9820 Ridgeland Ave', '9820 S Ridgeland Ave'),
                                   ('740 IL Rte 59', '740 Route 59'), ('114 Commerce Ln', '114 Commerce Lane')):
            self.assertTrue(addresses_match(registry, platform), (registry, platform))
        self.assertFalse(addresses_match('13352 Cicero Ave', '13352 S Pulaski Ave'))
        self.assertFalse(addresses_match('100 N Main St', '100 S Main St'))

    def test_store_sitemap_names_branch_pages_a_gated_home_page_hides(self):
        from backend.locators import _known_menu_candidates
        fixtures = Path('tests/fixtures/curaleaf')
        class Fetcher:
            def get(self, url):
                if url.endswith('/robots.txt'):return Response((fixtures/'robots.txt').read_text(encoding='utf-8'), url)
                if url.endswith('/dispensaries-sitemap.xml'):return Response((fixtures/'dispensaries-sitemap.xml').read_text(encoding='utf-8'), url)
                if 'sitemap' in url:raise AssertionError('only store sitemaps are read: '+url)
                return Response('<title>Curaleaf</title><a href="/shop">Shop</a>', 'https://curaleaf.com/')
        def urls(name, address, city):
            return [r['url'] for r in _known_menu_candidates(dict(name=name, address=address, city=city, state='IL'), Fetcher()) if r['status'] == 'candidate']
        self.assertEqual(['https://curaleaf.com/shop/illinois/curaleaf-il-morris'], urls('Curaleaf  Morris', '2400 W US Route 6', 'Morris'))
        self.assertEqual(['https://curaleaf.com/shop/illinois/curaleaf-il-melrose-park'], urls('Curaleaf  Melrose Park', '1413 West North Ave.', 'Melrose Park'))
        # The slug names the street, not the city; Florida's Lake Worth is another state's branch.
        self.assertEqual(['https://curaleaf.com/shop/illinois/curaleaf-il-weed-street'], urls('Curaleaf  Lincoln Park', '923 W. Weed St.', 'Chicago'))
        self.assertEqual(['https://curaleaf.com/shop/illinois/curaleaf-il-worth'], urls('Curaleaf  Worth', '11425 S Harlem Ave', 'Worth'))

    def test_curaleaf_house_number_and_city_accepted_other_chains_stay_strict(self):
        from backend.site_discovery import provider_address_matches
        sweed=lambda address:dict(provider='sweed',resolution_evidence=dict(retailer_address=address))
        morris='2400 Hiawatha Pioneer Trail, Morris, Illinois'
        self.assertTrue(provider_address_matches(dict(name='Curaleaf  Morris',address='2400 W US Route 6',city='Morris',state='IL'),sweed(morris)))
        self.assertFalse(provider_address_matches(dict(name='Curaleaf New Lenox',address='705 E Lincoln Hwy.',city='New Lenox',state='IL'),sweed('709 East Lincoln Highway, New Lenox, Illinois')))
        self.assertFalse(provider_address_matches(dict(name='Other Dispensary',address='2400 W US Route 6',city='Morris',state='IL'),sweed(morris)))
        self.assertFalse(provider_address_matches(dict(name='Curaleaf Morris',address='2401 W US Route 6',city='Morris',state='IL'),sweed(morris)))
        # New Lenox: the platform's branch pin sits on the registry point; the street number differs.
        pin=dict(name='Curaleaf New Lenox',address='705 E Lincoln Hwy.',city='New Lenox',state='IL',latitude=41.51329,longitude=-87.94875)
        new_lenox=dict(provider='sweed',resolution_evidence=dict(retailer_address='709 East Lincoln Highway, New Lenox, Illinois',retailer_location=dict(coords=dict(lat=41.5130198,lng=-87.9486632))))
        self.assertTrue(provider_address_matches(pin,new_lenox))
        self.assertFalse(provider_address_matches(dict(pin,name='Other Dispensary'),new_lenox))
        far=dict(new_lenox,resolution_evidence=dict(new_lenox['resolution_evidence'],retailer_location=dict(coords=dict(lat=41.7,lng=-87.9))))
        self.assertFalse(provider_address_matches(pin,far))


if __name__ == '__main__':
    unittest.main()
