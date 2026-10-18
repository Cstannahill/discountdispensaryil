"""Generic fetch uses JSON the rendered page loaded, and only claims completeness when totals reconcile."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backend.network import FetchResult
from backend.providers.generic import fetch

ENDPOINT = dict(url='https://shop.example/menu', provider='jane', license_type='recreational')


def api(count, total):
    return {'data': {'products': [dict(id=2000 + i, name=f'Flower {i}', brand={'name': 'B'}, category='Flower', price=20.0 + i, weight=3.5, unit='g', in_stock=True)
                                  for i in range(count)], 'total': total}}


class RenderedFetcher:
    """Static HTML has no products; the render captured one JSON response, retained as evidence."""
    browser_options = {}

    def __init__(self, root, payload, extra_html=''):
        self.evidence_dir = Path(root)
        self.renders = 0
        self.extra_html = extra_html
        body = json.dumps(payload).encode()
        sha = hashlib.sha256(body).hexdigest()
        (self.evidence_dir / 'bodies' / sha[:2]).mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / 'bodies' / sha[:2] / (sha + '.gz')).write_bytes(gzip.compress(body))
        (self.evidence_dir / 'manifests').mkdir(exist_ok=True)
        (self.evidence_dir / 'manifests' / 'api.json').write_text(json.dumps({'body_path': f'bodies/{sha[:2]}/{sha}.gz'}))
        (self.evidence_dir / 'browser').mkdir(exist_ok=True)
        self.entry = {'evidence_id': 'api', 'url': 'https://shop.example/api/products', 'method': 'GET', 'status': 200, 'bytes': len(body)}

    def get(self, url, headers=None):
        return FetchResult(url, 200, b'<h1>Our menu</h1>', {}, 'static', '2026-10-17T09:00:00Z')

    def render(self, url, **options):
        self.renders += 1
        evidence_id = f'render{self.renders}'
        (self.evidence_dir / 'browser' / f'{evidence_id}.json').write_text(json.dumps({'network_json': [self.entry]}))
        return FetchResult(url, 200, ('<h1>Our menu</h1>' + self.extra_html).encode(), {}, evidence_id, '2026-10-17T09:00:00Z')


class GenericNetworkTests(unittest.TestCase):
    def run_fetch(self, payload, extra_html=''):
        with tempfile.TemporaryDirectory() as tmp:
            return fetch(dict(ENDPOINT), RenderedFetcher(tmp, payload, extra_html))

    def test_reconciled_network_total_and_stable_passes_complete_the_menu(self):
        result = self.run_fetch(api(40, 40))
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(len(result['items']), 40)
        self.assertEqual(result['network_collections'][0]['count'], 40)

    def test_declared_total_larger_than_observed_stays_partial_with_items_retained(self):
        result = self.run_fetch(api(40, 759))
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']), 40)
        self.assertIn('does not reconcile', result['errors'][0]['message'])

    def test_no_total_but_matching_visible_counter_is_convergence(self):
        payload = api(40, 40)
        payload['data'].pop('total')
        result = self.run_fetch(payload, '<h2>All 40 products</h2>')
        self.assertFalse(result['complete'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['convergence']['kind'], 'visible_counter')

    def test_no_total_and_no_counter_stays_partial(self):
        payload = api(40, 40)
        payload['data'].pop('total')
        result = self.run_fetch(payload)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']), 40)
        self.assertIn('no independently verifiable', result['errors'][0]['message'])

    def test_non_product_json_is_not_a_menu(self):
        result = self.run_fetch({'events': [{'type': 'view', 'ts': i} for i in range(30)]})
        self.assertFalse(result['complete'])
        self.assertEqual(result['items'], [])


if __name__ == '__main__':
    unittest.main()


class IdentityRenderedFetcher(RenderedFetcher):
    """The render also captured the platform's own dispensary record."""
    def __init__(self, root, payload, street):
        super().__init__(root, payload)
        identity = {'data': {'filteredDispensaries': [{'id': 'd1', 'name': 'Store', 'cName': 'store', 'location': {'ln1': street, 'city': 'East Peoria', 'state': 'IL'}}]}}
        body = json.dumps(identity).encode()
        sha = hashlib.sha256(body).hexdigest()
        (self.evidence_dir / 'bodies' / sha[:2]).mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / 'bodies' / sha[:2] / (sha + '.gz')).write_bytes(gzip.compress(body))
        (self.evidence_dir / 'manifests' / 'identity.json').write_text(json.dumps({'body_path': f'bodies/{sha[:2]}/{sha}.gz'}))
        self.identity_entry = {'evidence_id': 'identity', 'url': 'https://shop.example/graphql?operationName=ConsumerDispensaries', 'method': 'GET', 'status': 200, 'bytes': len(body)}

    def render(self, url, **options):
        result = super().render(url, **options)
        path = self.evidence_dir / 'browser' / f'{result.evidence_id}.json'
        path.write_text(json.dumps({'network_json': [self.entry, self.identity_entry]}))
        return result


class MenuIdentityTests(unittest.TestCase):
    def run_identity(self, street):
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = IdentityRenderedFetcher(tmp, api(40, 40), street)
            fetcher.browser_options = {'target_store': dict(name='Noxx', address='300 S Main St', city='East Peoria', state='IL')}
            return fetch(dict(ENDPOINT, provider='dutchie'), fetcher)

    def test_a_platform_declared_matching_address_allows_the_menu(self):
        result = self.run_identity('300 S Main St')
        self.assertTrue(result['complete'], result['errors'])

    def test_a_menu_declaring_another_branch_address_is_refused_before_any_product_is_kept(self):
        result = self.run_identity('2200 28th St SE')
        self.assertFalse(result['complete'])
        self.assertEqual(result['items'], [])
        self.assertIn('different street address', result['errors'][0]['message'])
