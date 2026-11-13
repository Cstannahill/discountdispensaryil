import { NextRequest, NextResponse } from 'next/server';
import { storesInArea } from '@/lib/deals';
import { parseOrigin } from '@/lib/origin';

export const dynamic = 'force-dynamic';

// Dispensaries inside the search area (a lat/lon/radius origin, or a saved region_id).
export async function GET(req: NextRequest) {
  const u = req.nextUrl.searchParams;
  const origin = parseOrigin((k) => u.get(k));
  if (!origin && !u.get('region_id')) return NextResponse.json({ detail: { code: 'region_required', message: 'region_id is required' } }, { status: 400 });
  const items = await storesInArea({ region_id: u.get('region_id') ?? '', origin: origin ?? undefined, license_type: u.get('license_type') || undefined });
  return NextResponse.json({ items, total: items.length });
}
