import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';

import { DEFAULT_FILTERS, type Filters, type Offer, type Origin, type SavedDeal } from '@/lib/types';
import { isGrouped, massLabel, safeUrl } from '@/lib/format';

// One small persisted store: where the user is, how they search, what they saved and which dispensaries they hid.
export interface CalcPrefill { price: string; weight: string; license: string; category: string; flower_grade: string | null; thc_pct: string | null; label: string; nonce: number }
export interface AppState {
  ready: boolean;
  origin: Origin | null;
  filters: Filters;
  hidden: string[];
  hiddenNames: Record<string, string>;
  saved: SavedDeal[];
  calc: CalcPrefill | null;
  /** Price-drop notifications for saved deals are switched on. */
  alerts: boolean;
}

const KEY = 'ddil.state.v1';
const MAX_HIDDEN = 100; // the API accepts at most 100 hidden ids
let state: AppState = { ready: false, origin: null, filters: DEFAULT_FILTERS, hidden: [], hiddenNames: {}, saved: [], calc: null, alerts: false };
const listeners = new Set<() => void>();

function persist() {
  const { origin, filters, hidden, hiddenNames, saved, alerts } = state;
  AsyncStorage.setItem(KEY, JSON.stringify({ origin, filters: { ...filters, q: '' }, hidden, hiddenNames, saved, alerts })).catch(() => {});
}

function set(patch: Partial<AppState>, save = true) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
  if (save && state.ready) persist();
}

export async function hydrate(): Promise<void> {
  if (state.ready) return;
  let stored: Partial<AppState> = {};
  try { stored = JSON.parse((await AsyncStorage.getItem(KEY)) || '{}'); } catch { /* start clean */ }
  set({
    ready: true,
    origin: stored.origin ?? null,
    filters: { ...DEFAULT_FILTERS, ...(stored.filters ?? {}), q: '' },
    hidden: Array.isArray(stored.hidden) ? stored.hidden : [],
    hiddenNames: stored.hiddenNames ?? {},
    saved: Array.isArray(stored.saved) ? stored.saved : [],
    alerts: stored.alerts === true,
  }, false);
}

const subscribe = (l: () => void) => (listeners.add(l), () => listeners.delete(l));
export const getState = () => state;
export function useAppState<T>(pick: (s: AppState) => T): T {
  return useSyncExternalStore(subscribe, () => pick(state), () => pick(state));
}

export const setOrigin = (origin: Origin) => set({ origin });
export const setFilters = (patch: Partial<Filters>) => set({ filters: { ...state.filters, ...patch } });
export const resetFilters = () => set({ filters: { ...DEFAULT_FILTERS, license: state.filters.license, category: state.filters.category, radius: state.filters.radius, q: state.filters.q } });

/** Returns false when the hidden list is full. */
export function setStoreHidden(id: string, name: string, hide: boolean): boolean {
  if (hide) {
    if (state.hidden.includes(id)) return true;
    if (state.hidden.length >= MAX_HIDDEN) return false;
    set({ hidden: [...state.hidden, id], hiddenNames: { ...state.hiddenNames, [id]: name } });
  } else {
    const { [id]: _gone, ...names } = state.hiddenNames;
    set({ hidden: state.hidden.filter((x) => x !== id), hiddenNames: names });
  }
  return true;
}
export const clearHidden = () => set({ hidden: [], hiddenNames: {} });

export function savedFromOffer(o: Offer): SavedDeal {
  const mass = massLabel(o);
  return {
    id: o.id, store_id: o.store_id, name: isGrouped(o) ? `${o.brand || 'Offer'} (${mass})` : o.name, match_name: o.name, brand: o.brand, store_name: o.store_name,
    price_per_gram: o.price_per_gram, price_per_10mg: o.price_per_10mg, effective_price: o.effective_price, regular_price: o.regular_price,
    massLabel: mass, category: o.category, source_url: safeUrl(o.source_url) ?? null, distance_miles: o.distance_miles, saved_at: Date.now(),
    weight_grams: o.weight_grams, dose_mg: o.dose_mg, license_type: o.license_type, flower_grade: o.flower_grade, thc_pct: o.thc_pct,
    near: state.origin ? { lat: state.origin.lat, lon: state.origin.lon } : null,
  };
}

/** Returns true when the deal is now saved. */
export function toggleSaved(o: Offer): boolean {
  const on = state.saved.some((s) => s.id === o.id);
  set({ saved: on ? state.saved.filter((s) => s.id !== o.id) : [savedFromOffer(o), ...state.saved] });
  return !on;
}
export const removeSaved = (id: string) => set({ saved: state.saved.filter((s) => s.id !== id) });
/** Replaces a saved deal with its current listing, so the next comparison starts from today's price. */
export const refreshSaved = (id: string, o: Offer) =>
  set({ saved: state.saved.map((s) => (s.id === id ? { ...savedFromOffer(o), name: s.name, saved_at: s.saved_at, near: s.near, distance_miles: s.distance_miles } : s)) });

export const openCalculatorWith = (c: Omit<CalcPrefill, 'nonce'>) => set({ calc: { ...c, nonce: Date.now() } }, false);

export const setAlerts = (alerts: boolean) => set({ alerts });
