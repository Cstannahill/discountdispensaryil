// Mirror of backend/product_links.py: deep links to one product on a dispensary's own menu.
// Only patterns confirmed against live menus are built; anything else keeps the store menu link.
const SWEED_SKIP_HOSTS = ['curaleaf.com'];

const clean = (url?: string | null) => {
  try {
    const u = new URL(url ?? '');
    return ['https:', 'http:'].includes(u.protocol) ? `${u.protocol}//${u.host}${u.pathname}`.replace(/\/+$/, '') : null;
  } catch { return null; }
};

export function productUrl(provider: string, url: string, licenseType: string, item: Record<string, any>): string | null {
  let base = clean(url);
  if (!base) return null;
  const raw = item.raw ?? {};
  const sourceId = String(item.source_id ?? '');
  const host = new URL(base).host.toLowerCase().replace(/^www\./, '');
  if (provider === 'dutchie') {
    if (host === 'dutchie.com' && /\/embedded-menu\/[0-9a-f]+$/.test(base) && sourceId) return `${base}/product/${encodeURIComponent(sourceId)}`;
  } else if (provider === 'joint') {
    if (sourceId) return `${base}/?product_page=${encodeURIComponent(sourceId)}`;
  } else if (provider === 'sweed' || provider === 'verano') {
    const variant = raw.variant?.id, category = raw.product?.category ?? {};
    if (variant == null || !category.id || !category.canonicalName || SWEED_SKIP_HOSTS.includes(host)) return null;
    if (provider === 'verano') {
      if (!/\/locations\/[^/]+\/menu$/.test(base)) return null;
      base += `/${licenseType === 'medicinal' ? 'medical' : 'recreational'}/menu`;
    } else if (!base.endsWith('/menu')) return null;
    return `${base}/${encodeURIComponent(String(category.canonicalName))}-${category.id}/x-${variant}`;
  }
  return null;
}

/** The product page when the offer's link is only the store menu. */
export function withProductUrl(item: Record<string, any>, provider: string, url: string, licenseType: string): string {
  const current = item.source_url;
  if (current && clean(current) !== clean(url)) return current;
  return productUrl(provider, url, licenseType, item) ?? current ?? url;
}
