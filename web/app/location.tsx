'use client';
import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

const KEY = 'terpscout.origin';
type Pick = { lat: number; lon: number; place: string };

// Lets a visitor use their device location or a ZIP/city instead of the server's saved region; the choice lives in the URL and localStorage.
export default function LocationControl({ active }: { active: boolean }) {
  const router = useRouter();
  const sp = useSearchParams();
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');

  const go = (o: Pick) => {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch {}
    const u = new URLSearchParams(sp.toString());
    u.set('lat', o.lat.toFixed(5)); u.set('lon', o.lon.toFixed(5)); u.set('place', o.place); u.delete('region');
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
  const clear = () => { try { localStorage.removeItem(KEY); } catch {} router.push('/'); };

  return (
    <div className="glass-card rounded-2xl p-4 space-y-2">
      <form onSubmit={lookup} className="flex flex-wrap gap-2 items-end">
        <button type="button" className="btn" onClick={gps} disabled={busy}>{busy ? 'Locating…' : 'Use my location'}</button>
        <input className="min-w-0 flex-1" aria-label="ZIP or City, ST" placeholder="ZIP or City, ST (e.g. 61602)" value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn-primary" disabled={busy || !text.trim()}>Set</button>
        {active && <button type="button" className="btn" onClick={clear}>Reset</button>}
      </form>
      {msg && <p role="alert" className="text-xs text-amber-200">{msg}</p>}
    </div>
  );
}
