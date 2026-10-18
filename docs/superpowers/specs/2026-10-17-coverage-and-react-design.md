# TerpScout: verified coverage, complete menus, and React migration

Date: October 17, 2026  
Status: Written specification for review. The architecture direction is approved;
implementation has not started.

## 1. Purpose and agreed constraints

TerpScout must help the user compare actual dispensary offers in a selected
area. A polished ranking is insufficient if stores or most of their inventory
are missing. Discovery, complete initial imports, subsequent changes, and visible
coverage evidence are therefore core product behavior.

The user approved React + TypeScript + Vite with the existing Python FastAPI
backend, preserving the current appearance and improving maintainability and
component accessibility. Keep the dark colors, typography, artwork, glass cards,
category accents, responsive deals columns, navigation, directory/radar, charts,
menu inspector, calculator, catalog, audit history, exports, and watchlist.

The initial acceptance region is **ZIP 61358 with a 50-mile straight-line
radius**. The five user-reported omissions are Cloud 9 East Peoria, Stash Peru,
Snap Canna Pontiac, Beyond/Hello Bloomington, and Beyond/Hello Peoria. Validate
all other regional candidates too; these five are regression cases, not a
production store list.

This specification defines one integrated release with three verification
milestones: discovery and coverage; menu ingestion and persistence; frontend
migration and end-to-end verification. Passing an earlier milestone does not
establish that the later milestones or the product's coverage goal are complete.

## 2. Verified starting point

The [coverage audit](../../COVERAGE_AUDIT.md) and its saved evidence establish:

- The original frontend embeds 18 store/menu entries and 35 sample products.
- The SQLite database has no dispensaries, products, or sync audit records.
- Frontend polling manufactures changes; backend polling only reports success.
- No discovery service, provider adapters, catalog API, or live frontend data
  integration exists.
- The unused diff helper fails to update changed weights and has no protection
  against treating a failed or partial empty scrape as a complete empty menu.
- The saved Illinois map export has 287 rows, with 23 within 50 miles of the
  third-party ZIP 61358 centroid. All five user examples have registry candidates.
  These numbers describe the captured source, not permanent expected live counts.
- The current ZIP interpolation places 61358 about 8.6 miles from that lookup
  centroid. The replacement must perform a real lookup or use explicit GPS.

The evidence is dated October 17, 2026. Retailer operating status, current
provider mappings, the exact Bloomington branch address, and complete product
counts still require live corroboration. Never promote prototype license
numbers, addresses, menu links, prices, or provider labels into verified records.

## 3. Architecture and responsibilities

```text
Official registries + retailer locators + provider directories + suggestions
                         |
                  source observations
                         |
          identity, license and geographic reconciliation
                         |
         physical stores -> license-specific menu endpoints
                         |
             provider adapters / persistent jobs
                         |
         raw evidence -> staged snapshot -> completeness validation
                         |
            atomic catalog + diffs + successful observation
                         |
               FastAPI query and coverage contracts
                         |
               React / TypeScript / Vite dashboard
```

FastAPI owns persistence, discovery, provider access, normalization, ranking,
coverage, and job scheduling. React displays API results and controls; it does
not independently scrape retailers or simulate catalog changes.

Retain SQLite for this local application. Use versioned migrations, foreign
keys, explicit transactions, and WAL mode. Preserve the existing database with
a backup before its first migration, even though the audited copy is empty.
The supported deployment is one application worker with durable job records;
multiple workers must be refused until cross-process scheduler ownership is
implemented and tested. A frontend development server is optional; a production
build is served from FastAPI on the existing port 8000.

Suggested backend boundaries are storage/migrations, source fetching, discovery,
identity reconciliation, geocoding, provider adapters, normalization, snapshot
validation/reconciliation, jobs, and API contracts. Keep these independent enough
to test parsing and reconciliation without network access or a running browser.

## 4. Discovery, identity, and geographic scope

### Source acquisition

Import the unfiltered public Illinois dispensary map as the initial discovery
source. Persist the original response and source metadata before parsing. The
observed CSV repeats a column name; validate duplicate columns for agreement and
reject conflicting values instead of silently overwriting them. Validate row
widths, coordinates, required identity fields, and unexpected schema changes.

