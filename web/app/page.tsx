import LocationControl from './location';
import { parseOrigin } from '@/lib/origin';
import { CATEGORIES, GRADES, LICENSES, queryDeals, regions, type Offer } from '@/lib/deals';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 20;
const ACCENT: Record<string, string> = { concentrate: '#fbbf24', flower: '#34d399', vapes: '#c084fc' };
type Search = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';
const money = (v: string | null | undefined) => (v == null || v === '' ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v)));
const when = (v: string) => new Date(v).toLocaleString('en-US', { timeZone: 'America/Chicago', dateStyle: 'short', timeStyle: 'short' });
const safeUrl = (v?: string | null) => { try { const u = new URL(v ?? ''); return ['https:', 'http:'].includes(u.protocol) ? u.href : undefined; } catch { return undefined; } };

function OfferCard({ o }: { o: Offer }) {
  const href = safeUrl(o.source_url);
  return (
    <article className="rounded-xl border border-slate-700/60 bg-slate-900/90 p-3 space-y-2">
      <div>
        <h3 className="text-xs font-bold text-white">{o.name}</h3>
        <p className="text-[11px] text-slate-400">{o.brand || 'Brand not supplied'} · {o.strain_type || 'Strain not supplied'}{o.flower_grade && o.flower_grade !== 'whole' ? ` · ${o.flower_grade}` : ''}</p>
      </div>
      <div className="flex justify-between items-end">
        <div>
          <p className="text-lg font-bold font-mono">{money(o.price_per_gram)}<span className="text-[10px] text-slate-400">/g</span></p>
          <p className="text-[10px] text-slate-400 font-mono">{money(o.effective_price)} / {o.weight_label || (o.weight_grams ? `${o.weight_grams}g` : 'mass unknown')}{o.thc_pct ? ` · THC ${o.thc_pct}%` : ''}</p>
        </div>
        <span className="badge">{o.completeness === 'B' ? 'unverified total' : o.freshness}</span>
      </div>
      <p className="text-[11px] text-slate-300">{o.store_name} · {o.distance_miles.toFixed(1)} mi · {o.license_type}</p>
      <p className="text-[10px] text-slate-500">Observed {when(o.last_seen_at)}{o.conditional ? ' · Conditional promotion' : ''}</p>
      {href && <a className="text-[11px] text-emerald-400 underline" href={href} target="_blank" rel="noopener noreferrer">View on dispensary menu ↗</a>}
    </article>
  );
}

