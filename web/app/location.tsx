'use client';
import { useEffect, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { openCalculator } from './calculator';
import { openSavedDeals, getSavedDeals, SAVED_EVENT } from './saved-modal';
import { QUICK_HUBS } from '@/lib/deals';

const KEY = 'terpscout.origin';
const RKEY = 'terpscout.radius';
type Pick = { lat: number; lon: number; place: string };

const RADII = [5, 10, 25, 50, 100, 200] as const;

export type CategoryChip = {
  id: string;
  label: string;
  total: number;
  color: string;
};

const ICONS: Record<string, string> = {
  flower: '🌿',
  concentrate: '🍯',
  vapes: '💨',
  all: '⚡',
};

const CATEGORY_EVENT = 'terpscout:category-change';

export default function LocationControl({
  active,
  radius,
  place,
  license = 'recreational',
  dataVersion,
  chips,
}: {
  active: boolean;
  radius: number;
  place: string;
  license?: string;
  dataVersion?: string;
  chips?: readonly CategoryChip[];
}) {
  const router = useRouter();
  const sp = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [open, setOpen] = useState(!place);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');
  const [activeCategory, setActiveCategory] = useState('flower');
  const [savedCount, setSavedCount] = useState(0);

  useEffect(() => {
    setSavedCount(getSavedDeals().length);
    const onSaved = () => {
      setSavedCount(getSavedDeals().length);
    };
    window.addEventListener(SAVED_EVENT, onSaved);
    return () => window.removeEventListener(SAVED_EVENT, onSaved);
  }, []);

  useEffect(() => {
    try {
      const v = localStorage.getItem('terpscout.category');
      if (v) setActiveCategory(v);
    } catch {}

    const onCategoryChange = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail) setActiveCategory(detail);
    };

    window.addEventListener(CATEGORY_EVENT, onCategoryChange);
    return () => window.removeEventListener(CATEGORY_EVENT, onCategoryChange);
  }, []);

  const pickCategory = (id: string) => {
    setActiveCategory(id);
    try {
      localStorage.setItem('terpscout.category', id);
    } catch {}
    window.dispatchEvent(new CustomEvent(CATEGORY_EVENT, { detail: id }));
  };

  const pushUrl = (u: URLSearchParams) => {
    ['p_concentrate', 'p_flower', 'p_vapes'].forEach((k) => u.delete(k));
    startTransition(() => {
      router.push(`/?${u.toString()}`);
    });
  };

  const go = (o: Pick) => {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch {}
    const u = new URLSearchParams(sp.toString());
    u.set('lat', o.lat.toFixed(5));
    u.set('lon', o.lon.toFixed(5));
    u.set('place', o.place);
    u.delete('region');
    try {
      const r = localStorage.getItem(RKEY);
      if (r && !u.get('radius')) u.set('radius', r);
    } catch {}
    setOpen(false);
    pushUrl(u);
  };

  useEffect(() => {
    if (sp.get('lat') || sp.get('region')) return;
    try {
      const o = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (o && Number.isFinite(o.lat) && Number.isFinite(o.lon)) go(o);
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const gps = () => {
    setMsg('');
    if (!navigator.geolocation) {
      setMsg('Location is not available in this browser. Enter a ZIP or city.');
      return;
    }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setBusy(false);
        go({ lat: p.coords.latitude, lon: p.coords.longitude, place: 'Your location (GPS)' });
      },
      (e) => {
        setBusy(false);
        setMsg(`Could not get your location (${e.message}). Enter a ZIP or city.`);
      },
      { timeout: 15000, maximumAge: 60000 }
    );
  };

  const resolveQuery = async (query: string) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setMsg('');
    setBusy(true);
    try {
      const r = await fetch(`/api/v1/geocode?q=${encodeURIComponent(trimmed)}`);
      const j = await r.json();
      if (!r.ok) setMsg(j?.detail?.message || 'Lookup failed');
      else go({ lat: j.latitude, lon: j.longitude, place: j.label });
    } catch {
      setMsg('Lookup failed; try again');
    }
    setBusy(false);
  };

  const lookup = async (e: React.FormEvent) => {
    e.preventDefault();
    await resolveQuery(text);
  };

  const setRadius = (v: string) => {
    const u = new URLSearchParams(sp.toString());
    u.set('radius', v);
    try { localStorage.setItem(RKEY, v); } catch {}
    pushUrl(u);
  };

  const setLicense = (nextLicense: 'recreational' | 'medicinal') => {
    const u = new URLSearchParams(sp.toString());
    u.set('license', nextLicense);
    pushUrl(u);
  };

  const clear = () => {
    try { localStorage.removeItem(KEY); } catch {}
    setOpen(false);
    startTransition(() => {
      router.push('/');
    });
  };

  const allRadii = [...new Set([...RADII, radius])].sort((a, b) => a - b);

  const orderedChips = chips
    ? [
        ...chips.filter((c) => c.id === 'flower'),
        ...chips.filter((c) => c.id !== 'flower'),
        {
          id: 'all',
          label: 'All',
          total: chips.reduce((sum, c) => sum + c.total, 0),
          color: '#10b981',
        },
      ]
    : [];

  return (
    <header className="glass-header sticky top-0 z-40 -mx-3 px-3 sm:mx-0 sm:px-4 sm:rounded-2xl sm:border sm:border-white/10 py-2 sm:py-2.5">
      {/* Row 1: Unified Single-Line Command Bar */}
      <div className="flex items-center justify-between gap-1.5 sm:gap-2 min-w-0">
        {/* Brand Identity */}
        <div className="flex items-center gap-1.5 sm:gap-2.5 min-w-0 shrink-0">
          <div className="brand-icon !w-7 !h-7 !rounded-lg sm:!w-9 sm:!h-9 sm:!rounded-xl" aria-hidden="true">
            <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" strokeWidth="2.3" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v18m0-18c-3.5 3-6 6.5-6 10.5A6 6 0 0012 19.5a6 6 0 006-6C18 9.5 15.5 6 12 3z" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h1 className="font-extrabold text-sm sm:text-lg tracking-tight text-white leading-none">TerpScout</h1>
              <span className="badge text-emerald-300 border-emerald-500/30 hidden xs:inline-flex">$/g</span>
              {isPending && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" aria-label="Updating deals" />}
            </div>
            <p className="text-[10px] text-slate-400 truncate hidden sm:block">
              Illinois Dispensary $/g Finder{dataVersion ? ` · v${dataVersion}` : ''}
            </p>
          </div>
        </div>

        {/* Interactive Controls: Location Pill + Rec/Med Switch + OTD Calc */}
        <div className="flex items-center gap-1 sm:gap-1.5 ml-auto shrink-0">
          <button
            type="button"
            aria-expanded={open}
            aria-label="Change search location and distance radius"
            onClick={() => setOpen((v) => !v)}
            className={`pill !py-1 sm:!py-1.5 !px-2 sm:!px-2.5 max-w-[125px] sm:max-w-xs shrink-0 ${open ? 'pill-active' : ''}`}
          >
            <span aria-hidden="true">📍</span>
            <span className="truncate font-semibold text-white text-xs max-w-[55px] sm:max-w-none">
              {place ? place.replace(/, USA$/, '') : 'Set location'}
            </span>
            <span className="font-mono text-[10px] sm:text-[11px] text-emerald-300 shrink-0">· {radius}mi</span>
            <span className="text-[10px] text-slate-400 shrink-0">{open ? '▴' : '▾'}</span>
          </button>

          <div
            role="group"
            aria-label="License channel"
            className="inline-flex rounded-full bg-slate-950/90 border border-slate-700/80 p-0.5 text-xs shrink-0"
          >
            {(['recreational', 'medicinal'] as const).map((l) => {
              const selected = license === l;
              return (
                <button
                  key={l}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setLicense(l)}
                  className={`rounded-full px-2 sm:px-2.5 py-0.5 sm:py-1 text-[10px] sm:text-[11px] font-bold transition-colors ${
                    selected ? 'bg-emerald-500 text-slate-950' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {l === 'recreational' ? 'Rec' : 'Med'}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={() => openCalculator()}
            className="pill !py-1 sm:!py-1.5 !px-2 sm:!px-2.5 text-emerald-300 border-emerald-500/30 hover:border-emerald-400 shrink-0"
            aria-label="Open Out-The-Door tax and $/g calculator"
          >
            <span aria-hidden="true">🧮</span>
            <span className="hidden sm:inline">OTD Calc</span>
          </button>

          <button
            type="button"
            onClick={() => openSavedDeals()}
            className={`pill !py-1 sm:!py-1.5 !px-2 sm:!px-2.5 transition-colors shrink-0 ${
              savedCount > 0
                ? 'text-amber-300 border-amber-500/40 hover:border-amber-400 bg-amber-500/10'
                : 'text-slate-400 border-slate-700/80 hover:text-slate-200'
            }`}
            aria-label="View saved deals shortlist"
            title="View your saved deals shortlist"
          >
            <span aria-hidden="true">⭐</span>
            <span className="font-mono text-[10px] sm:text-[11px] font-bold">{savedCount}</span>
          </button>
        </div>
      </div>

      {/* Row 2: Mobile-only Category Segmented Rail */}
      {chips && chips.length > 0 && (
        <nav
          aria-label="Category navigation"
          className="lg:hidden flex items-center gap-1.5 overflow-x-auto no-scrollbar pt-2 border-t border-slate-800/80"
        >
          {orderedChips.map((c) => {
            const isSelected = activeCategory === c.id;
            return (
              <button
                key={c.id}
                type="button"
                aria-pressed={isSelected}
                onClick={() => pickCategory(c.id)}
                style={isSelected ? { borderColor: c.color } : undefined}
                className={`btn shrink-0 capitalize !py-1 !px-2.5 rounded-xl text-xs transition-all ${
                  isSelected ? 'selected' : 'text-slate-300'
                }`}
              >
                <span aria-hidden="true">{ICONS[c.id] ?? '🌿'}</span>
                <span>{c.label}</span>
                {c.total >= 0 && (
                  <span
                    className={`font-mono text-[10px] px-1.5 py-0.5 rounded-md ${
                      isSelected
                        ? 'bg-slate-950/30 text-slate-950 font-extrabold'
                        : 'bg-slate-950/70 text-slate-400'
                    }`}
                  >
                    {c.total}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      )}

      {/* Expandable Location Drawer */}
      {open && (
        <section
          aria-label="Search location"
          className="mt-3 pt-3 border-t border-slate-800/90 space-y-3"
        >
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              className="btn-primary py-2.5 text-xs sm:w-auto shrink-0"
              onClick={gps}
              disabled={busy}
            >
              {busy ? 'Locating…' : '📍 Use my current location'}
            </button>

            <form onSubmit={lookup} className="flex gap-2 flex-1">
              <label htmlFor="loc-text" className="sr-only">
                Or enter a ZIP code or city
              </label>
              <input
                id="loc-text"
                className="min-w-0 flex-1 !py-2"
                placeholder="Enter ZIP or City (e.g. 61602 or Peoria, IL)"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <button type="submit" className="btn-primary px-4" disabled={busy || !text.trim()}>
                Set
              </button>
            </form>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
              <span className="text-[11px] font-semibold text-slate-400 shrink-0">Quick IL Hubs:</span>
              {QUICK_HUBS.map(([label, zip]) => (
                <button
                  key={zip}
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setText(zip);
                    void resolveQuery(zip);
                  }}
                  className="pill !px-2.5 !py-1 !text-[11px]"
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1.5 flex-wrap">
              <label htmlFor="radius-select" className="text-[11px] font-semibold text-slate-400">
                Range:
              </label>
              <select
                id="radius-select"
                aria-label="Search range in miles"
                className="!py-1.5 !px-2.5 !rounded-lg font-mono"
                value={radius}
                onChange={(e) => setRadius(e.target.value)}
              >
                {allRadii.map((m) => (
                  <option key={m} value={m}>
                    Within {m} miles
                  </option>
                ))}
              </select>
              {active && (
                <button type="button" className="btn !py-1.5 !px-2.5 text-[11px]" onClick={clear}>
                  Reset
                </button>
              )}
            </div>
          </div>

          {msg && (
            <p role="alert" className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2">
              {msg}
            </p>
          )}
        </section>
      )}
    </header>
  );
}
