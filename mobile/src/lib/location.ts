import * as Location from 'expo-location';

import { reverseGeocode } from './api';
import { placeLabel } from './geo';
import type { Origin } from './types';

export type FixResult = { ok: true; origin: Origin } | { ok: false; reason: 'denied' | 'unavailable' };

/** A place name for a GPS point: the phone's own geocoder first, then the web API, then a plain fallback. */
export async function labelFor(lat: number, lon: number): Promise<string> {
  if (process.env.EXPO_OS !== 'web') {
    try {
      const label = placeLabel((await Location.reverseGeocodeAsync({ latitude: lat, longitude: lon }))[0]);
      if (label) return label;
    } catch { /* fall through to the API */ }
  }
  try { return await reverseGeocode(lat, lon); } catch { return 'Current location'; }
}

/** Reads the device position. `ask` shows the permission prompt; without it a missing permission just fails quietly. */
export async function currentFix(ask: boolean): Promise<FixResult> {
  try {
    let perm = await Location.getForegroundPermissionsAsync();
    if (!perm.granted && ask && perm.canAskAgain) perm = await Location.requestForegroundPermissionsAsync();
    if (!perm.granted) return { ok: false, reason: 'denied' };
    const pos = (await Location.getLastKnownPositionAsync({ maxAge: 60_000, requiredAccuracy: 2000 }))
      ?? (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }));
    const { latitude: lat, longitude: lon } = pos.coords;
    return { ok: true, origin: { lat, lon, place: await labelFor(lat, lon), src: 'gps', at: Date.now() } };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}
