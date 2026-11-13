import type { ReactNode } from 'react';
import CategoryGrid, { type CategoryChip } from '../categories';
import CategoryTabs, { CategoryJump } from '../category-tabs';
import DealRow from '../deal-row';
import { offerFacts } from '@/lib/offer-facts';
import AppNav from '../app-nav';
import StoreMap from '../store-map';
import type { MapStore } from '@/lib/store-map';
import { perUnit, unitLabel, type Offer, type Page } from '@/lib/deals';

// The alternative home-page layouts (see lib/layouts.ts). Each one receives the same data the classic layout
// renders and only changes how it is arranged; filters, location and paging are the shared controls.
export interface ViewProps {
  cats: readonly string[];
  results: Page<Offer>[];
  pages: Record<string, number>;
  pageSize: number;
  chips: CategoryChip[];
  accent: Record<string, string>;
  link: (category: string, page: number) => string;
  /** URL that clears every filter, or null when none is set. */
  clearUrl: string | null;
  bogo: boolean;
  placeLabel: string;
  /** Location header, filter strip and the hide-dispensaries control. */
  controls: ReactNode;
  /** "Showing recreational deals within…" line. */
  summary: ReactNode;
}

const money = (v: string | null | undefined) =>
  v == null || v === ''
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

const rankedBy = (category: string) => (category === 'edibles' ? 'price / 10 mg THC' : 'price / gram');

function Empty({ category, clearUrl }: { category: string; clearUrl: string | null }) {
  return (
    <div className="text-center py-8 px-4 space-y-3">
      <p className="text-xs font-semibold text-slate-300">No comparable {category} offers match these filters.</p>
      {clearUrl ? (
        <a href={clearUrl} className="btn-primary !py-1.5 !px-3 text-xs">
          ✕ Clear all filters
        </a>
      ) : (
        <p className="text-[11px] text-slate-500">Try widening your search radius or exploring another category.</p>
      )}
    </div>
  );
}

function Pager({ category, page, total, pageSize, link }: { category: string; page: number; total: number; pageSize: number; link: ViewProps['link'] }) {
  if (total <= pageSize) return null;
  const last = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav aria-label={`${category} pagination`} className="flex justify-between items-center px-3 py-2.5 text-xs">
      {page > 1 ? <a className="btn" href={link(category, page - 1)}>← Prev</a> : <span />}
      <span className="font-mono text-slate-400">Page {page} of {last}</span>
      {page < last ? <a className="btn" href={link(category, page + 1)}>Next →</a> : <span />}
    </nav>
  );
}

function BoardSections(p: ViewProps) {
  return (
      <div id="results">
        <CategoryGrid solo className="space-y-4">
          {p.cats.map((category, i) => {
            const r = p.results[i];
            const page = p.pages[category];
            return (
              <section key={category} data-cat={category} className="glass-card rounded-2xl overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 text-[11px] text-slate-400 border-b border-slate-800/90">
                  <span>
                    <strong className="capitalize" style={{ color: p.accent[category] }}>{category}</strong>
                    {p.bogo ? ' BOGO deals' : ''} · ranked by {rankedBy(category)}
                  </span>
                  <span className="font-mono">{r.total} {r.total === 1 ? 'listing' : 'listings'}</span>
                </div>
                {r.items.length > 0 && (
                  <div className="board-cols hidden lg:grid px-3 py-2 border-b border-slate-800/90 text-[10px] font-bold uppercase tracking-wider text-slate-500" aria-hidden="true">
                    <span>#</span>
                    <span>Product</span>
                    <span>{category === 'edibles' ? 'Dose' : 'Size'}</span>
                    <span>THC</span>
                    <span>Dispensary</span>
                    <span className="text-right">Dist.</span>
                    <span className="text-right">Was</span>
                    <span className="text-right">Price</span>
                    <span className="text-right">$/{unitLabel(category)}</span>
                    <span />
                  </div>
                )}
                {r.items.length === 0 ? (
                  <Empty category={category} clearUrl={p.clearUrl} />
                ) : (
                  r.items.map((o, idx) => <DealRow key={o.id} o={o} variant="board" rank={(page - 1) * p.pageSize + idx + 1} />)
                )}
                <Pager category={category} page={page} total={r.total} pageSize={p.pageSize} link={p.link} />
              </section>
            );
          })}
        </CategoryGrid>
      </div>
  );
}

