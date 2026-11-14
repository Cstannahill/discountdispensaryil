import { API_BASE, PAGE_SIZE } from './config';
import type { AreaStore, Filters, MapStore, Offer, Origin, Page, SavedDeal } from './types';

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) { super(message); }
}

async function get<T>(path: string, params: Record<string, string | undefined>, signal?: AbortSignal): Promise<T> {
  const qs = Object.entries(params).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v as string)}`).join('&');
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${qs ? `?${qs}` : ''}`, { signal, headers: { Accept: 'application/json' } });
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') throw e;
    throw new ApiError('No connection', 0, 'offline');
  }
  let body: any = null;
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) throw new ApiError(body?.detail?.message || `Request failed (${res.status})`, res.status, body?.detail?.code);
  return body as T;
}

const originParams = (o: Origin, radius: number) => ({ lat: o.lat.toFixed(4), lon: o.lon.toFixed(4), radius: String(radius) });

/** Query params for /api/v1/deals, matching what the web page sends. Also the cache key for a result list. */
export function dealParams(o: Origin, f: Filters, hidden: readonly string[], page = 1): Record<string, string | undefined> {
  const edibles = f.category === 'edibles';
  return {
    ...originParams(o, f.radius),
    license_type: f.license,
    category: f.category,
    q: f.q.trim() || undefined,
    sort: f.sort !== 'value' ? f.sort : undefined,
    flower_grade: f.category === 'flower' ? f.grade : 'all',
    strain_type: f.strain || undefined,
    size: !edibles && f.size !== 'any' ? f.size : undefined,
    include_stale: f.stale ? 'true' : undefined,
    include_unverified: f.unverified ? 'true' : undefined,
    hide: hidden.length ? hidden.join(',') : undefined,
    group: 'true',
    page: String(page),
    page_size: String(PAGE_SIZE),
  };
}

export const fetchDeals = (params: Record<string, string | undefined>, signal?: AbortSignal) => get<Page<Offer>>('/api/v1/deals', params, signal);

export const fetchStores = (o: Origin, radius: number, license: string, signal?: AbortSignal) =>
  get<{ items: AreaStore[]; total: number }>('/api/v1/stores', { ...originParams(o, radius), license_type: license }, signal).then((r) => r.items);

export const mapParams = (o: Origin, radius: number, license: string, category: string) => ({ ...originParams(o, radius), license_type: license, category });
export const fetchMapStores = (params: Record<string, string | undefined>, signal?: AbortSignal) =>
  get<{ items: MapStore[]; total: number }>('/api/v1/stores/map', params, signal).then((r) => r.items);

export const geocode = (q: string) => get<{ label: string; latitude: number; longitude: number }>('/api/v1/geocode', { q });

export const reverseGeocode = (lat: number, lon: number) =>
  get<{ label: string }>('/api/v1/geocode', { lat: lat.toFixed(4), lon: lon.toFixed(4) }).then((r) => r.label);

/** Current listings that could be a saved deal: the same search point, a radius that still covers its store, every grade and menu age. */
export function savedLookupParams(d: SavedDeal): Record<string, string | undefined> | null {
  if (!d.near) return null;
  return {
    lat: d.near.lat.toFixed(4), lon: d.near.lon.toFixed(4), radius: String(Math.min(200, Math.ceil(d.distance_miles) + 5)),
    license_type: d.license_type || undefined, category: d.category, q: d.match_name.slice(0, 300), flower_grade: 'all',
    include_stale: 'true', include_unverified: 'true', page_size: '50',
  };
}
