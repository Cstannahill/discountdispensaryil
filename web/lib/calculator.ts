export interface TaxPreset {
  id: string;
  label: string;
  shortLabel: string;
  rate: number;
  detail: string;
}

// Illinois rates, last verified 2026-10-25 against tax.illinois.gov (Cannabis Tax FAQ, bulletin FY 2025-09).
export const RATES_VERIFIED = '2026-10-25';
export const STATE_SALES_PCT = 6.25;
export const MEDICAL_PCT = 1;
// Adult-use local add-on (home-rule sales tax + municipal/county cannabis tax) beyond the 6.25% state rate. A flat estimate:
// the actual figure depends on the store's town and county (municipal cannabis tax up to 3%, county up to 3.75%).
export const DEFAULT_LOCAL_PCT = 5.75;

export const LOCAL_PRESETS: readonly { id: string; label: string; pct: number }[] = [
  { id: 'none', label: 'Low (~0%)', pct: 0 },
  { id: 'typical', label: 'Typical (~5.75%)', pct: DEFAULT_LOCAL_PCT },
  { id: 'chicago', label: 'Chicago/Cook (~10%)', pct: 10 },
] as const;

export const TAX_PRESETS: readonly TaxPreset[] = [
  { id: 'med', label: 'Medical (~1%)', shortLabel: 'Med 1%', rate: MEDICAL_PCT, detail: 'IL medical cannabis 1% state retail tax; no excise or local cannabis tax' },
  { id: 'rec_flower', label: 'Rec ≤35% THC (~22%)', shortLabel: 'Flower 22%', rate: 10 + STATE_SALES_PCT + DEFAULT_LOCAL_PCT, detail: '10% excise (≤35% THC) + 6.25% state + local' },
  { id: 'rec_infused', label: 'Rec Edibles / Infused (~32%)', shortLabel: 'Edibles 32%', rate: 20 + STATE_SALES_PCT + DEFAULT_LOCAL_PCT, detail: '20% excise (infused, not smoked) + 6.25% state + local' },
  { id: 'rec_high', label: 'Rec >35% THC / Conc (~37%)', shortLabel: 'Conc/>35% 37%', rate: 25 + STATE_SALES_PCT + DEFAULT_LOCAL_PCT, detail: '25% excise (>35% THC) + 6.25% state + local' },
] as const;

// thc_pct arrives as free text ("24.5", "24%", "20-25%", "THC 24.5 %"); take the first number, null when none.
export function parseThc(v?: string | number | null): number | null {
  if (v == null || v === '') return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const m = /([0-9]+(?:\.[0-9]+)?)/.exec(v);
  return m ? Number(m[1]) : null;
}

export function inferExcisePct(offer?: {
  category?: string | null;
  flower_grade?: string | null;
  thc_pct?: string | null;
}): number {
  if (!offer) return 10;
  const thc = parseThc(offer.thc_pct);
  if (thc != null) return thc > 35 ? 25 : 10;
  // THC unknown: concentrates and vape oil are >35% THC in practice; infused (smoked) pre-rolls are usually 35%+ too.
  if (offer.category === 'concentrate' || offer.category === 'vapes' || offer.flower_grade === 'infused') return 25;
  return 10;
}

export function inferTaxRate(offer?: {
  license_type?: string | null;
  category?: string | null;
  flower_grade?: string | null;
  thc_pct?: string | null;
}, localPct: number = DEFAULT_LOCAL_PCT): number {
  if (offer?.license_type === 'medicinal') return MEDICAL_PCT;
  return inferExcisePct(offer) + STATE_SALES_PCT + localPct;
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
  const hasDiscount = savingsDollars >= 0.5 && savingsPct >= 1;
  return {
    hasDiscount,
    savingsDollars: hasDiscount ? savingsDollars : 0,
    savingsPct: hasDiscount ? savingsPct : 0,
  };
}
