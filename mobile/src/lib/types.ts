// Shapes returned by the web app's /api/v1 routes (web/lib/deals.ts).
export const CATEGORIES = ['flower', 'concentrate', 'vapes', 'edibles'] as const;
export type Category = (typeof CATEGORIES)[number];
export const CATEGORY_LABEL: Record<Category, string> = { flower: 'Flower', concentrate: 'Concentrate', vapes: 'Vapes', edibles: 'Edibles' };
export const GRADES = ['whole', 'smalls', 'shake', 'infused', 'all'] as const;
export type Grade = (typeof GRADES)[number];
export const LICENSES = ['recreational', 'medicinal'] as const;
export type License = (typeof LICENSES)[number];
export const STRAINS = ['Indica', 'Sativa', 'Hybrid'] as const;
export const SIZES = ['any', '0.5', '1', '3.5', '7', '14', '28'] as const;
const FLOWER_ONLY_SIZES = new Set(['3.5', '7', '14', '28']);
export const SORT_OPTIONS = ['value', 'price', 'thc', 'distance', 'discount'] as const;
export type SortOption = (typeof SORT_OPTIONS)[number];
export const SORT_LABEL: Record<SortOption, string> = { value: 'Best value', price: 'Lowest price', thc: 'Highest THC', distance: 'Nearest', discount: 'Biggest discount' };
export const RADII = [5, 10, 25, 50, 100, 200] as const;

export const QUICK_HUBS: readonly (readonly [string, string])[] = [
  ['Chicago', '60601'], ['Naperville', '60540'], ['Joliet', '60431'], ['Rockford', '61101'], ['Quad Cities', '61265'], ['Peoria', '61602'],
  ['Normal', '61761'], ['Champaign', '61820'], ['Springfield', '62701'], ['Streator', '61358'], ['Metro East', '62234'], ['Carbondale', '62901'],
];

/** Sizes offered for a category: edibles have no gram size, and eighths and up exist only for flower. */
export function sizesFor(category: Category): readonly string[] {
  if (category === 'edibles') return ['any'];
  return category === 'flower' ? SIZES : SIZES.filter((s) => !FLOWER_ONLY_SIZES.has(s));
}

export interface Variant { id: string; name: string; strain_type: string | null; thc_pct: string | null; source_url: string | null }
export interface Offer {
  id: string; endpoint_id: string; store_id: string; store_name: string; license_type: string; name: string;
  brand?: string | null; category: string; strain_type?: string | null; thc_pct?: string | null;
  weight_grams: string | null; weight_label?: string | null; regular_price: string | null; effective_price: string | null;
  price_per_gram: string | null; dose_mg?: string | null; pack_count?: number | null; price_per_10mg?: string | null;
  conditional?: boolean; promo?: string | null; completeness: string; freshness: string; menu_as_of?: string | null; menu_age_hours?: number | null;
  flower_grade: string | null; distance_miles: number; last_seen_at: string; source_url?: string | null;
  variants?: Variant[];
}
export interface Page<T> { items: T[]; total: number; page: number; page_size: number; data_version: string }
export interface AreaStore { id: string; name: string; distance_miles: number }

export interface Origin { lat: number; lon: number; place: string; src: 'gps' | 'manual'; at: number }

export interface Filters {
  license: License; category: Category; q: string; sort: SortOption; grade: Grade; strain: string; size: string;
  stale: boolean; unverified: boolean; radius: number;
}
export const DEFAULT_FILTERS: Filters = {
  license: 'recreational', category: 'flower', q: '', sort: 'value', grade: 'whole', strain: '', size: 'any', stale: false, unverified: false, radius: 50,
};

export interface SavedDeal {
  id: string; store_id: string; name: string; brand?: string | null; store_name: string;
  price_per_gram?: string | null; price_per_10mg?: string | null; effective_price?: string | null; regular_price?: string | null;
  massLabel: string; category: string; source_url?: string | null; distance_miles: number; saved_at: number;
  weight_grams?: string | null; dose_mg?: string | null; license_type?: string | null; flower_grade?: string | null; thc_pct?: string | null;
  /** The product's own name, used to find it again on a later menu (name is a display title for grouped cards). */
  match_name: string;
  /** Where the search was centred when the deal was saved; its distance_miles is measured from here. */
  near: { lat: number; lon: number } | null;
}
