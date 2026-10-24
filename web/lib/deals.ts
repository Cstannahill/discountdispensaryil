import { rows } from './db';
import { withProductUrl } from './product-links';

export const CATEGORIES = ['concentrate', 'flower', 'vapes'] as const;
export const GRADES = ['whole', 'smalls', 'shake', 'infused', 'all'] as const;
export const LICENSES = ['recreational', 'medicinal'] as const;

export interface Region { id: string; label: string; latitude: number; longitude: number; radius_miles: number; precision: string }
export interface Offer {
  id: string; endpoint_id: string; store_id: string; store_name: string; license_type: string; name: string;
  brand?: string | null; category: string; strain_type?: string | null; thc_pct?: string | null;
  weight_grams: string | null; weight_label?: string | null; regular_price: string | null; effective_price: string | null;
  price_per_gram: string | null; conditional?: boolean; promo?: string | null; completeness: string; freshness: string;
  flower_grade: string | null; distance_miles: number; last_seen_at: string; last_diff_action: string; source_url?: string | null;
  variants?: Variant[];
}
// One strain inside a collapsed group of same-product offers.
export interface Variant { id: string; name: string; strain_type: string | null; thc_pct: string | null; source_url: string | null }
export interface Origin { latitude: number; longitude: number; radius_miles: number }
export interface DealQuery {
  region_id?: string; origin?: Origin; license_type?: string; category?: string; q?: string; include_stale?: boolean; include_unverified?: boolean;
  flower_grade?: string; strain_type?: string; promo?: string; group?: boolean; page?: number; page_size?: number;
}
export interface Page<T> { items: T[]; total: number; page: number; page_size: number; data_version: string }

// Same rules as backend/domain.py flower_grade: source subcategory first, then the name; \y is Postgres' word boundary.
const GRADE_RE = {
  infused: String.raw`\y(?:infused|moon ?rocks?|caviar|kaviar)\y`,
  shake: String.raw`\y(?:shake|trim|(?:pre[ _-]?)?ground|milled)\y`,
  smalls: String.raw`\y(?:popcorn|smalls|mini ?buds?|budlets|littles|lil ?buds|mixed buds|small buds)\y`,
};
const gradeOf = (col: string) =>
  `CASE WHEN ${col} ~* '${GRADE_RE.infused}' THEN 'infused' WHEN ${col} ~* '${GRADE_RE.shake}' THEN 'shake' WHEN ${col} ~* '${GRADE_RE.smalls}' THEN 'smalls' END`;

// Smallest group that collapses: below this, equal price and size at one brand is more likely coincidence than one product line.
export const MIN_GROUP = 3;
// Product-line words that stay in the group key, so "Live Resin Cart" and "Distillate Cart" at one price never merge.
const LINE_RE = String.raw`\y(?:live resin|live rosin|rosin|resin|distillate|diamonds?|badder|batter|budder|crumble|shatter|wax|kief|cartridge|cart|pod|disposable|pre-?rolls?|infused|solventless)\y`;

/** Indica / Sativa / Hybrid bucket for a source strain label; dominant-leaning labels follow their lean. */
export function strainBucket(v?: string | null): 'Indica' | 'Sativa' | 'Hybrid' | 'Unspecified' {
  const t = (v ?? '').toLowerCase();
  return t.includes('indica') ? 'Indica' : t.includes('sativa') ? 'Sativa' : t.includes('hybrid') ? 'Hybrid' : 'Unspecified';
}

export async function regions(): Promise<{ items: Region[]; active_region_id: string | null }> {
  const [items, active] = await Promise.all([
    rows<Omit<Region, 'radius_miles'> & { radius_miles: string }>('SELECT * FROM live_regions ORDER BY created_at DESC'),
    rows<{ value: string }>(`SELECT value FROM live_settings WHERE key='active_region_id'`),
  ]);
  return {
    items: items.map((r) => ({ ...r, radius_miles: Number(r.radius_miles) })),
    active_region_id: active[0] ? JSON.parse(active[0].value) : null,
  };
}

