import type { MapStore } from './types';

/** The store whose best deal is the cheapest per unit among stores the user has not hidden. */
export function cheapest(stores: readonly MapStore[], hidden: readonly string[]): MapStore | null {
  let top: MapStore | null = null;
  for (const s of stores) if (s.best && !hidden.includes(s.id) && (!top || Number(s.best.unit_price) < Number(top.best!.unit_price))) top = s;
  return top;
}
