import { fetchDeals, savedLookupParams } from './api';
import { money } from './format';
import { findCurrent, watchStatus, type WatchStatus } from './price-watch';
import type { Offer, SavedDeal } from './types';

export type Check = { status: WatchStatus; current: Offer | null };
export const MAX_CHECKS = 30;

async function checkOne(d: SavedDeal): Promise<Check | null> {
  const params = savedLookupParams(d);
  if (!params) return null;
  try {
    const current = findCurrent(d, (await fetchDeals(params)).items);
    return { status: watchStatus(d, current), current };
  } catch { return null; } // unknown, not "gone"
}

/** Looks each saved deal up on today's menu, four at a time. Deals that could not be checked are left out. */
export async function checkSaved(saved: readonly SavedDeal[]): Promise<Record<string, Check>> {
  const list = saved.slice(0, MAX_CHECKS);
  const out: Record<string, Check> = {};
  for (let i = 0; i < list.length; i += 4) {
    const res = await Promise.all(list.slice(i, i + 4).map(checkOne));
    res.forEach((r, j) => { if (r) out[list[i + j].id] = r; });
  }
  return out;
}

export interface Alert { id: string; title: string; body: string }
/** Saved-deal id to the dropped price the user has already been told about. */
export type Notified = Record<string, string>;

/**
 * Which price drops deserve a notification. Each drop is announced once per price: a further drop is announced
 * again, and a deal that goes back up (or could not be checked) is forgotten so a later drop is news again.
 */
export function dropsToAnnounce(saved: readonly SavedDeal[], checks: Record<string, Check>, notified: Notified): { alerts: Alert[]; notified: Notified } {
  const next: Notified = {};
  const alerts: Alert[] = [];
  for (const d of saved) {
    const c = checks[d.id];
    if (!c) { if (notified[d.id]) next[d.id] = notified[d.id]; continue; } // not checked this time: keep what we knew
    if (c.status.kind !== 'drop') continue;
    const price = c.status.to.toFixed(2);
    next[d.id] = price;
    if (notified[d.id] === price) continue;
    alerts.push({
      id: d.id,
      title: `Price drop: ${d.name}`,
      body: `Now ${money(c.status.to)} at ${d.store_name}, down ${money(c.status.from - c.status.to)} from ${money(c.status.from)}.`,
    });
  }
  return { alerts, notified: next };
}
