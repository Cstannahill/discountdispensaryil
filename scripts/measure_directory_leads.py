"""Measure directory-anchored discovery: how many stores in a stage get a corroborated website lead from Weedmaps.

Read-only for the database: the stage report runs on a private copy, and nothing is written to terpscout.db (no
leads, endpoints, offers or attempts). Directory and website fetches go through PublicFetcher, so their evidence is
recorded under the evidence folder and the directory cache there is reused by later syncs.

A corroborated lead is a listing within backend.directory.MATCH_MILES of the registry coordinates with the same
street number whose detail names a usable retailer website. --inspect also fetches each lead website once (no
browser) and reports the resolver's identity verdict for that page; that is a forecast, not a resolution.
"""
import argparse
import collections
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import directory
from backend.locators import addresses_match
from backend.network import PublicFetcher
from backend.domain import distance_miles
from backend.runtime import PIPELINE_VERSION
from backend.storage import Store

REGION = '8f7772ca082601b630476779'


def stage_stores(database, evidence, region_id, stage):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        copy = Path(folder) / 'copy.sqlite3'
        with closing(sqlite3.connect(f'file:{Path(database).resolve().as_posix()}?mode=ro', uri=True)) as source, closing(sqlite3.connect(copy)) as target:
            source.backup(target)
        store = Store(copy, Path(folder) / 'evidence')
        report = store.stage_report(region_id)
        stores = {row['id']: row for row in store.stores_in_region(region_id)}
        del store
    rows = [row for row in report['stores'] if stage == 'all' or row['stage'] == stage]
    return report, [dict(stores[row['store_id']], stage=row['stage'], code=row['code']) for row in rows]


def offset_listing(store, fetcher):
    """Diagnostic only: a listing at the same full street address beyond the match radius (registry coordinates off)."""
    try:listings = directory.tile_listings(fetcher, store['latitude'], store['longitude'])['listings']
    except Exception:return None
    near = [(distance_miles(store['latitude'], store['longitude'], x['latitude'], x['longitude']), x) for x in listings if x.get('latitude') is not None]
    near = sorted((d, x) for d, x in near if directory.MATCH_MILES < d <= 3 and addresses_match(store['address'], (x.get('address') or '').split(',')[0]))
    if not near:return None
    found = dict(slug=near[0][1]['slug'], address=near[0][1]['address'], distance_miles=round(near[0][0], 2))
    try:found.update(website=directory.website_url(directory.listing_detail(fetcher, found['slug'])['detail'].get('website')))
    except Exception as exc:found.update(error=str(exc))
    return found


def inspect(store, url, fetcher):
    from backend.documents import read_document
    from backend.site_discovery import inspect_page
    try:
        response = read_document(url, fetcher)
        if response.status_code != 200:return dict(url=url, identity='http_' + str(response.status_code))
        found = inspect_page(store, response)
        return dict(url=url, final_url=response.url, identity=found['identity_status'], evidence_id=response.evidence_id,
                    addresses=[a.get('streetAddress') for a in found['addresses']][:3])
    except Exception as exc:
        return dict(url=url, identity='failed', error=str(exc)[:200], evidence_id=getattr(exc, 'evidence_id', None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='terpscout.db')
    parser.add_argument('--evidence', default='data/evidence')
    parser.add_argument('--region', default=REGION)
    parser.add_argument('--stage', default='discovery_failed', help="stage from the stage report, or 'all'")
    parser.add_argument('--inspect', action='store_true', help='fetch each lead website once and report its identity verdict')
    parser.add_argument('--output', default='data/directory_leads_report.json')
    args = parser.parse_args()
    report, stores = stage_stores(args.db, args.evidence, args.region, args.stage)
    fetcher = PublicFetcher(Path(args.evidence), max_attempts=2, timeout_seconds=15, max_run_seconds=60)
    fetcher.browser_options = dict(enabled=False)
    rows = []
    for store in stores:
        found = directory.lookup(store, fetcher)
        row = dict(store_id=store['id'], name=store['name'], address=store['address'], city=store['city'], stage=store['stage'], code=store['code'],
                   status=found['status'], leads=[lead['url'] for lead in found['leads']], error=found.get('error'),
                   matches=[{key: x.get(key) for key in ('slug', 'name', 'address', 'distance_miles', 'website', 'license_number', 'license_type', 'menu_items_count')} for x in found['matches']],
                   near_misses=[{key: x.get(key) for key in ('slug', 'name', 'address', 'distance_miles')} for x in found['rejected']])
        if found['status'] in ('unmatched', 'skipped'):row['same_address_beyond_radius'] = offset_listing(store, fetcher)
        if args.inspect:row['inspected'] = [inspect(store, url, fetcher) for url in row['leads']]
        rows.append(row)
        print(f"{row['status']:<10} {store['name'][:38]:<38} {(row['leads'] or [''])[0][:48]:<48} "
              + (' '.join(x['identity'] for x in row.get('inspected', [])) or (row['error'] or '')[:60]))
    statuses = collections.Counter(row['status'] for row in rows)
    summary = dict(region=args.region, stage=args.stage, stores=len(rows), by_status=dict(statuses),
                   corroborated_website_leads=sum(bool(row['leads']) for row in rows),
                   listing_without_usable_website=statuses.get('no_website', 0),
                   rejected_near_misses=sum(bool(row['near_misses']) and row['status'] == 'unmatched' for row in rows),
                   same_address_beyond_radius=sum(bool(row.get('same_address_beyond_radius')) for row in rows),
                   same_address_beyond_radius_with_website=sum(bool((row.get('same_address_beyond_radius') or {}).get('website')) for row in rows))
    if args.inspect:
        summary['lead_identity'] = dict(collections.Counter(max((x['identity'] for x in row['inspected']), key=lambda v: v in ('matched', 'name_locality'))
                                                            for row in rows if row.get('inspected')))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(pipeline_version=PIPELINE_VERSION, stage_report=report['by_stage'], match_miles=directory.MATCH_MILES,
                                      note='Read-only measurement; directory results are leads, never menus.', summary=summary, stores=rows), indent=2),
                      encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
