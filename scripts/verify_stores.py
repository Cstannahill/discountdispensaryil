"""Run the store verifier on chosen or eligible registry stores and print each verdict, then a per-model comparison.

Without --write nothing is stored (evidence of the public reads is still saved). With --write each verdict goes to
live_store_verifications (model, tokens, cost and time included) and a cited menu/website URL becomes a live_leads row;
registry stores are never changed. Without an LLM key in .env every store reports `not_configured` and no request is made.

  .venv\\Scripts\\python.exe scripts/verify_stores.py <store_id ...> --model xiaomi/mimo-v2.6-flash
  .venv\\Scripts\\python.exe scripts/verify_stores.py --eligible --limit 10 --model a/x --model b/y --write   # same stores, each model
  .venv\\Scripts\\python.exe scripts/verify_stores.py --eligible --model all --write   # every TERPSCOUT_LLM_MODELS entry
  .venv\\Scripts\\python.exe scripts/verify_stores.py --compare                         # compare stored verdicts, no new runs
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.network import PublicFetcher
from backend.storage import Store
from backend import verifier, websearch


def print_comparison(summary, names):
    print('\nmodel comparison')
    for model, row in summary['models'].items():
        print(f"  {model:<40} runs={row['runs']} statuses={row['statuses']} verdicts={row['verdicts']} "
              f"claims kept/dropped={row['kept_claims']}/{row['dropped_claims']} leads={row['leads']} "
              f"usd={row['usd']} tokens={row['tokens']} seconds={row['seconds']}")
    for store_id, by_model in summary['disagreements'].items():
        print(f"  disagreement {names.get(store_id, store_id)[:34]}: " + ', '.join(f'{m}={v}' for m, v in by_model.items()))
    if not summary['disagreements']:
        print('  no verified disagreements')


def spent_since(store, since):
    """Verifier spend (stored verdicts, or the ledger when runs were not written) plus website-discovery search spend."""
    folder = Path('data/evidence')
    return max(store.verifier_spend_since(since), verifier.spend_since(folder, since, 'verifier')) + verifier.spend_since(folder, since, 'discovery')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('store_ids', nargs='*')
    parser.add_argument('--eligible', action='store_true', help='stores whose discovery failed with NO_LEAD, LEAD_UNVERIFIED or BRANCH_MISMATCH')
    parser.add_argument('--region', help='region id for --eligible (default: the active region)')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--model', action='append', default=[],
                        help='OpenRouter model id (repeatable or comma separated); "all" = TERPSCOUT_LLM_MODELS; default TERPSCOUT_LLM_MODEL')
    parser.add_argument('--compare', action='store_true', help='only compare stored verdicts (latest per store and model)')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--db', default='terpscout.db')
    args = parser.parse_args()
    store = Store(args.db, 'data/evidence')
    with store.connection() as conn:
        rows = {row['id']: dict(row) for row in conn.execute('SELECT * FROM live_stores')}
    names = {store_id: row['name'] for store_id, row in rows.items()}
    if args.compare:
        stored = store.verifications(per_model=True)
        if args.store_ids:
            stored = [row for row in stored if row['store_id'] in args.store_ids]
        print_comparison(verifier.compare(stored), names)
        return
    problems = {}
    if args.eligible:
        for row in verifier.eligible(store.stage_report(args.region)['stores']):
            problems[row['store_id']] = f"{row['code']}: {row['detail'] or ''}"[:400]
    chosen = [store_id for store_id in dict.fromkeys(args.store_ids + list(problems)) if store_id in rows][:args.limit]
    if not chosen:
        raise SystemExit('No known stores chosen')
    config = verifier.load_env()
    requested = [m.strip() for value in args.model for m in value.split(',') if m.strip()]
    chosen_models = list(dict.fromkeys(m for value in (requested or [config['TERPSCOUT_LLM_MODEL']])
                                       for m in (verifier.models(config) if value == 'all' else [value])))
    limits = verifier.budgets(config)
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    records = []
    for model in chosen_models:
        llm = verifier.llm_from_config(config, model)
        if llm: llm = websearch.configure_search(config, llm)
        for store_id in chosen:
            target = dict(rows[store_id], problem=problems.get(store_id))
            fetcher = PublicFetcher(Path('data/evidence'), max_attempts=2, timeout_seconds=15, max_run_seconds=limits['seconds'] + 30)
            try:
                record = verifier.verify_store(target, fetcher, llm, limits, spent_today=spent_since(store, since), model=model)
            finally:
                fetcher.close()
            records.append(record)
            if args.write and record['status'] not in ('not_configured', 'unsupported_model'):
                store.record_verification(record)
            result = record['result']
            print(f"{model[:32]:<32} {record['status']:<17} {record['verdict']:<8} {target['name'][:30]:<30} conf={result.get('confidence')} "
                  f"name={result.get('name')} site={result.get('website')} menu={result.get('menu_url')} address={result.get('address')} "
                  f"claims={len(record['claims'])} dropped={len(record['dropped'])} steps={record['steps']} usd={record['usd']} "
                  f"s={record.get('seconds')} {record.get('detail') or ''}")
    print_comparison(verifier.compare(records), names)


if __name__ == '__main__':
    main()
