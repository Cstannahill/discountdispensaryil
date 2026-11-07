import type { MetadataRoute } from 'next';
import { CITIES } from '@/lib/cities';
import { SEO_CATEGORIES } from '@/lib/seo';
import { SITE_URL } from '@/lib/site';

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE_URL}/`, changeFrequency: 'daily', priority: 1 },
    { url: `${SITE_URL}/illinois-dispensary-price-comparison`, changeFrequency: 'daily' as const, priority: 0.9 },
    ...CITIES.map((c) => ({ url: `${SITE_URL}/dispensary-deals/${c.slug}`, changeFrequency: 'daily' as const, priority: 0.8 })),
    ...CITIES.flatMap((c) => SEO_CATEGORIES.map((k) => ({ url: `${SITE_URL}/dispensary-deals/${c.slug}/${k.slug}`, changeFrequency: 'daily' as const, priority: 0.7 }))),
  ];
}
