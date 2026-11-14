import { dealParams, mapParams, savedLookupParams } from '../api';
import { cacheKey } from '../cache';
import { calculateOtd, inferTaxRate } from '../calculator';
import { directionsUrl, freshnessLabel, massLabel, money, relativeTime, safeUrl, shareText } from '../format';
import { miles, moveAction, placeLabel, regionFor, shouldRecheck, RECHECK_MS } from '../geo';
import { cheapest } from '../map';
import { findCurrent, watchStatus } from '../price-watch';
import { dropsToAnnounce, type Check } from '../saved-check';
import { DEFAULT_FILTERS, sizesFor, type MapStore, type Offer, type Origin, type SavedDeal } from '../types';

jest.mock('@react-native-async-storage/async-storage', () => ({}));

const origin: Origin = { lat: 41.8781, lon: -87.6298, place: 'Chicago, IL', src: 'gps', at: 0 };
const offer = (o: Partial<Offer> = {}): Offer => ({
  id: 'o1', endpoint_id: 'e1', store_id: 's1', store_name: 'Green Leaf', license_type: 'recreational', name: 'Blue Dream', brand: 'Acme', category: 'flower',
  weight_grams: '3.5', regular_price: '40', effective_price: '30', price_per_gram: '8.57', completeness: 'A', freshness: 'fresh', flower_grade: 'whole',
  distance_miles: 4.2, last_seen_at: '2026-11-13T12:00:00Z', ...o,
});
const saved = (d: Partial<SavedDeal> = {}): SavedDeal => ({
  id: 'o1', store_id: 's1', name: 'Blue Dream', match_name: 'Blue Dream', store_name: 'Green Leaf', effective_price: '30', massLabel: '3.5g', category: 'flower',
  distance_miles: 4.2, saved_at: 0, weight_grams: '3.5', license_type: 'recreational', near: { lat: 41.8781, lon: -87.6298 }, ...d,
});

describe('deal query', () => {
  test('sends the origin, license and grouping the web page sends', () => {
    const p = dealParams(origin, DEFAULT_FILTERS, []);
    expect(p).toMatchObject({ lat: '41.8781', lon: '-87.6298', radius: '50', license_type: 'recreational', category: 'flower', flower_grade: 'whole', group: 'true', page: '1', page_size: '20' });
    expect(p.sort).toBeUndefined();
    expect(p.hide).toBeUndefined();
  });
  test('drops gram sizes for edibles and the grade filter outside flower', () => {
    const p = dealParams(origin, { ...DEFAULT_FILTERS, category: 'edibles', size: '3.5', grade: 'shake' }, ['a', 'b'], 3);
    expect(p.size).toBeUndefined();
    expect(p.flower_grade).toBe('all');
    expect(p.hide).toBe('a,b');
    expect(p.page).toBe('3');
  });
  test('cache key ignores the page and empty values', () => {
    expect(cacheKey(dealParams(origin, DEFAULT_FILTERS, [], 1))).toBe(cacheKey(dealParams(origin, DEFAULT_FILTERS, [], 2)));
    expect(cacheKey({ b: '2', a: '1', c: undefined })).toBe('a=1&b=2');
  });
  test('eighths and larger are offered only for flower', () => {
    expect(sizesFor('flower')).toContain('3.5');
    expect(sizesFor('vapes')).toEqual(['any', '0.5', '1']);
    expect(sizesFor('edibles')).toEqual(['any']);
  });
});

