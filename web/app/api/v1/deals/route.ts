import { NextRequest, NextResponse } from 'next/server';
import { queryDeals, SORT_OPTIONS, type SortOption } from '@/lib/deals';
import { parseOrigin } from '@/lib/origin';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const u = req.nextUrl.searchParams;
  const flag = (k: string) => u.get(k) === 'true';
  const num = (k: string, d: number) => { const n = Number(u.get(k)); return Number.isFinite(n) && n > 0 ? n : d; };
  const origin = parseOrigin((k) => u.get(k));
  if (!origin && !u.get('region_id')) return NextResponse.json({ detail: { code: 'region_required', message: 'region_id is required' } }, { status: 400 });
  const sortParam = u.get('sort');
  const sort = SORT_OPTIONS.includes(sortParam as never) ? (sortParam as SortOption) : undefined;
  const page = await queryDeals({
    region_id: u.get('region_id') ?? '', origin: origin ?? undefined, license_type: u.get('license_type') || undefined, category: u.get('category') || undefined,
    q: (u.get('q') || '').slice(0, 300), include_stale: flag('include_stale'), include_unverified: flag('include_unverified'),
    flower_grade: u.get('flower_grade') || 'whole', strain_type: u.get('strain_type') || undefined, size: u.get('size') || undefined, promo: u.get('promo') || undefined, group: flag('group'),
    sort,
    page: num('page', 1), page_size: Math.min(200, num('page_size', 50)),
  });
  return NextResponse.json(page);
}