export async function dataVersion(): Promise<string> {
  const r = await rows<{ value: string }>(`SELECT value FROM live_settings WHERE key='data_version'`);
  return String(r[0] ? JSON.parse(r[0].value) : 0);
}

// Mirrors StoreDB.query_offers: eligible, active, fresh (12h), grade A and not a price outlier unless include_unverified, whole flower unless asked,
// ranked by effective price per gram then distance. Filtering, ranking and paging all happen in Postgres.
export async function queryDeals(q: DealQuery): Promise<Page<Offer>> {
  const page = Math.max(1, q.page ?? 1);
  const size = Math.min(200, Math.max(1, q.page_size ?? 20));
  const p: unknown[] = [];
  const arg = (v: unknown) => (p.push(v), `$${p.length}`);
  const o = q.origin;
  const rsel = o
    ? `SELECT ${arg(o.latitude)}::float8 AS latitude, ${arg(o.longitude)}::float8 AS longitude, ${arg(o.radius_miles)}::float8 AS radius_miles`
    : `SELECT latitude, longitude, radius_miles FROM live_regions WHERE id=${arg(q.region_id ?? '')}`;
  const where: string[] = ['true'];
  if (q.license_type) where.push(`license_type=${arg(q.license_type)}`);
  if (q.promo === 'bogo') {
    // Conditional BOGO promotions: their own list, never ranked with comparable deals.
    where.push(`j->>'promo'='bogo'`, `fresh`, `completeness='A'`, `(j->>'category') IN ('flower','concentrate','vapes')`);
  } else {
    where.push(`(j->>'eligible')='true'`, `NULLIF(j->>'weight_grams','')::numeric > 0`, `NULLIF(j->>'effective_price','') IS NOT NULL`);
    if (!q.include_stale) where.push('fresh');
    // price_outlier is stamped by the mirror (backend/matching.py): far under the same product at other stores.
    if (!q.include_unverified) where.push(`completeness='A'`, `(j->>'price_outlier') IS DISTINCT FROM 'true'`);
  }
  if (q.category && q.category !== 'all') where.push(`(j->>'category')=${arg(q.category)}`);
  if (q.strain_type && q.strain_type.toLowerCase() !== 'all') where.push(`lower(coalesce(j->>'strain_type',''))=${arg(q.strain_type.toLowerCase())}`);
  if (q.q) where.push(`position(${arg(q.q.toLowerCase())} in lower(concat_ws(' ',j->>'name',j->>'brand',store_name,j->>'subcategory')))>0`);
  const grade = q.flower_grade ?? 'whole';
  if (grade !== 'all') where.push(`(fgrade IS NULL OR fgrade=${arg(grade)})`);
  const text = `
WITH r AS (${rsel}),
st AS MATERIALIZED (
  SELECT s.id, coalesce((SELECT i.name FROM live_store_identity i WHERE i.store_id=s.id AND i.kind='rebrand' ORDER BY i.id DESC LIMIT 1), s.name) AS name, s.latitude AS lat, s.longitude AS lon,
         3958.8*2*asin(sqrt(least(1,greatest(0, power(sin(radians(s.latitude-r.latitude)/2),2)
           +cos(radians(r.latitude))*cos(radians(s.latitude))*power(sin(radians(s.longitude-r.longitude)/2),2))))) AS distance_miles
  FROM live_stores s CROSS JOIN r WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL),
b AS MATERIALIZED (
  SELECT o.id, o.endpoint_id, o.status, o.last_diff_action, o.last_seen_at, o.snapshot_id, o.payload_json::jsonb AS j,
         e.store_id, e.license_type, e.status AS ep_status, e.url AS endpoint_url, e.provider, e.last_success_at, e.last_converged_at,
         st.name AS store_name, st.distance_miles
  FROM live_offers o JOIN live_endpoints e ON e.id=o.endpoint_id JOIN st ON st.id=e.store_id
  WHERE o.status='active' AND e.status<>'superseded' AND st.distance_miles <= (SELECT radius_miles FROM r)),
c AS MATERIALIZED (
  SELECT b.*, coalesce(j->>'completeness','A') AS completeness,
         CASE WHEN j->>'category'='flower' THEN coalesce(${gradeOf(`(j->>'subcategory')`)}, ${gradeOf(`(j->>'name')`)}, 'whole') END AS fgrade
  FROM b),
d AS (
  SELECT c.*, coalesce(extract(epoch FROM now()-(CASE WHEN completeness='B' THEN last_converged_at ELSE last_success_at END)::timestamptz)/3600, 1e9) < 12 AS fresh
  FROM c),
e AS (
  SELECT d.*, concat_ws('|', store_id, license_type, j->>'category', lower(trim(coalesce(j->>'brand',''))), j->>'weight_grams', j->>'effective_price', coalesce(fgrade,''),
           lower(coalesce(j->>'subcategory','')), coalesce(j->>'promo',''), coalesce(j->>'conditional',''),
           coalesce((SELECT string_agg(m[1], ',' ORDER BY m[1]) FROM regexp_matches(lower(coalesce(j->>'name','')), '${LINE_RE}', 'g') m), '')) AS gkey
  FROM d WHERE ${where.join(' AND ')}),
f AS (SELECT e.*, ${q.group ? `CASE WHEN count(*) OVER (PARTITION BY gkey) >= ${MIN_GROUP} THEN gkey ELSE id END` : 'id'} AS gk FROM e),
reps AS (SELECT DISTINCT ON (gk) gk, j, distance_miles, id FROM f ORDER BY gk, id),
pg AS (
  SELECT gk, row_number() OVER (ORDER BY (j->>'effective_price')::numeric/(j->>'weight_grams')::numeric, round(distance_miles::numeric,3), id) AS ord, count(*) OVER() AS total
  FROM reps ORDER BY ord LIMIT ${arg(size)} OFFSET ${arg((page - 1) * size)})
SELECT f.id, endpoint_id, last_diff_action, last_seen_at, snapshot_id, j, store_id, license_type, store_name, endpoint_url, provider,
       completeness, fgrade, distance_miles, fresh, gk, total
FROM f JOIN pg USING (gk) ORDER BY ord, f.id`;
  const [data, version] = await Promise.all([rows<Record<string, any>>(text, p), dataVersion()]);
  const offers = data.map((r) => {
    const { raw: _raw, ...j } = r.j; // raw feeds withProductUrl below
    return {
      ...j,
      id: r.id, endpoint_id: r.endpoint_id, store_id: r.store_id, license_type: r.license_type, status: 'active',
      last_diff_action: r.last_diff_action, last_seen_at: r.last_seen_at, snapshot_id: r.snapshot_id,
      store_name: r.store_name, distance_miles: Math.round(Number(r.distance_miles) * 1000) / 1000,
      completeness: r.completeness, freshness: r.fresh ? 'fresh' : 'stale', flower_grade: r.fgrade,
      source_url: withProductUrl(r.j, r.provider, r.endpoint_url, r.license_type),
      gk: r.gk,
    };
  });
  // Members of one group arrive together (ordered by the group's rank); the first row stands for the group.
  const items: Offer[] = [];
  const seen = new Map<string, Offer>();
  for (const { gk, ...o } of offers) {
    const lead = seen.get(gk);
    if (!lead) { seen.set(gk, o); items.push(o); }
    const members: Variant[] = (lead ?? o).variants ??= [];
    const key = (o.name ?? '').trim().toLowerCase();
    if (!members.some((v) => (v.name ?? '').trim().toLowerCase() === key)) members.push({ id: o.id, name: (o.name ?? '').trim(), strain_type: o.strain_type ?? null, thc_pct: o.thc_pct ?? null, source_url: o.source_url ?? null });
  }
  for (const o of items) if ((o.variants?.length ?? 0) < 2) delete o.variants; // a lone strain is an ordinary card
  return { items, total: data[0] ? Number(data[0].total) : 0, page, page_size: size, data_version: version };
}
