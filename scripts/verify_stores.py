"""Run the store verifier on chosen or eligible registry stores and print each verdict.

Without --write nothing is stored (evidence of the public reads is still saved). With --write each verdict goes to
live_store_verifications and a cited menu/website URL becomes a live_leads row; registry stores are never changed.
Without an LLM key in .env every store reports `not_configured` and no request is made.

  .venv\\Scripts\\python.exe scripts/verify_stores.py <store_id ...>
  .venv\\Scripts\\python.exe scripts/verify_stores.py --eligible --region <region_id> --limit 10 --write
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.network import PublicFetcher
from backend.storage import Store
from backend import verifier


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('store_ids', nargs='*')
    parser.add_argument('--eligible', action='store_true', help='stores whose discovery failed with NO_LEAD, LEAD_UNVERIFIED or BRANCH_MISMATCH')
    parser.add_argument('--region', help='region id for --eligible (default: the active region)')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--db', default='terpscout.db')
    args = parser.parse_args()
    store = Store(args.db, 'data/evidence')
    registry = {row['id']: row for row in store.stores_in_region(args.region)} if args.eligible else {}
    problems = {}
    if args.eligible:
        for row in verifier.eligible(store.stage_report(args.region)['stores']):
            problems[row['store_id']] = f"{row['code']}: {row['detail'] or ''}"[:400]
    chosen = list(dict.fromkeys(args.store_ids + list(problems)))[:args.limit]
    if not chosen:
        raise SystemExit('No stores chosen')
    with store.connection() as conn:
        rows = {row['id']: dict(row) for row in conn.execute('SELECT * FROM live_stores WHERE id IN (%s)' % ','.join('?' * len(chosen)), chosen)}
    config = verifier.load_env()
    llm, limits = verifier.llm_from_config(config), verifier.budgets(config)
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    for store_id in chosen:
        target = rows.get(store_id) or registry.get(store_id)
        if not target:
            print(f'unknown store {store_id}')
            continue
        target['problem'] = problems.get(store_id)
        fetcher = PublicFetcher(Path('data/evidence'), max_attempts=2, timeout_seconds=15, max_run_seconds=limits['seconds'] + 30)
        try:
            record = verifier.verify_store(target, fetcher, llm, limits, spent_today=store.verifier_spend_since(since))
        finally:
            fetcher.close()
        if args.write and record['status'] != 'not_configured':
            store.record_verification(record)
        result = record['result']
        print(f"{record['status']:<15} {record['verdict']:<8} {target['name'][:34]:<34} conf={result.get('confidence')} "
              f"name={result.get('name')} site={result.get('website')} menu={result.get('menu_url')} address={result.get('address')} "
              f"claims={len(record['claims'])} dropped={len(record['dropped'])} steps={record['steps']} usd={record['usd']} {record.get('detail') or ''}")


if __name__ == '__main__':
    main()
