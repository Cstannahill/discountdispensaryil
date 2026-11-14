// The app talks only to the public JSON API the web app already serves. No database credentials ship in the app.
export const API_BASE = (process.env.EXPO_PUBLIC_API_URL || 'https://discountdispensaryil.tannahillsystems.com').replace(/\/+$/, '');
export const APP_NAME = 'DiscountDispensaryIL';
export const PAGE_SIZE = 20;
