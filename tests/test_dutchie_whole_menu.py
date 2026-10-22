"""A Dutchie embed is read through one whole-menu query from the page's own session, and a tunnel that ran out of transfer budget is not reported as an HTTP 403."""
import json
import os
from pathlib import Path
import tempfile
import unittest

import httpx

from backend.failures import FailureCode, classify
from backend.network import FetchResult, PublicFetcher
from backend.providers.generic import fetch, tunnel_budget_exhausted

ENDPOINT = dict(url='https://dutchie.com/embedded-menu/684991b85f1314468afebce7', provider='dutchie', provider_store_id='684991b85f1314468afebce7', license_type='recreational')


class ErrorPageFetcher:
    """The render ended on Chrome's error page; the tunnel had refused connections for lack of byte budget (or for another reason)."""
    browser_options = {}

    def __init__(self, root, tunnel_blocks):
        self.evidence_dir = Path(root)
        (self.evidence_dir / 'browser').mkdir(exist_ok=True)
        self.blocks = tunnel_blocks

    def get(self, url, headers=None):
        return FetchResult(url, 200, b'', {}, 'static', '2026-10-22T09:00:00Z')

    def render(self, url, **options):
        (self.evidence_dir / 'browser' / 'render1.json').write_text(json.dumps({'network_json': [], 'tunnel_blocks': self.blocks}))
        return FetchResult('chrome-error://chromewebdata/', 200, b'', {}, 'render1', '2026-10-22T09:00:00Z')


class TunnelBudgetLabelTests(unittest.TestCase):
    def fetch_message(self, blocks):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch(dict(ENDPOINT), ErrorPageFetcher(tmp, blocks))
        return result['errors'][0]['message']

    def test_a_render_that_ran_out_of_tunnel_budget_says_so(self):
        message = self.fetch_message([dict(host='dutchie.com', port=443, error='Browser tunnel byte budget exceeded')])
        self.assertIn('byte budget exceeded', message)
        self.assertNotIn('403', message)
        self.assertEqual(FailureCode.RESPONSE_TOO_LARGE, classify(message))

    def test_an_error_page_without_a_budget_block_is_still_reported_as_a_refusal(self):
        message = self.fetch_message([dict(host='www.google.com', port=443, error='Browser connection has no validated page request')])
        self.assertIn('refused this browser session', message)
        self.assertEqual(FailureCode.HTTP_REJECTED, classify(message))

    def test_budget_check_reads_the_render_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = ErrorPageFetcher(tmp, [dict(host='assets2.dutchie.com', port=443, error='Browser tunnel byte budget exceeded')])
            response = fetcher.render('https://dutchie.com/x')
            self.assertTrue(tunnel_budget_exhausted(fetcher, response))
            self.assertFalse(tunnel_budget_exhausted(fetcher, FetchResult('https://dutchie.com/x', 200, b'', {}, 'missing', '2026-10-22T09:00:00Z')))


