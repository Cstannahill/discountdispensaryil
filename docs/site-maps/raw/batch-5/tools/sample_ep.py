"""Sample specific saved endpoints (read-only, same code path as scripts/sample_stores.py). usage: sample_ep.py <endpoint_id>..."""
import sys,json,sqlite3,time
from pathlib import Path
sys.path.insert(0,'S:/Code/Other/terpscout_fullstack')
from backend.network import PublicFetcher
from backend.adapters import fetch_menu
from backend.runtime import configure_worker_stack
configure_worker_stack()
root=Path('S:/Code/Other/terpscout_fullstack/data/evidence')
db=sqlite3.connect('file:S:/Code/Other/terpscout_fullstack/terpscout.db?mode=ro',uri=True); db.row_factory=sqlite3.Row
setting=db.execute("SELECT value FROM live_settings WHERE key='browser_options'").fetchone()
options=json.loads(setting['value']) if setting else dict(enabled=True)
out=[]
for eid in sys.argv[1:]:
    row=dict(db.execute("select * from live_endpoints where id=?",(eid,)).fetchone()); ep=json.loads(row.get('resolution_json') or '{}'); ep.update(row); st=dict(db.execute("select * from live_stores where id=?",(ep['store_id'],)).fetchone())
    f=PublicFetcher(root,max_attempts=1,timeout_seconds=8,max_run_seconds=150)
    f.browser_options=dict(options,await_menu=True,scroll_menu=True,sample_pages=1,target_store={k:st.get(k) for k in ('id','name','address','city','state','latitude','longitude')})
    t=time.time(); rep=dict(endpoint_id=eid,store=st['name'],provider=ep['provider'],license=ep['license_type'],psid=ep['provider_store_id'],url=ep['url'][:120])
    try:
        r=fetch_menu(dict(ep,max_pages=1),f); items=r.get('items') or []
        rep.update(items=len(items),declared=r.get('expected_count') or r.get('source_count'),complete=r.get('complete'),errors=[(e.get('code'),str(e.get('message') or e.get('detail') or '')[:160]) for e in r.get('errors') or []][:4],keys=sorted(k for k in r.keys())[:14])
    except Exception as e: rep['exc']=str(e)[:200]
    finally: f.close()
    rep['sec']=round(time.time()-t,1); out.append(rep); print(json.dumps(rep),flush=True)
