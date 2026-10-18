# Phase 3: Phili POST-policy experiment and network-first extraction

Run 2026-10-17 against `https://www.philidispensary.com/our-menu/` (store `6666d607171c9195c37541f8`) with `scripts/probe_browser_cohort.py`. Probes read the registry read-only and write only evidence; no snapshot was accepted. Raw results: `data/phili-policy*.json`, `data/phili-diag-*.json`, `data/phili-scroll*.json`; screenshots under `data/evidence/browser/*.png`.

## The hypothesis was only half right

The audit's hypothesis was that the exact-URL POST allowlist starves Jane's menu. The experiment shows **two independent defects**, and both must be fixed before any Jane product loads.

| Arm | POST policy | Browser identity | Age gate | Jane store API | Jane product API (`dmerch.iheartjane.com` POST) | Products seen |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | strict (current) | `HeadlessChrome` | never revealed (spinner) | none | none | 0 |
| 2 | `platform_reads` | `HeadlessChrome` | never revealed | none | none | 0 |
| 3 | `diagnostic_posts` (all but mutations) | `HeadlessChrome` | never revealed | none | none | 0 |
| 4 | strict | Chrome UA + `TerpScout/1.0` | clicked | `api.iheartjane.com` GETs 200 | **denied** (3 paths) | 0 |
| 5 | `platform_reads` | Chrome UA + `TerpScout/1.0` | clicked | 200 | **200** (`/v2/multi`, `/v2/facets`, `/v2/smart`) | 27 to 28 cards, 32 products from JSON |

1. **Site-side crawler detection on the `HeadlessChrome` token.** The retailer's Age Gate WordPress plugin (3.7.3) ships a crawler list that includes `HeadlessChrome`. With that token the gate never rendered (final screenshot: a loading spinner), `confirmAge` found zero "Yes" buttons, and the Jane app never called its API at all. With an ordinary Chrome UA plus an honest product token, the gate rendered, was confirmed under the saved age setting, and the menu loaded. This is the real cause of "HTTP 200, zero products" on Phili, and it is a site behavior, not a challenge or block.
2. **The POST allowlist is obsolete.** `network._READ_ONLY_SEARCH_POSTS` lists Jane's former Algolia search URLs (`search.iheartjane.com/...`). Jane's menu now loads inventory from `dmerch.iheartjane.com/v2/{multi,smart,facets}`. The page never calls the old URLs, so even with a passing UA arm 4 yields nothing. A body-validated policy that allows read-shaped JSON POSTs to platform hosts (`platform_reads`) fixes this without allowing telemetry, fingerprinting, analytics, or anti-spam POSTs, all of which stay denied.

Findings that rule out other suspects:

- The telemetry and fingerprinting POSTs (LaunchDarkly events, GA, FingerprintJS, CleanTalk, `tjs.iheartjane.com`) are not needed for the menu to load. `platform_reads` leaves them denied and the menu still loads.
- WebSockets (closed by default) were not required.
- No access challenge or 403 appeared in Chrome at any point; Jane's API answered 200 in the ordinary browser session.

## What is implemented

| Piece | Where |
| --- | --- |
| Request policy: `strict` (default), `platform_reads`, `diagnostic_posts` (experiments only, not selectable through the API) | `backend/request_policy.py`; wired in `browser_render.py` VALIDATE; worker sends POST bodies for inspection |
| Policy decisions and captured JSON summaries (request bodies redacted) persisted per render | browser evidence JSON: `request_decisions`, `network_json`, `post_policy` |
| Honest product token option (replaces `HeadlessChrome`; default off) | worker option `user_agent_token`; setting `user_agent_token` (validated product-token pattern) |
| Menu scroll / "load more" / "All products" entry driver (default off) | worker `scrollMenu`, setting `scroll_menu` |
| Diagnostics: age-gate decisions, final screenshot (`--screenshot`), stack on worker failure | worker; `probe_browser_cohort.py` flags `--post-policy --user-agent-token --scroll --screenshot --websockets` |
| Product-collection detector, field mapper (weight-price families, specials, availability, conditional prices), total finder, evidence loader | `backend/network_extract.py` |
| Generic fetch uses network collections when they cover at least as many products as the DOM | `providers/generic.py` `network_collections` |
| **Shared bug fix**: a page declaring `addressRegion: "Illinois"` was a branch conflict against registry state `IL`, rejecting correct branches | `site_discovery.same_state` |
| Stock stays unknown for per-unit prices and empty weight lists | `network_extract` |