describe('location refresh', () => {
  const chicago = { lat: 41.8781, lon: -87.6298 };
  test('distance between Chicago and Peoria is about 130 miles', () => {
    expect(miles(chicago, { lat: 40.6936, lon: -89.589 })).toBeGreaterThan(125);
    expect(miles(chicago, { lat: 40.6936, lon: -89.589 })).toBeLessThan(135);
  });
  test('jitter is kept, a move across town swaps, a far move asks', () => {
    expect(moveAction(chicago, { lat: 41.89, lon: -87.63 })).toBe('keep');
    expect(moveAction(chicago, { lat: 41.7508, lon: -88.1535 })).toBe('ask'); // Naperville, about 28 mi
    expect(moveAction(chicago, { lat: 42.0451, lon: -87.6877 })).toBe('swap'); // Evanston, about 12 mi
  });
  test('only an old GPS origin is re-checked; a typed place never is', () => {
    expect(shouldRecheck({ src: 'gps', at: 0 }, RECHECK_MS)).toBe(true);
    expect(shouldRecheck({ src: 'gps', at: 0 }, RECHECK_MS - 1)).toBe(false);
    expect(shouldRecheck({ src: 'manual', at: 0 }, RECHECK_MS * 10)).toBe(false);
    expect(shouldRecheck(null)).toBe(false);
  });
  test('device geocode results become City, ST', () => {
    expect(placeLabel({ city: 'Peoria', region: 'IL' })).toBe('Peoria, IL');
    expect(placeLabel({ city: 'Peoria', region: 'Illinois' })).toBe('Peoria, IL');
    expect(placeLabel({ city: null, subregion: 'Woodford County', region: 'IL' })).toBe('Woodford County, IL');
    expect(placeLabel({ city: null })).toBeNull();
    expect(placeLabel(undefined)).toBeNull();
  });
});

describe('saved deal price watch', () => {
  test('finds the same offer by id, then by store, name and size', () => {
    expect(findCurrent(saved(), [offer({ id: 'x', name: 'Other' }), offer()])?.id).toBe('o1');
    expect(findCurrent(saved(), [offer({ id: 'new-id', name: ' blue dream ' })])?.id).toBe('new-id');
    expect(findCurrent(saved(), [offer({ id: 'n', store_id: 's2' })])).toBeNull();
    expect(findCurrent(saved(), [offer({ id: 'n', weight_grams: '7' })])).toBeNull();
  });
  test('reports drops, rises, no change and delisting', () => {
    expect(watchStatus(saved(), offer({ effective_price: '25' }))).toEqual({ kind: 'drop', from: 30, to: 25 });
    expect(watchStatus(saved(), offer({ effective_price: '35' }))).toEqual({ kind: 'rise', from: 30, to: 35 });
    expect(watchStatus(saved(), offer({ effective_price: '30.004' }))).toEqual({ kind: 'same' });
    expect(watchStatus(saved(), null)).toEqual({ kind: 'gone' });
  });
  test('looks the deal up from where it was saved, with a radius that still covers the store', () => {
    expect(savedLookupParams(saved({ distance_miles: 12.3 }))).toMatchObject({ lat: '41.8781', radius: '18', q: 'Blue Dream', flower_grade: 'all', include_stale: 'true' });
    expect(savedLookupParams(saved({ near: null }))).toBeNull();
  });
});

describe('formatting', () => {
  test('money', () => {
    expect(money('8.5')).toBe('$8.50');
    expect(money(1234.5)).toBe('$1,234.50');
    expect(money(null)).toBe('—');
    expect(money('abc')).toBe('—');
  });
  test('mass, freshness and share text', () => {
    expect(massLabel(offer({ category: 'edibles', dose_mg: '100', pack_count: 10 }))).toBe('100 mg THC · 10 pc');
    expect(massLabel(offer({ weight_label: null, weight_grams: null }))).toBe('mass unknown');
    expect(freshnessLabel(offer())).toEqual({ text: 'fresh', ok: true });
    expect(freshnessLabel(offer({ freshness: 'stale', menu_age_hours: 72 }))).toEqual({ text: 'last menu 3d ago', ok: false });
    expect(freshnessLabel(offer({ completeness: 'B' })).text).toBe('unverified total');
    expect(shareText(offer())).toBe('Blue Dream (3.5g) at Green Leaf for $30.00 ($8.57/g)');
  });
  test('relative time and link safety', () => {
    expect(relativeTime(0, 30_000)).toBe('just now');
    expect(relativeTime(0, 5 * 3_600_000)).toBe('5h ago');
    expect(relativeTime('nope')).toBe('recently');
    expect(safeUrl('https://example.com/menu?x=1')).toBe('https://example.com/menu?x=1');
    expect(safeUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeUrl(null)).toBeUndefined();
  });
  test('out-the-door math matches the web calculator', () => {
    expect(inferTaxRate({ license_type: 'medicinal' })).toBe(1);
    expect(inferTaxRate({ category: 'concentrate' })).toBe(37);
    expect(calculateOtd({ price: 40, weight: 3.5, discountPct: 25, taxPct: 22 }).outTheDoorTotal).toBeCloseTo(36.6);
  });
});

