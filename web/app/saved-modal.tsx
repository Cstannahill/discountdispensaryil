'use client';
import { useEffect, useState } from 'react';
import { openCalculator } from './calculator';

export const SAVED_STORAGE_KEY = 'terpscout.saved';
export const SAVED_EVENT = 'terpscout:saved-change';
export const OPEN_SAVED_EVENT = 'terpscout:open-saved';

export interface SavedDeal {
  id: string;
  name: string;
  brand?: string | null;
  store_name: string;
  price_per_gram?: string | null;
  effective_price?: string | null;
  regular_price?: string | null;
  massLabel: string;
  category: string;
  source_url?: string | null;
  distance_miles: number;
  saved_at: number;
  weight_grams?: string | null;
  license_type?: string | null;
  flower_grade?: string | null;
  thc_pct?: string | null;
}

export function openSavedDeals() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(OPEN_SAVED_EVENT));
  }
}

export function getSavedDeals(): SavedDeal[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(SAVED_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function toggleSaveDeal(deal: SavedDeal): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const list = getSavedDeals();
    const idx = list.findIndex((x) => x.id === deal.id);
    let nowSaved = false;
    if (idx >= 0) {
      list.splice(idx, 1);
      nowSaved = false;
    } else {
      list.unshift(deal);
      nowSaved = true;
    }
    localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(list));
    window.dispatchEvent(new CustomEvent(SAVED_EVENT, { detail: { id: deal.id, saved: nowSaved } }));
    return nowSaved;
  } catch {
    return false;
  }
}

const money = (v: string | null | undefined) =>
  v == null || v === ''
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

const safeUrl = (v?: string | null) => {
  try {
    const u = new URL(v ?? '');
    return ['https:', 'http:'].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
};

export default function SavedModal() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<SavedDeal[]>([]);

  const reload = () => {
    setItems(getSavedDeals());
  };

  useEffect(() => {
    reload();

    const onOpen = () => {
      reload();
      setOpen(true);
    };

    const onChange = () => {
      reload();
    };

    window.addEventListener(OPEN_SAVED_EVENT, onOpen);
    window.addEventListener(SAVED_EVENT, onChange);
    return () => {
      window.removeEventListener(OPEN_SAVED_EVENT, onOpen);
      window.removeEventListener(SAVED_EVENT, onChange);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!open) return null;

  const remove = (id: string) => {
    try {
      const filtered = items.filter((x) => x.id !== id);
      setItems(filtered);
      localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(filtered));
      window.dispatchEvent(new CustomEvent(SAVED_EVENT, { detail: { id, saved: false } }));
    } catch {}
  };

  const clearAll = () => {
    if (typeof window !== 'undefined' && !window.confirm('Clear all saved deals from your shortlist?')) {
      return;
    }
    try {
      setItems([]);
      localStorage.removeItem(SAVED_STORAGE_KEY);
      window.dispatchEvent(new CustomEvent(SAVED_EVENT, { detail: { id: null, saved: false } }));
    } catch {}
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/75 backdrop-blur-sm p-0 sm:p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Saved Deals Shortlist"
        className="glass-card w-full sm:max-w-xl rounded-t-3xl sm:rounded-2xl p-5 space-y-4 max-h-[90dvh] overflow-y-auto border-t sm:border border-emerald-500/30"
      >
        {/* Mobile Pull Handle */}
        <div className="w-10 h-1 bg-slate-700/80 rounded-full mx-auto sm:hidden mb-1" aria-hidden="true" />

        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base">⭐</span>
              <h2 className="text-base font-extrabold text-white">Your Saved Deals</h2>
              <span className="badge text-emerald-300 border-emerald-500/30 font-mono">
                {items.length}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Compare your top candidates across stores before heading out.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {items.length > 0 && (
              <button
                type="button"
                onClick={clearAll}
                className="text-xs text-slate-400 hover:text-rose-300 transition-colors px-2 py-1"
              >
                Clear all
              </button>
            )}
            <button
              type="button"
              className="btn !py-1 !px-2.5 text-slate-300"
              aria-label="Close saved deals modal"
              onClick={() => setOpen(false)}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Body */}
        {items.length === 0 ? (
          <div className="text-center py-10 px-4 space-y-2">
            <span className="text-3xl block">🔖</span>
            <p className="text-sm font-semibold text-slate-200">No deals pinned yet</p>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Tap the <strong className="text-emerald-300 font-mono">☆ Save</strong> button on any deal card to pin it to your shortlist for side-by-side comparison.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const menuHref = safeUrl(item.source_url);
              return (
                <article
                  key={item.id}
                  className="rounded-xl border border-slate-700/70 bg-slate-900/90 p-3 space-y-2"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="badge uppercase tracking-wider text-emerald-400 border-emerald-500/30">
                          {item.category}
                        </span>
                        {item.brand && (
                          <span className="text-[11px] font-bold text-slate-300 truncate">
                            {item.brand}
                          </span>
                        )}
                        <span className="badge text-slate-400 bg-slate-950/80">{item.massLabel}</span>
                      </div>
                      <h3 className="text-xs sm:text-sm font-bold text-white mt-1 leading-snug break-words">
                        {item.name}
                      </h3>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        📍 {item.store_name} · {typeof item.distance_miles === 'number' ? `${item.distance_miles.toFixed(1)} mi` : 'distance unknown'}
                      </p>
                    </div>

                    <div className="text-right shrink-0 bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1">
                      {item.price_per_gram && (
                        <p className="text-sm font-extrabold font-mono text-emerald-400 leading-none">
                          {money(item.price_per_gram)}/g
                        </p>
                      )}
                      <p className="text-[11px] font-mono text-slate-200 mt-0.5">
                        {money(item.effective_price)}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 pt-1 border-t border-slate-800/80">
                    {menuHref ? (
                      <a
                        href={menuHref}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 inline-flex items-center justify-center gap-1 text-xs font-semibold text-emerald-300 hover:text-emerald-200 py-1"
                      >
                        <span>Menu</span>
                        <span aria-hidden="true">↗</span>
                      </a>
                    ) : (
                      <span className="flex-1 text-[11px] text-slate-500">No link</span>
                    )}

                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      openCalculator({
                        name: item.name,
                        brand: item.brand,
                        store_name: item.store_name,
                        price: item.effective_price,
                        weight_grams: item.weight_grams,
                        category: item.category,
                        license_type: item.license_type,
                        flower_grade: item.flower_grade,
                        thc_pct: item.thc_pct,
                      });
                    }}
                    className="btn !py-1 !px-2.5 text-xs text-slate-300 hover:text-emerald-300"
                  >
                    🧮 OTD
                  </button>

                  <button
                    type="button"
                    onClick={() => remove(item.id)}
                    className="btn !py-1 !px-2 text-xs text-slate-400 hover:text-rose-300"
                    aria-label={`Remove ${item.name} from saved deals`}
                  >
                    ✕
                  </button>
                </div>
              </article>
            );
          })}
          </div>
        )}
      </section>
    </div>
  );
}
