import { unstable_cache } from 'next/cache';
import { dataVersion, queryDeals, regions, type DealQuery } from './deals.ts';

// Offers only change when a sync pushes a new data_version (about 4 times a day), but every page view used to
// re-run three full Postgres ranking queries against Neon. These wrappers keep the results in Vercel's data cache.

// The version is the only thing that must stay fresh, so it is re-read at most once a minute.
export const cachedVersion = unstable_cache(dataVersion, ['data-version'], { revalidate: 60 });

export const cachedRegions = unstable_cache(regions, ['regions'], { revalidate: 300 });

const dealsForVersion = unstable_cache(
  (_version: string, q: DealQuery) => queryDeals(q),
  ['deals'],
  { revalidate: 3600 }
);

// Keyed by data_version, so a new sync is picked up within a minute and old entries are simply never read again.
export async function cachedDeals(q: DealQuery) {
  return dealsForVersion(await cachedVersion(), q);
}