describe('map', () => {
  const store = (id: string, unit: string | null, lat = 40.7, lon = -89.6): MapStore => ({
    id, name: id, address: '1 Main St', city: 'Peoria', state: 'IL', latitude: lat, longitude: lon, distance_miles: 1, deals: unit ? 3 : 0,
    best: unit ? { offer_id: 'o', name: 'n', brand: null, unit_price: unit, effective_price: '10', weight_grams: '3.5', dose_mg: null, freshness: 'fresh', menu_age_hours: 1 } : null,
  });
  test('asks the API for the same area, license and category as the deal list', () => {
    expect(mapParams(origin, 25, 'recreational', 'vapes')).toEqual({ lat: '41.8781', lon: '-87.6298', radius: '25', license_type: 'recreational', category: 'vapes' });
  });
  test('the cheapest store ignores hidden stores and stores without deals', () => {
    const stores = [store('a', '9.00'), store('b', '4.50'), store('c', null), store('d', '10.00')];
    expect(cheapest(stores, [])?.id).toBe('b');
    expect(cheapest(stores, ['b'])?.id).toBe('a'); // compared as numbers: 9.00 is below 10.00
    expect(cheapest([store('c', null)], [])).toBeNull();
  });
  test('the region covers the search centre and every pin', () => {
    const c = { lat: 40.7, lon: -89.6 };
    const r = regionFor(c, 50, [store('a', '1', 41.2, -89.0), store('b', '1', 40.5, -90.1)]);
    expect(r.latitude - r.latitudeDelta / 2).toBeLessThan(40.5);
    expect(r.latitude + r.latitudeDelta / 2).toBeGreaterThan(41.2);
    expect(r.longitude - r.longitudeDelta / 2).toBeLessThan(-90.1);
    expect(r.longitude + r.longitudeDelta / 2).toBeGreaterThan(-89.0);
    const empty = regionFor(c, 50, []);
    expect(empty.latitudeDelta).toBeCloseTo(100 / 69);
    expect(regionFor(c, 50, [store('a', '1', 40.7, -89.6)]).latitudeDelta).toBe(0.02); // one pin on the centre still gets a usable zoom
  });
  test('directions use the street address when there is one', () => {
    expect(decodeURIComponent(directionsUrl('Green Leaf', { address: '1 Main St', city: 'Peoria', state: 'IL' }))).toContain('query=Green Leaf, 1 Main St, Peoria, IL');
    expect(decodeURIComponent(directionsUrl('Green Leaf', { address: ' ' }))).toContain('query=Green Leaf dispensary Illinois');
    expect(decodeURIComponent(directionsUrl('Green Leaf'))).toContain('query=Green Leaf dispensary Illinois');
  });
});

describe('price-drop alerts', () => {
  const drop = (to: number): Check => ({ status: { kind: 'drop', from: 30, to }, current: null });
  const a = saved({ id: 'a', name: 'Blue Dream' }), b = saved({ id: 'b', name: 'Gelato' });
  test('a drop is announced once per price', () => {
    const first = dropsToAnnounce([a, b], { a: drop(25), b: { status: { kind: 'same' }, current: null } }, {});
    expect(first.alerts).toEqual([{ id: 'a', title: 'Price drop: Blue Dream', body: 'Now $25.00 at Green Leaf, down $5.00 from $30.00.' }]);
    expect(first.notified).toEqual({ a: '25.00' });
    expect(dropsToAnnounce([a, b], { a: drop(25) }, first.notified).alerts).toEqual([]);
  });
  test('a further drop is announced again, and a recovered price is forgotten', () => {
    expect(dropsToAnnounce([a], { a: drop(22) }, { a: '25.00' }).alerts).toHaveLength(1);
    const back = dropsToAnnounce([a], { a: { status: { kind: 'same' }, current: null } }, { a: '25.00' });
    expect(back).toEqual({ alerts: [], notified: {} });
    expect(dropsToAnnounce([a], { a: drop(25) }, back.notified).alerts).toHaveLength(1);
  });
  test('a deal that could not be checked keeps its record, and removed deals are dropped', () => {
    expect(dropsToAnnounce([a], {}, { a: '25.00', gone: '9.00' })).toEqual({ alerts: [], notified: { a: '25.00' } });
  });
});
