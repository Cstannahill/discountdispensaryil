"""Directory-anchored discovery: a Weedmaps listing is a website lead, never a menu."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from backend import directory
from backend.network import FetchError, FetchResult

FIXTURES = Path(__file__).parent / 'fixtures' / 'directory_weedmaps'
# Registry rows as published (region 8f7772ca082601b630476779).
PEKIN_LOCAL = dict(id='pekin', name='Pekin Local Dispensary & Supply', address='359 Court St.', city='Pekin', state='IL', latitude=40.56971, longitude=-89.64703)
NUERA_PEKIN = dict(id='nuera', name='NuEra Pekin', address='3249 Court St.', city='Pekin', state='IL', latitude=40.56443, longitude=-89.62883)
ASCEND_RIVER_NORTH = dict(id='ascend', name='Ascend Moca  River North', address='216 W. Ohio St.', city='Chicago', state='IL', latitude=41.891171, longitude=-87.634354)
GREEN_ROSE_CHICAGO = dict(id='rose', name='Green Rose - Chicago', address='612 N. Wells St.', city='Chicago', state='IL', latitude=41.89293, longitude=-87.63401)
SUNNYSIDE_RIVER_NORTH = dict(id='sunny', name='Sunnyside - Chi-River North', address='436 N. Clark St.', city='Chicago', state='IL', latitude=41.89032, longitude=-87.63142)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def listings(name):
    return fixture(name)['data']['listings']


class WeedmapsFetcher:
    """Serves recorded Weedmaps responses by query; anything else is a fixture gap."""
    def __init__(self, evidence_dir=None, details=None):
        self.calls, self.sleeps = [], []
        self.details = details or {}
        if evidence_dir:self.evidence_dir = Path(evidence_dir)

    def sleeper(self, seconds):
        self.sleeps.append(seconds)

    def get(self, url, headers=None):
        self.calls.append(url)
        parts = urlsplit(url)
        if parts.path.startswith('/discovery/v1/listings/dispensaries/'):
            slug = parts.path.rsplit('/', 1)[1]
            if slug in self.details:body = json.dumps(self.details[slug]).encode()
            elif (FIXTURES / f'detail_{slug}.json').exists():body = (FIXTURES / f'detail_{slug}.json').read_bytes()
            else:raise FetchError('Public endpoint returned HTTP 404', 'detail-404')
            return FetchResult(url, 200, body, {}, 'detail-' + slug, '2026-10-18T20:00:00+00:00')
        query = parse_qs(parts.query)
        self.query = query
        tile = query['filter[bounding_latlng]'][0]
        name = FIXTURES / f"tile_{tile.replace(',', '_')}_size{query['page_size'][0]}_p{query['page'][0]}.json"
        if not name.exists():raise AssertionError('No recorded page for ' + url)
        return FetchResult(url, 200, name.read_bytes(), {}, 'page-' + query['page'][0], '2026-10-18T20:00:00+00:00')


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        directory._last_request[0] = 0.0

    def test_tile_is_paged_to_the_advertised_total_throttled_and_cached_for_the_region(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(directory, 'PAGE_SIZE', 5):
            fetcher = WeedmapsFetcher(folder)
            found = directory.tile_listings(fetcher, PEKIN_LOCAL['latitude'], PEKIN_LOCAL['longitude'])
            self.assertEqual(len(fetcher.calls), 3)
            self.assertEqual(fetcher.query['filter[bounding_latlng]'], ['40.5,-89.5'])
            self.assertEqual(fetcher.query['filter[bounding_radius]'], ['30mi'])
            self.assertEqual(fetcher.query['filter[plural_types][]'], ['dispensaries'])
            self.assertEqual(len({x['slug'] for x in found['listings']}), 14)
            self.assertEqual([x['evidence_id'] for x in found['pages']], ['page-1', 'page-2', 'page-3'])
            # Consecutive directory requests are spaced; the first one is not delayed.
            self.assertEqual(len(fetcher.sleeps), 2)
            self.assertTrue(all(0 < s <= directory.THROTTLE_SECONDS for s in fetcher.sleeps))
            # Another store in the same tile reuses it, and so does a restarted worker.
            directory.tile_listings(fetcher, NUERA_PEKIN['latitude'], NUERA_PEKIN['longitude'])
            restarted = WeedmapsFetcher(folder)
            again = directory.tile_listings(restarted, NUERA_PEKIN['latitude'], NUERA_PEKIN['longitude'])
            self.assertEqual((len(fetcher.calls), restarted.calls), (3, []))
            self.assertEqual(again['listings'], found['listings'])

    def test_a_short_or_failed_page_is_an_error_and_is_never_cached(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(directory, 'PAGE_SIZE', 5):
            fetcher = WeedmapsFetcher(folder)
            original = fetcher.get
            def missing_third(url, headers=None):
                if 'page=3' in url:raise FetchError('Public endpoint returned HTTP 503', 'page-503')
                return original(url, headers)
            fetcher.get = missing_third
            result = directory.lookup(PEKIN_LOCAL, fetcher)
            self.assertEqual((result['status'], result['leads']), ('failed', []))
            self.assertIn('503', result['error'])
            self.assertFalse(list(Path(folder).rglob('*.json')))

    def test_strict_match_needs_both_distance_and_street_number(self):
        nearby = listings('river_north_1mi.json')
        # Ascend Moca has no listing; Green Rose (0.12 mi) and Sunnyside are near-misses at other street numbers.
        matches, rejected = directory.match_listings(ASCEND_RIVER_NORTH, nearby)
        self.assertEqual(matches, [])
        self.assertEqual({x['slug'] for x in rejected}, {'green-rose-dispensary', 'sunnyside-dispensary-river-north'})
        self.assertTrue(all(x['distance_miles'] <= directory.MATCH_MILES for x in rejected))
        self.assertEqual([x['slug'] for x in directory.match_listings(GREEN_ROSE_CHICAGO, nearby)[0]], ['green-rose-dispensary'])
        self.assertEqual([x['slug'] for x in directory.match_listings(SUNNYSIDE_RIVER_NORTH, nearby)[0]], ['sunnyside-dispensary-river-north'])

    def test_same_street_address_beyond_the_radius_is_not_a_lead(self):
        # NuEra Pekin's registry coordinates are 1.7 mi from its listing at the same address; the rule stays strict.
        matches, _ = directory.match_listings(NUERA_PEKIN, listings('tile_40.5_-89.5_size100_p1.json'))
        self.assertEqual(matches, [])

    def test_name_tokens_only_break_ties_between_qualifying_listings(self):
        pekin = next(x for x in listings('tile_40.5_-89.5_size100_p1.json') if x['slug'] == 'pekin-s-local-dispensary-supply')
        cotenant = dict(pekin, slug='cotenant', name='Unrelated Wellness')
        lookalike = dict(pekin, slug='lookalike', address='361 Court St.')
        matches, rejected = directory.match_listings(PEKIN_LOCAL, [cotenant, lookalike, pekin])
        self.assertEqual([x['slug'] for x in matches], ['pekin-s-local-dispensary-supply', 'cotenant'])
        self.assertEqual([x['slug'] for x in rejected], ['lookalike'])

    def test_listing_in_another_state_is_never_a_match(self):
        pekin = next(x for x in listings('tile_40.5_-89.5_size100_p1.json') if x['slug'] == 'pekin-s-local-dispensary-supply')
        self.assertEqual(directory.match_listings(PEKIN_LOCAL, [dict(pekin, state='Iowa')])[0], [])

    def test_lookup_returns_the_retailer_website_as_a_candidate_lead_with_license_evidence(self):
        fetcher = WeedmapsFetcher()
        result = directory.lookup(PEKIN_LOCAL, fetcher)
        self.assertEqual(result['status'], 'matched')
        self.assertEqual([lead['url'] for lead in result['leads']], ['https://pekindispensary.com/'])
        lead = result['leads'][0]
        # A lead is never pre-verified: the resolver must still prove the branch on the retailer page.
        self.assertEqual((lead['status'], lead['source_role']), ('candidate', 'directory'))
        evidence = lead['evidence'][0]
        self.assertEqual((evidence['source'], evidence['license_number'], evidence['license_type']), ('weedmaps', '284.000371-AUDO', 'recreational'))
        self.assertEqual(evidence['listing_url'], 'https://weedmaps.com/dispensaries/pekin-s-local-dispensary-supply')
        self.assertEqual((evidence['listing_evidence_id'], evidence['detail_evidence_id']), ('page-1', 'detail-pekin-s-local-dispensary-supply'))
        self.assertLess(evidence['distance_miles'], 0.05)
        # Only the matched listing's detail is fetched.
        self.assertEqual(sum('/listings/dispensaries/' in url for url in fetcher.calls), 1)

    def test_listing_without_a_usable_website_is_recorded_but_seeds_nothing(self):
        with mock.patch.object(directory, 'tile_listings', return_value=dict(listings=[dict(x, evidence_id='page-1') for x in listings('river_north_1mi.json')], pages=[])):
            result = directory.lookup(SUNNYSIDE_RIVER_NORTH, WeedmapsFetcher())
        self.assertEqual((result['status'], result['leads']), ('no_website', []))
        self.assertEqual([x['slug'] for x in result['matches']], ['sunnyside-dispensary-river-north'])
        for website in ('', 'https://www.instagram.com/pekins_local_dispo', 'https://weedmaps.com/dispensaries/x', 'mailto:x@example.com'):
            self.assertIsNone(directory.website_url(website), website)
        self.assertEqual(directory.website_url('www.example.com/shop'), 'https://www.example.com/shop')

    def test_unit_suffix_and_grid_addresses_keep_their_street_number(self):
        self.assertEqual([directory.street_number(x) for x in ('6119A East Ave', '6119 East Ave A', '4S120 N Route 59', '359 Court St.', 'Route 59')],
                         ['6119', '6119', '4S120', '359', None])
        # Namaste: registry "6119 East Ave A", listing "6119A East Ave", 0.013 mi apart.
        namaste = dict(id='namaste', name='Namaste Wellness', address='6119 East Ave A', city='Hodgkins', state='IL', latitude=41.77939, longitude=-87.85795)
        self.assertEqual([x['slug'] for x in directory.match_listings(namaste, listings('namaste_0.5mi.json'))[0]], ['namaste'])

    def test_tracking_parameters_are_dropped_from_a_website_lead(self):
        cloud9 = dict(id='cloud9', name='Cloud 9 Cannabis - Schaumburg', address='1823 W Wise Rd.', city='Schaumburg', state='IL', latitude=42.00338, longitude=-88.1257)
        tile = dict(listings=[dict(x, evidence_id='page-1') for x in listings('cloud9_schaumburg_0.5mi.json')], pages=[])
        with mock.patch.object(directory, 'tile_listings', return_value=tile):
            result = directory.lookup(cloud9, WeedmapsFetcher())
        self.assertEqual([lead['url'] for lead in result['leads']], ['https://www.cloud9dispensaries.shop/'])
        self.assertIn('utm_source=gmb', result['matches'][0]['website'])
        self.assertEqual(directory.website_url('https://x.example/menu?utm_source=a&store=5&fbclid=z'), 'https://x.example/menu?store=5')

    def test_store_without_coordinates_is_skipped_without_requests(self):
        fetcher = WeedmapsFetcher()
        result = directory.lookup(dict(PEKIN_LOCAL, latitude=None), fetcher)
        self.assertEqual((result['status'], fetcher.calls), ('skipped', []))


class DirectoryResolverTests(unittest.TestCase):
    def lead(self, url='https://retailer.example/'):
        return dict(url=url, status='candidate', source_role='directory', reason='Weedmaps listing', evidence=[dict(source='weedmaps')])

    def resolve(self, page):
        from backend.adapters import resolve_menu
        calls = []
        class Fetcher:
            def get(self, url, headers=None):
                calls.append(url)
                if 'retailer.example' in url:return FetchResult(url, 200, page.encode(), {}, 'retailer', '2026-10-18T20:00:00+00:00')
                return FetchResult(url, 200, b'<html></html>', {}, 'search', '2026-10-18T20:00:00+00:00')
        store = dict(name='Example Cannabis', address='1 Main St', city='Rutland', state='IL', latitude=40.98, longitude=-89.04,
                     directory_leads=[self.lead()])
        return resolve_menu(store, Fetcher()), calls

    def test_directory_website_is_a_seed_ahead_of_web_search(self):
        page = '<h1>Example Cannabis Rutland</h1><p>1 Main St, Rutland IL</p><script src="https://dutchie.com/api/v2/embedded-menu/abc123.js"></script>'
        menus, calls = self.resolve(page)
        self.assertEqual(calls[0], 'https://retailer.example/')
        self.assertFalse(any('bing.com' in url or 'duckduckgo' in url for url in calls))
        self.assertTrue(any(m['provider'] == 'dutchie' and m['provider_store_id'] == 'abc123' for m in menus))
        self.assertEqual(next(m for m in menus if m['provider'] == 'dutchie')['locator_evidence'], [dict(source='weedmaps')])

    def test_directory_website_for_another_branch_proves_nothing_and_search_remains_the_fallback(self):
        page = '<h1>Example Cannabis</h1><script type="application/ld+json">' + json.dumps({'@type': 'Store', 'address': {'streetAddress': '99 Other St', 'addressRegion': 'IL'}}) + '</script><script src="https://dutchie.com/api/v2/embedded-menu/abc123.js"></script>'
        menus, calls = self.resolve(page)
        self.assertFalse(any(m['provider'] == 'dutchie' and not m.get('status') for m in menus))
        self.assertTrue(any('bing.com' in url for url in calls))


class DirectoryServiceTests(unittest.TestCase):
    def setUp(self):
        from backend.storage import Store
        from test_storage import observation
        self.temp = tempfile.TemporaryDirectory();root = Path(self.temp.name)
        self.store = Store(root / 'db.sqlite', root / 'evidence')
        self.store.import_registry([observation()], 'registry')
        self.region = self.store.create_region(40.9844, -89.0388, 'Initial region', 50)
        self.shop = self.store.stores_in_region()[0]
        self.service = None

    def tearDown(self):
        if self.service:self.service.close()
        self.temp.cleanup()

    def run_job(self, directory_lookup, resolver):
        from backend.service import SyncService
        from test_service import FixtureFetcher
        self.service = SyncService(self.store, FixtureFetcher(), resolver=resolver, directory=directory_lookup)
        job = self.store.enqueue(dict(region_id=self.region['id'], discover=False))
        self.service.run(job['id'])
        return self.store.job(job['id'])

    def test_directory_match_is_a_recorded_lead_that_seeds_the_resolver_and_never_an_endpoint(self):
        match = dict(source='weedmaps', listing_url='https://weedmaps.com/dispensaries/test-shop', slug='test-shop', website='https://testshop.example/',
                     lead_url='https://testshop.example/', distance_miles=0.02, street_number='100', license_number='284.000001-AUDO', license_type='recreational')
        lead = dict(url='https://testshop.example/', status='candidate', source_role='directory', reason='Weedmaps listing', evidence=[match])
        seen = []
        def resolver(store, fetcher):
            seen.append(store.get('directory_leads'))
            return []
        self.run_job(lambda store, fetcher: dict(status='matched', leads=[lead], matches=[match], rejected=[]), resolver)
        self.assertEqual(seen, [[lead]])
        self.assertEqual(self.store.endpoints(self.shop['id']), [])
        leads = self.store.leads(self.shop['id'])
        self.assertEqual([(x['url'], x['source']) for x in leads], [('https://weedmaps.com/dispensaries/test-shop', 'directory:weedmaps')])
        self.assertIn('https://testshop.example/', leads[0]['reason'])
        self.assertEqual(json.loads(leads[0]['evidence_json'])[0]['license_number'], '284.000001-AUDO')
        resolution = self.store.stores_in_region()[0]['resolution']
        self.assertEqual(json.loads(resolution['evidence_json'])['directory']['leads'], ['https://testshop.example/'])

    def test_directory_failure_never_blocks_resolution(self):
        seen = []
        def broken(store, fetcher):raise RuntimeError('directory down')
        self.run_job(broken, lambda store, fetcher: seen.append(store.get('directory_leads')) or [])
        self.assertEqual(seen, [[]])


if __name__ == '__main__':
    unittest.main()
