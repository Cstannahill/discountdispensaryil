# Platform-first extraction plan

Goal: stop adapting the pipeline one dispensary at a time. Fix things in units that move many stores at once
(platforms, chains, one directory) and keep per-store work for a short, named list of true one-offs.

Measured 2026-10-18 on the 190-store regional set (Minonk, IL, 100 mi), from `live_resolutions`, `live_attempts`,
`live_leads`, endpoint resolution evidence, and retained page/browser evidence. Platform counts mean "the store's own
evidence shows this platform"; they include some aggregator or wrong-branch pages, so treat them as approximate.

## 1. What the evidence says

Stage today: 37 accepted, 1 converged, 42 extraction failed, 110 discovery failed.

**Failures concentrate on a few platforms, not on 150 unique sites.**

| Platform (from evidence) | Stores | Accepted | Extraction failed | Discovery failed |
|---|---|---|---|---|
| Jane | 40 | 6 (+1 B) | 19 | 14 |
| Sweed | 29 | 20 | 4 | 5 |
| Dutchie | 24 | 2 | 9 | 13 |
| Sunnyside (Cresco, own site) | 14 | 0 | 4 | 10 |
| Joint (provider added 2026-10-18) | 10 | 3 | 2 | 5 |
| RISE (GTI, own site) | 9 | 0 (+1 B) | 4 | 4 |
| Treez | 7 | 2 | 5 | 0 |
| Curaleaf (own site) | 7 | 0 | 1 | 6 |
| Dispense, Flowhub, POSaBIT, Blaze | 13 | 12 | 0 | 1 |
| Zen Leaf (Verano, own site) | 3 | 0 | 3 | 0 |

Where a native provider reads the platform's own paged API with an exact total (Sweed, Dispense, Joint, Blaze),
stores reach grade A without any per-store work. Where we rely on DOM or partial network capture (Jane, Dutchie,
chain sites), they mostly fail.

**Stores belong to chains.** The top 20 brands hold 99 of the 190 stores; only 33 stores are single-location brands.
The failing set is led by NuEra (8), Curaleaf (7), Sunnyside (7), Verilife (6), RISE (5), Dutchess (5), Ascend (5),
and Starbuds (5).

**Discovery is the larger loss, and web search is its weak link.** 63 discovery failures have no platform signature at
all: no website was ever found. The registry carries only name, street address, coordinates, and a medical flag. The
leads table is dominated by aggregator and out-of-state pages (mintdeals 46, localdispensaryguide 26,
cannabispromotions 21, starbudscolorado 14, ...). The top resolution outcomes are "candidate website found; branch
not corroborated" (164) and "no retailer locator connector configured for this brand" (144).

**A geographic directory finds what search does not.** Weedmaps' public discovery API, tiled over the region, returned
133 Illinois listings. 58 registry stores match strictly (within 0.5 mi with the same street number), and 40 of the 63
no-website stores have a listing within 2 mi. A listing's detail carries the retailer's own `website`, the state
`license_number`, and `license_type`. Example: "Pekin Local Dispensary & Supply" failed web search but is listed at
359 Court St. with `website` pekindispensary.com.

## 2. Design: five shared layers instead of per-store fixes

### A. Directory-anchored discovery (replaces web search as the first resort)

- Query one geographic directory (Weedmaps discovery listings; Leafly later as a second source) around each registry
  store, cached per region.
- Match by coordinates (<0.25 mi) **and** street number, with name tokens as a tie-breaker. The listing gives
  `website`, `license_number`, and `license_type`.
- The result is a **lead**, never a menu (the invariant stands). The retailer page must still prove the branch
  through the existing identity checks, then platform detection takes over (layer C).
- Web search stays as the fallback for stores the directory lacks.
- **Trust:** two independent sources (registry address and directory address) must agree before the site is even
  fetched. Near-misses such as "Ascend Moca" vs "Green Rose" at 0.12 mi are rejected by the street-number rule.

### B. Chain registry (one entry per multi-location brand, not per store)

