'use client';
import 'leaflet/dist/leaflet.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { LayerGroup, Map as LeafletMap } from 'leaflet';
import { useActiveCategory } from './category-tabs';
import type { MapStore } from '@/lib/store-map';

const money = (v: string | number | null | undefined) =>
  v == null || v === '' ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// The map layout's main panel: every dispensary in range as a price pin (its best deal in the active category)
// beside a list of the same stores, cheapest first. Tiles come from OpenStreetMap; Leaflet loads in the browser only.
export default function StoreMap({
  byCategory,
  origin,
  baseQuery,
}: {
  byCategory: Record<string, MapStore[]>;
  origin: { latitude: number; longitude: number };
  /** Current filter query string without q or paging; a store's "see deals" link adds q=<store name>. */
  baseQuery: string;
}) {
  const active = useActiveCategory();
  const category = byCategory[active] ? active : 'flower';
  const unit = category === 'edibles' ? '10mg' : 'g';
  const stores = useMemo(() => {
    const all = byCategory[category] ?? [];
    const priced = all.filter((s) => s.best).sort((a, b) => Number(a.best!.unit_price) - Number(b.best!.unit_price) || a.distance_miles - b.distance_miles);
    return [...priced, ...all.filter((s) => !s.best)];
  }, [byCategory, category]);

  const [sel, setSel] = useState<string | null>(null);
  const el = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const pins = useRef<LayerGroup | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let dead = false;
    void import('leaflet').then((L) => {
      if (dead || !el.current || map.current) return;
      const m = L.map(el.current, { scrollWheelZoom: false, attributionControl: true }).setView([origin.latitude, origin.longitude], 10);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
      }).addTo(m);
      L.marker([origin.latitude, origin.longitude], {
        icon: L.divIcon({ className: '', html: '<span class="map-me" title="Search center"></span>', iconSize: [0, 0] }),
        interactive: false,
        keyboard: false,
      }).addTo(m);
      pins.current = L.layerGroup().addTo(m);
      map.current = m;
      setReady(true);
    });
    return () => {
      dead = true;
      map.current?.remove();
      map.current = null;
      pins.current = null;
    };
    // The origin only changes with a full navigation, which remounts this component.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redraw the pins when the category or selection changes.
  useEffect(() => {
    if (!ready) return;
    void import('leaflet').then((L) => {
      const g = pins.current;
      if (!g) return;
      g.clearLayers();
      stores.forEach((s, i) => {
        const cls = `map-pin${s.best ? '' : ' map-pin-none'}${i === 0 && s.best ? ' map-pin-best' : ''}${s.id === sel ? ' map-pin-sel' : ''}`;
        const text = s.best ? `${money(s.best.unit_price)}<small>/${unit}</small>` : '';
        L.marker([s.latitude, s.longitude], {
          icon: L.divIcon({ className: '', html: `<span class="${cls}">${text}</span>`, iconSize: [0, 0] }),
          title: s.best ? `${s.name}: from ${money(s.best.unit_price)}/${unit}` : `${s.name}: no ${category} deals listed`,
          alt: esc(s.name),
          zIndexOffset: s.id === sel ? 2000 : i === 0 ? 1000 : s.best ? 500 - i : 0,
        })
          .on('click', () => {
            setSel(s.id);
            listRef.current?.querySelector(`[data-store="${CSS.escape(s.id)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          })
          .addTo(g);
      });
    });
  }, [ready, stores, sel, unit, category]);

  // Frame every store (and the search center) whenever the set of stores changes.
  useEffect(() => {
    if (!ready || !map.current) return;
    void import('leaflet').then((L) => {
      const pts: [number, number][] = [[origin.latitude, origin.longitude], ...stores.map((s) => [s.latitude, s.longitude] as [number, number])];
      if (pts.length > 1) map.current?.fitBounds(L.latLngBounds(pts), { padding: [36, 36], maxZoom: 13 });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, stores]);

  const select = (s: MapStore) => {
    const next = s.id === sel ? null : s.id;
    setSel(next);
    if (next) map.current?.panTo([s.latitude, s.longitude]);
  };

  const priced = stores.filter((s) => s.best).length;

  return (
    <section aria-label="Dispensary map" className="glass-card rounded-2xl overflow-hidden lg:flex lg:h-[34rem]">
      <div ref={el} className="store-map h-72 sm:h-80 lg:h-auto lg:flex-1 lg:order-2 z-0" role="application" aria-label="Map of dispensaries with their best price" />
      <div className="lg:w-[25rem] lg:shrink-0 lg:order-1 flex flex-col min-h-0 border-t lg:border-t-0 lg:border-r border-slate-800/90">
        <p className="px-3 py-2 text-[11px] text-slate-400 border-b border-slate-800/90">
          <strong className="text-slate-200">{stores.length} {stores.length === 1 ? 'dispensary' : 'dispensaries'}</strong>
          {priced > 0 ? ` · cheapest ${category} first` : ` · no ${category} deals match`}
        </p>
        <div ref={listRef} className="overflow-y-auto max-h-80 lg:max-h-none lg:flex-1">
          {stores.length === 0 && <p className="px-3 py-8 text-center text-xs text-slate-400">No dispensaries in this area. Try a wider distance.</p>}
          {stores.map((s, i) => {
            const open = s.id === sel;
            const where = [s.address, s.city].filter(Boolean).join(', ');
            return (
              <div key={s.id} data-store={s.id} className={`border-b border-slate-800/70 ${open ? 'bg-emerald-500/10' : ''}`}>
                <button type="button" aria-expanded={open} onClick={() => select(s)} className="w-full text-left flex items-center gap-3 px-3 py-2.5 hover:bg-slate-900/60">
                  <span className={`w-6 h-6 shrink-0 rounded-full grid place-items-center text-[11px] font-extrabold ${s.best ? 'bg-slate-100 text-slate-950' : 'bg-slate-800 text-slate-400'}`}>
                    {s.best ? i + 1 : '–'}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-extrabold text-white">{s.name}</span>
                    <span className="block truncate text-[11px] text-slate-400">
                      {s.distance_miles.toFixed(1)} mi · {s.deals} {category} {s.deals === 1 ? 'deal' : 'deals'}
                      {s.best?.freshness === 'stale' ? ' · older menu' : ''}
                    </span>
                  </span>
                  {s.best ? (
                    <span className="shrink-0 text-right">
                      <span className="block text-[10px] text-slate-400 leading-none">from</span>
                      <span className="block text-base font-extrabold text-emerald-400 leading-tight">
                        {money(s.best.unit_price)}
                        <span className="text-[10px] font-semibold text-slate-400">/{unit}</span>
                      </span>
                    </span>
                  ) : (
                    <span className="shrink-0 text-[11px] text-slate-500">none listed</span>
                  )}
                </button>
                {open && (
                  <div className="px-3 pb-3 pl-12 space-y-2 text-xs">
                    {s.best && (
                      <p className="flex justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5">
                        <span className="truncate text-slate-200">
                          {s.best.name}
                          {category === 'edibles' ? (s.best.dose_mg ? ` · ${s.best.dose_mg}mg` : '') : s.best.weight_grams ? ` · ${+Number(s.best.weight_grams).toFixed(2)}G` : ''}
                        </span>
                        <strong className="shrink-0 font-mono text-emerald-400">{money(s.best.effective_price)}</strong>
                      </p>
                    )}
                    {where && <p className="text-slate-400">{where}</p>}
                    <div className="flex flex-wrap gap-2">
                      {s.deals > 0 && (
                        <a className="btn-primary !py-1.5 !px-3" href={`/?${baseQuery}${baseQuery ? '&' : ''}q=${encodeURIComponent(s.name)}#results`}>
                          See this store&apos;s deals
                        </a>
                      )}
                      <a
                        className="btn !py-1.5 !px-3"
                        target="_blank"
                        rel="noopener noreferrer"
                        href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.name} ${where || 'dispensary Illinois'}`)}`}
                      >
                        Directions ↗
                      </a>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
