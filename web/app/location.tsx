'use client';
import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

const KEY = 'terpscout.origin';
const RKEY = 'terpscout.radius';
type Pick = { lat: number; lon: number; place: string };

// Lets a visitor use their device location or a ZIP/city instead of the server's saved region; the choice lives in the URL and localStorage.
export default function LocationControl({ active, radius, place }: { active: boolean; radius: number; place: string }) {
  const router = useRouter();
  const sp = useSearchParams();
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');

  const go = (o: Pick) => {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch {}
    const u = new URLSearchParams(sp.toString());
    u.set('lat', o.lat.toFixed(5)); u.set('lon', o.lon.toFixed(5)); u.set('place', o.place); u.delete('region');
    try { const r = localStorage.getItem(RKEY); if (r && !u.get('radius')) u.set('radius', r); } catch {}
    ['p_concentrate', 'p_flower', 'p_vapes'].forEach((k) => u.delete(k));
    router.push(`/?${u.toString()}`);
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
    if (!navigator.geolocation) { setMsg('Location is not available in this browser. Enter a ZIP or city.'); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (p) => { setBusy(false); go({ lat: p.coords.latitude, lon: p.coords.longitude, place: 'Your location (GPS)' }); },
      (e) => { setBusy(false); setMsg(`Could not get your location (${e.message}). Enter a ZIP or city.`); },
      { timeout: 15000, maximumAge: 60000 });
  };
  const lookup = async (e: React.FormEvent) => {
    e.preventDefault(); setMsg(''); setBusy(true);
    try {
      const r = await fetch(`/api/v1/geocode?q=${encodeURIComponent(text)}`);
      const j = await r.json();
      if (!r.ok) setMsg(j?.detail?.message || 'Lookup failed');
      else go({ lat: j.latitude, lon: j.longitude, place: j.label });
    } catch { setMsg('Lookup failed; try again'); }
    setBusy(false);
  };
  const setRadius = (v: string) => {
    const u = new URLSearchParams(sp.toString());
    u.set('radius', v);
    try { localStorage.setItem(RKEY, v); } catch {}
    ['p_concentrate', 'p_flower', 'p_vapes'].forEach((k) => u.delete(k));
    router.push(`/?${u.toString()}`);
  };
  const clear = () => { try { localStorage.removeItem(KEY); } catch {} router.push('/'); };

  return (
    <section className="glass-card rounded-2xl p-4 space-y-3" aria-label="Search location">
      <div>
        <h2 className="font-bold text-sm">Where are you searching from?</h2>
        <p className="text-xs text-slate-400">{place ? <>Showing deals near <strong className="text-emerald-400">{place}</strong>{active ? ` within ${radius} miles` : ''}</> : 'Pick a location to see nearby deals.'}</p>
      </div>
      <button type="button" className="btn-primary w-full py-3 text-sm" onClick={gps} disabled={busy}>{busy ? 'Locating…' : '📍 Use my current location'}</button>
      <form onSubmit={lookup} className="space-y-1">
        <label htmlFor="loc-text" className="text-[11px] text-slate-400">Or enter a ZIP code or city</label>
        <div className="flex gap-2">
          <input id="loc-text" className="min-w-0 flex-1 !py-3 !text-sm" placeholder="e.g. 61602 or Peoria, IL" value={text} onChange={(e) => setText(e.target.value)} />
          <button className="btn-primary px-5" disabled={busy || !text.trim()}>Set</button>
        </div>
      </form>
      {active && (
        <div className="flex items-end gap-2">
          <label className="flex-1 space-y-1 text-[11px] text-slate-400">Range
            <select className="w-full !py-3 !text-sm" value={radius} onChange={(e) => setRadius(e.target.value)} aria-label="Search range in miles">
              {[...new Set([5, 10, 25, 50, 100, 200, radius])].sort((a, b) => a - b).map((m) => <option key={m} value={m}>Within {m} miles</option>)}
            </select>
          </label>
          <button type="button" className="btn py-3" onClick={clear}>Reset</button>
        </div>
      )}
      {msg && <p role="alert" className="text-xs text-amber-200">{msg}</p>}
    </section>
  );
}
