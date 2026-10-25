import LocationControl from './location';
import FilterStrip from './filters';
import CategoryGrid from './categories';
import OfferCard from './offer-card';
import CalculatorModal from './calculator';
import SavedModal from './saved-modal';
import ToastContainer from './toast';
import BackToTop from './back-to-top';
import { parseOrigin } from '@/lib/origin';
import {
  CATEGORIES,
  GRADES,
  LICENSES,
  SIZES,
  STRAINS,
  SORT_OPTIONS,
  type SortOption,
  queryDeals,
  regions,
  sizeForCategory,
} from '@/lib/deals';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 20;
const ACCENT: Record<string, string> = {
  concentrate: '#fbbf24',
  flower: '#34d399',
  vapes: '#c084fc',
};
type Search = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';
const money = (v: string | null | undefined) =>
  v == null || v === ''
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

export default async function Home({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const reg = await regions();
  const regionId = one(sp.region) || reg.active_region_id || reg.items[0]?.id || '';
  const origin = parseOrigin((k) => one(sp[k]) || null);
  const license = LICENSES.includes(one(sp.license) as never) ? one(sp.license) : 'recreational';
  const grade = GRADES.includes(one(sp.grade) as never) ? one(sp.grade) : 'whole';
  const strainRaw = one(sp.strain);
  const strain = STRAINS.find((s) => s.toLowerCase() === strainRaw.toLowerCase()) ?? '';
  const sizeRaw = one(sp.size);
  const size = SIZES.includes(sizeRaw as never) ? sizeRaw : 'any';
  const q = one(sp.q).slice(0, 300);
  const stale = one(sp.stale) === '1';
  const unverified = one(sp.unverified) === '1';
  const bogo = one(sp.promo) === 'bogo';
  const sortRaw = one(sp.sort);
  const sort = SORT_OPTIONS.includes(sortRaw as never) ? (sortRaw as SortOption) : 'value';
  const cats = CATEGORIES;
  const pages = Object.fromEntries(
    cats.map((c) => [c, Math.max(1, Number(one(sp[`p_${c}`])) || 1)])
  );

  const results = await Promise.all(
    cats.map((category) =>
      queryDeals({
        region_id: regionId,
        origin: origin ?? undefined,
        license_type: license,
        category,
        q,
        include_stale: stale,
        include_unverified: unverified,
        flower_grade: grade,
        strain_type: strain || undefined,
        size: sizeForCategory(category, size),
        promo: bogo ? 'bogo' : undefined,
        group: true,
        sort,
        page: pages[category],
        page_size: PAGE_SIZE,
      })
    )
  );

  const base = {
    ...(origin
      ? {
          lat: String(origin.latitude),
          lon: String(origin.longitude),
          radius: String(origin.radius_miles),
          place: origin.label,
        }
      : { region: regionId }),
    license,
    grade: grade !== 'whole' ? grade : '',
    strain,
    size: size !== 'any' ? size : '',
    q,
    stale: stale ? '1' : '',
    unverified: unverified ? '1' : '',
    promo: bogo ? 'bogo' : '',
    sort: sort !== 'value' ? sort : '',
  };

  const link = (category: string, page: number) => {
    const u = new URLSearchParams();
    Object.entries({
      ...base,
      ...Object.fromEntries(
        cats.map((c) => [`p_${c}`, c === category ? String(page) : String(pages[c])])
      ),
    }).forEach(([k, v]) => {
      if (v) u.set(k, v);
    });
    return `/?${u.toString()}`;
  };

  const makeUrl = (overrides: Record<string, string | null>) => {
    const u = new URLSearchParams();
    Object.entries({ ...base, ...overrides }).forEach(([k, v]) => {
      if (v) u.set(k, v);
    });
    return `/?${u.toString()}`;
  };

  const region = origin
    ? { radius_miles: origin.radius_miles, label: origin.label }
    : reg.items.find((r) => r.id === regionId);

  const categoryChips = cats.map((c, i) => ({
    id: c,
    label: c,
    total: results[i].total,
    color: ACCENT[c],
  }));

  return (
    <main className="max-w-7xl mx-auto px-3 sm:px-5 pb-12 sm:py-4 space-y-3">
      <LocationControl
        active={!!origin}
        radius={region?.radius_miles ?? 50}
        place={region?.label ?? ''}
        license={license}
        dataVersion={results[0]?.data_version}
        chips={categoryChips}
      />

      <FilterStrip
        q={q}
        grade={grade}
        strain={strain}
        size={size}
        bogo={bogo}
        stale={stale}
        unverified={unverified}
        sort={sort}
      />

      {region && (
        <p className="text-[11px] text-slate-400 px-1">
          Showing <strong className="text-slate-200">{license}</strong> deals within{' '}
          <strong className="text-slate-200">{region.radius_miles} miles</strong> of{' '}
          <strong className="text-emerald-400">{region.label}</strong>. Pre-tax observed menu prices; menus older than 12h hidden unless included.
        </p>
      )}

      <CategoryGrid chips={categoryChips}>
        {cats.map((category, i) => {
          const r = results[i];
          const last = Math.max(1, Math.ceil(r.total / PAGE_SIZE));
          const page = pages[category];
          const topDeal = r.items[0];
          const activeSize = sizeForCategory(category, size);

          return (
            <section
              key={category}
              data-cat={category}
              className="glass-card rounded-2xl overflow-hidden"
              style={{ borderColor: `${ACCENT[category]}40` }}
            >
              <div
                className="category-art relative h-24 sm:h-28"
                style={{
                  backgroundImage: `linear-gradient(to top,#060a0d 8%,rgba(6,10,13,.35)),url('/${category}.jpg')`,
                }}
              >
                <div className="absolute inset-x-4 bottom-3 flex items-end justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span
                        className="badge uppercase tracking-widest font-bold"
                        style={{ color: ACCENT[category] }}
                      >
                        {category}
                      </span>
                      {activeSize && (
                        <span className="badge text-emerald-300 border-emerald-500/40">
                          {activeSize}g
                        </span>
                      )}
                      {strain && (
                        <span className="badge text-slate-200">{strain}</span>
                      )}
                    </div>
                    <h2 className="font-extrabold text-base sm:text-lg text-white mt-1 capitalize leading-tight">
                      {category} {bogo ? 'BOGO Deals' : 'Best Deals'}
                    </h2>
                  </div>

                  {topDeal?.price_per_gram && (
                    <div className="text-right bg-slate-950/85 border border-slate-800 rounded-xl px-2.5 py-1">
                      <span className="block text-[9px] uppercase tracking-wider text-slate-400">
                        Best $/g
                      </span>
                      <span
                        className="font-mono font-extrabold text-sm"
                        style={{ color: ACCENT[category] }}
                      >
                        {money(topDeal.price_per_gram)}/g
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="px-4 py-2 bg-slate-900/95 border-b border-slate-800/90 flex items-center justify-between text-[11px] text-slate-400">
                <span>
                  Ranked by <strong style={{ color: ACCENT[category] }}>price / gram</strong>
                </span>
                <span className="font-mono">
                  {r.total} {r.total === 1 ? 'listing' : 'listings'}
                </span>
              </div>

              <div className="p-3 space-y-2.5">
                {r.items.length === 0 ? (
                  <div className="text-center py-8 px-4 space-y-3">
                    <div className="space-y-1">
                      <p className="text-xs font-semibold text-slate-300">
                        No comparable {category} offers match these filters.
                      </p>
                      {(q || strain || size !== 'any' || grade !== 'whole' || bogo || stale || unverified || Number(region?.radius_miles ?? 50) < 50) ? (
                        <p className="text-[11px] text-slate-500">
                          Try one of these quick adjustments:
                        </p>
                      ) : (
                        <p className="text-[11px] text-slate-500">
                          Try widening your search radius or exploring another category.
                        </p>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
                      {(q || strain || size !== 'any' || grade !== 'whole' || bogo || stale || unverified) && (
                        <a
                          href={makeUrl({ q: null, strain: null, size: null, grade: null, promo: null, stale: null, unverified: null })}
                          className="btn-primary !py-1.5 !px-3 text-xs"
                        >
                          ✕ Clear all filters
                        </a>
                      )}
                      {size !== 'any' && (
                        <a href={makeUrl({ size: null })} className="btn !py-1.5 !px-3 text-xs">
                          Switch to Any Size
                        </a>
                      )}
                      {strain && (
                        <a href={makeUrl({ strain: null })} className="btn !py-1.5 !px-3 text-xs">
                          Show All Strains
                        </a>
                      )}
                      {Number(region?.radius_miles ?? 50) < 50 && (
                        <a
                          href={
                            origin
                              ? makeUrl({ radius: '50' })
                              : region && 'latitude' in region && typeof region.latitude === 'number'
                              ? makeUrl({
                                  lat: String(region.latitude),
                                  lon: String(region.longitude),
                                  radius: '50',
                                  place: region.label,
                                  region: null,
                                })
                              : makeUrl({ radius: '50' })
                          }
                          className="btn !py-1.5 !px-3 text-xs"
                        >
                          Expand range to 50 mi
                        </a>
                      )}
                    </div>
                  </div>
                ) : (
                  r.items.map((o, idx) => (
                    <OfferCard
                      key={o.id}
                      o={o}
                      rank={(page - 1) * PAGE_SIZE + idx + 1}
                    />
                  ))
                )}
              </div>

              {r.total > PAGE_SIZE && (
                <nav
                  aria-label={`${category} pagination`}
                  className="flex justify-between items-center px-4 py-3 border-t border-slate-800/90 text-xs bg-slate-950/40"
                >
                  {page > 1 ? (
                    <a className="btn" href={link(category, page - 1)}>
                      ← Prev
                    </a>
                  ) : (
                    <span />
                  )}
                  <span className="font-mono text-slate-400">
                    Page {page} of {last}
                  </span>
                  {page < last ? (
                    <a className="btn" href={link(category, page + 1)}>
                      Next →
                    </a>
                  ) : (
                    <span />
                  )}
                </nav>
              )}
            </section>
          );
        })}
      </CategoryGrid>

      <CalculatorModal />
      <SavedModal />
      <ToastContainer />
      <BackToTop />
    </main>
  );
}
