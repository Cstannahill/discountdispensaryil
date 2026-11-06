import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { CITIES, cityBySlug } from '@/lib/cities';
import { cachedDeals } from '@/lib/cached';
import { CATEGORIES, perUnit, unitLabel, type Offer } from '@/lib/deals';
import { SITE_NAME, SITE_URL } from '@/lib/site';

// Rendered on first request, then re-generated at most hourly (offers refresh a few times a day).
export const revalidate = 3600;
export function generateStaticParams() {
  return [];
}

const TOP_N = 10;
const money = (v: string | null | undefined) =>
  v == null || v === '' ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));
const LABEL: Record<string, string> = { flower: 'Flower', concentrate: 'Concentrates', vapes: 'Vapes', edibles: 'Edibles' };

async function load(slug: string) {
  const city = cityBySlug(slug);
  if (!city) return null;
  const results = await Promise.all(
    CATEGORIES.map((category) =>
      cachedDeals({
        origin: { latitude: city.latitude, longitude: city.longitude, radius_miles: city.radius_miles },
        license_type: 'recreational',
        category,
        group: true,
        sort: 'value',
        page: 1,
        page_size: TOP_N,
      })
    )
  );
  return { city, results };
}

export async function generateMetadata({ params }: { params: Promise<{ city: string }> }): Promise<Metadata> {
  const data = await load((await params).city);
  if (!data) return {};
  const { city, results } = data;
  const flower = results[CATEGORIES.indexOf('flower')].items[0];
  const best = flower && perUnit(flower) ? ` Flower from ${money(perUnit(flower))}/g.` : '';
  const title = `Cheapest Weed in ${city.name}, IL: Best $/g Dispensary Deals`;
  const description = `Lowest observed prices per gram for flower, concentrates, vapes and edibles at recreational dispensaries within ${city.radius_miles} miles of ${city.name}, Illinois.${best} Pre-tax menu prices.`;
  const url = `/dispensary-deals/${city.slug}`;
  const empty = results.every((r) => r.total === 0);
  return {
    title,
    description,
    alternates: { canonical: url },
    robots: empty ? { index: false, follow: true } : undefined,
    openGraph: { type: 'website', siteName: SITE_NAME, url, title, description },
    twitter: { card: 'summary_large_image', title, description },
  };
}

function DealRow({ o, rank, category }: { o: Offer; rank: number; category: string }) {
  const meta = [o.brand, o.weight_label, o.thc_pct && `THC ${o.thc_pct}`].filter(Boolean).join(' · ');
  return (
    <li className="flex items-start justify-between gap-3 py-2 border-b border-slate-800/80 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-white truncate">
          {rank}. {o.name}
        </p>
        <p className="text-[11px] text-slate-400 truncate">
          {o.store_name} · {Math.round(o.distance_miles)} mi{meta ? ` · ${meta}` : ''}
        </p>
      </div>
      <div className="text-right shrink-0">
        <p className="font-mono font-extrabold text-emerald-300 text-sm">
          {money(perUnit(o))}/{unitLabel(category)}
        </p>
        <p className="text-[11px] text-slate-400 font-mono">{money(o.effective_price)} total</p>
      </div>
    </li>
  );
}

export default async function CityPage({ params }: { params: Promise<{ city: string }> }) {
  const data = await load((await params).city);
  if (!data) notFound();
  const { city, results } = data;
  const appHref = `/?${new URLSearchParams({ lat: String(city.latitude), lon: String(city.longitude), radius: String(city.radius_miles), place: `${city.name}, IL` })}`;
  const url = `${SITE_URL}/dispensary-deals/${city.slug}`;
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: SITE_NAME, item: `${SITE_URL}/` },
          { '@type': 'ListItem', position: 2, name: `${city.name} dispensary deals`, item: url },
        ],
      },
      {
        '@type': 'ItemList',
        name: `Cheapest cannabis per gram near ${city.name}, Illinois`,
        url,
        itemListElement: CATEGORIES.flatMap((c, i) => results[i].items.slice(0, 5).map((o) => ({ category: c, o })))
          .map(({ o }, idx) => ({ '@type': 'ListItem', position: idx + 1, name: `${o.name} at ${o.store_name}` })),
      },
    ],
  };

  return (
    <main className="max-w-3xl mx-auto px-3 sm:px-5 py-6 space-y-6">
      <nav aria-label="Breadcrumb" className="text-xs text-slate-400">
        <Link href="/" className="hover:text-emerald-300">{SITE_NAME}</Link> / <span>{city.name}</span>
      </nav>
      <header className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-extrabold text-white">Cheapest Weed in {city.name}, Illinois</h1>
        <p className="text-sm text-slate-300">
          The lowest price per gram on live recreational dispensary menus within {city.radius_miles} miles of {city.name}. {city.blurb} Prices are pre-tax, taken from menus synced in the last 12 hours, and ranked by cost per gram (per 10 mg THC for edibles).
        </p>
        <Link href={appHref} className="btn-primary inline-block !py-2 !px-4 text-sm">
          Filter and compare all {city.name} deals →
        </Link>
      </header>

      {CATEGORIES.map((category, i) => {
        const r = results[i];
        return (
          <section key={category} aria-labelledby={`h-${category}`} className="glass-card rounded-2xl p-4">
            <h2 id={`h-${category}`} className="text-lg font-extrabold text-white">
              Cheapest {LABEL[category]} near {city.name}
            </h2>
            {r.items.length === 0 ? (
              <p className="text-sm text-slate-400 mt-2">No comparable {category} offers right now.</p>
            ) : (
              <ol className="mt-2">
                {r.items.map((o, idx) => (
                  <DealRow key={o.id} o={o} rank={idx + 1} category={category} />
                ))}
              </ol>
            )}
            {r.total > TOP_N && (
              <p className="text-[11px] text-slate-500 mt-2">Showing the top {TOP_N} of {r.total} listings.</p>
            )}
          </section>
        );
      })}

      <section aria-labelledby="h-more" className="space-y-2">
        <h2 id="h-more" className="text-base font-extrabold text-white">Other Illinois cities</h2>
        <ul className="flex flex-wrap gap-2">
          {CITIES.filter((c) => c.slug !== city.slug).map((c) => (
            <li key={c.slug}>
              <Link href={`/dispensary-deals/${c.slug}`} className="btn !py-1.5 !px-3 text-xs">
                {c.name}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c') }} />
    </main>
  );
}
