"""Replay observed menu URLs with saved settings; capture diagnostics, not snapshots."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.network import PublicFetcher
from backend.runtime import configure_worker_stack, PIPELINE_VERSION
from backend.site_discovery import Page, inspect_page, objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', nargs=2, action='append', required=True,
                        metavar=('STORE_ID', 'OBSERVED_URL'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--readiness-ms', type=int, default=12000)
    parser.add_argument('--post-policy', default=None, choices=('strict', 'platform_reads', 'diagnostic_posts'),
                        help='default: the application default (platform_reads); diagnostic_posts is an experiment arm only')
    parser.add_argument('--websockets', action='store_true', help='diagnostic arm: let the page open WebSockets')
    parser.add_argument('--screenshot', action='store_true', help='save a PNG of the final viewport under data/evidence/browser/')
    parser.add_argument('--user-agent-token', default=None, help='default: the application default (TerpScout/1.0)')
    parser.add_argument('--no-user-agent-token', action='store_true', help='keep the HeadlessChrome token')
    parser.add_argument('--scroll', action='store_true', help='drive infinite scroll / load-more until the menu stops growing')
    parser.add_argument('--scroll-budget-ms', type=int, default=None, help='limit menu paging time')
    args = parser.parse_args()
    configure_worker_stack()
    root = Path('data/evidence')
    with sqlite3.connect('file:terpscout.db?mode=ro', uri=True) as database:
        database.row_factory = sqlite3.Row
        setting = database.execute("SELECT value FROM live_settings WHERE key='browser_options'").fetchone()
        options = json.loads(setting['value']) if setting else dict(enabled=True)
        targets = []
        for store_id, url in args.target:
            row = database.execute('SELECT * FROM live_stores WHERE id=?', (store_id,)).fetchone()
            if row is None:
                parser.error('Unknown registry store: ' + store_id)
            targets.append((dict(row), url))

    def probe(target):
        store, url = target
        fetcher = PublicFetcher(root, max_attempts=1, timeout_seconds=8, max_run_seconds=10)
        fetcher.browser_options = dict(options, await_menu=True, menu_readiness_ms=args.readiness_ms, allow_websockets=args.websockets, diagnostic_screenshot=args.screenshot, scroll_menu=args.scroll, target_store={
            key: store.get(key) for key in ('id', 'name', 'address', 'city', 'state')})
        if args.scroll_budget_ms:
            fetcher.browser_options['scroll_budget_ms'] = args.scroll_budget_ms
        if args.post_policy:
            fetcher.browser_options['post_policy'] = args.post_policy
        if args.no_user_agent_token:
            fetcher.browser_options['user_agent_token'] = None
        elif args.user_agent_token:
            fetcher.browser_options['user_agent_token'] = args.user_agent_token
        result = dict(store_id=store['id'], name=store['name'], url=url)
        evidence_id = None
        try:
            response = fetcher.render(url)
            evidence_id = response.evidence_id
            page = Page(response.body.decode('utf-8', errors='replace'), response.url)
            result.update(status=response.status_code,
                          structured_products=sum(obj.get('@type') == 'Product' for obj in objects(page.structured)),
                          identity_status=inspect_page(store, response)['identity_status'])
        except Exception as error:
            evidence_id = getattr(error, 'evidence_id', None)
            result['error'] = str(error)
        finally:
            fetcher.close()
        result['evidence_id'] = evidence_id
        if evidence_id:
            details = json.loads((root / 'browser' / (evidence_id + '.json')).read_text(encoding='utf-8'))
            for key in ('tunnel_capacity', 'menu_readiness', 'page_errors', 'console_errors',
                        'requests', 'tunnel_blocks', 'blocked_requests', 'request_decisions', 'network_json', 'post_policy', 'age_decisions', 'scroll'):
                result[key] = details.get(key)
            result['response_statuses'] = []
            for key in details.get('request_evidence', []):
                manifest = json.loads((root / 'manifests' / (key + '.json')).read_text(encoding='utf-8'))
                if manifest['status_code'] is None or manifest['status_code'] >= 400:
                    result['response_statuses'].append(dict(url=manifest['url'], status=manifest['status_code'], evidence_id=key))
        return result

    with ThreadPoolExecutor(max_workers=max(1, min(2, args.workers))) as pool:
        results = list(pool.map(probe, targets))
    report = dict(pipeline_version=PIPELINE_VERSION,
                  note='Acquisition probes only; no complete-menu or snapshot acceptance claim.', results=results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps([dict(name=row['name'], status=row.get('status'), error=row.get('error'),
                           structured_products=row.get('structured_products'),
                           tunnel_capacity=row.get('tunnel_capacity')) for row in results], indent=2))


if __name__ == '__main__':
    main()
