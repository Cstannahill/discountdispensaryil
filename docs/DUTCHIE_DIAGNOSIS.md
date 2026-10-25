# Dutchie through the browser path: diagnosis (2026-10-18)

Probes: `data/dutchie-probe1.json`, `data/dutchie-explore*.json`, `data/dutchie-replay.json`. Live fetches used `providers.generic.fetch` directly; nothing was written to `terpscout.db`.

## What was blocking Dutchie

| # | Blocker | Evidence | Status |
| --- | --- | --- | --- |
| 1 | **Not a challenge.** Dutchie's 403 is a raw-HTTP rejection. The ordinary browser path returns 200 for `dutchie.com/embedded-menu/<id>` and `dutchie.com/stores/<slug>` and loads products through `GET /api-N/graphql` persisted queries. | probe: 13 to 26 FilteredProducts responses, no 4xx, no gate | Browser path works. The stored `Access challenge ... HTTP 403` errors predate it. |
| 2 | **The extractor could not read Dutchie's schema.** Products carry `Name`, parallel arrays `Options[i]` / `recPrices[i]` / `recSpecialPrices[i]` / `medicalPrices[i]`, `THCContent.range`, `Status`, `optionsBelowThreshold`; the total is `queryInfo.totalCount`. Result before: 0 items. | `network_extract` returned 0 on the captured payload | Fixed: option/price-array variants, license-aware prices, `optionsBelowThreshold` availability, `queryInfo` totals. |
| 3 | **Only the first page of each query loads.** The home view fetches 25 products per category; the full menu needs paging. | 42 more whole-menu pages exist for Noxx | Fixed: the worker replays observed paged GET queries from inside the page (`replayPagination`); when there is no whole-menu query it visits each category page and steps its pager. |
| 4 | **Totals could be wrong.** A flagged query such as `staffPicks` (19 results) looked like a whole menu. | Excelleaf | Fixed: whole-menu detection is now a whitelist of benign filter keys; category totals sum to a catalog total; conflicting totals resolve to the larger, so a partial union cannot reconcile. |
| 5 | **Wrong-branch menus were attached to a store.** Noxx East Peoria has endpoints for other Noxx branches (28th St, Plainfield Ave) because carousel embeds on a multi-branch page were adopted under the page's identity. With a working extractor these would have been ingested. | embed `627458da...` declares `2440 28th St SE` | Fixed in extraction: a platform-declared street address (`location.ln1`) must match the registry store, else `different street address` (BRANCH_MISMATCH). Verified live: the 28th St embed is refused, the East Peoria one accepted. **Existing wrong endpoint rows are not cleaned up.** |
| 6 | **v2 embed script parsed as a store.** `.../api/v2/embedded-menu/<id>.js` produced `provider_store_id = "v2"` and the script URL as the menu (Excelleaf). | `live_endpoints` row | Fixed in `provider_links`. |
| 7 | Shared robustness found on the way | | Pending captures from a navigated-away page no longer hang the render; request budget raised to 4000 for paged menus; category navigation failures are reported. |

## Live results (generic fetch, scratch only)

| Store | Menu | Result |
| --- | --- | --- |
| Noxx East Peoria | `dutchie.com/embedded-menu/65772a69ac53410009424572` | `complete: true`, 1071 variants, whole-menu total 1058 reconciled (equals the category sum), two stable passes. About 70 s per pass. |
| Noxx, wrong branch | `.../627458da5d75a3008f52fc56` | Refused: `different street address: 2440 28th St SE`. |
| Excelleaf DeKalb | `dutchie.com/embedded-menu/64888ad400476b00104ffe4d` | Partial, 1301 products. Five categories reconcile exactly (Flower 333, Edible 339, Vaporizers 288, Pre-rolls 222, Concentrate 109 = 1291). The other 10 products (6 accessories, 4 topicals) appear only in the specials listing; their own category pages declared no total. The site contradicts itself, so it stays partial rather than being accepted. |

## Not done