/** A: dense ranked table, one category at a time. */
export function BoardView(p: ViewProps) {
  return (
    <>
      {p.controls}
      <CategoryTabs chips={p.chips} includeAll />
      <BoardSections {...p} />
      {p.summary}
    </>
  );
}

/** B: light theme, slim cards, bottom tab bar on phones and a side rail on desktop. */
export function AppView(p: ViewProps) {
  return (
    <div className="lg:flex lg:gap-5 lg:items-start">
      <AppNav />
      <div className="min-w-0 flex-1 space-y-3 pb-20 lg:pb-0">
        {p.controls}
        <div className="px-1">
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-white">Cheapest deals near {p.placeLabel}</h2>
        </div>
        <CategoryTabs chips={p.chips} variant="pills" />
        <div id="results">
          <CategoryGrid solo className="space-y-4">
            {p.cats.map((category, i) => {
              const r = p.results[i];
              const page = p.pages[category];
              return (
                <section key={category} data-cat={category}>
                  <p className="px-1 pb-2 text-xs text-slate-400">
                    <strong className="text-slate-200">{r.total}</strong> {category} {r.total === 1 ? 'listing' : 'listings'}{p.bogo ? ' with BOGO' : ''}, ranked by {rankedBy(category)}
                  </p>
                  {r.items.length === 0 ? (
                    <div className="glass-card rounded-2xl"><Empty category={category} clearUrl={p.clearUrl} /></div>
                  ) : (
                    <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3 items-start">
                      {r.items.map((o, idx) => <DealRow key={o.id} o={o} variant="tile" rank={(page - 1) * p.pageSize + idx + 1} />)}
                    </div>
                  )}
                  <Pager category={category} page={page} total={r.total} pageSize={p.pageSize} link={p.link} />
                </section>
              );
            })}
          </CategoryGrid>
        </div>
        {p.summary}
      </div>
    </div>
  );
}

function BestDeal({ category, o, total, accent }: { category: string; o?: Offer; total: number; accent: string }) {
  return (
    <>
      <span className="flex items-center justify-between gap-2 text-[10px] font-extrabold uppercase tracking-widest" style={{ color: accent }}>
        {category}
        <span className="font-semibold normal-case tracking-normal text-slate-400">{total} {total === 1 ? 'listing' : 'listings'}</span>
      </span>
      {o && perUnit(o) ? (
        <>
          <span className="block mt-1.5 font-mono text-2xl font-bold text-white tracking-tight">
            {money(perUnit(o))}
            <span className="text-xs font-medium text-slate-400">/{unitLabel(category)}</span>
          </span>
          <span className="block truncate text-xs font-bold text-slate-100 mt-0.5">{offerFacts(o).title}</span>
          <span className="block truncate text-[11px] text-slate-400">{o.store_name} · {o.distance_miles.toFixed(1)} mi</span>
        </>
      ) : (
        <span className="block mt-2 text-xs text-slate-400">No offers match these filters.</span>
      )}
    </>
  );
}

const tileStyle = (accent: string) => ({
  borderColor: `${accent}40`,
  backgroundImage: `linear-gradient(160deg, ${accent}33, transparent 70%)`,
});

