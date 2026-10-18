# TerpScout coverage audit and recommended direction

Audited October 17, 2026. This report describes the checked-in workspace and its
SQLite file, plus public-source probes. It is not evidence that the application
has been converted to live discovery or ingestion. No product behavior was
changed during this audit.

## Answer

The current app is a demonstration. It does not discover dispensaries or fetch
their products. Both lists are hard-coded in the frontend. The scheduler and
manual sync endpoint do not ingest anything. Consequently, its deal rankings
cannot currently establish which dispensaries have the best actual offers.

The small catalogs are not caused by importing only changes instead of an initial
snapshot: there is no external menu import path. The standalone Python diff
helper can seed an empty catalog, but nothing calls it from the backend jobs.

## User's actual search: ZIP 61358, 50 miles

The user supplied Cloud 9 East Peoria, Stash Peru, Snap Canna Pontiac, an
additional Beyond/Hello in Bloomington, and Beyond/Hello in Peoria. All five
have corresponding candidates in the public state map and are absent from the
prototype directory. The existing Beyond/Hello Normal recreational/medical
entries are two menu entries for the same address, not these other branches.

For this check, the [ZIP lookup response](https://api.zippopotam.us/us/61358)
places ZIP 61358 at Rutland, approximately 40.9844, -89.0388. This is a
third-party place centroid, not the user's precise location or an independently
verified postal polygon. The state snapshot has **23 candidates within 50
straight-line miles of that point**, including all five examples:

| User example / corresponding registry candidate | Registry address | Approximate distance |
| --- | --- | ---: |
| Cloud 9 - East Peoria | 406 W Camp St, East Peoria | 35.6 mi |
| Stash - Peru | 1320 38th St, Peru | 26.2 mi |
| Snap Canna - Pontiac | 1910 W Reynolds St Unit A, Pontiac | 20.9 mi |
| Beyond Hello Bloomington Keaton Place | 118 Keaton Place, Bloomington | 33.7 mi |
| Beyond/Hello - Peoria | 7620 N IL Rt 91, Peoria | 35.7 mi |

These are registry matches, not proof that full live menus were fetched or
that every operating store is in the registry. The exact Bloomington branch
identity/address still needs retailer corroboration rather than treating a
brand/city match as sufficient. The map supplies a concrete candidate to check.

The prototype interpolates ZIP 61358 to 40.8994, -88.9175, about **8.6 miles**
from this lookup centroid. That is a separate radius-accuracy defect. Correcting
the location alone would not add any of these stores to its fixed directory.

Additional regional candidates absent from the prototype include Verilife
Ottawa, Curaleaf Morris, Tree Haus Morris, and Tree Haus Diamond. The saved
regional audit lists all 23, so validation is not restricted to the examples
the user happened to know.

The user's [Snap Canna site](https://snapcanna.com/) links directly to its
[Pontiac menu](https://snapcanna.com/menu/pontiac/), which was readable during
research. Cloud 9's supplied homepage yielded a JavaScript shell to the web
reader, Stash redirected to an age gate, and Beyond/Hello pages could not be
opened by that reader. These access outcomes must remain explicit; none is a
valid reason to record an empty product inventory or a completed menu import.

## Verified findings

| Finding | Evidence | Consequence |
| --- | --- | --- |
| Fixed directory with 18 store/menu entries | `index.html:895`, `INITIAL_DISPENSARIES` | Changing the radius only filters these entries; it never searches for additional stores. Recreational/medical entries can refer to one physical location. |
| Only 35 sample products, 34 active | `index.html:1160`, `INITIAL_PRODUCTS`; audit JSON | Low counts are the available sample data, not real inventory totals. Two store/menu entries have zero samples. |
| Page state starts from those constants | `index.html:1873` | Initial sync time and cycle count are also fixed values. |
| No frontend HTTP calls or browser persistence | Full-file search and audit script | The UI does not read the backend catalog. Reloading resets its in-memory changes and watchlist. |
| SQLite contains zero dispensaries, products, and sync records | Read-only queries against `terpscout.db` | The displayed data is not coming from the database. |
| Backend poll job reports success without doing work | `backend/main.py:65`; direct invocation returned `completed` and left database bytes unchanged | Scheduler execution is incorrectly presented as successful ingestion. |
| Backend has no discovery/catalog/coverage APIs | Inspected FastAPI route inventory | Only frontend serving, health, sync trigger, and the Razer WebSocket handler exist beyond documentation routes. |
| Frontend poll manufactures products and price reductions | `index.html:2546` | Poll timestamps and audit events are not observations of retailer inventory. |
| New-store registration manufactures contact/license details and sample products | `index.html:3178` | Its success toast claims initial ingestion without fetching a menu. The menu URL is always Windy City's locations page. |
| Unknown ZIPs are interpolated or silently placed at Macomb | `index.html:2793` | Store inclusion and distances can be wrong even within the fixed directory. Unrecognized city text can change the label without moving the coordinates. |
| Browser scheduling is independent of server scheduling | `index.html:2975`; `backend/main.py:49` | Frequency buttons change local UI state only. Browser auto-poll simulates every 30 seconds. The backend's four-run schedule uses 21:00, while the UI shows 18:00. |
| Default deals filter includes unchanged items | `index.html:1884`, `index.html:2072` | The default 0–3 result is not explained by a changes-only filter. The store inspector also shows every active sample for that store without a three-item limit. |

The audit script locates known declarations in this particular prototype. Its
string-marker counts supplement manual source tracing; they are not a general
proof that arbitrary applications contain no networking or persistence.

## Reproduced defects in the unused diff helper

The read-only audit runs these probes against in-memory catalogs:

1. An empty catalog plus one valid product yields an `ADDED` record. Initial
   seeding works at the helper level; the missing component is ingestion and
   persistence orchestration.
2. Changing a product from 3.5g to 7g while keeping price and THC fixed leaves
   the stored weight at 3.5g and stored $/g at $10 rather than $5. The helper
   only detects price/THC changes; other product fields can remain stale.
3. Passing an empty incoming list marks the existing product removed. There is
   no completeness/error signal to distinguish a genuinely empty full menu
   from a failed fetch or a partial page. This is a contract defect to address
   before connecting an adapter; no live fetch currently invokes it.

These are reproductions of existing behavior, not claims that fixes have passed.

## External discovery evidence

The [Illinois dispensary locations page](https://cannabis.illinois.gov/about/locations.html)
states that its map was updated October 8, 2026 and links to a public Tableau
workbook. Its public, unfiltered CSV export returned HTTP 200 with 287 records.
Using the app's default Macomb origin (40.4592, -90.6718), the snapshot contains
38 records within 100 straight-line miles.

Examples with names and addresses absent from the prototype directory:

| Registry candidate | Address | Distance from default origin |
| --- | --- | ---: |
| Ivy Hall - Peoria | 3929 W. War Memorial Dr, Peoria | 57.532 mi |
| Aroma Hill - Peoria | 1210 W Glen Ave, Peoria | 59.080 mi |
| Cloud 9 - East Peoria | 406 W Camp St, East Peoria | 59.131 mi |
| Cookies - Peoria Heights | 1209 E War Memorial Dr, Peoria Heights | 60.549 mi |
| NuEra Pekin | 3249 Court St, Pekin | 55.268 mi |
| Pekin Local Dispensary & Supply | 359 Court St, Pekin | 54.368 mi |

Do not subtract 18 from 38 to calculate missing physical stores. The 18 app
entries mix physical locations and license-specific menus; aliases, addresses,
and license identities require reconciliation. The map itself also needs quality
checks: its CSV repeats the `Dispensary Name` column, and source coordinates and
medical-service flags are observations, not independently confirmed ground truth.
The audit rejects conflicting values in repeated columns.

The app also labels Windy City Macomb as having a medical menu, whereas this
registry snapshot says it does not serve medical patients. Other app addresses
and names differ from the registry. These are discrepancies to investigate, not
grounds for automatically overwriting records or inventing medical endpoints.

The older [IDFPR combined license list](https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/forms/auc/all-cannabis-licenses.pdf)
is another reconciliation source; the version surfaced during research is dated
February 20, 2026, so it must not silently supersede the newer map. Conditional
licenses must be separated from verified operating locations.

The map is an Illinois baseline, not a guarantee of all stores operating today.
Macomb's 100-mile circle also reaches neighboring states. An Illinois-only query
must explicitly disclose that geographic limitation until those jurisdictions
have their own sources and verified menu support.

## External menu evidence

The [Windy City Macomb menu](https://www.windycitycannabis.com/shop/macomb)
advertised 245 flower and 256 vape products in the research page response. These
are retailer-reported counts from that response, not totals ingested or
independently reconciled by TerpScout. Search/cache and direct responses can
differ as menus change.

A separate direct HTTP probe returned HTTP 200 and HTML loading a module from
`static-prime.sweedpos.com/web-ui-shop/`; the response contained Sweed references
and no Dutchie/iHeartJane markers. This supports a Sweed adapter investigation
for this storefront, rather than trusting the prototype's platform label. It
does not establish a working, complete adapter or permission to assume a private
API contract.

The menu's landing page includes category and brand carousels. Parsing those
visible cards would produce an incomplete, overlapping catalog. Actual ingestion
must follow the full product listing's pagination and variant representation.

## Recommended architecture to review

This is an architectural change spanning discovery, ingestion, persistence, API
contracts, and the frontend. The following is a proposed direction, not an
approved implementation specification.

### Alternatives

| Approach | Benefit | Limitation |
| --- | --- | --- |
| Keep the current HTML and implement the backend | Smallest immediate UI change | Leaves a large DOM/state script to maintain and migrate later. |
| React + TypeScript + Vite, retaining FastAPI (recommended) | Fits the dashboard and existing Python ingestion stack; build assets can be served by FastAPI | Public search indexing would need separate consideration if it becomes a requirement. |
| Next.js frontend, retaining FastAPI | Useful if server-rendered public store/product pages and search indexing are core requirements | Adds frontend server concerns when its dynamic server features are used; does not itself solve discovery or ingestion. |

Vite documents [backend integration](https://vite.dev/guide/backend-integration)
and [static deployment](https://vite.dev/guide/static-deploy.html). Next.js also
supports [static exports](https://nextjs.org/docs/pages/guides/static-exports),
but features requiring its server are unavailable in that mode. The Vite choice
is a recommendation based on this app's current dashboard, not a claim that
Next.js cannot serve it.

### Discovery and measurable coverage

- Refresh authoritative registries by jurisdiction, preserving raw response,
  source URL, fetch time, published date, hash, parser version, and import result.
  A failed refresh retains the prior snapshot with its actual age.
- Separate physical locations, licenses, operating status, aliases, and menu
  endpoints. Store every source observation and conflict. Do not infer a medical
  license or menu from an adult-use location or a discount for patients.
- Resolve addresses with a real geocoder; cache results, record precision, and
  surface unresolved or conflicting coordinates. Never interpolate a ZIP or
  silently move an unknown location to Macomb.
- Corroborate registry entries using retailer store locators and provider
  directories where available. User-supplied names enter the same candidate
  queue and can be traced through every stage; they are not the discovery list.
- Query the entire requested radius across supported jurisdictions. Expose
  unsupported territory and unresolved candidates separately. Use precise
  distance for inclusion and round only for display.
- Report unique known operating locations in scope, registry freshness, sources
  checked, endpoints resolved, complete fresh menus, partial/stale menus, failed
  menus, unsupported providers, and unresolved identities/locations. Denominators
  must be tied to dated sources, never an unqualified claim of all possible stores.

### Full catalog first, diffs afterward

- Resolve the actual retailer, menu provider, store identifier, license context,
  and product endpoint. Record the evidence for the mapping. Unsupported or
  inaccessible providers remain visible as coverage gaps.
- Each adapter must enumerate all pages/cursors, categories, product variants,
  package sizes, and stock states. Detect repeated cursors, missing pages,
  duplicate identities, and unstable paging; retry or report partial coverage.
  Caps and timeouts report incomplete work rather than a successful full import.
- Preserve all source products, including categories outside the three deal
  columns and items without comparable weight/price. Separate total products,
  sellable variants, supported-category items, rejected records, and eligible
  $/g offers. An edible's THC dose is not its package mass.
- Use stable provider/location/license/product/variant identity. Names are not
  product identifiers. Record regular price, sale price, promotion conditions,
  eligibility, stock, package mass, cannabinoid dose, source URL, and observation
  time independently. Unknown or conditional prices cannot become an invented
  unconditional best deal.
- Stage every snapshot with expected/fetched counts, page accounting, raw
  evidence, parser errors, and a completeness result. If a provider exposes no
  trustworthy total, record that limitation and verify traversal independently.
  A suspicious large count drop requires revalidation before removals.
- The first validated full snapshot seeds the catalog transactionally. Later
  complete snapshots update all changed fields, last-seen information, and diffs
  in the same transaction. A failed, partial, suspicious, or unvalidated empty
  snapshot must not remove existing products or advance last-success timestamps.
- Preserve the last good snapshot as stale when refresh fails. Do not synthesize
  observations. Serialize jobs per endpoint, make retries idempotent, and keep
  persisted job/snapshot/audit history through process restarts. Configure the
  scheduler once on the backend and expose its actual cadence and job state.

### UI migration while preserving the appearance

- Preserve the existing dark palette, typography, glass cards, category colors,
  three-column deals layout, mobile navigation, directory/radar, charts, menu
  inspector, calculator, audit view, export, and watchlist behavior.
- Extract the existing embedded artwork into static assets; retain the existing
  Tailwind styling during the first migration. Capture desktop and mobile
  baselines before replacing markup and review screenshots after migration.
- Build React components for the shell, location/radius/license filters, coverage
  summary, category cards, store directory, product table, sync activity, and
  dialogs. Use accessible dialog/table components where useful, with styles
  matching the existing app. Large menus need pagination or virtualization.
- FastAPI owns catalog data, discovery, ranking inputs, sync configuration, and
  run results. React consumes typed API contracts and shows loading, error,
  partial, stale, unsupported, and genuine empty states. Default operation uses
  persisted real data; any retained sample mode is explicit and isolated.
- Describe rankings as the lowest observed comparable prices among covered fresh
  menus, with counts and exclusions visible. Do not claim a universal best deal
  when coverage is incomplete. Display source links and the last successful
  observation, and label tax calculations as estimates unless supported by
  verified location/product-specific rules.

### Acceptance evidence required before calling coverage reliable

1. Reconcile every registry row and every user-supplied missing store in a chosen
   test region. Each has a matched identity and outcome, or an explicit unresolved,
   unsupported, closed, or failed status with evidence. No silent omissions.
   The first acceptance region is the user's ZIP 61358 and 50-mile radius,
   including the five named cases and all other registry candidates in scope.
2. For representative real menus, reconcile independently checked product/variant
   totals and categories against the ingested snapshot. Include pagination over
   1,000 items, multiple package variants, unknown categories, and duplicate rows.
3. Prove empty-database seeding, unchanged-menu reruns, full-field changes,
   additions, legitimate removals, reappearing products, and license isolation.
4. Inject timeouts, page failures, HTML/error responses, malformed prices/weights,
   repeated cursors, interrupted transactions, and suspicious zero/count drops.
   None may erase the prior good menu or report a successful complete import.
5. Verify restart persistence and that scheduled/manual jobs use the same backend
   path. UI controls must reflect actual backend configuration and job outcomes.
6. Verify API pagination/filter/ranking behavior, accurate coverage denominators,
   stale-data treatment, and geographic scope across jurisdiction boundaries.
7. Verify frontend build/types and the real desktop/mobile flows against screenshots;
   disclose unverified providers and territories in the completion report.

## Reproduce the local audit

```powershell
.venv/Scripts/python.exe scripts/audit_prototype.py --registry docs/evidence/2026-10-17-illinois-dispensary-map.csv
.venv/Scripts/python.exe scripts/audit_prototype.py --registry docs/evidence/2026-10-17-illinois-dispensary-map.csv --origin-latitude 40.9844 --origin-longitude -89.0388 --radius-miles 50
```

The script performs no network calls, opens SQLite with `mode=ro`, and runs diff
probes only in memory. The saved JSON confirms that database bytes were unchanged.

Evidence saved alongside this report:

- `evidence/2026-10-17-prototype-audit.json`: source hashes, counts, per-store
  samples, in-memory reproductions, and all 38 nearby registry rows.
- `evidence/2026-10-17-illinois-dispensary-map.csv`: raw public export.
- `evidence/2026-10-17-registry-source.json`: retrieval URL, UTC time, content type,
  size, hash, source date, and verification boundaries.
- `evidence/2026-10-17-61358-geocode.json`: actual ZIP lookup response and its
  precision/source boundary.
- `evidence/2026-10-17-61358-50mi-audit.json`: all 23 regional candidates, the
  five user-supplied cases, and the prototype's ZIP interpolation error.

The user's regional examples are now captured as acceptance cases. Complete
retailer identity corroboration, provider adapters, real menu imports, and the
frontend migration remain future implementation work.