Attempt a source refresh daily. Retrieval age and the source's stated publication
date are separate fields. A source last retrieved successfully more than 72
hours ago is stale. A failed refresh keeps the last accepted source with that
age and a visible failure; it never replaces the directory with an empty list.
The bundled audit export is evidence for replay tests, not an automatic live
fallback presented as a new scan.

Corroborate and supplement registry candidates through retailer location pages
and public provider directories. Persist each observation, its source, and
matching decision. Each scheduled discovery cycle checks the registry and
already-resolved retailer locators; previously unknown brands or inaccessible
locators remain a declared discovery limitation. A source change can introduce
new candidates without requiring a product release or a hard-coded store entry.

### Identity and licenses

Represent a physical location separately from its licenses and menus. A
recreational and medical menu at one address must not become two physical stores
in the directory total. Distinct branches of the same brand must remain separate.

Prefer a verified regulator credential for license identity and a verified
provider store identifier plus address for endpoint identity. Name/city similarity
alone creates a reconciliation candidate, not an automatic merge. Conflicting
addresses, coordinates, medical-service flags, relocations, and renamed stores
remain visible with their observations until corroborated. Registry membership
does not alone prove that a store is operating or has a usable online menu.

Every imported row receives a persisted outcome: resolved, unresolved identity,
unresolved location, source conflict, verified closed, conditional/not operating,
or otherwise excluded with a reason. Never silently discard an inconvenient row.
User suggestions enter this same workflow; they do not fabricate license data,
phone numbers, coordinates, or products.

### Location and distance

Use a real cached ZIP/city geocoder and browser GPS with explicit permission.
Persist provider, response evidence, coordinates, precision, and observation time.
The previously observed Zippopotam.us response can establish a ZIP place
centroid; label it as approximate. Unknown or ambiguous input returns a clear
resolution result and leaves the prior selected origin intact. Validate explicit
coordinates. Never interpolate ZIPs or silently substitute Macomb.

Use unrounded great-circle distance to test the selected 1/5/25/50/100-mile
radius; round only the displayed distance. Persist a selected region with its
origin evidence and radius so backend scheduling continues when the browser is
closed. Default to the user's ZIP 61358 and 50 miles after resolving it.

Illinois is the first supported registry jurisdiction. Report when a requested
circle intersects unsupported jurisdictions. An Illinois-only result must never
claim coverage of an entire cross-border circle. Unlocated source candidates are
reported separately because their absence from a radius denominator is uncertain.

## 5. Coverage contract and user-facing claims

Coverage is calculated for the requested region, selected license context, and
requested product categories. Return separate counts for:

- Registry candidates, corroborated operating physical locations, and unresolved
  identities, coordinates, or license contexts.
- Resolved menu endpoints and supported/unsupported providers.
- Endpoints with complete fresh snapshots, complete stale snapshots, partial or
  suspicious attempts, fetch/parse failures, and no attempted import.
- Source products, sellable variants, category-mapped variants, comparable $/g
  offers, and excluded/quarantined records with reasons.

Use physical locations for directory totals and license-specific endpoints for
menu totals. Publish both denominators and explain them; never divide a menu
count by a store count. Preserve per-endpoint last attempt, last success, latest
attempt result, last good snapshot, counts, source links, and adapter version.

A complete menu snapshot becomes stale 12 hours after its successful observation.
Default deal rankings use fresh, complete snapshots and currently available,
comparable offers. An explicit stale-data option can include older offers with
their age visible; it cannot imply current stock or participate silently in a
fresh-ranking KPI. A newer failed attempt remains visible even when an earlier
snapshot is still within its freshness window.

Describe results as the lowest observed comparable prices among the covered
menus. Display uncovered and unresolved stores next to those rankings. No state
in this release asserts that every possible operating dispensary is known.
An endpoint may be complete while geographic discovery remains incomplete.

## 6. Provider adapters and complete initial imports

### Resolve the actual source

Inspect each retailer's real location and menu links to establish provider,
provider location ID, license context, and endpoint. The observed Macomb page
loads Sweed assets; this is a lead to validate, not a provider contract for every
store. Prioritize actual providers found among the user's five examples and the
rest of the regional candidates. Reuse a validated provider adapter across stores.

