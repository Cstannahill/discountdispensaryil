import AsyncStorage from '@react-native-async-storage/async-storage';

// Last results per search, so the app opens with deals on screen and still works with no signal.
const PREFIX = 'ddil.cache.';
const INDEX = 'ddil.cache-index';
export const MAX_ENTRIES = 12;

export interface Cached<T> { at: number; data: T }

export const cacheKey = (params: Record<string, string | undefined>) =>
  Object.keys(params).filter((k) => params[k] != null && params[k] !== '' && k !== 'page').sort().map((k) => `${k}=${params[k]}`).join('&');

export async function readCache<T>(key: string): Promise<Cached<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as Cached<T>) : null;
  } catch { return null; }
}

export async function writeCache<T>(key: string, data: T): Promise<void> {
  try {
    const index: string[] = JSON.parse((await AsyncStorage.getItem(INDEX)) || '[]');
    const next = [key, ...index.filter((k) => k !== key)];
    const drop = next.splice(MAX_ENTRIES);
    await AsyncStorage.setItem(PREFIX + key, JSON.stringify({ at: Date.now(), data } satisfies Cached<T>));
    await AsyncStorage.setItem(INDEX, JSON.stringify(next));
    if (drop.length) await AsyncStorage.multiRemove(drop.map((k) => PREFIX + k));
  } catch { /* cache is best effort */ }
}
