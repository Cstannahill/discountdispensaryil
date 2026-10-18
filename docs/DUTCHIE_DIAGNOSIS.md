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