No universal HTML scraper may call a landing page or a visible carousel a full
menu. Public storefront data may be read using HTTP or a browser where necessary.
Authentication requirements, access challenges, absent public contracts, and
unsupported providers are explicit outcomes. Do not bypass access controls or
manufacture data to make an adapter appear complete.

### Adapter output

An adapter returns source observations and a manifest containing endpoint
identity, adapter version, observation times, page/cursor accounting, advertised
totals if available, fetched unique product/variant counts, category accounting,
stock semantics, raw response references, normalization errors, and completion
evidence. Completeness is an explicit result with reasons, never inferred from
HTTP 200 or the presence of a few products.

Enumerate every required page, category, product variant, package size, and stock
state exposed by the chosen source. Detect repeated cursors, duplicate pages,
missing pages, inconsistent totals, unstable page boundaries, and changed store
or license context. Deduplicate by provider identities, not product names.

Use bounded per-provider concurrency, timeouts, retries with backoff, and
Retry-After handling. Limits must be configurable and included in run evidence.
Reaching a page, response-size, retry, or run-time limit yields an incomplete
attempt. Never truncate to a small product count and report success.

### Preserve and normalize the whole source catalog

Retain products outside flower, concentrate, and vapes, plus records with
unknown categories, weights, or prices. Keep their raw category and reason they
are excluded from the three comparable deal columns. The full menu inspector
and catalog can show these other items separately.

An offer identity comprises provider, provider store, license context, product,
and variant IDs. Preserve provider SKUs separately. Normalize currency and
package mass using Decimal arithmetic; keep original units and source values.
Store monetary amounts as integer cents when they are exact cent amounts and
otherwise retain the provider's precision. Sort $/g using unrounded Decimal
values and display rounded values. Zero/negative or ambiguous mass is ineligible
for $/g ranking, with the reason preserved. THC dose in mg is not package mass.

Keep regular price, unconditional sale price, conditional promotions, eligibility,
discount windows, and stock state separate. A "from" price, loyalty price,
medical discount, or multi-buy offer cannot become an unconditional single-item
best deal without evidence that its conditions apply. The three category columns
rank by comparable price, not by whether an item has a sale badge.

### Validate, then commit

Stage each attempt separately. Validation checks endpoint context, traversal,
identity uniqueness, counts, error accounting, and normalization. Preserve raw
items that cannot be ranked; quarantine structural/identity failures. Invalid
rows must never disappear from count reconciliation.

An initial accepted full snapshot seeds all its offers, not only changed or
promoted items. In one transaction, commit the catalog, snapshot reference,
diffs, last-seen values, counts, and successful-observation timestamp. Later
accepted full snapshots update every changed field, including name, brand,
category, weight, promotion conditions, stock, and price. An unchanged product
still receives a new last-seen observation. Reappearing offers are recorded as
added with a reactivation marker. Removals are scoped to that exact endpoint
and license context.

An empty snapshot is eligible for removal only after an authoritative source
reports zero and a second independent fetch at least one minute later confirms
that empty result and the same endpoint context. A drop exceeding 30% of active
variants also requires independent revalidation. Record that confirmation with
the attempt; if source counts are unavailable or results disagree, retain a
suspicious/incomplete result and the last good menu. An adapter's ordinary empty
list, page failure, parse error, access page, or timeout can never authorize
removals. Rollback leaves the previous catalog and last-success timestamp intact.

## 7. Persistence, evidence, and jobs

Versioned storage covers sources/fetches, source observations, physical stores,
licenses, aliases/matching decisions, geocodes/regions, menu endpoints, jobs and
attempts, staged/accepted snapshots, offers, product observations, and diffs.
Relationships preserve source provenance and endpoint/license isolation.

Keep content-addressed compressed response bodies under `data/evidence/` with
SHA-256 references in SQLite. Write evidence atomically before committing a
database reference. Failed attempts retain diagnostic evidence too. Do not store
credentials or session secrets in raw diagnostic metadata, URLs, or frontend
responses. No automatic deletion of capture history is part of this release.

