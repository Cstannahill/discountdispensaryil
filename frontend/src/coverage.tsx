import { extractionMessage } from './extraction-errors';
import type { Coverage, Endpoint } from './api';
import { date } from './api';
import { Status, SourceLink } from './ui';

function EndpointFailures({ endpoints }: { endpoints: Endpoint[] }) {
  const stores = new Map<string, { name: string; issues: Map<string, { text: string; menus: Endpoint[] }> }>();
  for (const endpoint of endpoints) {
    if (!(endpoint.error || endpoint.last_error || endpoint.status === 'failed' || endpoint.latest_attempt_result === 'failed')) continue;
    const key = String(endpoint.store_id ?? endpoint.store_name ?? endpoint.id);
    const store = stores.get(key) ?? { name: endpoint.store_name ?? 'Dispensary', issues: new Map() };
    const text = extractionMessage(endpoint.error || endpoint.last_error || endpoint.latest_attempt_result || endpoint.status);
    const issueKey = JSON.stringify([endpoint.license_type, endpoint.provider, text]);
    const issue = store.issues.get(issueKey) ?? { text, menus: [] };
    issue.menus.push(endpoint); store.issues.set(issueKey, issue); stores.set(key, store);
  }
  if (!stores.size) return null;
  return <details open className="text-xs"><summary className="cursor-pointer text-amber-300">Latest endpoint failures and retained snapshots · {stores.size} stores</summary><ul className="mt-2 space-y-2">{[...stores].map(([key, store]) => <li key={key} className="rounded-lg bg-slate-950 p-3 space-y-2">
    <strong>{store.name}</strong>
    {[...store.issues].map(([issueKey, issue]) => <div key={issueKey} className="space-y-1">
      <p className="text-slate-400">{issue.menus[0].license_type} · {issue.menus[0].provider}{issue.menus.length > 1 ? ` · ${issue.menus.length} targets` : ''}</p>
      <p className="text-amber-200">{issue.text}</p>
      {issue.menus.length === 1 ? <p className="text-slate-500">Last success {date(issue.menus[0].last_success_at)}</p> : <details><summary className="cursor-pointer text-cyan-200">Target details & retained snapshots</summary>{issue.menus.map(menu => <div key={menu.id} className="mt-1 space-y-1"><p>Last success {date(menu.last_success_at)}</p>{menu.url && <SourceLink url={menu.url}/>}</div>)}</details>}
    </div>)}
  </li>)}</ul></details>;
}
export function CoverageSummary({ data }: { data: Coverage }) {
  const c = data.counts;
  return <section className="glass-card rounded-2xl p-4 space-y-3 border-amber-500/20" aria-label="Observed coverage">
    <div className="flex flex-wrap justify-between items-start gap-3"><div><h2 className="text-sm font-bold">Observed coverage · {c.known_stores} registry locations</h2><p className="text-xs text-slate-400 mt-1">Lowest observed comparable prices among covered menus. Discovery can remain incomplete.</p></div><div className="text-right"><strong className="font-mono text-emerald-300">{c.stores_with_fresh_menus ?? c.fresh_menus} / {c.known_stores} stores with fresh accepted menus</strong><p className="text-[10px] text-slate-400">{c.fresh_menus} / {c.menu_endpoints} latest menu imports complete</p>{c.fresh_accepted_snapshots!=null&&<p className="text-[10px] text-slate-400">{c.fresh_accepted_snapshots} fresh accepted snapshots retained independently of latest failures</p>}</div></div>
    <div className="flex flex-wrap gap-2 text-xs"><span className="badge">{c.stale_menus} stale</span><span className="badge">{c.failed_menus} failed</span><span className="badge">{c.unsupported_menus} unsupported</span><span className="badge">{c.unresolved_menus} unresolved</span><span className="badge">{c.products} source products · {c.eligible_offers} eligible offers</span></div>
    <div className="text-[11px] text-slate-400 space-y-1"><p>Registry: <Status value={data.source.status}/> Retrieved {date(data.source.last_success_at)} · Published {date(data.source.published_at)}</p>{data.source.error && <p className="text-amber-200">Latest source refresh: {data.source.error}</p>}<p>{data.territory.message || `Supported registry: ${data.territory.supported_jurisdictions.join(', ') || 'None loaded'}`}{data.territory.unsupported_jurisdictions.length > 0 && ` · Unsupported territory: ${data.territory.unsupported_jurisdictions.join(', ')}`}</p>{data.limitations.map((line, i) => <p key={i}>{line}</p>)}</div>
    <EndpointFailures endpoints={data.endpoints}/>
  </section>;
}
