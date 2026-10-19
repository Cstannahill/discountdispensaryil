"""Backfill the platform census from retained evidence and print it by stage.

Reads each regional store's resolution, endpoint, lead and attempt evidence (page bodies and browser network URLs),
detects menu platforms with backend.platforms, and with --write records them in live_store_platforms. Search-engine
and directory pages are skipped; pages from wrong-branch resolutions keep status identity_conflict.
Never creates endpoints, offers or attempts.
"""
import argparse
import collections
import gzip
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.platforms import detect
from backend.site_discovery import is_directory_url
from backend.storage import Store

SEARCH_HOSTS = re.compile(r'(?:^|\.)(?:bing\.com|duckduckgo\.com|google\.[a-z.]+|yahoo\.com|search\.brave\.com|openrouter\.ai)$')
EVIDENCE_ID = re.compile(r'"evidence_id":\s*"([0-9a-f]{40,64})"')


def evidence_text(root, evidence_id):
    """(url, text) for a retained page or browser render; text is None for search/directory pages or missing bodies."""
    try:
        manifest = json.loads((root / 'manifests' / f'{evidence_id}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None, None
    url = manifest.get('url') or ''
    if SEARCH_HOSTS.search(urlsplit(url).hostname or '') or is_directory_url(url):
        return url, None
    parts = []
    try:
        parts.append(gzip.decompress((root / manifest['body_path']).read_bytes())[:3_000_000].decode('utf-8', 'replace'))
    except (OSError, KeyError, EOFError):
        pass
    try:
        browser = json.loads((root / 'browser' / f'{evidence_id}.json').read_text(encoding='utf-8'))
        parts.append(' '.join(entry.get('url', '') for entry in browser.get('network_json') or []))
    except (OSError, ValueError):
        pass
    return url, ' '.join(parts) or None


def observations(conn, store_id):
    """(evidence_id, status) pairs from everything recorded for the store."""
    found = {}
    for status, evidence in conn.execute('SELECT status, evidence_json FROM live_resolutions WHERE store_id=?', (store_id,)):
        mapped = 'identity_conflict' if status == 'identity_conflict' else 'observed' if status == 'matched' else 'evidence'
        for evidence_id in EVIDENCE_ID.findall(evidence or ''):
            found.setdefault(evidence_id, mapped)
    for (evidence,) in conn.execute("SELECT resolution_json FROM live_endpoints WHERE store_id=? AND status!='superseded'", (store_id,)):
        for evidence_id in EVIDENCE_ID.findall(evidence or ''):
            found[evidence_id] = 'observed'
    for (evidence,) in conn.execute('SELECT evidence_json FROM live_leads WHERE store_id=?', (store_id,)):
        for evidence_id in EVIDENCE_ID.findall(evidence or ''):
            found.setdefault(evidence_id, 'evidence')
    for (evidence_id,) in conn.execute('SELECT evidence_id FROM live_attempts WHERE store_id=? AND evidence_id IS NOT NULL', (store_id,)):
        found.setdefault(evidence_id, 'observed')
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', required=True, help='region id')
    parser.add_argument('--write', action='store_true', help='record observations in live_store_platforms')
    parser.add_argument('--per-store', type=int, default=60, help='evidence items read per store')
    args = parser.parse_args()
    store = Store(Path('terpscout.db'), Path('data/evidence'))
    root = Path('data/evidence')
    for shop in store.stores_in_region(args.region):
        rows = []
        with store.connection() as conn:
            found = observations(conn, shop['id'])
        for evidence_id, status in list(found.items())[:args.per_store]:
            url, text = evidence_text(root, evidence_id)
            for platform in detect(text):
                rows.append(dict(platform=platform, url=url or '', status=status, evidence_id=evidence_id))
        if args.write and rows:
            store.record_platforms(shop['id'], rows, source='evidence_backfill')
    report = store.stage_report(args.region)
    print('stores', report['total_stores'], 'by stage', report['by_stage'])
    for platform, counts in sorted(report['by_platform'].items(), key=lambda kv: -sum(kv[1].values())):
        print(f'{platform:10} {sum(counts.values()):4}  {counts}')
    unplaced = collections.Counter(row['stage'] for row in report['stores'] if not row['platforms'])
    print('no platform observed:', dict(unplaced))


if __name__ == '__main__':
    main()