Manual and scheduled syncs enqueue the same persisted job path. Job states are
queued, running, succeeded, partial, failed, and interrupted. A terminal job
stores per-source/per-endpoint results; success requires every targeted endpoint
to meet its stated completion conditions. Unsupported endpoints produce an
explicit incomplete result, not a successful empty menu.

Serialize work per endpoint and record ownership/lease information. Retries are
idempotent; a restarted process marks abandoned work interrupted and resumes
through a new attempt without duplicate diffs. Do not hold a database write
transaction open while fetching remote pages.

Persist the global cadence: 2/day at 08:00 and 20:00; 3/day at 07:00, 15:00,
and 23:00; 4/day at 00:00, 06:00, 12:00, and 18:00, America/Chicago. Default to
4/day. Store event timestamps in UTC. The backend publishes the actual timezone,
slots, next execution, and run state; the browser does not maintain a separate
schedule. Slot identity and endpoint serialization prevent duplicate application
after retries or daylight-saving clock changes.

Outbound fetches use verified public HTTP(S) endpoints with bounded redirects.
Reject private, loopback, link-local, credential-bearing, and unsupported-scheme
targets, including after DNS resolution and on redirects. A submitted suggestion
does not automatically grant an arbitrary URL access to the local network.
Keep administration local by default and same-origin; exposing it beyond the
local machine requires a separate authenticated deployment design.

## 8. API surface

All responses use typed contracts, UTC timestamps, stable IDs, explicit states,
and structured error codes. Monetary/weight Decimal values are serialized as
strings rather than silently losing precision in JavaScript.

| Endpoint | Contract |
| --- | --- |
| `GET /api/v1/health` | Infrastructure readiness and scheduler state; does not claim successful ingestion. |
| `POST /api/v1/locations/resolve` | Resolve a ZIP/city or validate explicit coordinates; return precision and ambiguity/error information. |
| `POST /api/v1/regions` | Persist a resolved origin, allowed radius, and active-region selection. |
| `GET /api/v1/coverage?region_id=...` | Dated source/territory coverage, physical-store and menu counts, unresolved candidates, and per-endpoint results. |
| `GET /api/v1/dispensaries?region_id=...` | Paged physical stores with license/menu states, distance, provenance, and unresolved/conflict indicators. |
| `GET /api/v1/menus/{id}/products` | Paged products/variants, source categories, count reconciliation, freshness and snapshot identity. |
| `GET /api/v1/deals?region_id=...` | License/category/search/stock/freshness filters, stable $/g ordering, pagination, exclusions, and coverage summary. |
| `POST /api/v1/sync/runs` | Validate scope, enqueue work, and return HTTP 202 with a persisted run ID and status URL. |
| `GET /api/v1/sync/runs` and `GET /api/v1/sync/runs/{id}` | Paged history, state, progress units and per-endpoint outcomes; no fabricated percentage. |
| `GET/PATCH /api/v1/settings/schedule` | Persist and return the actual 2/3/4-per-day backend cadence. |
| `GET /api/v1/diffs` | Paged observations scoped by region/endpoint/license/action and linked to accepted snapshots. |
| `POST /api/v1/dispensary-suggestions` | Record a name/location/menu suggestion and its reconciliation status; never seed sample offers. |
| `GET /api/v1/catalog/export` | Export the requested catalog and provenance/freshness fields with safe CSV encoding. |

Retain the existing `/api/v1/sync/trigger` as a compatibility wrapper that
enqueues a real run and returns 202; it must not keep returning simulated
completion. Validate query/body values server-side, bound page sizes, and use
stable tie-breaker IDs so pagination does not silently skip equal-priced offers.
Catalog/deal pagination is pinned to a returned data-version token; requesting
an invalidated version returns an explicit refresh-required response.

## 9. React migration and visible behavior

Create `frontend/` with React, TypeScript, Vite, and build-time Tailwind. Preserve
the existing utility styles initially rather than combining the migration with
a theme rewrite. Extract the three embedded category images into static assets.
Retain Chart.js through a small lifecycle-managed component. Use React Query for
API caching, request state, and polling active runs, and an accessible headless
dialog primitive for modal focus/keyboard behavior. Pin resolved dependencies
in a lockfile after checking their current compatibility during implementation.

