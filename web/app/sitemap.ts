import type { MetadataRoute } from 'next';
import { CITIES } from '@/lib/cities';
import { SITE_URL } from '@/lib/site';

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE_URL}/`, changeFrequency: 'daily', priority: 1 },
    ...CITIES.map((c) => ({ url: `${SITE_URL}/dispensary-deals/${c.slug}`, changeFrequency: 'daily' as const, priority: 0.8 })),
  ];
}