- No sync against the real database. Noxx has six `dutchie` endpoint rows (three describe the correct store through different URLs, the rest are other branches). A sync now would accept the correct catalog more than once. First supersede the wrong-branch endpoints and de-duplicate by Dutchie dispensary id (`provider_store_id` is currently the URL slug on some rows). I did not change those rows.
- Excelleaf stays partial until a rule for products that exist only in a promotional listing is decided.
- Retailer-hosted pages (excelleaf.com/menu, noxx.com/location/...) only reference the Dutchie embed; the Dutchie-hosted menu is the reliable source, so discovery should resolve embeds to `dutchie.com/embedded-menu/<id>`.

## Update: Noxx cleaned up and synced for real (2026-10-18)

- Five Noxx East Peoria endpoint rows were retired with `Store.supersede_endpoint` (rows and evidence kept; reasons recorded; a before-image is in `data/noxx-endpoints-before-cleanup.json`): three other businesses/branches identified by their embed `routeRoot` (`noxx-28th-st`, `noxx-plainfield-ave`, `cookiesmd`) and two duplicates of the correct dispensary (reached by store slug and by an experiences URL, with slug-style `provider_store_id` values). The correct row `dutchie.com/embedded-menu/65772a69ac53410009424572` already had the dispensary id as its `provider_store_id`.
- `supersede_endpoint` refuses an endpoint that holds active accepted offers, and discovery no longer revives or imports a superseded endpoint (`service.py`).
- Targeted sync (run `df3251e2...`): `complete`, grade A, 1071 variants from 1058 products, reconciled to the platform's total of 1058; 615 variants are comparable offers (the rest lack package mass).

## Update: the "HTTP 403" stores were our own tunnel budget (2026-10-22)

- Nine Dutchie stores failed with `HTTP_REJECTED` ("HTTP 403"). Saved browser evidence shows no 4xx: each failing run (1,850 to 2,134 requests, about 200 MB captured) logged 29 to 122 `Browser tunnel byte budget exceeded` blocks in `tunnel_blocks`, then Chrome reported `net::ERR_SSL_PROTOCOL_ERROR` on a category navigation and showed its error page. 18 stores (15 Dutchie, 2 Joint, 1 other) have such runs. A plain HTTP client does get Cloudflare's 403 for the API, so reads must stay inside the loaded page.
- The embed home loads no `FilteredProducts` query, so the worker found no whole-menu query and replayed about 85 category and collection queries and opened 27 pages.
- Fix: `replayDutchieWholeMenu` (`browser_worker.cjs`) learns the query template from one `/products/<category>` page, then reads the whole menu from the page (`types: []`, `sortBy: name`, `removeProductsBelowOptionThresholds: false`, 100 per page, until the first empty page). With that flag off, rows equal `queryInfo.totalCount` and two traversals agree; with it on, the server drops 0 to 18 rows after paging and the rows never reach the total. If the read is not clean, the old category crawl still runs. `options.whole_menu_query=false` turns it off.
- `generic.py` now reports `Browser tunnel byte budget exceeded` (classified `RESPONSE_TOO_LARGE`) when the error page follows budget blocks, and keeps the "refused this browser session" wording for any other error page.
- Live, read-only provider fetches (nothing stored): Batavia 496/496 in 74 s, Mint Willowbrook 666/666 in 41 s (was COUNT_MISMATCH), Cookies Bolingbrook 1430/1430 in 170 s; each complete with two stable traversals. Not yet run through a sync or checked against registry branch addresses beyond the existing in-fetch check.

## Update: native provider (2026-10-18)

`backend/providers/dutchie.py` replaces the generic path for Dutchie endpoints. See `docs/PLATFORM_FIRST_PLAN.md`
section 7 for details. Two findings explain why generic Dutchie captures often failed with "does not reconcile":

- **Below-threshold products are counted but not returned.** `removeProductsBelowOptionThresholds: true` (the
  storefront's setting) drops products whose every option is below the online threshold after `totalCount` is
  computed. Noxx pages came back with 98 or 99 of 100, for 1042 of 1053. With `false`, every page is full, and the 11
  extra products carry their options in `optionsBelowThreshold`, so they are read as unavailable.
- **The default sort is not a stable paging order.** Under "Featured" order, Cloud9 East Peoria repeats 2 products and
  drops 2 across page boundaries, identically on every pass. The storefront's "Price low to high" view (`sortBy: price`,
  `isDefaultSort: false`) reconciles 1458/1458. `sortBy: "_id"` is not honored; it behaves like an unknown key.
