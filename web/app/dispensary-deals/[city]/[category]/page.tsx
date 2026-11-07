import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { CITIES, cityBySlug } from '@/lib/cities';
import { cachedDeals, cachedStoresInArea } from '@/lib/cached';
import { perUnit, unitLabel, type Offer } from '@/lib/deals';
import { SEO_CATEGORIES, seoCategoryBySlug } from '@/lib/seo';
import { SITE_NAME, SITE_URL } from '@/lib/site';

export const revalidate = 3600;
export function generateStaticParams() {
  return [];
}

const TOP_N = 25;
const money = (v: string | null | undefined) =>
  v == null || v === '' ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

async function load(citySlug: string, catSlug: string) {
  const city = cityBySlug(citySlug);
  const cat = seoCategoryBySlug(catSlug);
  if (!city || !cat) return null;
  const origin = { latitude: city.latitude, longitude: city.longitude, radius_miles: city.radius_miles };
  const [deals, stores] = await Promise.all([
    cachedDeals({ origin, license_type: 'recreational', category: cat.category, group: true, sort: 'value', page: 1, page_size: TOP_N }),
    cachedStoresInArea({ origin, license_type: 'recreational' }),
  ]);
  return { city, cat, deals, stores };
}

export async function generateMetadata({ params }: { params: Promise<{ city: string; category: string }> }): Promise<Metadata> {
  const { city: cs, category: ks } = await params;
  const data = await load(cs, ks);
  if (!data) return {};
  const { city, cat, deals } = data;
  const best = deals.items[0] && perUnit(deals.items[0]) ? ` Lowest right now: ${money(perUnit(deals.items[0]))} per ${cat.unit}.` : '';
  const title = `Cheapest ${cat.product} in ${city.name}, IL | ${SITE_NAME}`;
  const description = `Compare ${cat.label.toLowerCase()} prices at ${data.stores.length || ''} recreational dispensaries within ${city.radius_miles} miles of ${city.name}, Illinois, ranked by price per ${cat.unit}.${best} Pre-tax menu prices.`.replace(/\s+/g, ' ');
  const url = `/dispensary-deals/${city.slug}/${cat.slug}`;
  return {
    title,
    description,
    alternates: { canonical: url },
    robots: deals.total === 0 ? { index: false, follow: true } : undefined,
    openGraph: { type: 'website', siteName: SITE_NAME, url, title, description },
    twitter: { card: 'summary_large_image', title, description },
  };
}

function Row({ o, rank, category }: { o: Offer; rank: number; category: string }) {
  const meta = [o.brand, o.weight_label, o.thc_pct && `THC ${o.thc_pct}`].filter(Boolean).join(' · ');
  return (
    <li className="flex items-start justify-between gap-3 py-2 border-b border-slate-800/80 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-white truncate">{rank}. {o.name}</p>
        <p className="text-[11px] text-slate-400 truncate">{o.store_name} · {Math.round(o.distance_miles)} mi{meta ? ` · ${meta}` : ''}</p>
      </div>
      <div className="text-right shrink-0">
        <p className="font-mono font-extrabold text-emerald-300 text-sm">{money(perUnit(o))}/{unitLabel(category)}</p>
        <p className="text-[11px] text-slate-400 font-mono">{money(o.effective_price)} total</p>
      </div>
    </li>
  );
}