class DutchieServer:
    """A Dutchie-shaped storefront: the home view loads no product query; a category page loads one category's first page;
    the GraphQL endpoint pages a 250-product menu 100 at a time and hides 6 products below their option threshold unless asked not to."""
    TOTAL = 250
    HIDDEN = 6

    def __init__(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qs, urlsplit
        outer = self
        self.pages = []
        self.navigations = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def send(self, body, kind):
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parts = urlsplit(self.path)
                if parts.path == '/graphql':
                    variables = json.loads(parse_qs(parts.query)['variables'][0])
                    filtered = variables['productsFilter']
                    number = variables['page']
                    outer.pages.append(dict(page=number, types=filtered['types'], sort=filtered['sortBy'], remove=filtered['removeProductsBelowOptionThresholds']))
                    start = number * 100
                    rows = list(range(start, min(start + 100, outer.TOTAL)))
                    if filtered['types']:
                        rows = rows[:50]
                    elif filtered['removeProductsBelowOptionThresholds']:
                        rows = [i for i in rows if i % 41 != 40]
                    products = [dict(_id=f'p{i}', Name=f'Flower {i}', Options=['3.5g'], Prices=[30], recPrices=[30], Status='Active', type='Flower', brandName='B') for i in rows]
                    total = 50 if filtered['types'] else outer.TOTAL
                    self.send(json.dumps(dict(data=dict(filteredProducts=dict(products=products, queryInfo=dict(totalCount=total, totalPages=(total + 99) // 100))))).encode(), 'application/json')
                    return
                outer.navigations.append(parts.path)
                if parts.path == '/direct':
                    # This storefront's own home view already loads a whole-menu query, with the default threshold filter on.
                    variables = json.dumps(dict(productsFilter=dict(dispensaryId='d', types=[], strainTypes=[], subcategories=[], Status='Active', sortBy='popularSortIdx', sortDirection=1, isDefaultSort=True, removeProductsBelowOptionThresholds=True), page=0, perPage=100))
                    self.send(('<html><body><main>Menu</main><a href="/products/flower">Flower</a><script>fetch("/graphql?operationName=FilteredProducts&variables="+encodeURIComponent(%s),{headers:{"apollographql-client-name":"Marketplace (production)"}})</script></body></html>' % json.dumps(variables)).encode(), 'text/html')
                elif parts.path.startswith('/products/'):
                    variables = json.dumps(dict(productsFilter=dict(dispensaryId='d', types=['Flower'], strainTypes=[], subcategories=[], Status='Active', sortBy='popular', sortDirection=1, isDefaultSort=True, removeProductsBelowOptionThresholds=True), page=0, perPage=100))
                    self.send(('<html><body><main>Flower</main><script>fetch("/graphql?operationName=FilteredProducts&variables="+encodeURIComponent(%s),{headers:{"apollographql-client-name":"Marketplace (production)"}})</script></body></html>' % json.dumps(variables)).encode(), 'text/html')
                else:
                    self.send(b'<html><body><main>Menu</main><a href="/products/flower">Flower</a><a href="/products/vaporizers">Vaporizers</a><a href="/products/edibles">Edibles</a></body></html>', 'text/html')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@unittest.skipUnless(os.environ.get('TERPSCOUT_BROWSER_TEST') == '1', 'Set TERPSCOUT_BROWSER_TEST=1 for installed Chrome integration')
class WholeMenuReplayTests(unittest.TestCase):
    def test_one_category_page_teaches_the_query_and_the_whole_menu_is_read_without_visiting_the_rest(self):
        import socket
        import threading
        from unittest.mock import patch
        from backend.network_extract import extract_products, load_captured
        site = DutchieServer()
        real_timer = threading.Timer
        try:
            with tempfile.TemporaryDirectory() as folder:
                fetcher = PublicFetcher(Path(folder) / 'evidence', transport=httpx.MockTransport(lambda req: (_ for _ in ()).throw(AssertionError('Native traffic must use the controlled test tunnel'))), resolver=lambda *a, **k: [(2, 1, 6, '', ('93.184.216.34', 80))])
                fetcher.native_browser_allowed = True
                fetcher.browser_options = {'await_menu': True, 'menu_readiness_ms': 300, 'scroll_menu': True}
                try:
                    with patch('backend.browser_proxy.connect_public', side_effect=lambda *a, **k: (socket.create_connection(site.server.server_address, timeout=3), '93.184.216.34')), patch('backend.browser_render.threading.Timer', side_effect=lambda seconds, callback: real_timer(60, callback)):
                        result = fetcher.render('http://example.com/menu')
                    diagnostics = json.loads((Path(folder) / 'evidence/browser' / f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                    replay = diagnostics['scroll']['replay']
                    self.assertTrue(replay['whole'])
                    self.assertEqual(replay['errors'], 0)
                    # Only the first category page was needed to learn the query; no other category was opened.
                    self.assertEqual([p for p in site.navigations if p.startswith('/products/')], ['/products/flower'])
                    whole = [q for q in site.pages if not q['types']]
                    self.assertEqual([q['page'] for q in whole], [0, 1, 2])
                    self.assertTrue(all(q['sort'] == 'name' and q['remove'] is False for q in whole))
                    found = extract_products(load_captured(Path(folder) / 'evidence', result.evidence_id), 'http://example.com/menu')
                    self.assertEqual(found['total'], 250)
                    self.assertEqual(len({i['source_id'] for i in found['items']}), 250)
                finally:
                    fetcher.close()
        finally:
            site.close()


@unittest.skipUnless(os.environ.get('TERPSCOUT_BROWSER_TEST') == '1', 'Set TERPSCOUT_BROWSER_TEST=1 for installed Chrome integration')
class OwnWholeMenuQueryTests(unittest.TestCase):
    def test_a_storefront_whole_menu_query_is_reread_with_below_threshold_rows_so_it_reconciles(self):
        import socket
        import threading
        from unittest.mock import patch
        from backend.network_extract import extract_products, load_captured
        site = DutchieServer()
        real_timer = threading.Timer
        try:
            with tempfile.TemporaryDirectory() as folder:
                fetcher = PublicFetcher(Path(folder) / 'evidence', transport=httpx.MockTransport(lambda req: (_ for _ in ()).throw(AssertionError('Native traffic must use the controlled test tunnel'))), resolver=lambda *a, **k: [(2, 1, 6, '', ('93.184.216.34', 80))])
                fetcher.native_browser_allowed = True
                fetcher.browser_options = {'await_menu': True, 'menu_readiness_ms': 300, 'scroll_menu': True}
                try:
                    with patch('backend.browser_proxy.connect_public', side_effect=lambda *a, **k: (socket.create_connection(site.server.server_address, timeout=3), '93.184.216.34')), patch('backend.browser_render.threading.Timer', side_effect=lambda seconds, callback: real_timer(60, callback)):
                        result = fetcher.render('http://example.com/direct')
                    diagnostics = json.loads((Path(folder) / 'evidence/browser' / f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                    self.assertTrue(diagnostics['scroll']['replay']['whole'])
                    self.assertEqual([p for p in site.navigations if p.startswith('/products/')], [])
                    self.assertEqual([q['page'] for q in site.pages if q['remove'] is False], [0, 1, 2])
                    found = extract_products(load_captured(Path(folder) / 'evidence', result.evidence_id), 'http://example.com/direct')
                    self.assertEqual(len({i['source_id'] for i in found['items']}), 250)
                    self.assertEqual(found['total'], 250)
                finally:
                    fetcher.close()
        finally:
            site.close()


if __name__ == '__main__':
    unittest.main()
