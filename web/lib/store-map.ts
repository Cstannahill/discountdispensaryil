import { rows } from './db.ts';
import { gradeOf, SERVING_MG, type Origin } from './deals.ts';

// Map data for the mobile app: every dispensary in the search area with its coordinates and address, plus its single
// best-value comparable deal in one category. The web pages do not use this; they keep storesInArea and queryDeals.
export interface MapStore {
  id: string; name: string; address: string | null; city: string | null; state: string | null;
  latitude: number; longitude: number; distance_miles: number;
  /** Deals in this category that would appear in the default list (fresh or last-good menu, grade A, not an outlier). */
  deals: number;
  best: null | {
    offer_id: string; name: string; brand: string | null; unit_price: string; effective_price: string | null;
    weight_grams: string | null; dose_mg: string | null; freshness: 'fresh' | 'stale'; menu_age_hours: number | null;
  };
}
export interface MapQuery { origin: Origin; license_type?: string; category?: string }

export const MAP_CATEGORIES = ['flower', 'concentrate', 'vapes', 'edibles'] as const;

/** The SQL and parameters for storesForMap, split out so tests can run it against a real Postgres. */
export function storeMapQuery(q: MapQuery): { text: string; params: unknown[] } {
  const p: unknown[] = [];
  const arg = (v: unknown) => (p.push(v), `$${p.length}`);
  const o = q.origin;
  const category = MAP_CATEGORIES.includes(q.category as never) ? q.category! : 'flower';
  const lat = arg(o.latitude), lon = arg(o.longitude), radius = arg(o.radius_miles);
  const lic = q.license_type ? arg(q.license_type) : null;
  const cat = arg(category);
  // Same value measure as the deal list: price per gram, or per 10 mg THC for edibles.
  const unit = `CASE WHEN j->>'category'='edibles' THEN NULLIF(j->>'effective_price','')::numeric / nullif(NULLIF(j->>'dose_mg','')::numeric, 0) * ${SERVING_MG}
       ELSE NULLIF(j->>'effective_price','')::numeric / nullif(NULLIF(j->>'weight_grams','')::numeric, 0) END`;
  const text = `
WITH r AS (SELECT ${lat}::float8 AS latitude, ${lon}::float8 AS longitude, ${radius}::float8 AS radius_miles),
st0 AS (
  SELECT s.id, coalesce((SELECT i.name FROM live_store_identity i WHERE i.store_id=s.id AND i.kind='rebrand' ORDER BY i.id DESC LIMIT 1), s.name) AS name,
         s.address, s.city, s.state, s.latitude AS lat, s.longitude AS lon,
         3958.8*2*asin(sqrt(least(1,greatest(0, power(sin(radians(s.latitude-r.latitude)/2),2)
           +cos(radians(r.latitude))*cos(radians(s.latitude))*power(sin(radians(s.longitude-r.longitude)/2),2))))) AS distance_miles
  FROM live_stores s CROSS JOIN r WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL AND coalesce(s.operating_status,'') <> 'closed'),
st AS MATERIALIZED (
  SELECT st0.* FROM st0 WHERE st0.distance_miles <= (SELECT radius_miles FROM r)
    AND EXISTS (SELECT 1 FROM live_endpoints e WHERE e.store_id=st0.id AND e.status<>'superseded' ${lic ? `AND e.license_type=${lic}` : ''})),
b AS MATERIALIZED (
  SELECT o.id, o.payload_json::jsonb AS j, e.store_id, e.license_type, e.last_success_at
  FROM live_offers o JOIN live_endpoints e ON e.id=o.endpoint_id JOIN st ON st.id=e.store_id
  WHERE o.status='active' AND e.status<>'superseded' ${lic ? `AND e.license_type=${lic}` : ''}),
c AS (
  SELECT b.*, coalesce(j->>'completeness','A') AS completeness,
         CASE WHEN j->>'category'='flower' THEN coalesce(${gradeOf(`(j->>'subcategory')`)}, ${gradeOf(`(j->>'name')`)}, 'whole') END AS fgrade,
         coalesce(extract(epoch FROM now()-(last_success_at)::timestamptz)/3600, 1e9) AS age_h
  FROM b),
d AS (
  SELECT c.*, age_h < 12 AS fresh, coalesce(bool_or(age_h < 12) OVER (PARTITION BY store_id, license_type), false) AS store_fresh
  FROM c WHERE completeness='A'),
e AS (
  SELECT d.*, ${unit} AS unit_price FROM d
  WHERE (j->>'eligible')='true' AND NULLIF(j->>'effective_price','') IS NOT NULL
    AND (CASE WHEN j->>'category'='edibles' THEN NULLIF(j->>'dose_mg','')::numeric ELSE NULLIF(j->>'weight_grams','')::numeric END) > 0
    AND (fresh OR NOT store_fresh) AND (j->>'price_outlier') IS DISTINCT FROM 'true'
    AND (j->>'category')=${cat} AND (fgrade IS NULL OR fgrade='whole')),
k AS (
  SELECT e.*, row_number() OVER (PARTITION BY store_id ORDER BY unit_price ASC NULLS LAST, id) AS rn, count(*) OVER (PARTITION BY store_id) AS n
  FROM e)
SELECT st.id, st.name, st.address, st.city, st.state, st.lat, st.lon, st.distance_miles,
       coalesce(k.n, 0) AS deals, k.id AS offer_id, k.j->>'name' AS offer_name, k.j->>'brand' AS brand, k.unit_price,
       k.j->>'effective_price' AS effective_price, k.j->>'weight_grams' AS weight_grams, k.j->>'dose_mg' AS dose_mg, k.fresh, k.age_h
FROM st LEFT JOIN k ON k.store_id=st.id AND k.rn=1
ORDER BY st.distance_miles, st.name`;
  return { text, params: p };
}

const str = (v: unknown) => (v == null || v === '' ? null : String(v));

export function mapRow(r: Record<string, any>): MapStore {
  return {
    id: String(r.id), name: r.name, address: str(r.address), city: str(r.city), state: str(r.state),
    latitude: Number(r.lat), longitude: Number(r.lon), distance_miles: Math.round(Number(r.distance_miles) * 10) / 10,
    deals: Number(r.deals),
    best: r.offer_id == null || r.unit_price == null ? null : {
      offer_id: String(r.offer_id), name: r.offer_name ?? '', brand: str(r.brand), unit_price: Number(r.unit_price).toFixed(2),
      effective_price: str(r.effective_price), weight_grams: str(r.weight_grams), dose_mg: str(r.dose_mg),
      freshness: r.fresh ? 'fresh' : 'stale', menu_age_hours: Number(r.age_h) < 1e8 ? Math.round(Number(r.age_h)) : null,
    },
  };
}

export async function storesForMap(q: MapQuery): Promise<MapStore[]> {
  const { text, params } = storeMapQuery(q);
  return (await rows<Record<string, any>>(text, params)).map(mapRow);
}