/** C: best price in every category, biggest discounts, then compact lists (four columns on wide screens). */
export function DashboardView(p: ViewProps & { drops: Offer[] }) {
  return (
    <>
      {p.controls}
      <div className="px-1">
        <h2 className="text-lg sm:text-xl font-extrabold tracking-tight text-white">Today&apos;s best prices near {p.placeLabel}</h2>
      </div>

      <div className="grid grid-cols-2 gap-2.5 lg:hidden">
        {p.cats.map((category, i) => (
          <CategoryJump key={category} id={category} className="glass-card min-w-0 rounded-2xl p-3 text-left" style={tileStyle(p.accent[category])}>
            <BestDeal category={category} o={p.results[i].items[0]} total={p.results[i].total} accent={p.accent[category]} />
          </CategoryJump>
        ))}
      </div>

      {p.drops.length > 0 && (
        <section aria-label="Biggest discounts">
          <h3 className="px-1 pb-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">Biggest discounts</h3>
          <div className="flex gap-2.5 overflow-x-auto no-scrollbar">
            {p.drops.map((o) => {
              const f = offerFacts(o);
              const inner = (
                <>
                  <span className="shrink-0 rounded-lg bg-rose-500/20 text-rose-300 px-1.5 py-1.5 font-mono text-xs font-bold">-{f.savings.savingsPct}%</span>
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-bold text-white">{f.title}</span>
                    <span className="block truncate text-[11px] text-slate-400">
                      {money(o.effective_price)} was {money(o.regular_price)} · {o.store_name}
                    </span>
                  </span>
                </>
              );
              const cls = 'glass-card shrink-0 w-60 lg:w-auto lg:flex-1 lg:min-w-0 rounded-xl px-3 py-2.5 flex items-center gap-2.5';
              return o.source_url && /^https?:/.test(o.source_url) ? (
                <a key={o.id} href={o.source_url} target="_blank" rel="noopener noreferrer" className={`${cls} hover:border-slate-600`}>{inner}</a>
              ) : (
                <div key={o.id} className={cls}>{inner}</div>
              );
            })}
          </div>
        </section>
      )}

      <CategoryTabs chips={p.chips} variant="pills" className="lg:hidden" />

      <div id="results">
        <CategoryGrid className="grid gap-3 lg:grid-cols-2 xl:grid-cols-4 items-start">
          {p.cats.map((category, i) => {
            const r = p.results[i];
            const page = p.pages[category];
            return (
              <section key={category} data-cat={category} className="glass-card rounded-2xl overflow-hidden" style={{ borderColor: `${p.accent[category]}40` }}>
                <div className="hidden lg:block p-3 border-b border-slate-800/90" style={{ backgroundImage: tileStyle(p.accent[category]).backgroundImage }}>
                  <BestDeal category={category} o={r.items[0]} total={r.total} accent={p.accent[category]} />
                </div>
                <div className="lg:hidden flex items-center justify-between px-3 py-2 text-[11px] text-slate-400 border-b border-slate-800/90">
                  <span>
                    <strong className="capitalize" style={{ color: p.accent[category] }}>{category}</strong> · ranked by {rankedBy(category)}
                  </span>
                  <span className="font-mono">{r.total}</span>
                </div>
                {r.items.length === 0 ? (
                  <Empty category={category} clearUrl={p.clearUrl} />
                ) : (
                  r.items.map((o, idx) => (
                    <DealRow key={o.id} o={o} variant="compact" accent={p.accent[category]} rank={(page - 1) * p.pageSize + idx + 1} />
                  ))
                )}
                <Pager category={category} page={page} total={r.total} pageSize={p.pageSize} link={p.link} />
              </section>
            );
          })}
        </CategoryGrid>
      </div>
      {p.summary}
    </>
  );
}

/** D: where to go first. A price map and store list on top, the ranked deal table underneath. */
export function MapView(p: ViewProps & { mapStores: Record<string, MapStore[]>; center: { latitude: number; longitude: number } | null; baseQuery: string }) {
  return (
    <>
      {p.controls}
      <CategoryTabs chips={p.chips} variant="pills" />
      {p.center ? (
        <StoreMap byCategory={p.mapStores} origin={p.center} baseQuery={p.baseQuery} />
      ) : (
        <p className="glass-card rounded-2xl px-4 py-8 text-center text-xs text-slate-400">Set a location to see dispensaries on the map.</p>
      )}
      <h2 className="px-1 pt-1 text-sm font-extrabold text-white">All deals in this area</h2>
      <BoardSections {...p} />
      {p.summary}
    </>
  );
}
