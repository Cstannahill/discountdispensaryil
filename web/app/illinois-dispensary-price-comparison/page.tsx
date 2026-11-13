import type { Metadata } from 'next';
import Link from 'next/link';
import { CITIES } from '@/lib/cities';
import { cachedDeals } from '@/lib/cached';
import { perUnit, unitLabel } from '@/lib/deals';
import { SEO_CATEGORIES } from '@/lib/seo';
import { SITE_NAME, SITE_URL } from '@/lib/site';

// Needs the database, so render on request (the data itself is cached by cachedDeals) instead of at build time.
export const dynamic = 'force-dynamic';

const money = (v: string | null | undefined) =>
  v == null || v === '' ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

const title = 'Illinois Dispensary Price Comparison: Cheapest Cannabis by City';
const description =
  'Compare recreational cannabis prices across Illinois dispensaries. See the lowest price per gram for flower, concentrates and vapes in Chicago, Peoria, Bloomington-Normal, Champaign, Springfield and more.';
export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: '/illinois-dispensary-price-comparison' },
  openGraph: { type: 'website', siteName: SITE_NAME, url: '/illinois-dispensary-price-comparison', title, description },
};

export default async function Page() {
  // One cheapest offer per city and category (cached, so cheap after the first render).
  const table = await Promise.all(
    CITIES.map(async (city) => ({
      city,
      best: await Promise.all(
        SEO_CATEGORIES.map(async (cat) => {
          const r = await cachedDeals({
            origin: { latitude: city.latitude, longitude: city.longitude, radius_miles: city.radius_miles },
            license_type: 'recreational', category: cat.category, group: true, sort: 'value', page: 1, page_size: 1,
          });
          return r.items[0] ?? null;
        })
      ),
    }))
  );
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: SITE_NAME, item: `${SITE_URL}/` },
      { '@type': 'ListItem', position: 2, name: 'Illinois dispensary price comparison', item: `${SITE_URL}/illinois-dispensary-price-comparison` },
    ],
  };
  return (
    <main className="max-w-4xl mx-auto px-3 sm:px-5 py-6 space-y-6">
      <nav aria-label="Breadcrumb" className="text-xs text-slate-400">
        <Link href="/" className="hover:text-emerald-300">{SITE_NAME}</Link> / <span>Illinois price comparison</span>
      </nav>
      <header className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-extrabold text-white">Illinois Dispensary Price Comparison</h1>
        <p className="text-sm text-slate-300">
          {SITE_NAME} imports full recreational menus from Illinois dispensaries several times a day and ranks every product by cost per gram (per 10 mg THC for edibles). The table shows the lowest current price in each region; pick a city for the full ranked list, or use your location on the home page to find the best dispensary deals near you.
        </p>
        <Link href="/" className="btn-primary inline-block !py-2 !px-4 text-sm">Find deals near me →</Link>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <caption className="sr-only">Lowest current price by Illinois region and category</caption>
          <thead className="text-xs text-slate-400">
            <tr>
              <th scope="col" className="py-2 pr-3">Region</th>
              {SEO_CATEGORIES.map((c) => <th key={c.slug} scope="col" className="py-2 pr-3">{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {table.map(({ city, best }) => (
              <tr key={city.slug} className="border-t border-slate-800/80">
                <th scope="row" className="py-2 pr-3 font-semibold text-white">
                  <Link href={`/dispensary-deals/${city.slug}`} className="hover:text-emerald-300">{city.name}</Link>
                </th>
                {best.map((o, i) => (
                  <td key={SEO_CATEGORIES[i].slug} className="py-2 pr-3 font-mono">
                    {o ? (
                      <Link href={`/dispensary-deals/${city.slug}/${SEO_CATEGORIES[i].slug}`} className="text-emerald-300 hover:underline">
                        {money(perUnit(o))}/{unitLabel(o.category)}
                      </Link>
                    ) : <span className="text-slate-500">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">Prices are pre-tax menu prices from listings seen in the last 12 hours. Recreational menus only.</p>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c') }} />
    </main>
  );
}
