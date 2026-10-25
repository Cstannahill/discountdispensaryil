import type { Origin } from './deals.ts';

// Parses an ad-hoc origin (browser GPS or a geocoded ZIP/city) from query params; null when absent or out of range.
export function parseOrigin(get: (k: string) => string | null | undefined): (Origin & { label: string }) | null {
  const la = get('lat'), lo = get('lon');
  if (!la || !lo) return null;
  const lat = Number(la), lon = Number(lo);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  const r = Number(get('radius'));
  const radius = Number.isFinite(r) && r > 0 ? Math.min(r, 200) : 50;
  return { latitude: lat, longitude: lon, radius_miles: radius, label: (get('place') || 'Your location').slice(0, 80) };
}
