import { NextRequest, NextResponse } from 'next/server';
import { unstable_cache } from 'next/cache';
import { cachedVersion } from '@/lib/cached';
import { parseOrigin } from '@/lib/origin';
import { storesForMap } from '@/lib/store-map';

export const dynamic = 'force-dynamic';

// Same caching rule as the deal lists: results only change when a sync publishes a new data_version.
const mapForVersion = unstable_cache(
  (_version: string, q: Parameters<typeof storesForMap>[0]) => storesForMap(q),
  ['stores-map'],
  { revalidate: 3600 }
);

// Dispensaries in the search area with coordinates, address and their best deal in one category. Used by the mobile app's map.
export async function GET(req: NextRequest) {
  const u = req.nextUrl.searchParams;
  const origin = parseOrigin((k) => u.get(k));
  if (!origin) return NextResponse.json({ detail: { code: 'origin_required', message: 'lat and lon are required' } }, { status: 400 });
  const { latitude, longitude, radius_miles } = origin;
  const items = await mapForVersion(await cachedVersion(), {
    // Rounded to about 100 m so nearby requests share a cache entry.
    origin: { latitude: Math.round(latitude * 1000) / 1000, longitude: Math.round(longitude * 1000) / 1000, radius_miles },
    license_type: u.get('license_type') || undefined,
    category: u.get('category') || undefined,
  });
  return NextResponse.json({ items, total: items.length });
}
