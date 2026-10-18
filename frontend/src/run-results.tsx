import { Status, SourceLink } from './ui';
import { extractionMessage } from './extraction-errors';

type Event = Record<string, unknown>;
function message(value: unknown): string {
  return extractionMessage(value);
}
function issues(event: Event) {
  return [...new Set([event.error, event.reason, event.message, ...(Array.isArray(event.errors) ? event.errors : [])].map(message).filter(Boolean))];
}
function StageEvent({ event }: { event: Event }) {
  const stage = String(event.stage ?? 'observation').replaceAll('_', ' ');
  return <div className="border-t border-slate-800 pt-2 space-y-1">
    <p className="text-slate-300">{stage} · {String(event.license_type ?? 'license not recorded')} {event.provider ? `· ${event.provider}` : ''} · <Status value={String(event.status ?? 'recorded')} /></p>
    {event.source_count != null && <p>{String(event.source_count)} observed records</p>}
    {event.page != null && <p>Page {String(event.page)} · verification pass {String(event.traversal)}{Number(event.page_recheck) > 0 ? ` · overlap recheck ${String(event.page_recheck)}` : ''} · {String(event.observed_variants)} observed variants</p>}
    {issues(event).map(issue => <p key={issue} className="text-amber-200">{issue}</p>)}
    {typeof event.url === 'string' && <SourceLink url={event.url} />}
    {typeof event.endpoint_id === 'string' && <p className="text-slate-500 break-all">Menu {event.endpoint_id}</p>}
  </div>;
}

export function RunResults({ results, running = false }: { results: unknown[]; running?: boolean }) {
  const groups = new Map<string, { name: string; events: Event[] }>();
  const global: unknown[] = [];
  for (const value of results) {
    if (!value || typeof value !== 'object') { global.push(value); continue; }
    const event = value as Event;
    const key = event.store_id ?? event.store_name;
    if (!key) { global.push(event); continue; }
    const group = groups.get(String(key)) ?? { name: String(event.store_name ?? key), events: [] };
    group.events.push(event); groups.set(String(key), group);
  }
  return <div className="space-y-3">
    {global.map((value, index) => {
      if (typeof value === 'string') return <p key={index}>{value}</p>;
      if (!value || typeof value !== 'object') return null;
      const event = value as Event;
      return <div key={index} className="bg-slate-950 rounded-lg p-3 text-xs"><p>{event.stage === 'discovery' ? 'Registry refresh' : String(event.stage ?? 'Run event')} · <Status value={String(event.status ?? 'recorded')} /></p>{issues(event).map(issue => <p key={issue}>{issue}</p>)}</div>;
    })}
    {[...groups].map(([key, group]) => {
      const summary = [...group.events].reverse().find(event => event.stage === 'store_summary');
      const stages = group.events.filter(event => event.stage !== 'store_summary');
      const status = String(summary?.status ?? (running ? 'running' : stages.at(-1)?.status ?? 'recorded'));
      const menus = stages.filter(event => event.stage === 'menu');
      const progress = [...stages].reverse().find(event => event.stage === 'menu_progress');
      const channels = new Map<string, { menu: Event; count: number }>();
      for (const menu of menus) {
        const channel = `${menu.license_type}:${menu.provider}:${menu.status}`;
        const grouped = channels.get(channel) ?? { menu, count: 0 };
        grouped.count++; channels.set(channel, grouped);
      }
      const problems = [...new Set(stages.flatMap(issues).concat(summary ? issues(summary) : []))];
      return <article key={key} className="bg-slate-950 rounded-lg p-3 text-xs space-y-2">
        <h3 className="font-semibold">{group.name} · <Status value={status} /></h3>
        {progress?.status === 'running' && <p className="text-cyan-200">Page {String(progress.page)} · verification pass {String(progress.traversal)}{Number(progress.page_recheck) > 0 ? ` · overlap recheck ${String(progress.page_recheck)}` : ''} · {String(progress.observed_variants)} observed variants · source total {String(progress.advertised_total)}</p>}
        {summary && <p className="text-slate-400">{String(summary.menu_targets_attempted ?? menus.length)} menu targets attempted · {String(summary.accepted_snapshots ?? 0)} accepted snapshots</p>}
        {channels.size > 0 && <div className="flex flex-wrap gap-2">{[...channels].map(([channel, {menu, count}]) => <span key={channel} className="text-slate-300">{String(menu.license_type ?? 'License not recorded')} · {String(menu.provider ?? 'menu')} · <Status value={String(menu.status ?? 'recorded')} />{count > 1 ? ` (${count} targets)` : typeof menu.source_count === 'number' ? ` · ${menu.source_count} observed records` : ''}</span>)}</div>}
        {problems.slice(0, 3).map(issue => <p key={issue} className="text-amber-200">{issue}</p>)}
        <details><summary className="cursor-pointer text-cyan-200">Stage details ({stages.length})</summary><div className="space-y-2 mt-2">{stages.map((event, index) => <StageEvent key={index} event={event} />)}</div></details>
      </article>;
    })}
  </div>;
}
