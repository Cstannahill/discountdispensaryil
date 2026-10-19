"""Troubleshooting sampler: render each store's saved menu URL with a per-category page cap and report what came back.

Read-only: writes evidence and a JSON report, never snapshots, offers, endpoints or attempts. A sample that extracts
products from the saved branch is a signal to run the full sync, not an accepted menu.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.network import PublicFetcher
from backend.adapters import fetch_menu
from backend.runtime import configure_worker_stack, PIPELINE_VERSION
from backend.storage import endpoint_from_row


def saved_targets(database, store_ids):
    rows = database.execute('SELECT * FROM live_stores').fetchall()
    stores = {row['id']: dict(row) for row in rows}
    chosen = store_ids or [row['id'] for row in rows]
    targets = []
    for store_id in chosen:
        if store_id not in stores:
            raise SystemExit('Unknown registry store: ' + store_id)
        # Sync refreshes every accepted endpoint, one per license, loaded with its resolution context. Sample that same set;
        # a store with none accepted gets its latest live attempt so troubleshooting still has something to look at.
        endpoints = [endpoint_from_row(row) for row in database.execute(
            "SELECT * FROM live_endpoints WHERE store_id=? AND status!='superseded' ORDER BY last_attempt_at DESC", (store_id,)).fetchall()]
        retained = [endpoint for endpoint in endpoints if endpoint.get('last_success_at')]
        targets.extend((stores[store_id], endpoint) for endpoint in (retained or endpoints[:1]))
    return targets


def sample(store, endpoint, options, root, pages):
    started = time.time()
    fetcher = PublicFetcher(root, max_attempts=1, timeout_seconds=8, max_run_seconds=150)
    fetcher.browser_options = dict(options, await_menu=True, scroll_menu=True, sample_pages=pages, target_store={
        key: store.get(key) for key in ('id', 'name', 'address', 'city', 'state', 'latitude', 'longitude')})
    report = dict(store_id=store['id'], name=store['name'], provider=endpoint['provider'], url=endpoint['url'],
                  license_type=endpoint['license_type'], pages=pages)
    try:
        # The real provider extractor, run on a sampled render. fetch_menu returns a result; nothing is stored.
        result = fetch_menu(dict(endpoint, max_pages=pages), fetcher)
        items = result.get('items') or []
        report.update(items=len(items), declared_total=result.get('expected_count') or result.get('source_count'),
                      complete=result.get('complete'), errors=[e.get('code') for e in result.get('errors') or []][:3])
    except Exception as error:
        report.update(error=str(error)[:200], evidence_id=getattr(error, 'evidence_id', None))
    finally:
        fetcher.close()
    report['seconds'] = round(time.time() - started, 1)
    report['verdict'] = verdict(report)
    return report


def verdict(report):
    if report.get('error'):
        return 'ERROR'
    if not report.get('items'):
        return 'NO_PRODUCTS'
    if any('BRANCH' in str(code) for code in report.get('errors') or []):
        return 'BRANCH_UNPROVEN'
    return 'SAMPLE_PRODUCTS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('store_ids', nargs='*', help='registry store ids; default every store with a saved endpoint')
    parser.add_argument('--pages', type=int, default=1, help='pages per category/query (1 = first page only)')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--output', default='data/sample_report.json')
    args = parser.parse_args()
    configure_worker_stack()
    root = Path('data/evidence')
    with sqlite3.connect('file:terpscout.db?mode=ro', uri=True) as database:
        database.row_factory = sqlite3.Row
        setting = database.execute("SELECT value FROM live_settings WHERE key='browser_options'").fetchone()
        options = json.loads(setting['value']) if setting else dict(enabled=True)
        targets = saved_targets(database, args.store_ids)
    with ThreadPoolExecutor(max_workers=max(1, min(6, args.workers))) as pool:
        results = list(pool.map(lambda target: sample(target[0], target[1], options, root, args.pages), targets))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(pipeline_version=PIPELINE_VERSION, pages=args.pages,
                                      note='Sample only; nothing was accepted or stored.', results=results), indent=2),
                      encoding='utf-8')
    for row in results:
        print(f"{row['verdict']:<18} {row['name'][:30]:<30} {row['provider'] or '':<8} items={row.get('items')} "
              f"declared={row.get('declared_total')} {row['seconds']}s {row.get('error') or ''} {row.get('errors') or ''}")


if __name__ == '__main__':
    main()