export default async function Home({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const reg = await regions();
  const regionId = one(sp.region) || reg.active_region_id || reg.items[0]?.id || '';
  const origin = parseOrigin((k) => one(sp[k]) || null);
  const license = LICENSES.includes(one(sp.license) as never) ? one(sp.license) : 'recreational';
  const grade = GRADES.includes(one(sp.grade) as never) ? one(sp.grade) : 'whole';
  const q = one(sp.q).slice(0, 300);
  const stale = one(sp.stale) === '1';
  const unverified = one(sp.unverified) === '1';
  const bogo = one(sp.promo) === 'bogo';
  const cats = CATEGORIES;
  const pages = Object.fromEntries(cats.map((c) => [c, Math.max(1, Number(one(sp[`p_${c}`])) || 1)]));
  const results = await Promise.all(cats.map((category) => queryDeals({
    region_id: regionId, origin: origin ?? undefined, license_type: license, category, q, include_stale: stale, include_unverified: unverified,
    flower_grade: grade, promo: bogo ? 'bogo' : undefined, page: pages[category], page_size: PAGE_SIZE,
  })));
  const base = { ...(origin ? { lat: String(origin.latitude), lon: String(origin.longitude), radius: String(origin.radius_miles), place: origin.label } : { region: regionId }), license, grade, q, stale: stale ? '1' : '', unverified: unverified ? '1' : '', promo: bogo ? 'bogo' : '' };
  const link = (category: string, page: number) => {
    const u = new URLSearchParams();
    Object.entries({ ...base, ...Object.fromEntries(cats.map((c) => [`p_${c}`, c === category ? String(page) : String(pages[c])])) })
      .forEach(([k, v]) => { if (v) u.set(k, v); });
    return `/?${u.toString()}`;
  };
  const region = origin ? { radius_miles: origin.radius_miles, label: origin.label } : reg.items.find((r) => r.id === regionId);

  return (
    <main className="max-w-7xl mx-auto px-3 py-6 space-y-5">
      <header className="flex items-center gap-3">
        <div className="brand-icon">🌿</div>
        <div>
          <h1 className="font-extrabold text-lg leading-tight">TerpScout</h1>
          <p className="text-[11px] text-slate-400">Lowest observed price per gram from full dispensary menu imports · data v{results[0].data_version}</p>
        </div>
      </header>

      <LocationControl active={!!origin} radius={origin?.radius_miles ?? 50} place={region?.label ?? ''} />

      <form method="get" className="glass-card rounded-2xl p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6 items-end">
        {origin
          ? <><input type="hidden" name="lat" value={origin.latitude} /><input type="hidden" name="lon" value={origin.longitude} /><input type="hidden" name="radius" value={origin.radius_miles} /><input type="hidden" name="place" value={origin.label} /></>
          : <input type="hidden" name="region" value={regionId} />}
        <label className="field">License
          <select name="license" defaultValue={license}>{LICENSES.map((l) => <option key={l} value={l}>{l}</option>)}</select>
        </label>
        <label className="field">Flower grade
          <select name="grade" defaultValue={grade}>{GRADES.map((g) => <option key={g} value={g}>{g === 'whole' ? 'whole flower' : g}</option>)}</select>
        </label>
        <label className="field lg:col-span-2">Search
          <input name="q" defaultValue={q} placeholder="product, brand or store" maxLength={300} />
        </label>
        <div className="flex flex-wrap gap-4 text-xs text-slate-300 lg:col-span-4">
          <label className="flex items-center gap-1.5"><input type="checkbox" name="unverified" value="1" defaultChecked={unverified} />Include unverified totals</label>
          <label className="flex items-center gap-1.5"><input type="checkbox" name="stale" value="1" defaultChecked={stale} />Include stale menus</label>
          <label className="flex items-center gap-1.5"><input type="checkbox" name="promo" value="bogo" defaultChecked={bogo} />BOGO promotions only</label>
        </div>
        <button className="btn-primary lg:col-span-2" type="submit">Apply</button>
      </form>

      {region && <p className="text-xs text-slate-400">Showing deals within {region.radius_miles} miles of {region.label}. Prices are pre-tax; menus older than 12 hours are hidden unless included.</p>}

      <div className="grid gap-4 lg:grid-cols-3">
        {cats.map((category, i) => {
          const r = results[i];
          const last = Math.max(1, Math.ceil(r.total / PAGE_SIZE));
          const page = pages[category];
          return (
            <section key={category} className="glass-card rounded-2xl overflow-hidden" style={{ borderColor: `${ACCENT[category]}45` }}>
              <div className="category-art relative h-28" style={{ backgroundImage: `linear-gradient(to top,#020617,rgba(2,6,23,.3)),url('/${category}.jpg')` }}>
                <div className="absolute bottom-3 left-4">
                  <span className="badge uppercase tracking-widest" style={{ color: ACCENT[category] }}>Category 0{i + 1}</span>
                  <h2 className="font-extrabold text-base mt-1 capitalize">{category} {bogo ? 'BOGO' : 'best deals'}</h2>
                </div>
              </div>
              <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 text-[11px] text-slate-400">
                Lowest observed comparable <strong style={{ color: ACCENT[category] }}>price / gram</strong> · {r.total} offers
              </div>
              <div className="p-3 space-y-3">
                {r.items.length === 0
                  ? <p className="text-xs text-slate-400 p-3">No comparable offers for these filters.</p>
                  : r.items.map((o) => <OfferCard key={o.id} o={o} />)}
              </div>
              {r.total > PAGE_SIZE && (
                <nav className="flex justify-between items-center px-4 py-3 border-t border-slate-800 text-xs">
                  {page > 1 ? <a className="btn" href={link(category, page - 1)}>← Prev</a> : <span />}
                  <span className="text-slate-400">Page {page} of {last}</span>
                  {page < last ? <a className="btn" href={link(category, page + 1)}>Next →</a> : <span />}
                </nav>
              )}
            </section>
          );
        })}
      </div>
    </main>
  );
}