Many chain sites list every branch with its address in their own config or API. For example, the Terrabis page embeds
`jointEcommerce.stores`, and Jane and Dutchie chain sites expose a store picker backed by a store list. A chain entry
says three things:
- the chain's host and platform;
- where the chain's own branch list lives;
- how a branch maps to a tenant id or menu URL.

One fetch then matches every registry branch of that chain by address and saves all of their endpoints at once. That
retires the "no retailer locator connector configured" failures (144) per chain rather than per store.

Targets by evidence: Sunnyside/Cresco, RISE/GTI, Curaleaf, Zen Leaf/Verano, Verilife, Ascend, NuEra (Jane), Ivy Hall,
Starbuds, Dutchess, Terrabis/Cookies (Joint, partly done).

### C. Platform providers (table-driven; the main lever)

Each platform module supplies:
- a page/network **signature**;
- **tenant extraction** from the retailer page;
- a **platform-declared branch address** for identity proof;
- a **native paged fetch** that reconciles to the platform's exact total over two traversals.

This is the shape Dispense and Joint already have. Gaps, in order of stores unblocked:

1. **Jane native provider** (about 33 failing stores). Jane menus are served from its search index (Algolia
   `menu-products-production`, already on the POST allowlist) with an exact hit count. Read it by store id and menu
   type and page it. `api.iheartjane.com/v1/stores/{id}` returns the store's address for branch proof. This replaces
   DOM/scroll capture for every Jane store.
2. **Dutchie native provider** (about 22 failing stores). Promote the browser's paged `FilteredProducts` replay to a
   direct reader keyed by dispensary id, using the persisted-query hash the page itself uses. Totals come from
   `queryInfo`, and the platform-declared address check already exists (docs/DUTCHIE_DIAGNOSIS.md).
3. **Chain-own platforms** (Sunnyside, RISE, Curaleaf, Zen Leaf): one module each, covering about 33 stores.

Lessons from Joint that apply to every platform:
- Use the page's own filters (business, menu type, not deleted).
- Add a deterministic sort tiebreaker. `itemsSold` alone returned only 455 distinct products out of 483.
- Send the origin and referer the storefront sends.

### D. Recipe learner for unknown platforms (generic, no per-store code)

For a page whose platform is unknown, the browser already captures the JSON traffic. Generalize the existing
`replayPagination` / `replayOffsets` into a **recipe** with these parts:
- endpoint, method, and body template;
- paging key (`from`/`size`, `page`, `offset`/`limit`, cursor, GraphQL variables);
- the path to the total and the path to the product array.

A recipe is accepted only when a direct replay reconciles to its total twice. It is stored against the platform
signature (host family plus API path shape), not against a store, so every other store with the same signature reuses
it. Joint would have been found this way: an ES `_search` POST whose `from` pages to `hits.total`.

### E. LLM agent (last resort, unchanged in role)

As in ROBUST_EXTRACTION_PLAN.md, but its output is a **recipe for layer D** or a chain entry for layer B. It is never
an imported catalog, and nothing it proposes is used until the deterministic reconciliation passes.

## 3. Trust without per-store review

- **The grade gate stays as it is.** A requires an exact total plus two agreeing traversals. B and C are never shown
  as complete.
- **Independent count cross-check.** Compare the directory's `menu_items_count` with our item count. A large gap flags
  a store for inspection, for example Ivy Hall Montgomery at 1,158 accepted vs 341 fresh. The gap is a flag only,
  never proof of completeness.
- **One canary per platform and per chain.** Run a nightly sample-mode check (`scripts/sample_stores.py`) on one store
  per platform or chain. If the canary breaks, the platform is broken for all of its stores, which is one alert
  instead of N silent partials.
- **One recorded fixture per platform** (as `tests/fixtures/provider_*`), plus a regression test for each shared
  defect.
- **The census becomes a standing report:** per platform and chain, store count, grade distribution, and top failure
  codes. The work queue is ordered by stores unblocked per fix.

## 4. Sequencing and expected effect

