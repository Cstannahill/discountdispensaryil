'use client';
import { useEffect, useState } from 'react';
import { openCalculator } from './calculator';
import { showToast } from './toast';
import { toggleSaveDeal, getSavedDeals, SAVED_EVENT } from './saved-modal';
import { calculateSavings } from '@/lib/calculator';
import { strainBucket, type Offer } from '@/lib/deals';

const BUCKETS = ['Indica', 'Sativa', 'Hybrid', 'Unspecified'] as const;

const BUCKET_BADGE: Record<(typeof BUCKETS)[number], string> = {
  Indica: 'strain-indica',
  Sativa: 'strain-sativa',
  Hybrid: 'strain-hybrid',
  Unspecified: 'strain-unspecified',
};

const money = (v: string | null | undefined) =>
  v == null || v === ''
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

const when = (v: string) =>
  new Date(v).toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    dateStyle: 'short',
    timeStyle: 'short',
  });

const safeUrl = (v?: string | null) => {
  try {
    const u = new URL(v ?? '');
    return ['https:', 'http:'].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
};

function StrainList({ o }: { o: Offer }) {
  const vs = o.variants ?? [];
  return (
    <details className="group rounded-xl bg-slate-950/70 border border-slate-800/90 px-3 py-2 text-xs">
      <summary className="cursor-pointer font-semibold text-emerald-300 flex items-center justify-between select-none">
        <span>🌿 {vs.length} strains at this price — show list</span>
        <span className="text-[10px] text-slate-400 group-open:rotate-180 transition-transform">▾</span>
      </summary>
      <div className="mt-2.5 pt-2 border-t border-slate-800/80 space-y-2.5">
        {BUCKETS.map((b) => {
          const list = vs
            .filter((v) => strainBucket(v.strain_type) === b)
            .sort((x, y) => x.name.localeCompare(y.name));
          if (list.length === 0) return null;
          return (
            <div key={b} className="space-y-1">
              <div className="flex items-center gap-1.5">
                <span className={`badge ${BUCKET_BADGE[b]} uppercase tracking-wider font-sans font-bold`}>
                  {b}
                </span>
                <span className="text-[10px] font-mono text-slate-500">{list.length}</span>
              </div>
              <ul className="grid gap-1 sm:grid-cols-2 lg:grid-cols-1">
                {list.map((v) => {
                  const u = safeUrl(v.source_url);
                  return (
                    <li
                      key={v.id}
                      className="flex items-center justify-between gap-2 rounded-lg bg-slate-900/70 px-2.5 py-1.5 text-[11px]"
                    >
                      {u ? (
                        <a
                          className="text-slate-100 font-medium underline decoration-slate-600 hover:text-emerald-300 truncate"
                          href={u}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {v.name} ↗
                        </a>
                      ) : (
                        <span className="text-slate-200 truncate">{v.name}</span>
                      )}
                      {v.thc_pct && (
                        <span className="text-[10px] font-mono text-slate-400 shrink-0">
                          {v.thc_pct}% THC
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </details>
  );
}

export default function OfferCard({ o, rank }: { o: Offer; rank?: number }) {
  const href = safeUrl(o.source_url);
  const grouped = (o.variants?.length ?? 0) > 1;
  const bucket = strainBucket(o.strain_type);
  const massLabel = o.weight_label || (o.weight_grams ? `${o.weight_grams}g` : 'mass unknown');
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    setIsSaved(getSavedDeals().some((x) => x.id === o.id));

    const onSavedChange = (e: Event) => {
      const detail = (e as CustomEvent<{ id: string | null; saved: boolean }>).detail;
      if (detail?.id === o.id) setIsSaved(detail.saved);
      else if (detail?.id === null) setIsSaved(false);
    };

    window.addEventListener(SAVED_EVENT, onSavedChange);
    return () => window.removeEventListener(SAVED_EVENT, onSavedChange);
  }, [o.id]);

  const savings = calculateSavings(o.regular_price, o.effective_price);

  return (
    <article className="rounded-2xl border border-slate-700/60 hover:border-slate-600/80 bg-slate-900/90 p-3.5 space-y-2.5 transition-colors shadow-sm">
      {/* Top Row: Identity & Hero $/g Metric */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 flex-wrap min-w-0">
              {rank != null && rank <= 3 && (
                <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-extrabold">
                  #{rank}
                </span>
              )}
              <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400/90 truncate">
                {o.brand || 'Brand not supplied'}
              </span>
            </div>

            <button
              type="button"
              onClick={() => {
                const now = toggleSaveDeal({
                  id: o.id,
                  name: grouped ? `${o.brand || 'Offer'} (${massLabel})` : o.name,
                  brand: o.brand,
                  store_name: o.store_name,
                  price_per_gram: o.price_per_gram,
                  effective_price: o.effective_price,
                  regular_price: o.regular_price,
                  massLabel,
                  category: o.category,
                  source_url: href,
                  distance_miles: o.distance_miles,
                  saved_at: Date.now(),
                  weight_grams: o.weight_grams,
                  license_type: o.license_type,
                  flower_grade: o.flower_grade,
                  thc_pct: o.thc_pct,
                });
                setIsSaved(now);
                showToast(now ? 'Deal saved to shortlist! ⭐' : 'Removed from saved deals');
              }}
              className={`px-2 py-0.5 text-xs rounded-lg border transition-colors shrink-0 ${
                isSaved
                  ? 'bg-amber-500/20 text-amber-300 border-amber-400/40 font-bold'
                  : 'bg-slate-950/60 text-slate-400 border-slate-800 hover:text-slate-200'
              }`}
              aria-label={isSaved ? `Remove ${o.name} from saved deals` : `Save ${o.name} to shortlist`}
              title={isSaved ? 'Saved in shortlist' : 'Save deal to shortlist'}
            >
              {isSaved ? '★ Saved' : '☆ Save'}
            </button>
          </div>

          <h3 className="text-sm font-bold text-white leading-snug break-words">
            {grouped ? `${o.brand || 'Assorted'} · ${o.variants!.length} strains` : o.name}
          </h3>

          {/* Badges Row */}
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
            {!grouped && o.strain_type && (
              <span className={`badge ${BUCKET_BADGE[bucket]} font-sans font-semibold`}>
                {o.strain_type}
              </span>
            )}
            {o.flower_grade && o.flower_grade !== 'whole' && (
              <span className="badge bg-amber-500/15 text-amber-200 border-amber-500/30 capitalize font-sans font-medium">
                {o.flower_grade}
              </span>
            )}
            <span className="badge text-slate-200 bg-slate-950/80">{massLabel}</span>
            {!grouped && o.thc_pct && (
              <span className="badge text-slate-300">THC {o.thc_pct}%</span>
            )}
          </div>
        </div>

        {/* Hero Price Box */}
        <div className="text-right shrink-0 bg-slate-950/80 border border-slate-800/90 rounded-xl px-2.5 py-1.5 flex flex-col items-end">
          {savings.hasDiscount && (
            <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-400/50 font-extrabold font-mono mb-1 text-[9px]">
              {savings.savingsPct}% OFF · SAVE {savings.savingsDollars % 1 === 0 ? `$${savings.savingsDollars.toFixed(0)}` : `$${savings.savingsDollars.toFixed(2)}`}
            </span>
          )}
          <p className="text-lg sm:text-xl font-extrabold font-mono text-emerald-400 leading-none">
            {money(o.price_per_gram)}
            <span className="text-[10px] font-normal text-slate-400">/g</span>
          </p>
          <p className="text-[11px] font-mono text-slate-200 mt-1">
            {savings.hasDiscount && (
              <s className="text-slate-500 mr-1 text-[10px]">{money(o.regular_price)}</s>
            )}
            <span className="font-bold">{money(o.effective_price)}</span>
          </p>
        </div>
      </div>

      {/* Store & Observation Metadata */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-800/70 text-xs">
        <div className="flex items-center gap-1.5 min-w-0">
          <a
            href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${o.store_name} dispensary Illinois`)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-slate-200 hover:text-emerald-300 font-semibold truncate hover:underline flex items-center gap-1"
            title={`Open directions to ${o.store_name} in Google Maps`}
          >
            <span aria-hidden="true">📍</span>
            <span className="truncate">{o.store_name}</span>
          </a>
          <span className="badge text-emerald-300 border-emerald-500/30 shrink-0">
            {o.distance_miles.toFixed(1)} mi
          </span>
          <span className="text-[10px] uppercase tracking-wider text-slate-400 shrink-0">
            {o.license_type === 'medicinal' ? 'Med' : 'Rec'}
          </span>
        </div>

        <span
          className={`badge ${
            o.completeness === 'B' || o.freshness !== 'fresh'
              ? 'text-amber-300 border-amber-500/30'
              : 'text-emerald-300 border-emerald-500/30'
          }`}
        >
          {o.completeness === 'B' ? 'unverified total' : o.freshness}
        </span>
      </div>

      <p className="text-[10px] text-slate-400">
        Observed {when(o.last_seen_at)}
        {o.conditional ? ' · Conditional promotion' : ''}
      </p>

      {/* Grouped Strains List */}
      {grouped && <StrainList o={o} />}

      {/* Bottom Action Row: Menu Link + Share + 1-Tap OTD Calculator */}
      <div className="flex items-center gap-2 pt-0.5">
        {href ? (
          <a
            className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 px-3 py-2 text-xs font-bold text-emerald-300 transition-colors"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span>View on dispensary menu</span>
            <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <span className="flex-1 text-[11px] text-slate-500 py-1">Menu link unavailable</span>
        )}

        <button
          type="button"
          onClick={async () => {
            const cardTitle = grouped ? `${o.brand || 'Assorted'} · ${o.variants!.length} strains` : o.name;
            const shareData = {
              title: `TerpScout: ${cardTitle}`,
              text: `${cardTitle} (${massLabel}) at ${o.store_name} for ${money(o.effective_price)} (${money(o.price_per_gram)}/g)`,
              url: href || (typeof window !== 'undefined' ? window.location.href : ''),
            };
            if (typeof navigator !== 'undefined' && navigator.share) {
              try {
                await navigator.share(shareData);
                return;
              } catch (err: unknown) {
                if ((err as Error)?.name === 'AbortError') return;
              }
            }
            try {
              await navigator.clipboard.writeText(`${shareData.text}\n${shareData.url}`);
              showToast('Deal details & link copied to clipboard!');
            } catch {
              showToast('Unable to share deal');
            }
          }}
          className="btn !py-2 !px-2.5 text-slate-300 hover:text-emerald-300 shrink-0"
          aria-label={`Share deal for ${o.name}`}
          title="Share deal with friends"
        >
          <span>↗</span>
          <span className="hidden sm:inline">Share</span>
        </button>

        <button
          type="button"
          onClick={() =>
            openCalculator({
              name: grouped ? `${o.brand || 'Offer'} (${massLabel})` : o.name,
              brand: o.brand,
              store_name: o.store_name,
              price: o.effective_price,
              weight_grams: o.weight_grams,
              category: o.category,
              license_type: o.license_type,
              flower_grade: o.flower_grade,
              thc_pct: o.thc_pct,
            })
          }
          className="btn !py-2 !px-3 text-slate-300 hover:text-emerald-300 shrink-0"
          aria-label={`Estimate Out-The-Door price for ${o.name}`}
          title="Estimate Out-The-Door price with tax & discounts"
        >
          🧮 OTD
        </button>
      </div>
    </article>
  );
}
