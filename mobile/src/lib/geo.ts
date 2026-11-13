// Same thresholds as the web app (web/app/location.tsx), except the re-check is cheap natively so it runs sooner.
export const RECHECK_MS = 5 * 60 * 1000;
export const MIN_MOVE_MI = 3; // ignore GPS jitter below this
export const PROMPT_MOVE_MI = 25; // ask before swapping for moves above this

export interface Point { lat: number; lon: number }

export function miles(a: Point, b: Point): number {
  const R = 3958.8, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}

export type MoveAction = 'keep' | 'swap' | 'ask';

/** What to do with a new GPS fix when a saved GPS origin exists. */
export function moveAction(saved: Point, current: Point): MoveAction {
  const d = miles(saved, current);
  return d < MIN_MOVE_MI ? 'keep' : d <= PROMPT_MOVE_MI ? 'swap' : 'ask';
}

/** Only a GPS origin is re-checked, and only once the last fix is old enough. A manual pick is never overwritten. */
export function shouldRecheck(origin: { src: 'gps' | 'manual'; at: number } | null, nowMs = Date.now()): boolean {
  return !!origin && origin.src === 'gps' && nowMs - origin.at >= RECHECK_MS;
}

const US_STATES: Record<string, string> = { illinois: 'IL', indiana: 'IN', wisconsin: 'WI', iowa: 'IA', missouri: 'MO', kentucky: 'KY', michigan: 'MI' };

/** "City, ST" from a device reverse-geocode result; null when it carries no place name. */
export function placeLabel(a?: { city?: string | null; subregion?: string | null; district?: string | null; region?: string | null } | null): string | null {
  const city = a?.city || a?.district || a?.subregion;
  if (!city) return null;
  const region = (a?.region ?? '').trim();
  const st = region.length === 2 ? region.toUpperCase() : US_STATES[region.toLowerCase()] ?? region;
  return st ? `${city}, ${st}` : city;
}

export interface Region { latitude: number; longitude: number; latitudeDelta: number; longitudeDelta: number }

/** A map region that shows the search centre and every pin, with a margin; falls back to the search radius when there are no pins. */
export function regionFor(center: Point, radiusMiles: number, pins: readonly { latitude: number; longitude: number }[]): Region {
  const milesPerLat = 69, milesPerLon = Math.max(1, 69 * Math.cos(center.lat * Math.PI / 180));
  if (!pins.length) return { latitude: center.lat, longitude: center.lon, latitudeDelta: (radiusMiles * 2) / milesPerLat, longitudeDelta: (radiusMiles * 2) / milesPerLon };
  const lats = [center.lat, ...pins.map((p) => p.latitude)], lons = [center.lon, ...pins.map((p) => p.longitude)];
  const minLat = Math.min(...lats), maxLat = Math.max(...lats), minLon = Math.min(...lons), maxLon = Math.max(...lons);
  return {
    latitude: (minLat + maxLat) / 2, longitude: (minLon + maxLon) / 2,
    latitudeDelta: Math.max(0.02, (maxLat - minLat) * 1.3), longitudeDelta: Math.max(0.02, (maxLon - minLon) * 1.3),
  };
}
