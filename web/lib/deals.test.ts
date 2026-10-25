import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { strainBucket, parseSize, sizeForCategory, strainClause, SORT_OPTIONS, type SortOption, sortOrderClause, QUICK_HUBS } from './deals.ts';
import { formatRelativeTime } from './time.ts';
import { calculateOtd, inferTaxRate, calculateSavings, parseThc } from './calculator.ts';
import { parseOrigin } from './origin.ts';

describe('strainBucket and strainClause consistency', () => {
  it('buckets dominant-leaning and hybrid labels consistently', () => {
    assert.equal(strainBucket('Indica'), 'Indica');
    assert.equal(strainBucket('Indica Dominant Hybrid'), 'Indica');
    assert.equal(strainBucket('Sativa'), 'Sativa');
    assert.equal(strainBucket('Sativa-Hybrid'), 'Sativa');
    assert.equal(strainBucket('Hybrid'), 'Hybrid');
    assert.equal(strainBucket('Balanced Hybrid'), 'Hybrid');
    assert.equal(strainBucket(null), 'Unspecified');
    assert.equal(strainBucket(''), 'Unspecified');
  });

  it('builds SQL predicates that match strainBucket precedence', () => {
    const bound: unknown[] = [];
    const bind = (v: unknown) => (bound.push(v), `$${bound.length}`);
    const ind = strainClause('Indica', bind);
    assert.ok(ind?.includes("position('indica'"));
    const sat = strainClause('Sativa', bind);
    assert.ok(sat?.includes("position('sativa'") && sat?.includes("position('indica'"));
    const hyb = strainClause('Hybrid', bind);
    assert.ok(hyb?.includes("position('hybrid'") && hyb?.includes("position('indica'") && hyb?.includes("position('sativa'"));
    assert.equal(strainClause('all', bind), null);
    assert.equal(strainClause('', bind), null);
  });
});

describe('package size parsing and category scoping', () => {
  it('rejects invalid, negative, zero, or "any" sizes and accepts positive gram weights', () => {
    assert.equal(parseSize('any'), null);
    assert.equal(parseSize(''), null);
    assert.equal(parseSize(null), null);
    assert.equal(parseSize('abc'), null);
    assert.equal(parseSize('-3.5'), null);
    assert.equal(parseSize('0'), null);
    assert.equal(parseSize('3.5'), 3.5);
    assert.equal(parseSize('0.5'), 0.5);
    assert.equal(parseSize('28'), 28);
  });

  it('scopes flower-only weights (3.5g, 7g, 14g, 28g) to flower on multi-column views while keeping 0.5g/1g universal', () => {
    assert.equal(sizeForCategory('flower', '3.5'), '3.5');
    assert.equal(sizeForCategory('concentrate', '3.5'), undefined);
    assert.equal(sizeForCategory('vapes', '3.5'), undefined);
    assert.equal(sizeForCategory('concentrate', '1'), '1');
    assert.equal(sizeForCategory('vapes', '0.5'), '0.5');
    assert.equal(sizeForCategory('flower', 'any'), undefined);
  });
});

describe('OTD calculator and Illinois tax inference', () => {
  it('calculates discounted pre-tax $/g, OTD total, and OTD $/g accurately', () => {
    const res = calculateOtd({ price: 40, weight: 3.5, discountPct: 25, taxPct: 22 });
    assert.equal(res.valid, true);
    assert.equal(res.discountedSubtotal, 30);
    assert.ok(Math.abs(res.preTaxPerGram - 30 / 3.5) < 1e-6);
    assert.ok(Math.abs(res.outTheDoorTotal - 36.6) < 1e-6);
    assert.ok(Math.abs(res.outTheDoorPerGram - 36.6 / 3.5) < 1e-6);
  });

  it('marks invalid inputs as valid: false without NaN or Infinity', () => {
    assert.equal(calculateOtd({ price: -10, weight: 3.5, discountPct: 0, taxPct: 20 }).valid, false);
    assert.equal(calculateOtd({ price: 30, weight: 0, discountPct: 0, taxPct: 20 }).valid, false);
    assert.equal(calculateOtd({ price: 30, weight: 3.5, discountPct: 120, taxPct: 20 }).valid, false);
    assert.equal(calculateOtd({ price: 30, weight: 3.5, discountPct: 0, taxPct: -5 }).valid, false);
  });

  it('infers Illinois tax rate from license, category, flower grade, and THC %', () => {
    assert.equal(inferTaxRate({ license_type: 'medicinal', category: 'concentrate', thc_pct: '80' }), 1);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'concentrate', thc_pct: '72' }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', thc_pct: '38' }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'vapes', thc_pct: '85' }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'vapes', thc_pct: null }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'vapes', thc_pct: '30' }), 22);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', thc_pct: '38.5%' }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', thc_pct: '24' }, 10), 26.25);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', thc_pct: null }), 22);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', flower_grade: 'infused', thc_pct: '30' }), 22);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', flower_grade: 'infused', thc_pct: null }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', flower_grade: 'whole', thc_pct: '24' }), 22);
  });
});

