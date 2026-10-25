import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { strainBucket, parseSize, sizeForCategory, strainClause } from './deals.ts';
import { calculateOtd, inferTaxRate } from './calculator.ts';
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
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'vapes', thc_pct: null }), 32);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', flower_grade: 'infused', thc_pct: '30' }), 32);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', flower_grade: 'whole', thc_pct: '24' }), 22);
  });
});

describe('parseOrigin', () => {
  it('parses valid coordinates and clamps radius to 200 miles', () => {
    const p = new Map([['lat', '40.6936'], ['lon', '-89.589'], ['radius', '500'], ['place', 'Peoria, IL']]);
    const o = parseOrigin((k) => p.get(k));
    assert.deepEqual(o, { latitude: 40.6936, longitude: -89.589, radius_miles: 200, label: 'Peoria, IL' });
  });
});
