# DiscountDispensaryIL mobile app

The React Native (Expo SDK 58, Expo Router, TypeScript) version of the web app in `web/`. It is a separate app: nothing in
`web/` or `backend/` changes, and it reads the same public JSON API the site already serves
(`/api/v1/deals`, `/api/v1/stores`, `/api/v1/geocode`) plus one route added for it, `/api/v1/stores/map`. No database
credentials ship in the app.

## Run it

```bash
cd mobile
npm install
npx expo start          # scan the QR code with Expo Go, or press a / i for an emulator
npm run typecheck
npm test
```

The API host defaults to `https://discountdispensaryil.tannahillsystems.com`. Point it elsewhere (for example a local
`web` dev server reachable from the phone) with `EXPO_PUBLIC_API_URL=http://192.168.1.x:3000 npx expo start`.

`npm run web` is a developer preview in a browser. It works against the live site because `/api/v1/*` allows any origin
(set in `web/next.config.mjs`). The native map is replaced by a list there. Phone builds never needed those headers.

## What the first slice does

| Area | Behaviour |
| --- | --- |
| Deals | Ranked $/g list per category (flower, concentrate, vapes, edibles), search as you type, Rec/Med switch, sort, grade, strain, size, older-menu and unverified toggles, infinite scroll, pull to refresh. Same query params as the web page, so results match. |
| Location | Native GPS with the system permission prompt, place name from the phone's own geocoder (falls back to the API), ZIP or city entry, the 12 quick hubs, radius. |
| Fresh location | Every time the app returns to the foreground a GPS fix older than 5 minutes is re-read. Under 3 miles nothing changes, 3 to 25 miles swaps with a toast, over 25 miles asks first. A typed ZIP or city is never overwritten. No background location. |
| Freshness | `fresh` / `last menu Nd ago` / `unverified total` badge on every card, "updated" time, and a "checked 2m ago" line on the list. |
| Offline | The last result of each of the 12 most recent searches is stored on the phone. The list shows it at once on launch and, with no signal, says how old it is. |
| Map | A pin per dispensary showing its best $/g in the chosen category, the cheapest one highlighted. Tap a pin for the address, the best deal, exact-address directions, its deals, or to hide it. Uses Apple Maps on iPhone and Google Maps on Android. Needs `/api/v1/stores/map` to be deployed; until then the tab says so. |
| Saved deals | Save from any card. Opening the Saved tab re-reads each deal from today's menu and flags price drops, rises and delisted products. |
| Dispensaries | Stores in the search area with a show/hide switch (also long-press a store name on a card). Hidden stores are filtered by the API, as on the web. |
| Out the door | The web calculator's Illinois tax math (`src/lib/calculator.ts` is a copy of `web/lib/calculator.ts`), prefilled from a card's OTD button. |
| Native touches | Haptics on selection, save and refresh; system share sheet; menus open in the in-app browser; directions open the maps app; native tab bar; deep links `discountdispensaryil://`, `discountdispensaryil://saved`, `discountdispensaryil://?q=rosin&category=concentrate`. |

## Layout

- `src/app/` screens (Expo Router): `index` Deals, `map`, `saved`, `stores`, `calculator`, `_layout` native tabs.
- `web/lib/store-map.ts` and `web/app/api/v1/stores/map/route.ts` (in the web app) serve the map. They are new files; no existing web page or route uses them.
- `src/lib/` pure logic with unit tests in `src/lib/__tests__/`: API client, query building, cache, location rules, price watch, formatting.
- `src/state/store.ts` one small persisted store (AsyncStorage): origin, filters, saved deals, hidden stores.
- `src/components/` offer card, location sheet, filter sheet, UI primitives.

## Roadmap

1. **Done.** Everything in the table above, including the map.
2. **Price-drop push notifications.** A watch on saved deals and on searches ("flower under $5/g within 25 mi"), delivered as push after each sync, with a deep link to the deal.
3. **Store pages and history.** A dispensary screen (all its deals, call, directions) and a price-history sparkline per product.
4. **Polish for release.** Home-screen widget with today's best deal, age gate (21+), store listing, EAS build profiles, TestFlight and Play internal testing.

### API additions the next phases need (not built)

New routes under `web/app/api/v1/` only, reading the Neon mirror server-side as today. Existing routes and pages stay as they are.

- `GET /api/v1/offers?ids=`: current state of specific offers. Replaces the per-deal search the Saved tab does now with one request.
- `POST /api/v1/push/subscribe` with a new `push_subscriptions` table (Expo push token, watched offers and searches), and a step after each sync's Neon push that compares prices and sends through Expo's push service. This is the only piece that writes data.

### Things to know before a store release

- Apple allows cannabis apps that do not facilitate sales, but requires them to be geo-restricted to legal regions and rated 17+. Google Play does not allow apps that facilitate cannabis sales; a price comparison that links out to dispensary menus is a grey area, so expect review questions there.
- Publishing needs an Apple Developer account ($99/yr) and a Google Play account ($25 once). Until then the app runs through Expo Go or a development build.
- Android store builds need a free Google Maps API key for the map (set through the `react-native-maps` config plugin in `app.json`). Expo Go and iPhone builds do not.
- The bundle id `com.tannahillsystems.discountdispensaryil` in `app.json` is a placeholder choice and is easy to change before the first store build.

## Not verified yet

Built and tested in a cloud container: type check, unit tests, iOS / Android / web bundles, and a browser walkthrough of every
screen against mocked API responses in the shape of `web/lib/deals.ts`. The map query was run against a local Postgres 16
with fixture stores and offers. The native map view itself cannot render in a browser, so it has only been bundled, not seen. It has not been run on a physical phone or against
the live API from here, so GPS prompts, haptics, the share sheet and the in-app browser still need a first pass on a device.