| Step | Work | Stores it can move (upper bound) |
|---|---|---|
| 1 | Census as code: persist each store's platform/chain signature; add the report to `/pipeline/stages` | 0, but it orders everything else |
| 2 | Jane native provider | about 33 |
| 3 | Directory-anchored discovery (Weedmaps) | about 40 of the 63 no-website stores get a lead |
| 4 | Dutchie native provider | about 22 |
| 5 | Chain registry for the top failing chains | about 40, overlapping steps 2 and 4 |
| 6 | Recipe learner for unknown platforms | the remainder with captured APIs |

The steps overlap: a NuEra store needs both its chain entry and the Jane provider. The realistic target after steps
1–5 is a large majority of the region at A or B, with failures named by code rather than unknown.

## 5. What stays per-store

- Single-location brands on platforms nobody else in the region uses: at most about 15 today. These go to the recipe
  learner or the agent first; hand work happens only if both fail.
- Honest blocks: age/terms gates we must not bypass, 403s, and challenges. These are reported, never worked around.
- Registry disputes, where the registry street address differs from both the retailer and the directory (for example,
  Beyond Hello Bloomington Keaton Place). These need a human decision about the registry.

## 6. Open decisions

- **Weedmaps menus as a source.** Listings carry `menu_id` and item counts, so the directory could also act as a
  menu source. That contradicts "directories are leads, not menus" and adds sync lag versus the retailer's POS. The
  recommendation is to use it only for discovery and the count cross-check.
- **Directory use limits.** Cache per region, throttle, and record evidence the same way as other public fetches.

## 7. Status (2026-10-18)

**Step 1, census as code: done.**
- `backend/platforms.py` holds the signature table and `brand_key`. Migration `004_store_platforms.sql` adds `live_store_platforms`.
- The resolver tags every page's results with the platforms seen on it, and the service records them.
- `stage_report` (and `/api/v1/pipeline/stages`) now returns `platforms` and `brand` per store, plus `by_platform` and `by_brand`.
- `scripts/platform_census.py --write` backfilled the census from retained evidence.

**Step 2, Jane native provider: done** (`backend/providers/jane.py`).
- **How it reads:** the storefront's own search (`dmerch.iheartjane.com`, with the public SDK key read from the store page), sliced by the `kind` facet. A kind above the 1000-hit window is split by brand. Each slice must return exactly its facet count, ids beyond the first page are hydrated 60 at a time, and two traversals must agree.
- **Branch and license:** these come from each record's `_geoloc` and `store_types`. Jane's store-detail API refuses our honestly identified client with 403; that block is respected, not worked around.
- **Coordinates:** registry coordinates are 1–3 mi off for some stores (NuEra Pekin: the same street address in both sources, 1.79 mi apart). So a location within 0.35 mi proves the branch by itself. Within 5 mi, it proves the branch only together with the retailer-page identity from resolution. The proof method and distance are recorded in `branch_proof`.
- **Result:**
  - All 13 stores with Jane endpoints grade A.
  - Eight of them had no accepted menu before: Beyond Hello Bloomington, NuEra Pekin and Champaign, High Haven Darien and Elgin, Consume Oakbrook Terrace, Bloom Hometown, and Earthmed Rosemont.
  - Six sibling endpoints (Consume Marion/Antioch, 37–300 mi away) were rejected as `BRANCH_MISMATCH`.
  - Regional accepted stores went from 37 to 45.

Remaining Jane failures are chain sites (NuEra's own shop, Verilife, RISE, Cannabist, Starbuds) whose branch pages are not yet tied to a Jane store id. That is step 5 (chain registry).

Re-resolving the 11 Jane-signature extraction failures detected Jane store ids on three more retailer sites: NuEra
Aurora (1,167), EarthMed (1,351), and Hatch (1,585) now grade A, and Verilife Rosemont is B. The region stands at 48
accepted and 2 converged. The rest (RISE, NuEra Chicago Southland's filtered shop pages, Cannabist) need chain entries
(step 5).
