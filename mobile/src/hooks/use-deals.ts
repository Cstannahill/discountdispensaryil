import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApiError, dealParams, fetchDeals } from '@/lib/api';
import { cacheKey, readCache, writeCache } from '@/lib/cache';
import { PAGE_SIZE } from '@/lib/config';
import type { Filters, Offer, Origin, Page } from '@/lib/types';

export interface DealsState {
  items: Offer[]; total: number; loading: boolean; refreshing: boolean; loadingMore: boolean;
  error: string | null; offline: boolean; cachedAt: number | null; loadedAt: number | null;
}
const EMPTY: DealsState = { items: [], total: 0, loading: false, refreshing: false, loadingMore: false, error: null, offline: false, cachedAt: null, loadedAt: null };

/** Ranked deals for one search: shows the saved copy at once, then the live list, and pages as the user scrolls. */
export function useDeals(origin: Origin | null, filters: Filters, hidden: readonly string[]) {
  const params = useMemo(() => (origin ? dealParams(origin, filters, hidden, 1) : null), [origin, filters, hidden]);
  const key = params ? cacheKey(params) : null;
  const [st, setSt] = useState<DealsState>(EMPTY);
  const page = useRef(1);
  const run = useRef(0);

  const load = useCallback(async (mode: 'initial' | 'refresh') => {
    if (!params || !key) return;
    const id = ++run.current;
    page.current = 1;
    setSt((p) => ({ ...(mode === 'initial' ? EMPTY : p), loading: mode === 'initial', refreshing: mode === 'refresh', error: null }));
    const cached = mode === 'initial' ? await readCache<Page<Offer>>(key) : null;
    if (id !== run.current) return;
    if (cached) setSt((p) => ({ ...p, items: cached.data.items, total: cached.data.total, cachedAt: cached.at }));
    try {
      const data = await fetchDeals(params);
      if (id !== run.current) return;
      setSt({ ...EMPTY, items: data.items, total: data.total, loadedAt: Date.now() });
      writeCache(key, data);
    } catch (e) {
      if (id !== run.current) return;
      const offline = e instanceof ApiError && e.status === 0;
      setSt((p) => ({ ...p, loading: false, refreshing: false, offline, error: offline ? 'No connection' : (e as Error).message || 'Could not load deals' }));
    }
  }, [params, key]);

  useEffect(() => { load('initial'); }, [load]);

  const loadMore = useCallback(async () => {
    if (!params || st.loading || st.refreshing || st.loadingMore || st.offline || st.loadedAt == null || st.items.length >= st.total || st.total <= page.current * PAGE_SIZE) return;
    const id = run.current, next = page.current + 1;
    setSt((p) => ({ ...p, loadingMore: true }));
    try {
      const data = await fetchDeals({ ...params, page: String(next) });
      if (id !== run.current) return;
      page.current = next;
      setSt((p) => {
        const seen = new Set(p.items.map((o) => o.id));
        return { ...p, loadingMore: false, total: data.total, items: [...p.items, ...data.items.filter((o) => !seen.has(o.id))] };
      });
    } catch {
      if (id === run.current) setSt((p) => ({ ...p, loadingMore: false }));
    }
  }, [params, st]);

  const refresh = useCallback(() => load('refresh'), [load]);
  return { ...st, refresh, loadMore };
}