Browser settings (`PATCH /api/v1/settings/browser`) gained `post_policy` (`strict` or `platform_reads`), `user_agent_token`, `scroll_menu`. **Defaults are unchanged**, so nothing above alters production behavior until you opt in. Phili needs both `post_policy=platform_reads` and a `user_agent_token`.

## Live end-to-end result (generic fetch, no snapshot written)

With both settings on, `providers.generic.fetch` on Phili: branch identity now matches; 32 products extracted from Jane's own JSON (two collections, source totals 759 and 760); `complete: false` with "Structured product total does not reconcile with traversed catalog". That is the correct outcome: the page's featured rows are 32 of 759.

## What is still open

- **Full Phili catalog.** The landing view is "Featured". Jane's grid (`/v2/smart`, `menu_inline_table`, `nb_hits: 759`, page size 60) never requested product pages in my runs: the "All products" tab click reported success but the view did not change, and scrolling did not trigger pagination. I did not find the interaction that loads the grid headlessly. Next step: record the same flow in an ordinary browser session and diff the request sequence, or have the Tier 3 agent learn it. A reliable source total (759, also summed by the facet `kind` counts) exists for reconciliation.
- **Intermittent `Frame was detached`** after clicking entry controls on this SPA (about 1 run in 3). The scroll step is now non-fatal, but the underlying race in later collection steps is not fixed.
- **Default-off decision.** Enabling `platform_reads` and an honest UA token is a policy choice for you. The token is transparent about being an automated agent and avoids the `HeadlessChrome` crawler string; it does not hide automation. A site that wants to exclude `TerpScout` still can.
- `_READ_ONLY_SEARCH_POSTS` still lists the dead Algolia URLs; harmless, remove when convenient.
- Whether other storefronts show the same Age Gate crawler behavior is unmeasured; the settings make it a one-line test per store.

## Update: defaults changed and the full Phili grid now extracts

**Defaults (your decision).** `post_policy=platform_reads`, `user_agent_token=TerpScout/1.0` and `scroll_menu=true` are now applied under saved settings (`network.BROWSER_DEFAULTS`, `BrowserInput`). An absent key takes the default; an explicit `user_agent_token: null` or `post_policy: strict` turns it off. Menu paging runs only during menu extraction (`await_menu`), never during website discovery. `diagnostic_posts` remains unselectable through the API. `platform_reads` now also refuses analytics and tracking paths (`/event`, `/track`, `/capture`, ...) on platform hosts; Phili loads without them.

**How Jane's full grid loads** (measured, not guessed):

1. After the age gate, the page shows "Featured". Activating the **All products** control routes the SPA to `/our-menu/menu/all`.
2. That view's `POST dmerch.iheartjane.com/v2/multi` returns all 759 product *ids* but only the first 60 hydrated with prices.
3. A **View more** button at the bottom triggers `POST /v2/smartpage` (a page of about 60 hydrated products per call). About 12 clicks cover the catalog.

**What changed to follow it:**

- The worker activates "All products" and "View more" from inside the page (open shadow roots included) instead of by pointer click. The pointer click timed out on a fixed navigation bar, which is why earlier runs saw nothing. A click that loads nothing new counts toward stopping, so a leftover button cannot loop.
- Menu paging runs after the menu-readiness wait (it used to run before the app had rendered).
- Age gates are polled for up to 6 s (they initialise after DOMContentLoaded and some reload the page on confirm). Frame-detach errors are retried. This removes the intermittent `Frame was detached` failure.
- Render deadline is 200 s when paging; the 1000-px-tall viewport keeps fixed bars on screen.
- The extractor ignores id-only placeholder entries when judging an array, accepts short last pages once the same path has proved to be a product collection, and takes the menu total from the largest collection that declares one (a featured row's own hit count no longer overrides it).

**Result (live, no change to the real database).** `providers.generic.fetch` on Phili with defaults: 759 products / 810 variants, `nb_hits` 759 reconciled, two stable passes, `complete: true`. Applied to a scratch store, `apply_snapshot` returned `status complete`, `grade A`, with 513 comparable offers (the rest have no package mass, for example edibles priced per unit). Runtime about 2 minutes for the two required passes.

**Still open:** Aces (same Jane platform) and the other generic/Jane/Dutchie stores are untested against this path. Dutchie traffic still returns HTTP 403 to raw HTTP and has not been run through the browser path.
