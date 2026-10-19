"""Breadth-first triage: rediscover each store's menu with the current code, then sample one page per category.

Read-only: writes evidence and a JSON report, never endpoints, snapshots, offers or attempts. A store "works" when a
menu target was found and its sample returned products; everything else is grouped by where it stopped.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import collections
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.adapters import fetch_menu, has_menu_contract, resolve_menu
from backend.network import PublicFetcher
from backend.runtime import configure_worker_stack, PIPELINE_VERSION
from backend.storage import Store

KEYS = ('id', 'name', 'address', 'city', 'state', 'latitude', 'longitude')


def triage(store, leads, options, root, pages):
    started = time.time()
    fetcher = PublicFetcher(root, max_attempts=1, timeout_seconds=12, max_run_seconds=240)
    fetcher.browser_options = dict(options, await_menu=True, scroll_menu=True, sample_pages=pages,
                                   target_store={key: store.get(key) for key in KEYS})
    report = dict(store_id=store['id'], name=store['name'], city=store['city'])
    try:
        found = resolve_menu(dict(store, lead_urls=leads) if leads else store, fetcher)
        targets = [t for t in found if not t.get('status') and has_menu_contract(t)]
        report.update(targets=[dict(provider=t['provider'], url=t['url'], store_id=t.get('provider_store_id'), license=t['license_type']) for t in targets][:6],
                      platforms=sorted({p for t in found for p in t.get('platforms') or []}),
                      reason=None if targets else next((t.get('reason') for t in found if t.get('reason')), 'No menu target'))
        # Native readers first: they prove branch and totals; a generic page is the fallback.
        for target in sorted(targets, key=lambda t: t['provider'] == 'generic')[:2]:
            result = fetch_menu(dict(target, max_pages=pages), fetcher)
            sample = dict(provider=target['provider'], url=target['url'], items=len(result.get('items') or []),
                          errors=[e.get('message', '')[:160] for e in result.get('errors') or []][:2])
            report.setdefault('samples', []).append(sample)
            if sample['items']:
                break
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {str(error)[:200]}'
    finally:
        fetcher.close()
    samples = report.get('samples') or []
    report['verdict'] = ('ERROR' if report.get('error') else 'NO_TARGET' if not report.get('targets') else
                         'WORKS' if any(s['items'] for s in samples) else 'TARGET_NO_PRODUCTS')
    report['seconds'] = round(time.time() - started, 1)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', required=True)
    parser.add_argument('store_ids', nargs='*', help='default: every store in the region without an accepted menu')
    parser.add_argument('--all', action='store_true', help='include stores that already have an accepted menu')
    parser.add_argument('--pages', type=int, default=1)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', default='data/triage_report.json')
    args = parser.parse_args()
    configure_worker_stack()
    root = Path('data/evidence')
    store = Store(Path('terpscout.db'), root)
    stores = store.stores_in_region(args.region)
    if args.store_ids:
        stores = [s for s in stores if s['id'] in set(args.store_ids) or s['id'][:8] in set(args.store_ids)]
    elif not args.all:
        stores = [s for s in stores if not any(e.get('last_success_at') for e in s['endpoints'])]
    with sqlite3.connect('file:terpscout.db?mode=ro', uri=True) as database:
        setting = database.execute("SELECT value FROM live_settings WHERE key='browser_options'").fetchone()
        options = json.loads(setting[0]) if setting else dict(enabled=True)
        leads = {s['id']: [row[0] for row in database.execute("SELECT url FROM live_leads WHERE store_id=? AND source='verifier' ORDER BY id", (s['id'],))]
                 for s in stores}
    print(f'triaging {len(stores)} stores with {args.workers} workers', flush=True)

    def run(row):
        result = triage(row, leads[row['id']], options, root, args.pages)
        print(f"{result['verdict']:<18} {result['name'][:32]:<32} {result['seconds']:>6}s "
              f"{(result.get('samples') or [{}])[-1].get('provider') or ''} items={(result.get('samples') or [{}])[-1].get('items')} "
              f"{result.get('reason') or result.get('error') or ''}"[:220], flush=True)
        return result
    with ThreadPoolExecutor(max_workers=max(1, min(6, args.workers))) as pool:
        results = list(pool.map(run, stores))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(pipeline_version=PIPELINE_VERSION, region=args.region, pages=args.pages,
                                      note='Triage only; nothing was accepted or stored.', results=results), indent=1), encoding='utf-8')
    print(dict(collections.Counter(r['verdict'] for r in results)))


if __name__ == '__main__':
    main()
