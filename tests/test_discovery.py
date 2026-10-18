import csv
import io
import json
from pathlib import Path
import unittest

from backend.discovery import parse_registry, resolve_location, haversine_miles, territory_scope

FIXTURES = Path(__file__).resolve().parents[1] / 'docs' / 'evidence'


class DiscoveryTests(unittest.TestCase):
    def test_captured_rows_and_five_regressions_are_accounted_for(self):
        rows = parse_registry((FIXTURES / '2026-10-17-illinois-dispensary-map.csv').read_bytes())
        self.assertEqual(len(rows), 287)
        for name, city in [('Cloud 9', 'East Peoria'), ('Stash', 'Peru'), ('Snap', 'Pontiac'), ('Beyond', 'Bloomington'), ('Beyond', 'Peoria')]:
            self.assertTrue(any(name.lower() in r['name'].lower() and r['city'] == city for r in rows), (name, city))
        self.assertEqual(len({r['source_key'] for r in rows}), 287)
        self.assertTrue(all(r['raw'] and r['state'] == 'IL' for r in rows))
        nearby = [r for r in rows if haversine_miles(40.9844, -89.0388, r['latitude'], r['longitude']) <= 50]
        self.assertEqual(len(nearby), 23)  # Dated fixture count, never a live coverage target.
        self.assertTrue(any('Cloud 9' in r['name'] for r in nearby))
        self.assertTrue(any('Snap' in r['name'] for r in nearby))
        self.assertTrue(any('Stash' in r['name'] for r in nearby))

    def mutate(self, change):
        rows = list(csv.reader(io.StringIO((FIXTURES / '2026-10-17-illinois-dispensary-map.csv').read_text(encoding='utf-8-sig'))))[:2]
        change(rows)
        out = io.StringIO()
        csv.writer(out).writerows(rows)
        return out.getvalue().encode()

    def test_duplicate_columns_cannot_silently_overwrite_conflicts(self):
        with self.assertRaisesRegex(ValueError, 'row 2.*Dispensary Name.*conflict'):
            parse_registry(self.mutate(lambda rows: rows[1].__setitem__(6, 'Different store')))

    def test_invalid_rows_and_changed_schema_fail_the_import(self):
        for change in [lambda r: r[1].pop(), lambda r: r[1].__setitem__(1, 'nan'), lambda r: r[1].__setitem__(2, '181'), lambda r: r[1].__setitem__(3, 'Maybe'), lambda r: r[1].__setitem__(7, ''), lambda r: r[0].__setitem__(4, 'Unexpected Column')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_registry(self.mutate(change))

    def test_zip_uses_real_response_and_approximate_precision(self):
        payload = json.loads((FIXTURES / '2026-10-17-61358-geocode.json').read_text())['response']
        def fetch(url):
            self.assertEqual(url, 'https://api.zippopotam.us/us/61358')
            return payload
        result = resolve_location('61358', fetch)
        self.assertEqual((result['latitude'], result['longitude']), (40.9844, -89.0388))
        self.assertEqual(result['precision'], 'approximate_zip_centroid')
        self.assertIn('Rutland', result['label'])

    def test_unknown_ambiguous_and_invalid_coordinates_never_fallback(self):
        for query, payload in [('00000', {}), ('61358', {'places': []}), ('unknown city', [{'lat': '40', 'lon': '-89'}, {'lat': '41', 'lon': '-88'}]), ('91,-89', {})]:
            with self.subTest(query=query), self.assertRaises(ValueError):
                resolve_location(query, lambda url: payload)

    def test_explicit_coordinates_do_not_fetch(self):
        result = resolve_location('40.9844, -89.0388', lambda _: self.fail('coordinates should not fetch'))
        self.assertEqual(result['precision'], 'explicit_coordinates')

    def test_mismatched_zip_response_is_not_accepted(self):
        payload = {'country abbreviation': 'US', 'post code': '90210', 'places': [{'place name': 'Beverly Hills', 'state abbreviation': 'CA', 'latitude': '34.1', 'longitude': '-118.4'}]}
        with self.assertRaisesRegex(ValueError, 'ZIP.*context'):
            resolve_location('61358', lambda _: payload)

    def test_distance_keeps_precision_at_radius_boundary(self):
        # One degree on the equator is about 69.09 statute miles.
        distance = haversine_miles(0, 0, 0, 1)
        self.assertGreater(distance, 69.09)
        self.assertLess(distance, 69.10)
        self.assertNotEqual(distance, round(distance, 2))
        self.assertEqual(haversine_miles(40, -89, 40, -89), 0)

    def test_territory_never_claims_verified_cross_border_coverage(self):
        result = territory_scope(41.88, -87.63, 100)
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['supported_jurisdictions'], ['IL'])
        self.assertIn('IN', result['unsupported_jurisdictions'])
        self.assertEqual(result['boundary_status'], 'not_evaluated')


if __name__ == '__main__':
    unittest.main()
