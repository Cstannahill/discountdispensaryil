"""Search every missing retailer brand in a saved region; retain leads and evidence.

This is website discovery, not a claim that the resulting menus are imported.
Positive searches persist for reuse by normal application syncs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.storage import Store
from backend.network import PublicFetcher
from backend.locators import CONNECTORS
from backend.site_discovery import search_websites


def main():
    from backend.runtime import configure_worker_stack
    configure_worker_stack()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region-id',required=True)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--output',default='data/regional-website-discovery.json')
    parser.add_argument('--inspect',action='store_true',help='Inspect branch pages and menu platforms after search; does not import inventory')
    parser.add_argument('--max-stores',type=int,default=0,help='Bound one resumable inspection batch; zero processes all remaining stores')
    args=parser.parse_args()
    store=Store(Path('terpscout.db'),Path('data/evidence'))
    rows=store.stores_in_region(args.region_id)
    missing=[s for s in rows if not any(re.search(pattern,re.sub(r"[’']",'',s['name']),re.I) for pattern,url in CONNECTORS)]
    target=Path(args.output)
    resumed=json.loads(target.read_text(encoding='utf-8')).get('results',[]) if args.inspect and target.exists() else []
    completed={r['store_id'] for r in resumed}
    pending=[row for row in missing if row['id'] not in completed]
    if args.max_stores:pending=pending[:args.max_stores]
    lock=threading.Lock();progress=[len(resumed)];local=threading.local();fetchers=[];checkpoint=list(resumed)
    def save(status):
        report=dict(checked_at=datetime.now(timezone.utc).isoformat(),region=store.region(args.region_id),regional_stores=len(rows),
                    searched_stores=len(checkpoint),target_stores=len(missing),status=status,
                    stores_with_candidates=sum(bool(r['candidates']) for r in checkpoint),
                    stores_without_candidates=sum(not r['candidates'] for r in checkpoint),results=checkpoint)
        temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        temporary.replace(target)
        return report
    def search(row):
        if not getattr(local,'fetcher',None):
            local.fetcher=PublicFetcher(Path('data/evidence'),max_attempts=1,timeout_seconds=8,max_run_seconds=10)
            with lock:fetchers.append(local.fetcher)
        candidates=search_websites(row,local.fetcher)
        result=dict(store_id=row['id'],name=row['name'],city=row['city'],candidates=candidates,
                    status='website_candidates_found' if candidates else 'search_unresolved',
                    attempts=getattr(local.fetcher,'_last_search_attempts',[]))
        if args.inspect and candidates:
            try:
                from backend.adapters import resolve_menu
                result['endpoints']=resolve_menu(dict(row,max_discovery_pages=4),local.fetcher)
            except Exception as exc:
                result['inspection_error']=str(exc)
        with lock:
            progress[0]+=1
            checkpoint.append(result)
            save('running')
            if progress[0]%10==0 or progress[0]==len(missing):print(f"Searched {progress[0]}/{len(missing)} previously unconfigured stores",flush=True)
        return result
    try:
        with ThreadPoolExecutor(max_workers=max(1,min(4,args.workers))) as pool:list(pool.map(search,pending))
    finally:
        for fetcher in fetchers:fetcher.close()
    report=save('complete' if len(checkpoint)==len(missing) else 'batch_complete')
    print(json.dumps({k:v for k,v in report.items() if k not in ('region','results')}),flush=True)


if __name__=='__main__':main()
