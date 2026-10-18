"""Read-only public adapter probe, saving full snapshots and raw fetch evidence."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.adapters import resolve_menu, fetch_menu
from backend.network import PublicFetcher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--output', default='tests/fixtures/provider_live')
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    fetcher = PublicFetcher(out / 'evidence')
    endpoints = resolve_menu({'menu_url': args.url}, fetcher)
    results = []
    for endpoint in endpoints:
        result = fetch_menu(endpoint, fetcher)
        results.append({'endpoint': endpoint, 'snapshot': result})
        print(json.dumps({'endpoint': endpoint, 'complete': result['complete'], 'count': len(result['items']), 'expected_count': result['expected_count'], 'pages': len(result['pages']), 'errors': result['errors']}, ensure_ascii=True))
    (out / 'snapshot.json').write_text(json.dumps(results, indent=2, ensure_ascii=True), encoding='utf-8')


if __name__ == '__main__':
    main()