Organize components around the app shell, shared location/license/radius filters,
coverage summary, deal category columns/cards, directory/radar, menu inspector,
catalog table, sync/history view, calculator, watchlist, and toasts. Large product
lists use server pagination; the inspector must not attempt to render thousands
of DOM rows at once. Navigation/filter state is shareable in URL parameters;
the watchlist persists locally using stable offer identities and shows stale or
removed entries honestly after a refresh.

The default UI reads the real API. Loading, failed, unsupported, partial, stale,
not-yet-imported, and confirmed-empty states have distinct text and controls.
An unsuccessful live request never substitutes demonstration products. Remove
simulated mutations from normal operation; retain any replay fixtures solely in
tests or an explicitly identified development-only demonstration entry point.

The directory displays known stores even if their menus cannot be read. Menu
actions show provider state and source links. The sync view controls real runs
and the actual cadence, with per-store errors and retry outcomes. A stockout
requires valid source evidence. The calculator remains useful independently of
coverage; tax figures are labeled estimates and cannot become verified
out-the-door rankings without verified rules.

Capture the original page at desktop and mobile sizes before replacing markup.
Use the same sizes and equivalent filters to check the migrated layout. Permit
the new coverage information and necessary accessible controls to add space,
while preserving the existing visual identity and all retained functional views.

## 10. Acceptance and evidence matrix

| Area | Required evidence |
| --- | --- |
| Regional discovery | Replay the saved source deterministically, then refresh live. Account for all source rows and all five user examples. Inspect every current candidate in ZIP 61358/50 miles, including additions since capture. No frozen count of 23 is used as a live completeness assertion. |
| Branch identity | Confirm Beyond/Hello Bloomington separately from Normal and Peoria using retailer/provider evidence; preserve ambiguous or relocated-address conflicts until resolved. |
| Geolocation | Resolve 61358 with provenance/precision; verify unknown inputs do not move the origin; exercise boundary distances and unsupported jurisdictions. |
| Full menus | For each supported provider in the initial region, capture and replay representative pages, independently reconcile live totals/variants/categories, and verify traversal beyond 1,000 items using a deterministic large fixture. A fixture alone does not validate a live provider. |
| Initial import and diffs | Empty-database import, unchanged rerun, every mutable field changing, add/remove/reactivation, package variants, same IDs across different stores/licenses, and idempotent retry. |
| Failure preservation | Inject timeouts, malformed data, HTML/access responses, missing pages, repeated cursors, inconsistent totals, empty results, and large count drops. Prove no unvalidated removal, false completion, or last-success advancement. |
| Persistence | Restart after successful imports and during a staged job; verify catalog, evidence, source decisions, schedule, and history survive and interrupted work cannot duplicate diffs. |
| API/ranking | Verify Decimal ranking, conditional-price exclusions, data-version pagination, license/category isolation, stale-data selection, coverage denominators, and safe exports. |
| Frontend | Typecheck, production build, component tests for meaningful state transitions, and browser tests of every retained view, real sync controls, missing-menu states, keyboard dialogs, watchlist persistence, and mobile/desktop screenshots. |
| Local runtime | Run the production frontend served by FastAPI; prove displayed records come from persisted real observations, and report live source failures/provider limits explicitly. |

Do not call regional menu coverage complete while any in-scope operating store
or license context has an unresolved, inaccessible, partial, stale, or unsupported
required menu. These states may be shipped visibly as an incremental milestone,
but the completion report must identify the unmet acceptance criteria. Evidence
that every known menu is complete still does not justify claiming discovery of
every possible store outside the dated source coverage.

## 11. Delivery boundaries

Preserve the original prototype as a visual reference and the captured audit
artifacts as dated evidence. Do not initialize a Git repository or make deployment
changes as part of this design: the current workspace is not a Git checkout.
No external service account, paid API, cloud deployment, checkout flow, or
multi-user authentication system is required by this release.

Provider implementations are accepted only against observed contracts and
complete evidence. If a source cannot be read reliably, record the concrete
limitation and keep its coverage gap visible. A generalized adapter skeleton,
an importer populated by the five supplied names, or a React copy of the demo
does not satisfy the agreed outcome.
