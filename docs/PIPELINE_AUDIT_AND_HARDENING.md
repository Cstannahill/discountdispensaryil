# Discovery and ingestion pipeline audit

2026-10-17. Scope: the entire application pipeline and saved region, not one retailer. This supersedes the implementation order in MENU_RECOVERY_PLAN.md: review and harden orchestration/contracts before adding individual extractors.

## Measured baseline

`data/regional-failure-audit.json` captures the selected Minonk 61760 / 100-mile region: 190 registry locations, 22 with an accepted menu, 154 without an endpoint and 14 with unsuccessful extraction. This is a location denominator, not an endpoint count. The audit's 75 generic partial endpoints include pagination aliases and are not 75 distinct dispensaries. Source observations currently contain 287 Illinois rows, all present; one shared-address pair exists (Alton Dispensary / Terrace Alton), whose physical/license relationship has not been established.

Latest resolution messages for the unimported baseline include 110 legacy "no retailer connector" results, 11 age/terms results, 10 missing locator links, 10 HTTP 403, 9 missing address matches and 5 candidate identity gaps. These are saved historical results while a newer regional job is running; they are not a claim that the current engine has just reproduced each failure. Job `931c59f95ee645a8a40585e164ef0a6d` had 100 result records when examined. Result records are not distinct completed stores.

## Pre-hardening execution observed during this audit

1. Enqueue one regional job; its region may be implicit until execution.
2. Optionally refresh the Illinois registry and choose rows inside a straight-line radius.
3. For every store, call the resolver again. It starts from supplied URLs or known brand locators, otherwise public search.
4. Crawl up to 24 pages, infer branch identity, collect embedded platforms and generic candidates.
5. Save each resolved endpoint; call its extractor serially.
6. Normalize products, reconcile completeness, atomically accept a full snapshot or retain the previous catalog and partial evidence.
7. Aggregate endpoint counts and expose directory/deal views through cached client queries.

## Findings: should it work this way?

| Area | Current decision and evidence | Required behavior |
| --- | --- | --- |
| Store universe | `discovery.py:parse_registry` only imports the Illinois map. `storage.py:import_registry` derives entity IDs from source keys containing name/address. | Separate source observations from durable physical-store identity. Support multiple candidate sources, aliases and explicit operating-status uncertainty. Calculate jurisdiction scope before claiming regional coverage. Preserve history when a listing disappears. |
| Known menus | `service.py:run` always resolves first and only refreshes endpoints returned by that attempt. | Refresh an existing accepted endpoint independently of rediscovery. A locator/search failure must not stop its successful menu refresh. Rediscovery supplements or replaces sources only with evidence. |
| Queue scope | `submit` enqueues an optional region ID; `run` resolves an omitted ID later. One executor and run lock cover an entire region. | Pin the region and selected stores at enqueue. Track per-store work and checkpoint it. Bound stage time and support cooperative interruption; targeted work must not be trapped behind hours of retries. |
| Website search | `site_discovery.py:search_websites` parses a few engine HTML formats and stops after direct-looking results. The cache does not distinguish current algorithm attempts from old persisted resolutions. | Record provider/query/version/attempt time, rank official candidates using explicit evidence and retain alternate leads. Search outages, no results, rejected candidates and unattempted work are separate states. |
| Official-site authority | Previously an age-gated official site was displaced by a directory. Current directory handling corrects that specific class, but there is no durable selected-source policy. | Model official retailer -> branch -> delegated menu relationships. Directories can supply leads; menu authority comes from retailer delegation or corroborated branch evidence. Keep alternatives separately and do not add competing provider catalogs together as one inventory. |
| Branch identity | `inspect_page` allows any overlapping brand token plus city; addresses can come from broad visible text. Resolver propagates a verified flag to menu links. | Record confidence and scope explicitly. Shared navigation/global branch lists do not verify the selected store. Missing evidence is uncertainty; a contradictory selected provider branch is rejection. Store/tenant identity is revalidated during extraction. |
| Menu identity | URL identity allowed anchors and pagination to become separate endpoints; runner loops over every returned target. | Canonicalize traversal state, preserve branch/license/filter context and deduplicate before dispatch. Persist aliases and historical attempts without counting them as separate active menus. Ordinary filtered pages are not full-menu proofs. |
| Capabilities | `fetch_menu` sends Jane/Dutchie/Cresco to generic fallback despite lacking native complete-traversal implementations. | Make detected platform and supported extraction capability separate fields. Expose inspection-only/conditional/native-full support. A platform name alone is not evidence of a working importer. |
| Acquisition | Static locator discovery only invokes rendering for a narrow age-gate branch. Browser rendering may succeed while the next static request loses the selected context. | A shared acquisition layer carries authorized site context and chooses static, hydrated or delegated data based on observed needs. Record the mechanism, selected store/license and all transitions. |
| Product identity | Generic extraction ignored `Offer.url`, yielding zero observations despite declared stable product links. It also treated missing stock as false. | Accept source-declared stable IDs/URLs, preserve unknown stock/mass and quarantine ambiguous records without inventing identities. Keep valid partial observations. |
| Completeness | Native extractors compare two traversals, but long traversals can fail when live inventory changes. Some fingerprints include raw metadata. Generic advertised totals are deliberately strict. | Separate acquisition completeness from normalization quality. Compare stable inventory fields; distinguish changing inventory from ignored pagination and missing records. Retry bounded unstable traversals while preserving partial evidence. Never authorize removals from a partial crawl. |
| Persistence | Atomic snapshots, retained accepted data, independent zero/drop confirmation and evidence capture are sound. Source removal and endpoint replacement policy are incomplete. | Preserve these protections. Add explicit source/alias lifecycle and supersession policy; never silently remove a physical store because a provider or search failed. |
| Coverage/UI | `coverage` counts recency independently of latest attempt, so "fresh and complete" can overlap failed counts. Historic failures lack engine version. Local HTML and live app can be confused; user confirmed this caused the Snap report. | Report physical-store discovery, source resolution, supported extraction, accepted snapshot freshness and latest attempt separately. Clearly identify historic/unattempted statuses and client data revision. Keep all physical stores visible with explicit filters and exclusions. |
| Testing | Many provider/page fixtures and storage protections pass, but a successful component test does not prove the entire decision chain. | Add mixed-cohort end-to-end tests spanning discovery failure + retained endpoint, duplicate aliases, competing sources, branch conflicts, unsupported capability, restart, queued-region changes and UI denominator consistency. Replay captured real failures through the same orchestration used in production. |

