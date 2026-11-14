import type { Offer, SavedDeal } from './types';

export type WatchStatus =
  | { kind: 'same' }
  | { kind: 'drop'; from: number; to: number }
  | { kind: 'rise'; from: number; to: number }
  | { kind: 'gone' };

const norm = (s?: string | null) => (s ?? '').trim().toLowerCase();
const num = (v?: string | null) => { const n = Number(v); return v != null && v !== '' && Number.isFinite(n) ? n : null; };

/** The saved product on a current menu: the same offer id, else the same store, product name and size. */
export function findCurrent(saved: SavedDeal, offers: readonly Offer[]): Offer | null {
  const same = (o: Offer) => o.store_id === saved.store_id && norm(o.name) === norm(saved.match_name)
    && (num(o.weight_grams) ?? num(o.dose_mg ?? null)) === (num(saved.weight_grams ?? null) ?? num(saved.dose_mg ?? null));
  return offers.find((o) => o.id === saved.id) ?? offers.find(same) ?? null;
}

/** Compares the saved price with the current one; changes under 1 cent count as unchanged. */
export function watchStatus(saved: SavedDeal, current: Offer | null): WatchStatus {
  if (!current) return { kind: 'gone' };
  const from = num(saved.effective_price ?? null), to = num(current.effective_price);
  if (from == null || to == null || Math.abs(from - to) < 0.01) return { kind: 'same' };
  return to < from ? { kind: 'drop', from, to } : { kind: 'rise', from, to };
}
