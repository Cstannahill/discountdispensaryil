'use client';
import { useEffect, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { openCalculator } from './calculator';

const KEY = 'terpscout.origin';
const RKEY = 'terpscout.radius';
type Pick = { lat: number; lon: number; place: string };

const QUICK_HUBS: readonly [string, string][] = [
  ['Peoria', '61602'],
  ['Normal', '61761'],
  ['Champaign', '61820'],
  ['Springfield', '62701'],
  ['Chicago', '60601'],
  ['Rockford', '61101'],
  ['Streator', '61358'],
];

const RADII = [5, 10, 25, 50, 100, 200] as const;

export default function LocationControl({
  active,
  radius,
  place,
  license = 'recreational',
  dataVersion,
}: {
  active: boolean;
  radius: number;
  place: string;
  license?: string;
  dataVersion?: string;
}) {
  const router = useRouter();
  const sp = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [open, setOpen] = useState(!place);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');

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

  return (
    <header className="glass-header sticky top-0 z-40 -mx-3 px-3 sm:mx-0 sm:px-4 sm:rounded-2xl sm:border sm:border-white/10 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* Brand Identity */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="brand-icon" aria-hidden="true">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.3" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v18m0-18c-3.5 3-6 6.5-6 10.5A6 6 0 0012 19.5a6 6 0 006-6C18 9.5 15.5 6 12 3z" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h1 className="font-extrabold text-base sm:text-lg tracking-tight text-white leading-none">TerpScout</h1>
              <span className="badge text-emerald-300 border-emerald-500/30 hidden xs:inline-flex">$/g</span>
              {isPending && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" aria-label="Updating deals" />}
            </div>
            <p className="text-[10px] text-slate-400 truncate">
              Illinois Dispensary $/g Finder{dataVersion ? ` · v${dataVersion}` : ''}
            </p>
          </div>
        </div>

        {/* Interactive Controls: Location Pill + Rec/Med Switch + OTD Calc */}
        <div className="flex items-center gap-1.5 ml-auto">
          <button
            type="button"
            aria-expanded={open}
            aria-label="Change search location and distance radius"
            onClick={() => setOpen((v) => !v)}
            className={`pill !py-1.5 !px-2.5 max-w-[190px] sm:max-w-xs ${open ? 'pill-active' : ''}`}
          >
            <span aria-hidden="true">📍</span>
            <span className="truncate font-semibold text-white">
              {place ? place.replace(/, USA$/, '') : 'Set location'}
            </span>
            <span className="font-mono text-[11px] text-emerald-300 shrink-0">· {radius}mi</span>
            <span className="text-[10px] text-slate-400 shrink-0">{open ? '▴' : '▾'}</span>
          </button>

          <div
            role="group"
            aria-label="License channel"
            className="inline-flex rounded-full bg-slate-950/90 border border-slate-700/80 p-0.5 text-xs"
          >
            {(['recreational', 'medicinal'] as const).map((l) => {
              const selected = license === l;
              return (
                <button
                  key={l}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setLicense(l)}
                  className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors ${
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
            className="pill !py-1.5 !px-2.5 text-emerald-300 border-emerald-500/30 hover:border-emerald-400"
            aria-label="Open Out-The-Door tax and $/g calculator"
          >
            <span aria-hidden="true">🧮</span>
            <span className="hidden sm:inline">OTD Calc</span>
          </button>
        </div>
      </div>

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
