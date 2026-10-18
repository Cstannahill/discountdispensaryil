"""Read-only, evidence-capturing public source research. No access challenge bypass."""
import argparse
import gzip
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.network import PublicFetcher, FetchError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*')
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--inspect-evidence')
    parser.add_argument('--jane-store', type=int)
    parser.add_argument('--cloud-details', action='store_true')
    parser.add_argument('--branch-details', action='store_true')
    args = parser.parse_args()
    if args.branch_details:
        text = Path('tests/fixtures/provider_probe/beyond.txt').read_text(encoding='utf-8')
        for term in ['Keaton', '"title":"Bloomington', '"title":"Normal', '"title":"Peoria', '2754', 'bloomington']:
            print(term, [text[max(0, m.start()-100):m.start()+1600] for m in list(re.finditer(re.escape(term), text))[:3]])
        return
    if args.cloud_details:
        text = Path('tests/fixtures/provider_probe/cloud.txt').read_text(encoding='utf-8')
        for term in ['apiPath:"p/ordering_apps', 'ordering_apps/op', 'ordering_app_id=n', '/p/ordering_apps']:
            print(term, [text[max(0, m.start()-120):m.start()+260] for m in list(re.finditer(re.escape(term), text))[:20]])
        return
    if args.jane_store:
        text = Path('tests/fixtures/provider_probe/beyond.txt').read_text(encoding='utf-8')
        settings = json.loads(re.search(r'<script id="jane-app-settings"[^>]*>(.*?)</script>', text, re.S)[1])
        public_settings = json.loads(re.search(r'<script id="jane-app-secrets"[^>]*>(.*?)</script>', text, re.S)[1])
        root = Path('data/evidence/jane-research')
        fetcher = PublicFetcher(root, max_attempts=1, timeout_seconds=20)
        url = 'https://search.iheartjane.com/1/indexes/menu-products-production/query'
        payload = {'query': '', 'filters': f'store_id:{args.jane_store}', 'hitsPerPage': 100, 'page': 0}
        try:
            response = fetcher.post(url, json=payload, headers={'x-algolia-api-key': public_settings['algoliaApiKey'], 'x-algolia-application-id': settings['algoliaAppId']})
            data = response.json()
            print(json.dumps({'url': response.url, 'status': response.status_code, 'bytes': len(response.body), 'evidence_id': response.evidence_id,
                              'counts': {key: data.get(key) for key in ['nbHits', 'nbPages', 'hitsPerPage', 'page', 'exhaustiveNbHits', 'exhaustive']},
                              'products': [{key: item.get(key) for key in ['objectID', 'product_id', 'store_id', 'name', 'kind', 'root_types', 'price_each', 'price_gram', 'net_weight_grams']} for item in data.get('hits', [])[:2]]}))
        except FetchError as exc:
            print(json.dumps({'url': url, 'error': str(exc), 'evidence_id': exc.evidence_id}))
        fetcher.close()
        return
    if args.inspect_evidence:
        root = Path('data/evidence/jane-research')
        manifest = json.loads((root / 'manifests' / (args.inspect_evidence + '.json')).read_text())
        text = gzip.decompress((root / manifest['body_path']).read_bytes()).decode('utf-8', errors='replace')
        print('imports', list(dict.fromkeys(re.findall(r'["\x27`]([^"\x27`\s]+\.js)["\x27`]', text)))[:80])
        print('script IDs', re.findall(r'<script[^>]*id=["\x27]([^"\x27]+)', text))
        for term in ['menu_products', 'menu-products', '/stores/', '/menu', 'apiPath', 'Algolia', 'algolia', 'facetFilters', 'store_id', 'hitsPerPage', 'searchClient', 'search.iheartjane.com', 'filters:', 'getInventory', 'store-inventory-breakdown']:
            print(term, [text[max(0, m.start()-70):m.start()+180] for m in list(re.finditer(re.escape(term), text))[:6]])
        return
    if args.inspect:
        base = Path('tests/fixtures/provider_probe')
        for filename, terms in [('beyond.txt', ['jane-app-settings', 'storeId']), ('janejs.txt', ['menu_products', 'menu-products', '/stores/', 'algolia', 'apiPath']), ('cloud.txt', ['store-inventory-breakdown', 'store-inventory', 'api.crescolabs.com'])]:
            text = (base / filename).read_text(encoding='utf-8')
            print(filename)
            if filename == 'janejs.txt':
                print('imports', list(dict.fromkeys(re.findall(r'["\x27`]([^"\x27`\s]+\.js)["\x27`]', text)))[:80])
            if filename == 'beyond.txt':
                print('scripts', re.findall(r'<script[^>]+src=["\x27]([^"\x27]+)', text)[-20:])
            for term in terms:
                print(term, [text[max(0, m.start()-100):m.start()+160] for m in list(re.finditer(re.escape(term), text))[:5]])
        return
    root = Path('data/evidence/jane-research')
    fetcher = PublicFetcher(root, max_attempts=1, timeout_seconds=20)
    for url in args.urls:
        try:
            response = fetcher.get(url)
            print(json.dumps({'url': response.url, 'status': response.status_code, 'bytes': len(response.body), 'evidence_id': response.evidence_id, 'content_type': response.headers.get('content-type')}))
            try:
                data = response.json()
                print('JSON', list(data)[:30] if isinstance(data, dict) else f'list[{len(data)}]')
            except ValueError:
                text = response.body.decode('utf-8', errors='replace')
                print('scripts', re.findall(r'<script[^>]+src=["\x27]([^"\x27]+)', text)[-15:])
                print('Jane IDs', list(dict.fromkeys(re.findall(r'(?:storeId["\x27]?\s*:\s*|/embed/stores/|/stores/)(\d+)', text)))[:15])
        except FetchError as exc:
            print(json.dumps({'url': url, 'error': str(exc), 'evidence_id': exc.evidence_id}))
    fetcher.close()


if __name__ == '__main__':
    main()
