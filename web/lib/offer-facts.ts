import { calculateSavings } from './calculator.ts';
import { perUnit, unitLabel, type Offer } from './deals.ts';

// Display facts shared by the compact deal rows (client) and the layout views (server).
export function offerFacts(o: Offer) {
  const grouped = (o.variants?.length ?? 0) > 1;
  const edible = o.category === 'edibles';
  const size = edible
    ? `${o.dose_mg ?? '?'}mg${o.pack_count ? ` · ${o.pack_count}pc` : ''}`
    : o.weight_label || (o.weight_grams ? `${o.weight_grams}g` : '—');
  const title = grouped ? `${o.brand || 'Assorted'} · ${o.variants!.length} strains` : o.name;
  const savings = calculateSavings(o.regular_price, o.effective_price);
  const aged = o.completeness === 'B' || o.freshness !== 'fresh';
  return { grouped, size, title, savings, aged, unit: unitLabel(o.category), unitPrice: perUnit(o) };
}

