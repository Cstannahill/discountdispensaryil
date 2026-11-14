// Visitor-selectable page layouts for the home page. The choice lives in a cookie so the server renders the
// chosen layout directly (no flash of the default one), and is changed from the ⋯ menu.
export const LAYOUT_COOKIE = 'dd_layout';

export const LAYOUTS = [
  { id: 'classic', label: 'Classic', hint: 'Large cards by category' },
  { id: 'board', label: 'Price board', hint: 'Dense ranked list' },
  { id: 'app', label: 'App style', hint: 'Light theme, slim cards' },
  { id: 'dashboard', label: 'Overview', hint: 'All categories at a glance' },
  { id: 'map', label: 'Map', hint: 'Dispensaries by best price' },
] as const;

export type LayoutId = (typeof LAYOUTS)[number]['id'];
export const DEFAULT_LAYOUT: LayoutId = 'classic';

export function parseLayout(v?: string | null): LayoutId {
  return LAYOUTS.find((l) => l.id === v)?.id ?? DEFAULT_LAYOUT;
}
