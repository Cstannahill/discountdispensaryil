export interface TaxPreset {
  id: string;
  label: string;
  shortLabel: string;
  rate: number;
  detail: string;
}

export const TAX_PRESETS: readonly TaxPreset[] = [
  { id: 'med', label: 'Medical (~1%)', shortLabel: 'Med 1%', rate: 1, detail: 'IL medical cannabis 1% state retail tax' },
  { id: 'rec_flower', label: 'Rec Flower ≤35% (~22%)', shortLabel: 'Flower 22%', rate: 22, detail: '10% IL excise + state/local retail taxes' },
  { id: 'rec_vape', label: 'Rec Vape / Infused (~32%)', shortLabel: 'Vape/Infused 32%', rate: 32, detail: '20% IL infused excise + state/local taxes' },
  { id: 'rec_high', label: 'Rec >35% THC / Conc (~37%)', shortLabel: 'Conc/>35% 37%', rate: 37, detail: '25% IL high-THC excise + state/local taxes' },
] as const;

export function inferTaxRate(offer?: {
  license_type?: string | null;
  category?: string | null;
  flower_grade?: string | null;
  thc_pct?: string | null;
}): number {
  if (!offer) return 22;
  if (offer.license_type === 'medicinal') return 1;
  const thc = Number(offer.thc_pct);
  if (offer.category === 'concentrate' || (Number.isFinite(thc) && thc > 35)) return 37;
  if (offer.category === 'vapes' || offer.flower_grade === 'infused') return 32;
  return 22;
}

export function calculateOtd(input: {
  price: number;
  weight: number;
  discountPct: number;
  taxPct: number;
}) {
  const { price, weight, discountPct, taxPct } = input;
  const valid =
    Number.isFinite(price) &&
    Number.isFinite(weight) &&
    Number.isFinite(discountPct) &&
    Number.isFinite(taxPct) &&
    price >= 0 &&
    weight > 0 &&
    discountPct >= 0 &&
    discountPct <= 100 &&
    taxPct >= 0 &&
    taxPct <= 100;
  if (!valid) {
    return {
      valid: false,
      discountedSubtotal: 0,
      preTaxPerGram: 0,
      outTheDoorTotal: 0,
      outTheDoorPerGram: 0,
    };
  }
  const discountedSubtotal = price * (1 - discountPct / 100);
  const outTheDoorTotal = discountedSubtotal * (1 + taxPct / 100);
  return {
    valid: true,
    discountedSubtotal,
    preTaxPerGram: discountedSubtotal / weight,
    outTheDoorTotal,
    outTheDoorPerGram: outTheDoorTotal / weight,
  };
}

export function calculateSavings(
  regularPrice?: number | string | null,
  effectivePrice?: number | string | null
): {
  hasDiscount: boolean;
  savingsDollars: number;
  savingsPct: number;
} {
  if (
    regularPrice == null ||
    regularPrice === '' ||
    effectivePrice == null ||
    effectivePrice === ''
  ) {
    return { hasDiscount: false, savingsDollars: 0, savingsPct: 0 };
  }
  const reg = Number(regularPrice);
  const eff = Number(effectivePrice);
  if (!Number.isFinite(reg) || !Number.isFinite(eff) || reg <= 0 || eff < 0 || reg <= eff) {
    return { hasDiscount: false, savingsDollars: 0, savingsPct: 0 };
  }
  const savingsDollars = reg - eff;
  const savingsPct = Math.round((savingsDollars / reg) * 100);
  return {
    hasDiscount: true,
    savingsDollars,
    savingsPct,
  };
}
