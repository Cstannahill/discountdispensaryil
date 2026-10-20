"""Chain location lists, recorded 2026-10-19 (see tests/fixtures/chains). A list answers for its chain: a branch on the
list gets its menu, a branch off it is reported, and no open-web search runs for it."""
from pathlib import Path
import unittest
from unittest import mock

from backend import site_discovery
from backend.adapters import resolve_menu
from backend.chains import ASCEND_LIST, IVY_LIST, NUERA_LIST, chain_candidates
from backend.locators import discover_menu_candidates
from backend.network import FetchError

FIXTURES = Path('tests/fixtures/chains')
MIDWAY_ID = '67db1a78b40c6b931564d063'


def fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


class Response:
    status_code = 200
    evidence_id = 'captured-chain-list'
    fetched_at = '2026-10-19T19:00:00Z'

    def __init__(self, text, url):
        self.body, self.url = text.encode(), url


class Fetcher:
    """Serves the recorded lists. Any other URL is a test failure; `fetched` records every request."""
    def __init__(self):
        self.routes = {ASCEND_LIST: fixture('ascend_locations.json'),
                       'letsascend.com/stores/chicago-midway-illinois': fixture('ascend_store_page.html'),
                       IVY_LIST: fixture('ivy_locations.html'),
                       NUERA_LIST: fixture('nuera_dispensaries.html'),
                       'verilife.com/locations': fixture('verilife_locations.html'),
                       'verilife.com/il/locations/galena': FetchError('Public endpoint returned HTTP 403', 'evidence-403')}
        self.fetched = []

    def get(self, url, headers=None):
        self.fetched.append(url)
        for prefix, value in self.routes.items():
            if prefix in url:
                if isinstance(value, Exception):
                    raise value
                return Response(value, url)
        raise AssertionError('unexpected fetch ' + url)


def store(name, address, city, state='IL'):
    return dict(id='store-under-test', name=name, address=address, city=city, state=state, latitude=None, longitude=None)


def no_search(*args, **kwargs):
    raise AssertionError('open-web search ran for a chain store')


class ChainListTests(unittest.TestCase):
    def test_ascend_branch_menu_is_the_dutchie_dispensary_on_its_own_page(self):
        found = chain_candidates(store('Midway by Ascend', '5650 S Archer Ave', 'Chicago'), Fetcher())
        self.assertEqual(['matched'], [c['status'] for c in found])
        endpoint = found[0]['endpoint']
        self.assertEqual(('dutchie', MIDWAY_ID, f'https://dutchie.com/embedded-menu/{MIDWAY_ID}'),
                         (endpoint['provider'], endpoint['provider_store_id'], endpoint['url']))

    def test_near_miss_street_is_reported_without_a_menu_lead_or_a_page_read(self):
        fetcher = Fetcher()
        found = chain_candidates(store('Midway by Ascend', '5648 S Archer Ave', 'Chicago'), fetcher)
        self.assertEqual(['unresolved'], [c['status'] for c in found])
        self.assertIsNone(found[0]['url'])
        self.assertIn('5650', found[0]['reason'])
        self.assertFalse(any('chicago-midway' in url for url in fetcher.fetched))

    def test_out_of_state_branch_is_never_matched(self):
        # The Maryland Ascend branch sits at 226 S. Philadelphia; an Illinois registry store must not take it.
        found = chain_candidates(store('Ascend - Test', '226 S. Philadelphia', 'Aberdeen'), Fetcher())
        self.assertEqual(['unresolved'], [c['status'] for c in found])
        self.assertTrue(found[0]['store_list'])

    def test_branch_absent_from_the_list_is_an_answer(self):
        found = chain_candidates(store('Ascend - Test', '1 Main St', 'Rutland'), Fetcher())
        self.assertTrue(found[0]['store_list'])
        self.assertIn('absent', found[0]['reason'])

    def test_ivy_hall_branch_menu_is_its_listed_menu_page(self):
        found = chain_candidates(store('Ivy Hall - Glendale Heights', '2130 Bloomingdale Rd Unit B', 'Glendale Heights'), Fetcher())
        self.assertEqual([('matched', 'https://ivyhalldispensary.com/locations/glendaleheights/menu/')],
                         [(c['status'], c['url']) for c in found])

    def test_nuera_jane_ids_are_chosen_by_city_and_license(self):
        def ids(name, city):
            return sorted((c['endpoint']['license_type'], c['endpoint']['provider_store_id'])
                          for c in chain_candidates(store(name, '1 Main St', city), Fetcher()))
        self.assertEqual([('medicinal', '7415'), ('recreational', '6878')], ids('nuEra Chicago Southland', 'Harvey'))
        self.assertEqual([('medicinal', '1461'), ('recreational', '1462')], ids('Nuera Chicago', 'Chicago'))
        self.assertEqual([('recreational', '3050')], ids('NuEra Pekin', 'Pekin'))

    def test_verilife_branch_is_confirmed_but_its_rise_menu_is_reported_blocked(self):
        found = chain_candidates(store('Verilife Galena', '115 Perry St.', 'Galena'), Fetcher())
        self.assertEqual([('blocked', 'https://www.verilife.com/il/locations/galena')], [(c['status'], c['url']) for c in found])
        self.assertIn('HTTP 403', found[0]['reason'])

    def test_chain_list_answers_discovery_without_web_search(self):
        with mock.patch.object(site_discovery, 'search_websites', no_search):
            ivy = discover_menu_candidates(store('Ivy Hall - Crystal Lake', '501 Pingree Rd.', 'Crystal Lake'), Fetcher())
            verilife = discover_menu_candidates(store('Verilife Galena', '115 Perry St.', 'Galena'), Fetcher())
        self.assertEqual('matched', ivy[0]['status'])
        self.assertEqual('blocked', verilife[0]['status'])

    def test_resolver_carries_the_chain_dutchie_menu_without_reading_it_or_searching(self):
        fetcher = Fetcher()
        with mock.patch.object(site_discovery, 'search_websites', no_search):
            endpoints = resolve_menu(store('Midway by Ascend', '5650 S Archer Ave', 'Chicago'), fetcher)
        self.assertEqual([('dutchie', MIDWAY_ID)], [(e['provider'], e['provider_store_id']) for e in endpoints])
        self.assertFalse(any('dutchie.com' in url for url in fetcher.fetched))


if __name__ == '__main__':
    unittest.main()