export default async function CityCategoryPage({ params }: { params: Promise<{ city: string; category: string }> }) {
  const { city: cs, category: ks } = await params;
  const data = await load(cs, ks);
  if (!data) notFound();
  const { city, cat, deals, stores } = data;
  const url = `${SITE_URL}/dispensary-deals/${city.slug}/${cat.slug}`;
  const best = deals.items[0];
  const appHref = `/?${new URLSearchParams({ lat: String(city.latitude), lon: String(city.longitude), radius: String(city.radius_miles), place: `${city.name}, IL` })}`;
  const faq = [
    {
      q: `Where is the cheapest ${cat.label.toLowerCase()} in ${city.name}, IL?`,
      a: best
        ? `Right now the lowest ${cat.label.toLowerCase()} price we see near ${city.name} is ${money(perUnit(best))} per ${cat.unit} for ${best.name} at ${best.store_name}. Prices change as menus update, so check the list above.`
        : `We do not have comparable ${cat.label.toLowerCase()} prices near ${city.name} right now.`,
    },
    {
      q: 'Are these prices before tax?',
      a: 'Yes. Prices are the dispensary menu price before Illinois cannabis taxes, which vary by product type and THC level, so compare them against each other rather than against your final receipt.',
    },
    {
      q: 'How often are the prices updated?',
      a: 'Menus are re-imported several times a day, and only listings seen in the last 12 hours are shown.',
    },
  ];
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: SITE_NAME, item: `${SITE_URL}/` },
          { '@type': 'ListItem', position: 2, name: `${city.name} dispensary deals`, item: `${SITE_URL}/dispensary-deals/${city.slug}` },
          { '@type': 'ListItem', position: 3, name: `Cheapest ${cat.label}`, item: url },
        ],
      },
      {
        '@type': 'ItemList',
        name: `Cheapest ${cat.label.toLowerCase()} near ${city.name}, Illinois`,
        url,
        itemListElement: deals.items.slice(0, 10).map((o, i) => ({ '@type': 'ListItem', position: i + 1, name: `${o.name} at ${o.store_name}` })),
      },
      { '@type': 'FAQPage', mainEntity: faq.map((f) => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })) },
    ],
  };

  return (
    <main className="max-w-3xl mx-auto px-3 sm:px-5 py-6 space-y-6">
      <nav aria-label="Breadcrumb" className="text-xs text-slate-400">
        <Link href="/" className="hover:text-emerald-300">{SITE_NAME}</Link> /{' '}
        <Link href={`/dispensary-deals/${city.slug}`} className="hover:text-emerald-300">{city.name}</Link> / <span>{cat.label}</span>
      </nav>
      <header className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-extrabold text-white">Cheapest {cat.product} in {city.name}, Illinois</h1>
        <p className="text-sm text-slate-300">
          {cat.intro} We compare {stores.length > 0 ? `${stores.length} ` : ''}recreational dispensaries within {city.radius_miles} miles of {city.name}. {city.blurb} Prices are pre-tax menu prices from the last 12 hours.
        </p>
        <Link href={appHref} className="btn-primary inline-block !py-2 !px-4 text-sm">Filter and compare all {city.name} {cat.label.toLowerCase()} →</Link>
      </header>

      <section aria-labelledby="h-deals" className="glass-card rounded-2xl p-4">
        <h2 id="h-deals" className="text-lg font-extrabold text-white">Lowest {cat.label.toLowerCase()} prices near {city.name}</h2>
        {deals.items.length === 0 ? (
          <p className="text-sm text-slate-400 mt-2">No comparable {cat.label.toLowerCase()} offers right now.</p>
        ) : (
          <ol className="mt-2">{deals.items.map((o, i) => <Row key={o.id} o={o} rank={i + 1} category={cat.category} />)}</ol>
        )}
        {deals.total > TOP_N && <p className="text-[11px] text-slate-500 mt-2">Showing the top {TOP_N} of {deals.total} listings.</p>}
      </section>

      {stores.length > 0 && (
        <section aria-labelledby="h-stores" className="space-y-2">
          <h2 id="h-stores" className="text-base font-extrabold text-white">Dispensaries we compare near {city.name}</h2>
          <ul className="text-sm text-slate-300 grid sm:grid-cols-2 gap-x-6 gap-y-1">
            {stores.slice(0, 40).map((s) => (
              <li key={s.id}>{s.name} <span className="text-slate-500 text-xs">· {Math.round(s.distance_miles)} mi</span></li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="h-faq" className="space-y-3">
        <h2 id="h-faq" className="text-base font-extrabold text-white">Questions</h2>
        {faq.map((f) => (
          <div key={f.q}>
            <h3 className="text-sm font-bold text-white">{f.q}</h3>
            <p className="text-sm text-slate-300">{f.a}</p>
          </div>
        ))}
      </section>

      <nav aria-label="Other categories" className="space-y-2">
        <h2 className="text-base font-extrabold text-white">More in {city.name}</h2>
        <ul className="flex flex-wrap gap-2">
          <li><Link href={`/dispensary-deals/${city.slug}`} className="btn !py-1.5 !px-3 text-xs">All {city.name} deals</Link></li>
          {SEO_CATEGORIES.filter((c) => c.slug !== cat.slug).map((c) => (
            <li key={c.slug}><Link href={`/dispensary-deals/${city.slug}/${c.slug}`} className="btn !py-1.5 !px-3 text-xs">Cheapest {c.label.toLowerCase()}</Link></li>
          ))}
        </ul>
        <ul className="flex flex-wrap gap-2 pt-1">
          {CITIES.filter((c) => c.slug !== city.slug).map((c) => (
            <li key={c.slug}><Link href={`/dispensary-deals/${c.slug}/${cat.slug}`} className="text-xs text-slate-400 hover:text-emerald-300">{cat.label} in {c.name}</Link></li>
          ))}
        </ul>
      </nav>

      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c') }} />
    </main>
  );
}
