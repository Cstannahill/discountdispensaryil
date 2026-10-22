import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const fail = (status: number, code: string, message: string) => NextResponse.json({ detail: { code, message } }, { status });

// Resolves a US ZIP or "City, ST" to coordinates so people can set their own origin when GPS is unavailable.
export async function GET(req: NextRequest) {
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
