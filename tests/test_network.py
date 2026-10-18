import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from backend.network import PublicFetcher, FetchError, UnsafeTargetError, _PinnedBackend


def resolver(host, port, **kwargs):
    return [(2, 1, 6, '', ('93.184.216.34', port))]


class NetworkTests(unittest.TestCase):
    def test_observed_public_dispense_key_is_allowed_only_on_its_api_host(self):
        fetch=self.fetcher(lambda req: httpx.Response(200,json={'key_present':bool(req.headers.get('api-key'))}))
        self.assertTrue(fetch.get('https://api.dispenseapp.com/v1/venues/public/products',headers={'api-key':'public-storefront-key'}).json()['key_present'])
        with self.assertRaises(Exception):fetch.get('https://unrelated.example/menu',headers={'api-key':'public-storefront-key'})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def fetcher(self, handler, **kwargs):
        return PublicFetcher(self.root, resolver=resolver, transport=httpx.MockTransport(handler), sleeper=lambda _: None, **kwargs)

    def test_captures_replayable_response_before_returning(self):
        result = self.fetcher(lambda req: httpx.Response(200, json={'ok': True}, headers={'set-cookie': 'secret=hidden'})).get('https://example.com/catalog')
        self.assertTrue(result.json()['ok'])
        manifest = json.loads((self.root / 'manifests' / (result.evidence_id + '.json')).read_text())
        body = gzip.decompress((self.root / manifest['body_path']).read_bytes())
        self.assertEqual(body, result.body)
        self.assertEqual(hashlib.sha256(body).hexdigest(), manifest['body_sha256'])
        self.assertNotIn('set-cookie', manifest['headers'])

    def test_rejects_unsafe_urls_and_records_failure(self):
        for url in ['file:///etc/passwd', 'http://user:pass@example.com', 'http://127.0.0.1', 'http://[::1]', 'http://169.254.169.254', 'http://example.com:22']:
            with self.subTest(url=url), self.assertRaises(UnsafeTargetError):
                self.fetcher(lambda req: self.fail('unsafe URL fetched')).get(url)
        self.assertEqual(len(list((self.root / 'manifests').glob('*.json'))), 6)

    def test_rejects_private_dns_and_redirect_targets(self):
        blocked = lambda host, port, **kwargs: [(2, 1, 6, '', ('10.0.0.1', port))]
        fetch = PublicFetcher(self.root, resolver=blocked, transport=httpx.MockTransport(lambda req: self.fail('private DNS fetched')))
        with self.assertRaises(UnsafeTargetError):
            fetch.get('https://example.com')
        with self.assertRaises(UnsafeTargetError):
            self.fetcher(lambda req: httpx.Response(302, headers={'location': 'http://127.0.0.1/admin'})).get('https://example.com')

    def test_retries_are_bounded_and_each_attempt_is_preserved(self):
        fetch = self.fetcher(lambda req: httpx.Response(503, content=b'unavailable'), max_attempts=3)
        with self.assertRaises(FetchError) as caught:
            fetch.get('https://example.com')
        manifests = [json.loads(p.read_text()) for p in (self.root / 'manifests').glob('*.json')]
        self.assertEqual(len(manifests), 3)
        self.assertTrue(caught.exception.evidence_id)
        self.assertEqual({m['status_code'] for m in manifests}, {503})
        final = json.loads((self.root / 'manifests' / (caught.exception.evidence_id + '.json')).read_text())
        self.assertEqual(len(final['previous_evidence_ids']), 2)

    def test_redirect_and_response_limits_are_explicit_failures(self):
        with self.assertRaisesRegex(FetchError, 'redirect'):
            self.fetcher(lambda req: httpx.Response(302, headers={'location': '/again'}), max_redirects=1).get('https://example.com')
        with self.assertRaisesRegex(FetchError, 'size'):
            self.fetcher(lambda req: httpx.Response(200, content=b'12345'), max_response_bytes=4).get('https://example.com')

    def test_sensitive_query_values_are_not_diagnostic_metadata(self):
        self.fetcher(lambda req: httpx.Response(200, content=b'ok')).get('https://example.com/?api_key=secretvalue&x-algolia-api-key=publishable-value&store=123')
        text = next((self.root / 'manifests').glob('*.json')).read_text()
        self.assertNotIn('secretvalue', text)
        self.assertNotIn('publishable-value', text)
        self.assertIn('store=123', text)

    def test_connection_uses_validated_ip_instead_of_resolving_hostname_again(self):
        backend = _PinnedBackend(resolver)
        with patch('httpcore.SyncBackend.connect_tcp', return_value=object()) as connect:
            backend.connect_tcp('example.com', 443, timeout=5)
        self.assertEqual(connect.call_args.kwargs['host'], '93.184.216.34')

    def test_public_provider_headers_are_sent_and_secrets_are_refused(self):
        def handler(request):
            return httpx.Response(200, json={'store': request.headers.get('x-store')})
        fetch = self.fetcher(handler)
        result = fetch.get('https://example.com', headers={'X-Store': 'public-store-id', 'Accept': 'application/json'})
        self.assertEqual(result.json()['store'], 'public-store-id')
        with self.assertRaises(ValueError):
            fetch.get('https://example.com', headers={'Authorization': 'Bearer secret'})

    def test_rebinding_to_private_ip_is_rejected_at_connection_time(self):
        def rebound(host, port, **kwargs):
            return [(2, 1, 6, '', ('127.0.0.1', port))]
        backend = _PinnedBackend(rebound)
        with self.assertRaises(UnsafeTargetError):
            backend.connect_tcp('example.com', 443, timeout=5)

    def test_unexpected_secret_response_headers_are_not_persisted(self):
        result = self.fetcher(lambda req: httpx.Response(200, content=b'ok', headers={'X-Api-Key': 'secretvalue', 'X-Session-Token': 'anothersecret', 'Content-Type': 'text/plain'})).get('https://example.com')
        manifest = (self.root / 'manifests' / (result.evidence_id + '.json')).read_text()
        self.assertNotIn('secretvalue', manifest)
        self.assertNotIn('anothersecret', manifest)
        self.assertEqual(result.headers['content-type'], 'text/plain')

    def test_transport_failure_is_preserved_without_losing_prior_capture(self):
        good = self.fetcher(lambda req: httpx.Response(200, content=b'catalog')).get('https://example.com')
        def timeout(req):
            raise httpx.ReadTimeout('https://example.com/?api_key=secretvalue')
        with self.assertRaises(FetchError):
            self.fetcher(timeout, max_attempts=1).get('https://example.com')
        manifests = list((self.root / 'manifests').glob('*.json'))
        self.assertEqual(len(manifests), 2)
        self.assertTrue((self.root / 'manifests' / (good.evidence_id + '.json')).exists())
        self.assertNotIn('secretvalue', ''.join(path.read_text() for path in manifests))

    def test_redirect_following_validates_relative_destination(self):
        def handler(request):
            if request.url.path == '/start':
                return httpx.Response(302, headers={'location': '/catalog'})
            if request.url.path == '/catalog':
                return httpx.Response(200, json={'products': [1, 2]})
            self.fail(f'Unexpected URL {request.url}')
        result = self.fetcher(handler).get('https://example.com/start')
        self.assertEqual(result.json(), {'products': [1, 2]})
        self.assertEqual(result.url, 'https://example.com/catalog')
        self.assertEqual(len(list((self.root / 'manifests').glob('*.json'))), 2)
        final = json.loads((self.root / 'manifests' / (result.evidence_id + '.json')).read_text())
        self.assertEqual(len(final['previous_evidence_ids']), 1)

    def test_read_only_post_supports_only_observed_search_endpoint(self):
        url = 'https://search-kyrok9udlk.gapcommerceapi.com/product/search'
        payload = {'from': 0, 'size': 100, 'track_total_hits': True, 'query': {'bool': {'must': [{'term': {'isHideFromMenu': False}}]}}}
        def handler(request):
            self.assertEqual(request.method, 'POST')
            self.assertEqual(json.loads(request.content), payload)
            self.assertEqual(request.headers['x-api-key'], 'public-publishable-value')
            return httpx.Response(200, json={'hits': {'total': {'value': 0}, 'hits': []}})
        result = self.fetcher(handler).post(url, json=payload, headers={'X-Api-Key': 'public-publishable-value', 'entity-id': 'public-store-id', 'org-id': 'public-org-id'})
        manifest = (self.root / 'manifests' / (result.evidence_id + '.json')).read_text()
        self.assertNotIn('public-publishable-value', manifest)
        self.assertNotIn('public-store-id', manifest)
        self.assertNotIn('public-org-id', manifest)
        self.assertEqual(json.loads(manifest)['method'], 'POST')
        for unsafe in ['https://example.com/product/search', 'https://search-kyrok9udlk.gapcommerceapi.com/orders', 'http://search-kyrok9udlk.gapcommerceapi.com/product/search']:
            with self.subTest(url=unsafe), self.assertRaises(ValueError):
                self.fetcher(lambda _: self.fail('Unapproved POST sent')).post(unsafe, json=payload)

    def test_read_only_post_does_not_follow_redirect_or_leak_header_to_get(self):
        url = 'https://search-kyrok9udlk.gapcommerceapi.com/product/search'
        with self.assertRaises(FetchError):
            self.fetcher(lambda _: httpx.Response(307, headers={'location': 'https://example.com/orders'})).post(url, json={})
        with self.assertRaises(ValueError):
            self.fetcher(lambda _: self.fail('Secret header sent to GET')).get(url, headers={'X-Api-Key': 'public-key'})

    def test_observed_jane_search_post_is_scoped_and_headers_are_redacted(self):
        def handler(request):
            self.assertEqual(request.headers['x-algolia-api-key'], 'public-search-key')
            self.assertEqual(json.loads(request.content)['filters'], 'store_id:2754')
            return httpx.Response(200, json={'hits': [], 'nbHits': 0})
        fetch = self.fetcher(handler)
        for index in ['menu-products-production', 'menu-products-by-price-production']:
            result = fetch.post(f'https://search.iheartjane.com/1/indexes/{index}/query', json={'filters': 'store_id:2754'}, headers={'x-algolia-api-key': 'public-search-key', 'x-algolia-application-id': 'public-app-id'})
            manifest = (self.root / 'manifests' / (result.evidence_id + '.json')).read_text()
            self.assertNotIn('public-search-key', manifest)
        with self.assertRaises(ValueError):
            fetch.post('https://search.iheartjane.com/1/indexes/other-index/query', json={})
        with self.assertRaises(ValueError):
            fetch.post('https://search-kyrok9udlk.gapcommerceapi.com/product/search', json={}, headers={'x-algolia-api-key': 'key'})


if __name__ == '__main__':
    unittest.main()


class BrowserDefaultsTests(unittest.TestCase):
    def render_options(self, saved):
        from unittest.mock import patch
        fetcher=PublicFetcher(Path(tempfile.mkdtemp()))
        fetcher.browser_options=saved
        with patch('backend.browser_render.render') as render:
            fetcher.render('https://example.com/menu')
        return render.call_args.kwargs['options']

    def test_absent_keys_take_the_platform_defaults(self):
        options=self.render_options({'enabled':True})
        self.assertEqual((options['post_policy'],options['user_agent_token']),('platform_reads','TerpScout/1.0'))

    def test_saved_values_and_explicit_null_override_defaults(self):
        options=self.render_options({'post_policy':'strict','user_agent_token':None})
        self.assertEqual((options['post_policy'],options['user_agent_token']),('strict',None))


class ScrollDefaultTests(BrowserDefaultsTests):
    def test_menu_paging_is_on_by_default_and_can_be_disabled(self):
        self.assertTrue(self.render_options({'enabled':True})['scroll_menu'])
        self.assertFalse(self.render_options({'scroll_menu':False})['scroll_menu'])
