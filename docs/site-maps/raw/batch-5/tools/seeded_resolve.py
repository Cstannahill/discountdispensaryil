"""Scratch (not repo code): run the CURRENT resolve_menu + one-page fetch_menu for a store, seeded with a hand-found URL.
Read-only DB, web search patched out (no LLM spend). Usage: seeded_resolve.py OUT.json WORKERS storeid=url [storeid=url ...]"""
import json, os, sqlite3, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, 'S:/Code/Other/terpscout_fullstack')
import backend.site_discovery as sd
sd.search_websites = lambda store, fetcher, **kw: (setattr(fetcher, '_last_search_attempts', [dict(url=None, error='web search disabled in seeded run')]) or [])
from backend.adapters import fetch_menu, has_menu_contract, resolve_menu
from backend.network import PublicFetcher
from backend.runtime import configure_worker_stack, PIPELINE_VERSION
KEYS = ('id', 'name', 'address', 'city', 'state', 'latitude', 'longitude')
out, workers, pairs = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
configure_worker_stack()
root = Path('S:/Code/Other/terpscout_fullstack/data/evidence')
db = sqlite3.connect('file:S:/Code/Other/terpscout_fullstack/terpscout.db?mode=ro', uri=True); db.row_factory = sqlite3.Row
setting = db.execute("SELECT value FROM live_settings WHERE key='browser_options'").fetchone()
options = json.loads(setting[0]) if setting else dict(enabled=True)
stores = {r['id']: dict(r) for r in db.execute('SELECT * FROM live_stores')}
def run(pair):
    sid, url = pair.split('=', 1)
    store = dict(stores[sid]); store.pop('raw_json', None); store['menu_url'] = url
    t0 = time.time()
    f = PublicFetcher(root, max_attempts=1, timeout_seconds=12, max_run_seconds=240)
    f.sample_run = True
    f.browser_options = dict(options, await_menu=True, scroll_menu=True, sample_pages=1, target_store={k: store.get(k) for k in KEYS})
    rep = dict(store_id=sid, name=store['name'], seed=url)
    try:
        found = resolve_menu(store, f)
        targets = [t for t in found if not t.get('status') and has_menu_contract(t)]
        rep['targets'] = [dict(provider=t['provider'], url=t['url'], provider_store_id=t.get('provider_store_id'), license=t['license_type'], identity=t.get('identity_confidence')) for t in targets][:8]
        rep['platforms'] = sorted({p for t in found for p in t.get('platforms') or []})
        rep['failures'] = [dict(status=t.get('status'), reason=(t.get('reason') or '')[:200], url=(t.get('url') or '')[:120]) for t in found if t.get('status')][:6]
        if not targets and not rep['failures']:
            rep['failures'] = [dict(status='none', reason='resolve_menu returned only targets without contract: ' + json.dumps([dict(p=t.get('provider'), u=t.get('url')) for t in found])[:300])]
        for t in sorted(targets, key=lambda t: t['provider'] == 'generic')[:3]:
            try:
                native = t['provider'] in ('sweed','jane','joint','dispense','blaze','verano')
                r = fetch_menu(dict(t) if (os.environ.get('FULL') and native) else dict(t, max_pages=1), f)
                rep.setdefault('samples', []).append(dict(provider=t['provider'], url=t['url'], items=len(r.get('items') or []), expected=r.get('expected_count') or r.get('source_count'),
                    complete=r.get('complete'), errors=[(e.get('code'), (e.get('message') or '')[:140]) for e in r.get('errors') or []][:2]))
            except Exception as e:
                rep.setdefault('samples', []).append(dict(provider=t['provider'], url=t['url'], error=f'{type(e).__name__}: {str(e)[:200]}'))
    except Exception as e:
        rep['error'] = f'{type(e).__name__}: {str(e)[:250]}'
    finally:
        f.close()
    rep['seconds'] = round(time.time() - t0, 1)
    print(sid[:6], store['name'][:28], '|', 'targets=%s' % [(t['provider'], t['url'][-50:]) for t in rep.get('targets', [])][:2], '| samples=%s' % [(s['provider'], s.get('items'), s.get('error') or s.get('errors')) for s in rep.get('samples', [])][:2], '| fail=%s' % [(x['status'], x['reason'][:70]) for x in rep.get('failures', [])][:2], rep.get('error', ''), rep['seconds'], flush=True)
    return rep
with ThreadPoolExecutor(max_workers=workers) as pool:
    res = list(pool.map(run, pairs))
Path(out).write_text(json.dumps(dict(pipeline_version=PIPELINE_VERSION, results=res), indent=1), encoding='utf-8')
