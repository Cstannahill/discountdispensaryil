// Canonical site origin. Set NEXT_PUBLIC_SITE_URL when a custom domain is attached.
const raw =
  process.env.NEXT_PUBLIC_SITE_URL ||
  (process.env.VERCEL_ENV === 'production' && process.env.VERCEL_PROJECT_PRODUCTION_URL
    ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
    : '') ||
  'https://discountdispensaryil.vercel.app';

export const SITE_URL = raw.replace(/\/+$/, '');
export const SITE_NAME = 'DiscountDispensaryIL';
export const SITE_TITLE = 'DiscountDispensaryIL: Cheapest Cannabis $/g at Illinois Dispensaries';
export const SITE_DESCRIPTION =
  'Compare the lowest observed price per gram for flower, concentrates, vapes and edibles at Illinois dispensaries near you, from full menu imports.';
