'use client';
import { useEffect, useRef, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { openCalculator } from './calculator';
import { showToast } from './toast';
import { openSavedDeals, getSavedDeals, SAVED_EVENT } from './saved-modal';
import { CATEGORIES, QUICK_HUBS } from '@/lib/deals';

const KEY = 'terpscout.origin';
const RKEY = 'terpscout.radius';
// src 'gps' marks a device fix that may go stale; 'manual' (typed ZIP/city) is never auto-refreshed.
type Pick = { lat: number; lon: number; place: string; src?: 'gps' | 'manual'; at?: number };

const GPS_LABEL = 'Your location (GPS)';
const STALE_MS = 30 * 60 * 1000; // re-check a GPS fix after 30 minutes
const MIN_MOVE_MI = 3; // ignore GPS jitter below this
const PROMPT_MOVE_MI = 25; // ask before swapping for moves above this

function miles(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const R = 3958.8, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function ago(ms: number) {
  const m = Math.round(ms / 60000);
  if (m < 60) return `${Math.max(m, 1)}m ago`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

function readStored(): Pick | null {
  try {
    const o = JSON.parse(localStorage.getItem(KEY) || 'null');
    return o && Number.isFinite(o.lat) && Number.isFinite(o.lon) ? o : null;
  } catch {
    return null;
  }
}

async function reverseLabel(lat: number, lon: number): Promise<string | null> {
  try {
    const r = await fetch(`/api/v1/geocode?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}`, { signal: AbortSignal.timeout(4000) });
    if (!r.ok) return null;
    const j = await r.json();
    return typeof j?.label === 'string' && j.label ? j.label : null;
  } catch {
    return null;
  }
}

const RADII = [5, 10, 25, 50, 100, 200] as const;
const MIN_RADIUS = 1;
const MAX_RADIUS = 200;

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
  edibles: '🍬',
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
  const [custom, setCustom] = useState('');
  const [activeCategory, setActiveCategory] = useState('flower');
  const [savedCount, setSavedCount] = useState(0);
  const [src, setSrc] = useState<'gps' | 'manual' | ''>('');
  const [fixAt, setFixAt] = useState(0);
  const [now, setNow] = useState(0);
  const [moved, setMoved] = useState<Pick | null>(null);
  const checking = useRef(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: Event) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  // Tell the page shell when listings are refreshing so it can show a progress bar.
  useEffect(() => {
    // busy covers the GPS fix and ZIP/city lookup; isPending covers the listings reload that follows.
    window.dispatchEvent(new CustomEvent('terpscout:pending', { detail: { source: 'location', pending: isPending || busy } }));
  }, [isPending, busy]);

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
    CATEGORIES.map((c) => `p_${c}`).forEach((k) => u.delete(k));
    startTransition(() => {
      router.push(`/?${u.toString()}`);
    });
  };

  const go = (o: Pick, keepOpen = false) => {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch {}
    setSrc(o.src ?? '');
    setFixAt(o.at ?? 0);
    setMoved(null);
    const u = new URLSearchParams(sp.toString());
    u.set('lat', o.lat.toFixed(5));
    u.set('lon', o.lon.toFixed(5));
    u.set('place', o.place);
    u.delete('region');
    try {
      const r = localStorage.getItem(RKEY);
      if (r && !u.get('radius')) u.set('radius', r);
    } catch {}
    if (!keepOpen) setOpen(false);
    pushUrl(u);
  };

  useEffect(() => {
    if (sp.get('lat') || sp.get('region')) return;
    const o = readStored();
    if (o) go(o);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Pick up the saved source/time for the pill even when the URL already carries the origin.
  useEffect(() => {
    const o = readStored();
    if (o) { setSrc(o.src ?? ''); setFixAt(o.at ?? 0); }
    setNow(Date.now());
  }, []);

  // A phone browser resumes a tab without reloading, so re-check a stale GPS fix when the page comes back.
  const recheck = async () => {
    const o = readStored();
    if (!o || o.src !== 'gps' || checking.current) return;
    setNow(Date.now());
    if (Date.now() - (o.at ?? 0) < STALE_MS) return;
    if (!navigator.geolocation || !navigator.permissions) return;
    try {
      const st = await navigator.permissions.query({ name: 'geolocation' });
      if (st.state !== 'granted') return; // never trigger a surprise permission prompt
    } catch {
      return;
    }
    checking.current = true;
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        const cur = { lat: p.coords.latitude, lon: p.coords.longitude };
        const d = miles(o, cur);
        if (d < MIN_MOVE_MI) {
          const kept = { ...o, at: Date.now() };
          try { localStorage.setItem(KEY, JSON.stringify(kept)); } catch {}
          setFixAt(kept.at);
        } else {
          const label = (await reverseLabel(cur.lat, cur.lon)) || GPS_LABEL;
          const next: Pick = { ...cur, place: label, src: 'gps', at: Date.now() };
          if (d >= PROMPT_MOVE_MI) setMoved(next);
          else {
            go(next, true);
            showToast(`Location updated to ${label.replace(/, USA$/, '')}`);
          }
        }
        checking.current = false;
      },
      () => { checking.current = false; },
      { timeout: 10000, maximumAge: 300000, enableHighAccuracy: false }
    );
  };
  const recheckRef = useRef(recheck);
  recheckRef.current = recheck;

  useEffect(() => {
    const onShow = () => {
      if (document.visibilityState === 'visible') void recheckRef.current();
    };
    document.addEventListener('visibilitychange', onShow);
    window.addEventListener('pageshow', onShow);
    onShow();
    return () => {
      document.removeEventListener('visibilitychange', onShow);
      window.removeEventListener('pageshow', onShow);
    };
  }, []);

  const keepOld = () => {
    const o = readStored();
    if (o) {
      const kept = { ...o, at: Date.now() };
      try { localStorage.setItem(KEY, JSON.stringify(kept)); } catch {}
      setFixAt(kept.at);
    }
    setMoved(null);
  };

  const gps = () => {
    setMsg('');
    if (!navigator.geolocation) {
      setMsg('Location is not available in this browser. Enter a ZIP or city.');
      return;
    }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        const lat = p.coords.latitude, lon = p.coords.longitude;
        const label = (await reverseLabel(lat, lon)) || GPS_LABEL;
        setBusy(false);
        go({ lat, lon, place: label, src: 'gps', at: Date.now() });
      },
      (e) => {
        setBusy(false);
        setMsg(`Could not get your location (${e.message}). Enter a ZIP or city.`);
      },
      { timeout: 15000, maximumAge: 60000 }
    );
  };

  const lastQuery = useRef('');
  const resolveQuery = async (query: string, keepOpen = false) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    lastQuery.current = trimmed;
    setMsg('');
    setBusy(true);
    try {
      const r = await fetch(`/api/v1/geocode?q=${encodeURIComponent(trimmed)}`);
      const j = await r.json();
      if (!r.ok) setMsg(j?.detail?.message || 'Lookup failed');
      else go({ lat: j.latitude, lon: j.longitude, place: j.label, src: 'manual', at: Date.now() }, keepOpen);
    } catch {
      setMsg('Lookup failed; try again');
    }
    setBusy(false);
  };

  const lookup = async (e: React.FormEvent) => {
    e.preventDefault();
    await resolveQuery(text);
  };

  // Typing a ZIP or city applies itself after a short pause (Enter applies at once).
  useEffect(() => {
    const t = text.trim();
    if (t.length < 3 || t === lastQuery.current) return;
    const timer = setTimeout(() => void resolveQuery(t, true), 700);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const setRadius = (v: string) => {
    const u = new URLSearchParams(sp.toString());
    u.set('radius', v);
    try { localStorage.setItem(RKEY, v); } catch {}
    pushUrl(u);
  };

  const [customMode, setCustomMode] = useState(false);
  const showCustom = customMode || !(RADII as readonly number[]).includes(radius);

  // A typed custom distance applies itself after a short pause.
  useEffect(() => {
    if (!custom) return;
    const timer = setTimeout(() => {
      const n = Number(custom);
      if (!/^\d+$/.test(custom) || n < MIN_RADIUS || n > MAX_RADIUS) {
        setMsg(`Enter a distance from ${MIN_RADIUS} to ${MAX_RADIUS} miles.`);
        return;
      }
      setMsg('');
      if (n !== radius) setRadius(String(n));
    }, 600);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [custom]);

  const pickRange = (v: string) => {
    if (v === 'custom') {
      setCustomMode(true);
      setCustom(String(radius));
      return;
    }
    setCustomMode(false);
    setCustom('');
    setMsg('');
    setRadius(v);
  };

  const setLicense = (nextLicense: 'recreational' | 'medicinal') => {
    const u = new URLSearchParams(sp.toString());
    u.set('license', nextLicense);
    pushUrl(u);
  };

  const clear = () => {
    try { localStorage.removeItem(KEY); } catch {}
    setSrc('');
    setMoved(null);
    setOpen(false);
    startTransition(() => {
      router.push('/');
    });
  };

  const stale = src === 'gps' && fixAt > 0 && now - fixAt > STALE_MS;

  // Highlight only the chip that matches the active location: a hub's ZIP ends its geocoded label ("Chicago, IL 60601").
  const activeZip = active && src !== 'gps' ? (place.match(/\b(\d{5})$/)?.[1] ?? '') : '';
  const gpsActive = active && src === 'gps';

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
      <div className="flex items-center justify-between gap-2 min-w-0">
        {/* Brand Identity */}
        <div className="flex items-center gap-1.5 sm:gap-2.5 min-w-0 shrink-0 sm:shrink">
          <div className="brand-icon shrink-0 !w-9 !h-9 !rounded-xl" aria-hidden="true">
            <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" strokeWidth="2.3" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v18m0-18c-3.5 3-6 6.5-6 10.5A6 6 0 0012 19.5a6 6 0 006-6C18 9.5 15.5 6 12 3z" />
            </svg>
          </div>
          <h1 className="sr-only sm:hidden">DiscountDispensaryIL</h1>
          <div className="min-w-0 hidden sm:block">
            <div className="flex items-center gap-1.5">
              <h1 className="font-extrabold text-sm sm:text-lg tracking-tight text-white leading-none">DiscountDispensaryIL<span className="sr-only">: cheapest cannabis price per gram at Illinois dispensaries</span></h1>
              <span className="badge text-emerald-300 border-emerald-500/30 hidden sm:inline-flex">$/g</span>
              {isPending && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" aria-label="Updating deals" />}
            </div>
            <p className="text-[10px] text-slate-400 truncate hidden sm:block">
              Illinois Dispensary $/g Finder{dataVersion ? ` · v${dataVersion}` : ''}
            </p>
          </div>
        </div>

        {/* Interactive Controls: Location Pill + Rec/Med Switch + OTD Calc */}
        <div className="flex items-center gap-1.5 ml-auto min-w-0 flex-1 justify-end">
          <button
            type="button"
            aria-expanded={open}
            aria-label="Change search location and distance radius"
            title="Change location and distance"
            onClick={() => setOpen((v) => !v)}
            className={`pill !py-1.5 !px-2.5 max-w-none sm:max-w-xs min-w-0 !shrink flex-1 sm:flex-none justify-start ${open ? 'pill-active' : ''}`}
          >
            <span aria-hidden="true">📍</span>
            <span className="truncate min-w-0 font-semibold text-white text-xs sm:max-w-none">
              {place ? place.replace(/, USA$/, '').replace(/^Your location \(GPS\)$/, 'Near me') : 'Set location'}
            </span>
            {src === 'gps' && place && (
              <span className={`text-[10px] shrink-0 ${stale ? 'text-amber-300' : 'text-slate-400'}`}>
                {stale ? `GPS · ${ago(now - fixAt)}` : 'GPS'}
              </span>
            )}
            <span className="font-mono text-[10px] sm:text-[11px] text-emerald-300 shrink-0">· {radius}mi</span>
            <span className="text-[10px] text-slate-400 shrink-0">{open ? '▴' : '▾'}</span>
          </button>

          {src === 'gps' && place && (
            <button
              type="button"
              disabled={busy}
              onClick={gps}
              className="pill !py-1.5 !px-2 shrink-0"
              aria-label="Refresh my current location"
              title="Refresh my current location"
            >
              <span aria-hidden="true">{busy ? '…' : '↻'}</span>
            </button>
          )}

          <div ref={menuRef} className="relative shrink-0">
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label="More options: license, calculator, saved deals"
              title="More"
              onClick={() => setMenuOpen((v) => !v)}
              className={`pill !py-1.5 !px-2.5 relative ${menuOpen ? 'pill-active' : ''}`}
            >
              <span aria-hidden="true" className="text-base leading-none">⋯</span>
              {license === 'medicinal' && (
                <span className="text-[10px] font-bold text-amber-300">Med</span>
              )}
              {savedCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-amber-400 text-slate-950 text-[9px] font-extrabold flex items-center justify-center">
                  {savedCount}
                </span>
              )}
            </button>
            {menuOpen && (
              <div
                role="menu"
                aria-label="More options"
                className="absolute right-0 top-full mt-2 w-56 rounded-2xl border border-slate-700/80 bg-slate-950/98 shadow-xl shadow-black/60 p-2 z-50 space-y-1"
              >
                <div role="group" aria-label="License channel" className="flex rounded-xl bg-slate-900 border border-slate-700/80 p-0.5 text-xs">
                  {(['recreational', 'medicinal'] as const).map((l) => {
                    const selected = license === l;
                    return (
                      <button
                        key={l}
                        type="button"
                        role="menuitemradio"
                        aria-checked={selected}
                        onClick={() => { setLicense(l); setMenuOpen(false); }}
                        className={`flex-1 rounded-[10px] px-2 py-2 text-[12px] font-bold transition-colors ${
                          selected ? 'bg-emerald-500 text-slate-950' : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {l === 'recreational' ? 'Recreational' : 'Medical'}
                      </button>
                    );
                  })}
                </div>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); openCalculator(); }}
                  className="w-full flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-slate-200 hover:bg-slate-800/80 text-left"
                >
                  <span aria-hidden="true">🧮</span>
                  <span>Out-the-door calculator</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); openSavedDeals(); }}
                  className="w-full flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-slate-200 hover:bg-slate-800/80 text-left"
                >
                  <span aria-hidden="true">⭐</span>
                  <span className="flex-1">Saved deals</span>
                  <span className="font-mono text-[11px] text-amber-300">{savedCount}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {moved && (
        <div role="status" className="mt-2 flex flex-wrap items-center gap-2 text-xs text-emerald-100 bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-3 py-2">
          <span className="min-w-0 flex-1">
            Looks like you&apos;re near {moved.place.replace(/, USA$/, '')} now. Update your location?
          </span>
          <button type="button" className="btn !py-1 !px-2.5 text-[11px]" onClick={() => go(moved, true)}>Update</button>
          <button type="button" className="btn !py-1 !px-2.5 text-[11px]" onClick={keepOld}>Keep {place.replace(/, USA$/, '') || 'current'}</button>
        </div>
      )}

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
                title={`Show ${c.label} deals`}
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
          <form onSubmit={lookup} className="flex gap-2">
            <label htmlFor="loc-text" className="sr-only">
              Enter a ZIP code or city
            </label>
            <input
              id="loc-text"
              title="Type a ZIP code or city; results update as you type"
              className="min-w-0 flex-1 !py-2"
              placeholder="ZIP or city, e.g. 61602 or Peoria"
              autoComplete="postal-code"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </form>

          <div
            className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5"
            role="group"
            aria-label="Quick locations"
          >
            <button
              type="button"
              disabled={busy}
              title="Use your device's location"
              onClick={gps}
              className={`pill !px-2.5 !py-1 !text-[11px] shrink-0 font-semibold ${
                gpsActive ? 'pill-active' : ''
              }`}
              aria-pressed={gpsActive}
            >
              {busy ? 'Locating…' : '📍 Current location'}
            </button>
            {QUICK_HUBS.map(([label, zip]) => (
              <button
                key={zip}
                type="button"
                disabled={busy}
                title={`Search near ${label}`}
                onClick={() => {
                  setText('');
                  void resolveQuery(zip);
                }}
                aria-pressed={activeZip === zip}
                className={`pill !px-2.5 !py-1 !text-[11px] shrink-0 ${activeZip === zip ? 'pill-active' : ''}`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="radius-select" className="text-[11px] font-semibold text-slate-400 shrink-0">
              Distance
            </label>
            <select
              id="radius-select"
              aria-label="Search distance in miles"
              title="How far to search"
              className="!py-1.5 !px-2.5 !rounded-lg min-w-0 flex-1 sm:flex-none sm:w-44"
              value={showCustom ? 'custom' : radius}
              onChange={(e) => pickRange(e.target.value)}
            >
              {RADII.map((m) => (
                <option key={m} value={m}>
                  Within {m} miles
                </option>
              ))}
              <option value="custom">Custom…</option>
            </select>
            {showCustom && (
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={3}
                aria-label={`Custom distance in miles (${MIN_RADIUS} to ${MAX_RADIUS})`}
                placeholder="miles"
                className="!py-1.5 !px-2.5 !rounded-lg w-20 shrink-0 text-[16px] sm:text-[12px]"
                value={custom}
                onChange={(e) => setCustom(e.target.value.replace(/\D/g, '').slice(0, 3))}
              />
            )}
            {active && (
              <button type="button" title="Clear location and go back to the default view" className="btn !py-1.5 !px-2.5 text-[11px] shrink-0 ml-auto" onClick={clear}>
                Reset
              </button>
            )}
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
