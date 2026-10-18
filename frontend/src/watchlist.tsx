import { useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { api, date, money, type Offer, type MenuPage } from './api';
import { Status, SourceLink } from './ui';
const key = 'terpscout.watchlist.v1';
export const offerIdentity = (offer: Offer) => `${offer.endpoint_id}:${offer.id}`;
export function useWatchlist() {
  const [error, setError] = useState('');
  const [items, setItems] = useState<Offer[]>(() => { try { const raw = JSON.parse(localStorage.getItem(key) || '[]') as unknown; return Array.isArray(raw) ? raw.filter((o): o is Offer => !!o && typeof o === 'object' && 'id' in o && 'endpoint_id' in o && 'name' in o) : []; } catch { return []; } });
  function toggle(offer: Offer) { setItems(current => { const next = current.some(o => offerIdentity(o) === offerIdentity(offer)) ? current.filter(o => offerIdentity(o) !== offerIdentity(offer)) : [...current, offer]; try { localStorage.setItem(key, JSON.stringify(next)); setError(''); } catch { setError('Browser storage is unavailable. This watchlist will not survive closing the page.'); } return next; }); }
  return { items, toggle, error };
}
export function Watchlist({ items, onRemove }: { items: Offer[]; onRemove: (offer: Offer) => void }) {
  const endpoints = items.map(offerIdentity);
  const queries = useQueries({ queries: items.map(offer => ({ queryKey: ['watch-menu', offerIdentity(offer)], queryFn: () => api<MenuPage>(`/menus/${offer.endpoint_id}/products?offer_id=${encodeURIComponent(String(offer.id))}&page=1&page_size=1&include_removed=true`), staleTime: 0 })) });
  return <div className="space-y-3">{items.length === 0 && <p className="text-sm text-slate-400">Save an observed offer to compare it here. Saved prices are historical until rechecked.</p>}{items.map(saved => { const query = queries[endpoints.indexOf(offerIdentity(saved))]; const observed = query?.data?.items.find(o => offerIdentity(o) === offerIdentity(saved)); const current = observed ?? saved; return <article className="glass-card rounded-xl p-4 space-y-2" key={offerIdentity(saved)}><div className="flex justify-between gap-3"><h3 className="font-bold text-sm">{current.name}</h3><button className="btn" onClick={() => onRemove(saved)}>Remove</button></div><p className="text-xs text-slate-400">{current.store_name} · {current.license_type}</p><p className="font-mono">{money(current.effective_price)} · {money(current.price_per_gram)}/g <Status value={observed?.status === 'removed' ? 'removed' : observed?.freshness || 'saved observation'}/></p><p className="text-xs text-amber-200">{query?.isError ? 'Recheck failed; showing the saved observation.' : !observed ? 'Current offer could not be verified. Your saved observation is shown.' : `Last observed ${date(observed.last_seen_at)}. Stock: ${observed.available === true ? 'available at observation' : observed.available === false ? 'unavailable at observation' : 'unknown'}.`}</p><SourceLink url={current.source_url}/></article>; })}</div>;
}