## Hardened contract

Every store produces one work report with: immutable region/store scope; pipeline version; candidate sources; selected authoritative source or reason none was selected; branch/license evidence; canonical menu targets; extraction capability; stage timings; attempt outcome; latest accepted snapshot; and the precise next action/retry class. A failed stage does not erase an earlier durable stage.

State boundaries:

`candidate store -> retailer candidates -> verified/delegated branch source -> canonical menu target -> acquired source observations -> normalized partial catalog -> reconciled accepted snapshot -> eligible offers`

These boundaries must remain distinct in storage and reporting. "No products" cannot stand in for no website, unimplemented provider, request failure, failed normalization or a verified empty menu.

## Implementation sequence and acceptance

1. **Orchestration invariants:** pin queued scope; deduplicate canonical targets; refresh retained accepted endpoints despite rediscovery failure; capture a versioned per-store summary; cooperatively interrupt without replacing accepted snapshots. Regression matrix first.
2. **Source selection:** persist candidate provenance and source authority, branch confidence, alternative sources and rejection reasons. Add generic rendered-locator discovery and measure all previously unattempted stores with the current engine.
3. **Extraction contracts:** publish capability reporting; improve shared structured/Flight acquisition and add platform implementations based on measured provider cohorts. Validate source totals and branch context using the same run path.
4. **Coverage/read models:** use non-overlapping location-level stage counts, separate latest attempt from accepted freshness, and show algorithm-version/retry state. Cache invalidation follows a durable server revision.
5. **Regional acceptance:** replay every candidate in the selected region, compare before/after at store and provider levels, inspect all residual failure classes, and persist a machine-readable report. No "robust" or "all covered" claim based only on fixture passes or one recovered retailer.

This audit does not establish a universal foolproof scraper. Official Treez POS APIs require partner credentials; documented store/customer-type deep links and public SSR payloads are alternative observed storefront paths. Source research: https://code.treez.io/docs/product-apis , https://support.treez.io/en/articles/11101609-direct-store-linking-for-multi-store-operators-deep-links , https://support.treez.io/en/articles/11583861-deep-direct-links-for-medical-or-adult-use-menus .

## Implemented foundation and remaining work

The production runner now pins queued region scope, refreshes accepted endpoints before rediscovery, canonicalizes/deduplicates menu targets, checkpoints versioned physical-store reports, and cooperatively interrupts before publication. Duplicate active requests coalesce. Regional and targeted jobs have separate bounded workers; same-store work is serialized and HTTP clients/cookie jars are isolated per job. Unexpected per-store failures are checkpointed without aborting subsequent stores. These changes do not implement every source-selection requirement above.

Coverage now separates physical-store counts, current-engine attempts, retained accepted menus and latest extraction outcomes. Pipeline versions fingerprint the relevant source files, so an interrupted older engine's result cannot be presented as a current-engine attempt. The UI invalidates cached data when the server's durable/job revision changes. Historical accepted menus remain visible after failed refreshes.

Browser acquisition now supports Chrome's native HTTP/TLS through a bounded public-destination-only tunnel as well as the captured HTTP transport. Captures retain actual HTTP statuses, resource evidence, blocked-request reasons and shopping-context transitions. Authorized age handling and choosing a menu type are separate steps. A recognized medical/recreational dialog defaults to recreational; an explicit medicinal endpoint selects medical. Choice and continuation controls are scoped to the dialog, including embedded frames. This does not claim universal support for every custom gate.

Noxx evidence must be kept distinct: the normal Chrome tab reached the public menu, and on reinspection showed Recreational selected with products visible. The user observed an earlier medical/recreational dialog; the old worker had no handler for that choice. Separately, the fresh headless native acquisition probe returned an access-challenge page. Neither observation proves that the other session had the same blocker. Native transport alone has not established a successful complete Noxx import. Do not label an ordinary shopping-context selector as a CAPTCHA/access challenge.

Still open: durable retailer/branch/delegated-source authority and alternate-candidate lifecycle; source-independent physical-store identity and jurisdiction coverage; stronger selected-branch context; measured platform-specific full traversals for unsupported providers; generic rendered-locator coverage; and final regional acceptance with residual failure classes. A successful browser fixture or one retailer menu does not close these items.
