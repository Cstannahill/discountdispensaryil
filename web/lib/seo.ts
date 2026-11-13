import type { City } from './cities.ts';

// Category landing pages: URL slug -> data category, plus the wording people actually search for.
export interface SeoCategory {
  slug: 'flower' | 'concentrates' | 'vapes' | 'edibles';
  category: 'flower' | 'concentrate' | 'vapes' | 'edibles';
  label: string; // plural display name
  product: string; // phrase used in titles: "Cheapest <product> in <city>"
  unit: string;
  intro: string;
}

export const SEO_CATEGORIES: readonly SeoCategory[] = [
  { slug: 'flower', category: 'flower', label: 'Flower', product: 'Weed (Flower)', unit: 'gram', intro: 'Whole flower ranked by price per gram, so an eighth, a quarter and an ounce compare fairly.' },
  { slug: 'concentrates', category: 'concentrate', label: 'Concentrates', product: 'Concentrates', unit: 'gram', intro: 'Wax, shatter, rosin, live resin and other concentrates ranked by price per gram.' },
  { slug: 'vapes', category: 'vapes', label: 'Vapes', product: 'Vapes and Cartridges', unit: 'gram', intro: 'Vape cartridges and disposables ranked by price per gram of oil.' },
  { slug: 'edibles', category: 'edibles', label: 'Edibles', product: 'Edibles', unit: '10 mg THC', intro: 'Gummies, chocolates and other edibles ranked by price per 10 mg of THC, the Illinois single serving.' },
];

export const seoCategoryBySlug = (slug: string) => SEO_CATEGORIES.find((c) => c.slug === slug);

// Place name used in searches. "Bloomington-Normal" is also searched as plain "Bloomington IL".
export const searchName = (c: City) => c.name;
