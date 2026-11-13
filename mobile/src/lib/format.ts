import type { Offer } from './types';

export const unitLabel = (category: string) => (category === 'edibles' ? '10mg' : 'g');
export const perUnit = (o: { category: string; price_per_gram?: string | null; price_per_10mg?: string | null }) =>
  (o.category === 'edibles' ? o.price_per_10mg : o.price_per_gram) ?? null;

export function money(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return `${n < 0 ? '-' : ''}$${Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
}

export function strainBucket(v?: string | null): 'Indica' | 'Sativa' | 'Hybrid' | 'Unspecified' {
  const t = (v ?? '').toLowerCase();
  return t.includes('indica') ? 'Indica' : t.includes('sativa') ? 'Sativa' : t.includes('hybrid') ? 'Hybrid' : 'Unspecified';
}

export function massLabel(o: Pick<Offer, 'category' | 'dose_mg' | 'pack_count' | 'weight_label' | 'weight_grams'>): string {
  if (o.category === 'edibles') return `${o.dose_mg ?? '?'} mg THC${o.pack_count ? ` · ${o.pack_count} pc` : ''}`;
  return o.weight_label || (o.weight_grams ? `${o.weight_grams}g` : 'mass unknown');
}

export const isGrouped = (o: Offer) => (o.variants?.length ?? 0) > 1;
export const cardTitle = (o: Offer) => (isGrouped(o) ? `${o.brand || 'Assorted'} · ${o.variants!.length} strains` : o.name);

export const ageLabel = (h?: number | null) => (h == null ? 'date unknown' : h < 48 ? `${h}h ago` : `${Math.round(h / 24)}d ago`);

export function freshnessLabel(o: Pick<Offer, 'completeness' | 'freshness' | 'menu_age_hours'>): { text: string; ok: boolean } {
  if (o.completeness === 'B') return { text: 'unverified total', ok: false };
  if (o.freshness === 'fresh') return { text: 'fresh', ok: true };
  return { text: `last menu ${ageLabel(o.menu_age_hours)}`, ok: false };
}

export function relativeTime(iso: string | number | null | undefined, nowMs = Date.now()): string {
  const t = typeof iso === 'number' ? iso : Date.parse(iso ?? '');
  if (!Number.isFinite(t)) return 'recently';
  const d = nowMs - t;
  if (d < 60_000) return 'just now';
  if (d < 3_600_000) return `${Math.floor(d / 60_000)}m ago`;
  if (d < 86_400_000) return `${Math.floor(d / 3_600_000)}h ago`;
  return `${Math.floor(d / 86_400_000)}d ago`;
}

export function safeUrl(v?: string | null): string | undefined {
  const m = /^https?:\/\/[^\s/]+\S*$/i.exec((v ?? '').trim());
  return m ? m[0] : undefined;
}

export const directionsUrl = (storeName: string) =>
  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${storeName} dispensary Illinois`)}`;

export function shareText(o: Offer): string {
  const unit = unitLabel(o.category);
  return `${cardTitle(o)} (${massLabel(o)}) at ${o.store_name} for ${money(o.effective_price)} (${money(perUnit(o))}/${unit})`;
}
