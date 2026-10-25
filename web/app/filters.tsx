'use client';
import { useEffect, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { GRADES, STRAINS } from '@/lib/deals';

const SIZE_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'any', label: 'Any Size' },
  { value: '0.5', label: '0.5g' },
  { value: '1', label: '1g' },
  { value: '3.5', label: '3.5g (⅛)' },
  { value: '7', label: '7g (¼)' },
  { value: '14', label: '14g (½)' },
  { value: '28', label: '28g (1 oz)' },
];

const GRADE_LABELS: Record<string, string> = {
  whole: 'Whole Flower',
  smalls: 'Smalls / Popcorn',
  shake: 'Shake / Ground',
  infused: 'Infused',
  all: 'All Flower Grades',
};

const STRAIN_STYLES: Record<string, string> = {
  Indica: 'strain-indica border-purple-400/60',
  Sativa: 'strain-sativa border-amber-400/60',
  Hybrid: 'strain-hybrid border-emerald-400/60',
};

export default function FilterStrip({
  q,
  grade,
  strain,
  size,
  bogo,
  stale,
  unverified,
}: {
  q: string;
  grade: string;
  strain: string;
  size: string;
  bogo: boolean;
  stale: boolean;
  unverified: boolean;
}) {
  const router = useRouter();
  const sp = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [search, setSearch] = useState(q);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    setSearch(q);
  }, [q]);

  const updateParams = (updates: Record<string, string | null>) => {
    const u = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v == null || v === '' || (k === 'grade' && v === 'whole') || (k === 'size' && v === 'any')) {
        u.delete(k);
      } else {
        u.set(k, v);
      }
    }
    ['p_concentrate', 'p_flower', 'p_vapes'].forEach((k) => u.delete(k));
    startTransition(() => {
      router.push(`/?${u.toString()}`);
    });
  };

  useEffect(() => {
    if (search === q) return;
    const timer = setTimeout(() => {
      updateParams({ q: search.trim() || null });
    }, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, q]);

  const extraFilterCount =
    (grade !== 'whole' ? 1 : 0) +
    (bogo ? 1 : 0) +
    (stale ? 1 : 0) +
    (unverified ? 1 : 0);

  const hasAnyFilter =
    Boolean(q) ||
    grade !== 'whole' ||
    Boolean(strain) ||
    Boolean(size && size !== 'any') ||
    bogo ||
    stale ||
    unverified;

  const resetAll = () => {
    setSearch('');
    updateParams({
      q: null,
      grade: null,
      strain: null,
      size: null,
      promo: null,
      stale: null,
      unverified: null,
    });
  };

  return (
    <section aria-label="Deal filters" className="glass-card rounded-2xl p-3 space-y-2.5">
      {/* Row 1: Search Input + Advanced Filters Button */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs" aria-hidden="true">
            🔍
          </span>
          <input
            type="search"
            aria-label="Search deals by product, brand, or dispensary"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                updateParams({ q: search.trim() || null });
              }
            }}
            placeholder="Search strain, brand, or dispensary…"
            maxLength={300}
            className="w-full !pl-8 !pr-8 !py-2"
          />
          {search && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => {
                setSearch('');
                updateParams({ q: null });
              }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-xs px-1"
            >
              ✕
            </button>
          )}
        </div>

        <button
          type="button"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen((v) => !v)}
          className={`btn shrink-0 !py-2 ${extraFilterCount > 0 || drawerOpen ? 'border-emerald-400/60 text-emerald-300 bg-emerald-500/15' : ''}`}
        >
          <span>⚙ Filters</span>
          {extraFilterCount > 0 && (
            <span className="rounded-full bg-emerald-400 text-slate-950 px-1.5 py-0.5 text-[10px] font-extrabold font-mono">
              {extraFilterCount}
            </span>
          )}
        </button>

        {hasAnyFilter && (
          <button
            type="button"
            onClick={resetAll}
            className="btn shrink-0 !py-2 text-slate-400 hover:text-white inline-flex text-xs"
            aria-label="Reset all filters"
          >
            ✕ Reset
          </button>
        )}
      </div>

      {/* Row 2: Unified Single-Rail Strain Type & Package Size Horizontal Track */}
      <div
        className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5"
        role="group"
        aria-label="Filter by strain type and package size"
      >
        {/* Strain Type Pills */}
        <button
          type="button"
          aria-pressed={!strain}
          onClick={() => updateParams({ strain: null })}
          className={`pill !py-1 !px-2.5 !text-[11px] shrink-0 ${!strain ? 'pill-active' : ''}`}
        >
          All Strains
        </button>
        {STRAINS.map((s) => {
          const active = strain.toLowerCase() === s.toLowerCase();
          return (
            <button
              key={s}
              type="button"
              aria-pressed={active}
              onClick={() => updateParams({ strain: active ? null : s })}
              className={`pill !py-1 !px-2.5 !text-[11px] shrink-0 ${active ? STRAIN_STYLES[s] + ' font-bold' : ''}`}
            >
              {s}
            </button>
          );
        })}

        <span className="text-slate-700 px-1 select-none shrink-0" aria-hidden="true">
          |
        </span>

        {/* Package Size Pills */}
        {SIZE_OPTIONS.map((opt) => {
          const active = (size || 'any') === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              onClick={() => updateParams({ size: opt.value === 'any' ? null : opt.value })}
              className={`pill !py-1 !px-2.5 !text-[11px] font-mono shrink-0 ${active ? 'pill-active' : ''}`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {/* Expandable Advanced Filters Drawer */}
      {drawerOpen && (
        <div className="pt-2.5 border-t border-slate-800/90 space-y-3">
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
              Flower Grade
            </span>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Flower grade">
              {GRADES.map((g) => {
                const active = grade === g;
                return (
                  <button
                    key={g}
                    type="button"
                    aria-pressed={active}
                    onClick={() => updateParams({ grade: g })}
                    className={`pill !py-1 !px-3 !text-xs ${active ? 'pill-active' : ''}`}
                  >
                    {GRADE_LABELS[g] ?? g}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="flex flex-wrap gap-4 text-xs text-slate-300">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={bogo}
                  onChange={(e) => updateParams({ promo: e.target.checked ? 'bogo' : null })}
                />
                <span>BOGO promotions only</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={unverified}
                  onChange={(e) => updateParams({ unverified: e.target.checked ? '1' : null })}
                />
                <span>Include unverified totals</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={stale}
                  onChange={(e) => updateParams({ stale: e.target.checked ? '1' : null })}
                />
                <span>Include stale menus (&gt;12h)</span>
              </label>
            </div>

            {hasAnyFilter && (
              <button type="button" onClick={resetAll} className="btn !py-1.5 !px-3 text-xs">
                Reset all filters
              </button>
            )}
          </div>
        </div>
      )}

      {isPending && (
        <div className="h-0.5 w-full bg-slate-800 overflow-hidden rounded-full" role="status" aria-label="Updating deals">
          <div className="h-full w-1/2 bg-emerald-400 animate-pulse" />
        </div>
      )}
    </section>
  );
}