describe('calculateSavings', () => {
  it('calculates savings percentage and dollar difference accurately', () => {
    const s1 = calculateSavings('50', '35');
    assert.equal(s1.hasDiscount, true);
    assert.equal(s1.savingsDollars, 15);
    assert.equal(s1.savingsPct, 30);

    const s2 = calculateSavings(60, 45);
    assert.equal(s2.hasDiscount, true);
    assert.equal(s2.savingsDollars, 15);
    assert.equal(s2.savingsPct, 25);
  });

  it('returns hasDiscount false when regular price is less than or equal to effective price or invalid', () => {
    assert.equal(calculateSavings('35', '35').hasDiscount, false);
    assert.equal(calculateSavings('30', '40').hasDiscount, false);
    assert.equal(calculateSavings(null, '30').hasDiscount, false);
    assert.equal(calculateSavings('50', null).hasDiscount, false);
    assert.equal(calculateSavings('0', '0').hasDiscount, false);
    assert.equal(calculateSavings('abc', '20').hasDiscount, false);
  });

  it('returns hasDiscount false for trivial discounts under $0.50 or under 1%', () => {
    assert.equal(calculateSavings('30.00', '29.99').hasDiscount, false);
    assert.equal(calculateSavings('100.00', '99.60').hasDiscount, false);
    assert.equal(calculateSavings('20.00', '19.80').hasDiscount, false);
    const s = calculateSavings('30.00', '29.00');
    assert.equal(s.hasDiscount, true);
    assert.equal(s.savingsDollars, 1);
    assert.equal(s.savingsPct, 3);
  });
});

describe('parseOrigin', () => {
  it('parses valid coordinates and clamps radius to 200 miles', () => {
    const p = new Map([['lat', '40.6936'], ['lon', '-89.589'], ['radius', '500'], ['place', 'Peoria, IL']]);
    const o = parseOrigin((k) => p.get(k));
    assert.deepEqual(o, { latitude: 40.6936, longitude: -89.589, radius_miles: 200, label: 'Peoria, IL' });
  });
});

describe('SORT_OPTIONS and sortOrderClause', () => {
  it('defines all 5 supported sorting criteria', () => {
    assert.deepEqual(SORT_OPTIONS, ['value', 'price', 'thc', 'distance', 'discount']);
  });

  it('generates safe SQL clauses for all options', () => {
    assert.match(sortOrderClause('value'), /NULLIF\(j->>'effective_price',\s*''\)::numeric.*NULLIF\(j->>'weight_grams',\s*''\)::numeric.*ASC/);
    assert.match(sortOrderClause('price'), /NULLIF\(j->>'effective_price',\s*''\)::numeric.*ASC/);
    assert.match(sortOrderClause('thc'), /substring\(j->>'thc_pct'\s+from\s+'\(\[0-9\]\+\(\?:\\\.\[0-9\]\+\)\?\)'\)::numeric.*DESC/);
    assert.match(sortOrderClause('distance'), /distance_miles.*ASC/);
    assert.match(sortOrderClause('discount'), /regular_price.*effective_price.*DESC/);
    assert.match(sortOrderClause(undefined as unknown as SortOption), /effective_price.*weight_grams/);
    assert.match(sortOrderClause('invalid' as SortOption), /effective_price.*weight_grams/);
  });
});

describe('formatRelativeTime', () => {
  it('returns "Just now" and isLive for recent stamps and future clock skew', () => {
    const now = Date.parse('2026-10-25T12:00:00Z');
    const res1 = formatRelativeTime('2026-10-25T11:59:30Z', now);
    assert.equal(res1.label, 'Just now');
    assert.equal(res1.isLive, true);

    const res2 = formatRelativeTime('2026-10-25T12:00:15Z', now);
    assert.equal(res2.label, 'Just now');
    assert.equal(res2.isLive, true);
  });

  it('returns minutes and live flag for under 60m', () => {
    const now = Date.parse('2026-10-25T12:00:00Z');
    const res = formatRelativeTime('2026-10-25T11:35:00Z', now);
    assert.equal(res.label, '25m ago');
    assert.equal(res.isLive, true);
  });

  it('returns hours with isLive under 4h, not live >= 4h', () => {
    const now = Date.parse('2026-10-25T12:00:00Z');
    const res1 = formatRelativeTime('2026-10-25T10:00:00Z', now);
    assert.equal(res1.label, '2h ago');
    assert.equal(res1.isLive, true);

    const res2 = formatRelativeTime('2026-10-25T06:00:00Z', now);
    assert.equal(res2.label, '6h ago');
    assert.equal(res2.isLive, false);
  });

  it('returns days for >= 24h', () => {
    const now = Date.parse('2026-10-25T12:00:00Z');
    const res = formatRelativeTime('2026-10-23T12:00:00Z', now);
    assert.equal(res.label, '2d ago');
    assert.equal(res.isLive, false);
  });

  it('handles invalid date strings gracefully', () => {
    const res = formatRelativeTime('not-a-valid-date');
    assert.equal(res.label, 'Recently observed');
    assert.equal(res.isLive, false);
  });
});

describe('QUICK_HUBS validity', () => {
  it('contains all 12 target Illinois locations with valid 5-digit ZIPs', () => {
    assert.equal(QUICK_HUBS.length, 12);
    const expectedNames = [
      'Chicago', 'Naperville', 'Joliet', 'Rockford', 'Quad Cities',
      'Peoria', 'Normal', 'Champaign', 'Springfield', 'Streator',
      'Metro East', 'Carbondale'
    ];
    assert.deepEqual(QUICK_HUBS.map(([name]) => name), expectedNames);
    for (const [name, zip] of QUICK_HUBS) {
      assert.match(zip, /^\d{5}$/, `${name} ZIP must be 5 digits`);
      assert.match(zip, /^6[0-2]/, `${name} ZIP must be in Illinois (60xxx-62xxx)`);
    }
  });
});

describe('parseThc', () => {
  it('extracts the first number from messy THC text', () => {
    assert.equal(parseThc('24.5'), 24.5);
    assert.equal(parseThc('38%'), 38);
    assert.equal(parseThc('THC 20-25 %'), 20);
    assert.equal(parseThc(''), null);
    assert.equal(parseThc(null), null);
    assert.equal(parseThc('n/a'), null);
  });
});
