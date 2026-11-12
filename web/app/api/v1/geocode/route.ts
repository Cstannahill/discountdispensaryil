import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const fail = (status: number, code: string, message: string) => NextResponse.json({ detail: { code, message } }, { status });

// Resolves a US ZIP or "City, ST" to coordinates so people can set their own origin when GPS is unavailable.
export async function GET(req: NextRequest) {
  // Reverse lookup: ?lat=&lon= returns a "City, ST" label for a GPS point.
  const rl = req.nextUrl.searchParams.get('lat'), ro = req.nextUrl.searchParams.get('lon');
  if (rl && ro) {
    const lat = Number(rl), lon = Number(ro);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return fail(400, 'bad_coordinates', 'Invalid coordinates');
    try {
      const r = await fetch('https://nominatim.openstreetmap.org/reverse?' + new URLSearchParams({ lat: lat.toFixed(4), lon: lon.toFixed(4), format: 'jsonv2', zoom: '10', addressdetails: '1' }),
        { cache: 'no-store', headers: { 'User-Agent': 'terpscout-web/0.1 (location lookup)' } });
      const a = r.ok ? (await r.json())?.address : null;
      const city = a?.city || a?.town || a?.village || a?.hamlet || a?.municipality || a?.county;
      const st = typeof a?.['ISO3166-2-lvl4'] === 'string' ? a['ISO3166-2-lvl4'].replace(/^US-/, '') : a?.state;
      if (!city) return fail(404, 'not_found', 'No place name for these coordinates');
      return NextResponse.json({ label: st ? `${city}, ${st}` : String(city) });
    } catch {
      return fail(502, 'lookup_failed', 'Location lookup failed');
    }
  }
  const q = (req.nextUrl.searchParams.get('q') || '').trim().slice(0, 120);
  if (!q) return fail(400, 'query_required', 'Enter a ZIP or city');
  try {
    if (/^\d{5}(-\d{4})?$/.test(q)) {
      const zip = q.slice(0, 5);
      const r = await fetch(`https://api.zippopotam.us/us/${zip}`, { cache: 'no-store' });
      const p = r.ok ? (await r.json())?.places?.[0] : null;
      if (!p) return fail(404, 'not_found', `ZIP ${zip} was not found`);
      return NextResponse.json({ label: `${p['place name']}, ${p['state abbreviation']} ${zip}`, latitude: Number(p.latitude), longitude: Number(p.longitude) });
    }
    const r = await fetch('https://nominatim.openstreetmap.org/search?' + new URLSearchParams({ q, format: 'jsonv2', countrycodes: 'us', limit: '1' }),
      { cache: 'no-store', headers: { 'User-Agent': 'terpscout-web/0.1 (location lookup)' } });
    const j = r.ok ? await r.json() : [];
    if (!Array.isArray(j) || !j[0]) return fail(404, 'not_found', `"${q}" was not found; try a ZIP or City, ST`);
    return NextResponse.json({ label: String(j[0].display_name).split(',').slice(0, 2).join(',').trim(), latitude: Number(j[0].lat), longitude: Number(j[0].lon) });
  } catch {
    return fail(502, 'lookup_failed', 'Location lookup failed; try again');
  }
}
