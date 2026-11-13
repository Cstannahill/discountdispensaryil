'use client';
import { useState } from 'react';
import OfferCard from './offer-card';
import { perUnit, strainBucket, type Offer } from '@/lib/deals';
import { offerFacts } from '@/lib/offer-facts';

const money = (v: string | null | undefined) =>
  v == null || v === ''
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

const STRAIN_DOT: Record<string, string> = {
  Indica: 'bg-purple-400',
  Sativa: 'bg-amber-400',
  Hybrid: 'bg-emerald-400',
  Unspecified: 'bg-slate-600',
};
const ICONS: Record<string, string> = { flower: '🌿', concentrate: '🍯', vapes: '💨', edibles: '🍬' };

// A compact, one-or-two-line deal used by the dense layouts. Clicking it opens the full OfferCard in place,
// so every action (menu link, save, share, OTD, strain list) stays available without repeating it per row.
export default function DealRow({
  o,
  rank,
  variant,
  accent,
}: {
  o: Offer;
  rank: number;
  variant: 'board' | 'compact' | 'tile';
  accent?: string;
}) {
  const [open, setOpen] = useState(false);
  const f = offerFacts(o);
  const bucket = strainBucket(o.strain_type);
  const off = f.savings.hasDiscount ? (
    <span className="rounded bg-emerald-500/20 text-emerald-300 px-1 py-px font-mono text-[10px] font-bold">-{f.savings.savingsPct}%</span>
  ) : null;
  const label = `${f.title}, ${money(f.unitPrice)} per ${f.unit} at ${o.store_name}. ${open ? 'Hide' : 'Show'} details`;

  if (open) {
    return (
      <div className={variant === 'tile' ? '' : 'px-2 py-2 border-b border-slate-800/70'}>
        <OfferCard o={o} rank={rank} />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="mt-1 w-full text-center text-[11px] font-semibold text-slate-400 hover:text-white py-1"
        >
          ▴ Collapse
        </button>
      </div>
    );
  }

  if (variant === 'tile') {
    return (
      <button
        type="button"
        aria-expanded={false}
        aria-label={label}
        onClick={() => setOpen(true)}
        className="glass-card w-full text-left rounded-2xl p-3 flex items-center gap-3 hover:border-slate-600 transition-colors"
      >
        <span className="relative w-12 h-12 shrink-0 rounded-xl bg-emerald-500/15 grid place-items-center text-xl" aria-hidden="true">
          {ICONS[o.category] ?? '🌿'}
          {rank <= 3 && (
            <span className="absolute -top-2 -left-2 rounded-full bg-slate-100 text-slate-950 text-[9px] font-extrabold px-1.5 py-px">#{rank}</span>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-extrabold text-white">{f.title}</span>
          <span className="block truncate text-xs text-slate-400">
            {[o.brand, f.size, f.grouped ? null : o.strain_type, !f.grouped && o.thc_pct ? `${o.thc_pct}%` : null].filter(Boolean).join(' · ')}
          </span>
          <span className="block truncate text-xs font-semibold text-slate-200 mt-1">
            {o.store_name} <span className="font-normal text-slate-400">· {o.distance_miles.toFixed(1)} mi{f.aged ? ' · older menu' : ''}</span>
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className="block text-lg font-extrabold text-emerald-400 leading-tight">
            {money(f.unitPrice)}
            <span className="text-[11px] font-semibold text-slate-400">/{f.unit}</span>
          </span>
          <span className="block text-xs font-bold text-slate-200">
            {f.savings.hasDiscount && <s className="font-normal text-slate-500 mr-1">{money(o.regular_price)}</s>}
            {money(o.effective_price)}
          </span>
          {f.savings.hasDiscount && (
            <span className="inline-block mt-1 rounded-md bg-amber-500/15 text-amber-300 px-1.5 py-px text-[10px] font-extrabold">{f.savings.savingsPct}% off</span>
          )}
        </span>
      </button>
    );
  }

  if (variant === 'compact') {
    return (
      <button
        type="button"
        aria-expanded={false}
        aria-label={label}
        onClick={() => setOpen(true)}
        className="w-full text-left flex items-center gap-2 px-3 py-2 border-b border-slate-800/70 hover:bg-slate-900/60 transition-colors"
      >
        <span className="w-4 shrink-0 font-mono text-[11px] text-slate-500">{rank}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-bold text-white">{f.title}</span>
          <span className="block truncate text-[11px] text-slate-400">
            {[f.grouped ? null : o.brand, f.size, o.store_name, `${o.distance_miles.toFixed(1)} mi`].filter(Boolean).join(' · ')}
          </span>
        </span>
        <span className="shrink-0 text-right font-mono">
          <span className="block text-[13px] font-bold" style={{ color: accent }}>
            {money(f.unitPrice)}
          </span>
          <span className="block text-[10px] text-slate-400">{money(o.effective_price)}</span>
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      aria-expanded={false}
      aria-label={label}
      onClick={() => setOpen(true)}
      className="board-cols grid w-full text-left px-3 py-2.5 border-b border-slate-800/70 hover:bg-slate-900/60 transition-colors text-xs"
    >
      <span className={`font-mono text-[11px] ${rank <= 3 ? 'text-emerald-400 font-bold' : 'text-slate-500'}`}>{rank}</span>
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-bold text-white">{f.title}</span>
        <span className="block truncate text-[11px] text-slate-400">
          <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${STRAIN_DOT[bucket]}`} aria-hidden="true" />
          {[f.grouped ? null : o.brand, f.grouped ? null : o.strain_type].filter(Boolean).join(' · ') || 'Tap for the strain list'}
          <span className="lg:hidden">
            {' · '}
            {f.size}
            {!f.grouped && o.thc_pct ? ` · ${o.thc_pct}% THC` : ''}
          </span>
        </span>
        <span className="block truncate text-[11px] text-slate-300 lg:hidden">
          {o.store_name} · {o.distance_miles.toFixed(1)} mi{f.aged ? ' · older menu' : ''}
        </span>
      </span>
      <span className="hidden lg:block font-mono text-slate-200">{f.size}</span>
      <span className="hidden lg:block font-mono text-slate-300">{!f.grouped && o.thc_pct ? `${o.thc_pct}%` : '—'}</span>
      <span className="hidden lg:block truncate text-slate-200">
        {o.store_name}
        {f.aged && <span className="ml-1.5 text-[10px] text-amber-300">older menu</span>}
      </span>
      <span className="hidden lg:block text-right font-mono text-slate-300">{o.distance_miles.toFixed(1)} mi</span>
      <span className="hidden lg:block text-right font-mono text-[11px] text-slate-500">
        {f.savings.hasDiscount ? <s>{money(o.regular_price)}</s> : ''}
      </span>
      <span className="hidden lg:flex items-center justify-end gap-1.5 font-mono text-slate-100">
        {off}
        {money(o.effective_price)}
      </span>
      <span className="text-right">
        <span className="block font-mono text-[15px] font-bold text-emerald-400 leading-tight">
          {money(f.unitPrice)}
          <span className="text-[10px] font-medium text-slate-400">/{f.unit}</span>
        </span>
        <span className="block font-mono text-[11px] text-slate-200 lg:hidden">
          {f.savings.hasDiscount && <s className="text-slate-500 mr-1">{money(o.regular_price)}</s>}
          {money(o.effective_price)}
        </span>
        {off && <span className="lg:hidden">{off}</span>}
      </span>
      <span className="hidden lg:block text-slate-500 text-[10px]" aria-hidden="true">▾</span>
    </button>
  );
}
