# Implementation ledger

## Authorized age flow and live-view verification: 2026-10-17

- User explicitly confirmed being 35 and authorized ordinary age confirmation and terms acceptance on their behalf for this session. Persisted browser settings are now enabled, age_confirmed=true, terms_accepted=true; verified through the running API. Do not ask for the same authorization again within this scope.
- Fixed a late-resource/result race: a broken stdin reply after successful Node completion no longer discards an already queued browser result.
- Preserve observed same-host Next.js RSC navigation headers through the browser bridge. Carry saved, real browser consent cookies into subsequent same-site menu reads, respecting host, path, expiry and secure flags. Strip navigation headers and cookies on cross-host redirects. Public read-only search requests retain only the endpoint's permitted observed headers.
- Live Stash browser passed the age gate and reached the actual storefront with products and location choices (17.46 seconds, capture `62a98d79172146430e8563d1ae9b74fd29fadcf2a0a9e419cba48731362df8d2`). App retry `e303e9598d2c4412ac852334a71bd825` follows official `/shop` links; it remains partial due to structured-product identity extraction, not disabled age permissions. Captured API search responses also include Cloudflare HTTP 403. No full inventory claim is made.
- Snap disappearance report: registry record and accepted 668-variant snapshot remained present. Verified directory card and rendered live deal results: 238 flower, 139 vapes, 28 concentrates. User confirmed the conflicting screen was the old local HTML version; it was not a lost-store record. Original HTML remains preserved.
- Added server data revisions and five-second client change detection to invalidate stale catalog/directory/coverage caches after sync changes. Regression covers retaining an imported store/menu after a later resolution failure.
- Verification: 126 backend tests discovered, 120 passed and six Chrome tests skipped in the standard gate. All six Chrome integrations passed separately; four browser-boundary tests passed. Frontend: 14 tests and production build passed. Evidence: `data/age-and-visibility-tests.txt`, `data/authorized-browser-tests.txt`, `data/stash-authorized-live.txt`, `data/authorized-stash-app-acceptance.json`.

## Official-site selection and browser deadlock: 2026-10-17

- Reproduced Stash's official age-gated locator being displaced by a public-search JointCommerce listing. Matching a store name/address on a directory and finding `/menu` in its URL incorrectly promoted it to an inventory endpoint.
- Retain the official locator and its actual failure; known directories are discovery leads only. Follow their explicitly labeled external Website links to find retailers. Prefer direct-site search candidates and continue searching when only directories appear.
- Canonicalize ordinary document anchors before crawling and saving endpoints, while preserving SPA hash routes. Corrected the branch-link matcher to follow bare `/menu` and `/shop` paths. Added regressions for source selection, outgoing Website links, fragments, persisted aliases and stable legacy IDs.
- Retired eight existing invalid directory/anchor endpoints from active coverage at startup. Their records, source evidence and diagnostic history remain accessible. Accepted retailer snapshots were preserved.
- Cookies reproduction: both Python/Node pipes blocked while Python wrote a large resource response. The 50-second watchdog killed the worker; closing its broken stdin then raised Windows errno 22, masking the timeout. Independently draining stdout resolves the duplex deadlock. Cleanup no longer masks the cause; failures retain capture manifests and useful timeout/exit diagnostics. Node awaits final output flushing.
- Live rechecks: Cookies rendered 858,897 bytes in 4.91 seconds; official Stash rendered 170,226 bytes in 4.92 seconds. The Stash retry uses `www.stashdispensaries.com`, reports its age/terms gate, and creates no JointCommerce menu. Saved age/terms preferences remain false. Cookies' retry no longer times out; its current storefront still needs extraction beyond the generic schema/card fallback, so no complete inventory is claimed.
- Sweed now reports actual failed page/count discrepancies and retains successfully observed earlier pages for partial-menu inspection. Bisa Lina's captured failed traversal reached page 143, where it advertised 3,445 records but returned 17 instead of the expected 24. This is recorded as incomplete rather than silently accepting missing inventory.
- Verification: 121 backend tests discovered, 116 passed and five installed-Chrome tests skipped by the default gate. All five Chrome integration tests passed separately, including 300 KB HTML plus 24 script responses. Logs/evidence: `data/source-selection-backend-tests.txt`, `data/browser-failure-reproduction.txt`, `data/browser-hang-trace.txt`, `data/browser-fixed-live.txt`, `data/source-selection-acceptance.json`.
- Reload was waiting for a long-running old sync. Restarted only this app's child worker; its unfinished job was retained as interrupted, API health recovered and targeted retries completed. No unrelated service was stopped.

## Development proxy correction: 2026-10-17

- Reproduced the reported region-write 403 through the actual Vite proxy: string shorthand enabled `changeOrigin`, rewriting Host to port 8000 while retaining the browser Origin on 5173.
- Replaced shorthand with explicit `changeOrigin: false`; the backend same-origin guard remains intact. Added HTTP proxy regressions for matching and foreign origins, plus Node type definitions for the integration test.
- Running development server verified for both localhost and 127.0.0.1: GET regions 200, same-origin empty POST reaches schema validation (422), foreign-origin POST remains 403. No region was changed by these checks.
- Found the missing default favicon request (404); added an explicit SVG favicon link. Frontend 13 tests and production build passed; all 13 API tests passed.

## Latest expansion: 2026-10-17

- Continued under the user's existing implementation approval. Added public website search for missing connectors, cached evidence, branch crawling, provider-address validation, recreational defaults, Dispense ingestion, structured/visible-card/browser extraction, partial-observation inspection, browser preferences and targeted retries.
- Corrected over-strict absent-address handling while rejecting actual conflicting branch metadata. Added regression checks for wrong-branch navigation and featured-carousel false completeness.
- Mitigated a reproduced native Windows background-parser crash with an 8 MiB worker stack; the complete 143-location discovery audit then finished. No global Python installation was changed.
- Website audit: 143 previously unconfigured-brand locations inspected; 70 had website candidates, 73 did not. Candidates are not accepted menus.
- Final targeted app job `9b7f49d85a434dc29c0473831e96d349`: eight of nine selected stores yielded complete snapshots. Bisa Lina totals remained inconsistent. Region status is partial.
- Current GPS / 100-mile region: 213 stores; 22 stores have accepted complete menus, 31 fresh complete source endpoints, four failed/partial endpoints, 189 stores without resolved endpoints. Stored counts: 28,021 source product identities, 30,056 source variants, 12,104 comparable offers. Alternative providers/license channels are counted separately.
- Latest backend gate: 112 tests, 108 passed and four browser tests skipped; the four installed-Chrome integration tests passed separately. Frontend: 11 tests, TypeScript and production build passed. API health and scheduler verified live after the import.
- Evidence and precise limits: `docs/DISCOVERY_FALLBACK_RESULTS.md`, `data/regional-expanded-import.json`, `data/regional-platform-discovery.json`, `data/backend-final-tests.txt`, `data/browser-fallback-tests.txt`.
- Older measurements below document the original implementation baseline, not the current region or coverage.

Plan: `docs/superpowers/plans/2026-10-17-coverage-and-react.md`
Spec: `docs/superpowers/specs/2026-10-17-coverage-and-react-design.md`

- Architecture and written spec approved by the user. User explicitly requested implementation.
- Ruling: proceed after saving the plan without another approval checkpoint, following the user's explicit instruction and existing authorization.
- Ruling: this workspace is not a Git repository; preserve original sources and database backup, and record progress here rather than initializing Git or creating a worktree.
- Pre-flight: discovery and adapter contracts are plain JSON dictionaries; persistence does not perform network calls. Frontend consumes the typed API contract in the plan. These independent work areas have disjoint file ownership.
- Status: implementation integrated; regional menu coverage remains partial and explicitly disclosed.

## Implemented and verified on 2026-10-17

- Replaced simulated default runtime with additive SQLite migrations, source observations, transactional snapshot reconciliation, durable jobs, persistent schedules, a typed API and React/TypeScript/Vite frontend.
- Discovery imports all 287 rows of the observed Illinois registry: 23 locations within 50 straight-line miles of ZIP 61358. All named examples appear independently of custom store seeds.
- Public locators corroborate addresses and discover provider IDs. Blaze and Sweed use observed schemas and two independent full traversals. Access/schema/identity gaps remain explicit.
- Live run: five menus across four stores. Snap Pontiac: 668 variants; Ivy Hall Peoria recreational and medical: 1,054 each; Tree Haus Morris: 1,035; Tree Haus Diamond: 1,027. Combined: 4,542 source product identities, 4,838 variants, 1,403 comparable offers. Nineteen stores lack imported menus. Overall status: `partial`.
- Tests cover initial seeding, metadata updates, removals/reactivation, restart, stale/new failures, malformed/duplicate pages, >1,000-item menus, unsafe network targets, license isolation, CSV safety, benchmark aggregation and query versions.
- Integration fixed Sweed landing/category URL selection, selected-license expansion, blank-name quarantine, publication metadata selection, region payload validation, exact watchlist lookup, date-only formatting and filtered exports.
- Latest backend gate: 77 tests passed. Frontend: 9 tests, TypeScript and production build passed. Production dependency audit: zero reported vulnerabilities (`frontend/output/npm-audit-production.json`). TestClient emits a dependency deprecation warning; tests pass.
- Browser verified live directory entries, Snap's 668-record menu and page 2 of 27. Screenshots and view checks: `frontend/output/playwright/`.
- Subagents implemented disjoint areas but exhausted their quota before final review. Primary agent performed integration/regression/live/browser review; no independent final reviewer result is claimed.

## Evidence and limits

- Machine-readable report: `data/live-acceptance-final.json`; per-location gaps: `docs/LIVE_ACCEPTANCE.md`.
- Original HTML, database backup and backend entrypoint preserved. No Git initialization, deployment or access-control bypass.
- Cloud 9's ordinary browser reaches an age/qualified-patient assertion and terms/cookie agreement. Those assertions were not made for the user. Stash and other storefronts expose gates; other sources return HTTP failures or unresolved branch identities.
- Registry listing does not prove operating status or exhaustive discovery. Illinois-only sources and unverified boundary intersections remain disclosed. The region's absolute best deal is not established.

- Final browser checks: all four retained views, keyboard dialog close, 668-product inspector page 2, mobile navigation/layout, and desktop screenshots. App console: zero errors or warnings. History now has server/client pagination without a 100-run ceiling; catalog export applies category/search/freshness/removal filters.

- Final production restart probe: health OK, scheduler running, five accepted menus retained; history pagination and a 21-record filtered CSV match the catalog. Evidence: `data/runtime-smoke-final.json`.

- Browser watchlist verification: saved a real Snap Canna offer, reloaded, confirmed the saved identity and a fresh live recheck, then removed the review-only entry. Final console remained free of errors/warnings.

## Pipeline hardening follow-up, 2026-10-17

Earlier figures and authorization limits above describe the initial implementation, not the current coverage or session preferences. The user subsequently authorized ordinary age/terms handling; live saved options are enabled/age_confirmed/terms_accepted true. The selected Minonk 61760 / 100-mile region contains 190 registry locations. The baseline audit found 22 stores with accepted menus; that is not complete regional coverage.

The current audit and remaining requirements are in PIPELINE_AUDIT_AND_HARDENING.md. Shared orchestration now pins job scope, refreshes retained sources independently of discovery, deduplicates traversal aliases, checkpoints per-store attempts, coalesces active duplicate requests, isolates targeted retries and job cookie jars, serializes same-store work, and continues after isolated unexpected store failures. Frontend coverage distinguishes physical stores from endpoint totals and invalidates cached views on server revision changes.

The worker now handles recognized medical/recreational dialogs, defaults to recreational, preserves explicit medicinal endpoint context and records transitions. The user correctly identified that this step was absent; it must not be conflated with separate HTTP/access-challenge observations. Generic product identity now accepts a unique declared Offer.url and preserves unknown stock. Directory listings are leads rather than authoritative menu targets. Native Chrome transport preserves HTTP status and public-network restrictions.

Validation: 148 backend tests completed successfully, including 9 opt-in Chrome tests skipped in that invocation; the separate installed-Chrome suite passed all 18 tests and is recorded in data/authorized-browser-tests.txt. Frontend 16 tests, TypeScript and production build passed. New regression coverage includes queued-region changes, retained refresh despite search failure, canonical target deduplication, interruption before publication, targeted-job fairness/coalescing, isolated store failures, job cookie-jar separation, and dialog-scoped recreational/medical selection.

A new region-wide acceptance run uses the current source fingerprint; its job is recorded in data/pipeline-hardening-final-job.json. Source selection and unsupported full-platform extraction remain unfinished. No claim of all-store discovery, complete regional menus or the region's best deal is made.

### Branch selection follow-up

The initial regional run above was interrupted during subsequent implementation; it did not validate all 190 locations. The user's reported branch-selection failures were reproduced as a missing target-store context and unsupported picker shapes, with additional off-screen duplicate controls and a low browser request budget. The actual Stash worker now selects Peru and verifies its visible address. Promotion/product/category pages are excluded as independent full menus, with `/shop` preferred; legacy evidence remains retained. Progress is grouped by physical store with explicit license channels and stage details. See BRANCH_SELECTION_VALIDATION.md for exact live evidence and remaining limits. Latest verification: 156 backend tests (13 opt-in skips), separate 22-test Chrome/browser suite, frontend 18 tests and production build. Full Stash and regional inventory acceptance are still pending.

### Catalog reconciliation and address fallback follow-up

See CATALOG_RECONCILIATION.md. The shared browser catalog session and Treez Flight adapter follow observed pagination and expand capped variant groups through declared detail links. Identical cross-page overlaps are deduplicated without accepting gaps or changed variants. Failed later verification retains the larger earlier partial traversal separately. Blaze, Sweed and Dispense now compare inventory fields rather than raw source timestamps; all three reproduced the false-rejection test before correction. Known analytics/map resources are excluded after branch selection, and resource diagnostics survive acquisition failures.

Unsuccessful known-brand candidates no longer suppress independent fallback search. The resolver reserves bounded crawl capacity for name/address leads, invalidates old search strategy caches, and permits an exact street/city cannabis-business match after rebranding. The official RISE locator currently calls Revolution Normal's address Bloom Wellness Normal Northbrook (formerly Revolution). Live HTML search returned unrelated results/HTTP 202, so that branch remains unresolved; the search recovery fixture is not live recovery evidence.

Progress and coverage failures are grouped by physical store, preserve license/provider/target details, and render persisted errors as readable messages. Verification: 178 backend tests (18 browser skips), a separately passing 27-test browser suite, and 25 frontend tests plus TypeScript/build. The cross-provider application result is recorded in data/catalog-resource-validation-result.json: Snap 653 and Tree Haus Morris 1,043 records accepted; Stash 1,616 retained partial observations against 1,635 advertised variants, with no accepted removals. The remaining failures include unstable source pagination and a transient navigation timeout, not an observed CAPTCHA. A focused native-browser recheck loaded the failing page transition successfully. A single bounded navigation retry now preserves catalog position; no complete Stash or regional acceptance is claimed.


### Catalog traversal and provider-contract correction, 2026-10-17

Treez now rechecks overlapping pages at most twice per page, within the existing three-pass/900-second limits. Store, license, page index and variant consistency checks still apply on every read. Independent exact-count, stable-inventory verification remains required for acceptance. The UI reports overlap rechecks explicitly. Regression fixtures cover both recovered overlaps and persistent gaps.

The next live Stash run (1dfb18538d654fad9126e1f378dec146) retained 1,619 observed variants against 1,635 advertised variants. A later pass failed with `Empty`; its captured browser diagnostic reports timeout=false and exit_code=null. This was the Python message queue's 55-second idle timeout, not evidence of a CAPTCHA. The protocol now polls for cancellation while respecting the existing overall rendering deadline, allowing the worker's bounded navigation retries to finish. No complete Stash snapshot was published. Evidence: data/page-recheck-live-result.json.

A regional website-search audit completed 122 unconfigured-brand candidates: 61 had website leads and 61 had none. Of 112 without accepted catalogs, 56 had leads. These are unverified leads, not recovered stores or menus. A 15-store inspection cohort found Jane targets, HTTP/session failures, identity gaps and a separate false-resolution defect: a Sweed script reference without a tenant ID could stop discovery at a landing page. The resolver now continues crawling after platform-only hints, and the sync service independently rejects those hints before persistence/extraction. Tests use synthetic source fixtures. Evidence: data/page-recheck-regional-search-audit.json, data/page-recheck-platform-cohort.json, data/provider-contract-tests.txt, data/provider-service-tests.txt.

Validation after the provider and protocol corrections: 187 backend tests completed successfully (19 opt-in browser cases skipped in that invocation), recorded in data/pipeline-contract-final-tests.txt. The page-recheck frontend changes passed 25 tests and a production build (frontend/output/page-recheck-tests.txt and page-recheck-build.txt). Regional completeness, reliable search, rebrand matching and additional full-provider acquisition remain open; retained accepted catalogs and physical registry stores are preserved.

The separate installed-Chrome browser-render suite passed all 21 cases after the protocol correction, including catalog rechecks, transient navigation recovery, location selection and shopping-context dialogs (data/pipeline-contract-browser-tests.txt). A fresh complete live retailer traversal after this protocol correction remains unverified.


### Dynamic discovery, branch scope and traversal verification

Continued the approved shared-pipeline recovery work. Search strategy 4 selects the primary result anchor rather than auxiliary links/resources, preserves search-attempt provenance on memory/disk cache hits, invalidates earlier search caches, and uses domain-boundary matching for redirect decoding and excluded hosts. An offline replay of 61 previously captured positive searches (322 candidates) removed zero candidates in that historical cohort; the new regression reproduces the auxiliary-link failure, but the replay does not establish additional live coverage.

The branch inspector excludes navigation/footer location lists from branch evidence, scopes declared schema URLs to the current hostname/path, and gives explicit conflicting street addresses precedence over general business/locality text. Discovery also follows observed same-site menu/shop/order/location anchor labels rather than requiring fixed route names. Fixtures cover /our-menu/, /plainfield-menu/, /adult-use/ and arbitrary retailer-declared /start-here/ routes, while excluding unrelated-host and privacy links. Existing crawl bounds and provider validation remain in force.

Generic structured extraction version 2 checks the actual acquired document's source hostname, explicit license context and contradictory branch address on every page before collecting products. Missing branch evidence does not become a contradiction. Prior valid observations survive a subsequent wrong-branch page. Independent inventory fingerprints omit raw metadata while retaining normalized identity, prices, mass and availability. These safeguards do not add native Jane or Dutchie traversal.

Validation: 197 backend tests passed (19 opt-in cases skipped in that run); the separate installed-Chrome render suite passed all 21 cases. Logs: data/dynamic-pipeline-backend-tests.txt and data/dynamic-pipeline-browser-tests.txt. Focused red/green logs cover search provenance, branch scope, semantic navigation and generic traversal. No frontend code changed in this pass.

Live production-path cohort job 3d15aabbc8e445c39ceaff18a7270bbd uses regional-pipeline-2.af1738e29c and four physical stores: Snap Canna Pontiac, Tree Haus Morris, Phili Bourbonnais and Aces Plainfield. Snap accepted 651 products. Tree Haus observed 1,038 products but the independent complete traversals changed; the accepted prior snapshot was preserved. Phili's Jane targets were resolved but yielded no structured products. The full job and channel-level outcomes are retained in data/dynamic-pipeline-live-result.json. This run does not demonstrate new accepted-store recovery, exhaustive regional coverage, or support for arbitrary future menu schemas.

Next recovery work remains the measured provider acquisition gap (especially Jane/Dutchie), reliable search/source authority, stronger selected-location proof on chain-wide pages and a full regional acceptance pass. Existing captured Jane evidence includes HTTP rejection and successful script loading without a structured catalog; neither alone proves that every Jane failure is an access challenge. Captured age-template markup is not proof that a visible age dialog blocked acquisition.


### Browser readiness and diagnostics follow-up

Browser acquisition now preserves up to 100 page errors and 100 console errors (1,000 characters each) in its evidence diagnostics. A browser regression proves runtime exceptions and console failures are retained. Generic menu acquisition explicitly requests a bounded product-readiness wait across the page and embedded frames: it stops on declared/visible product evidence or after 12 seconds. This does not prove catalog completeness, paginate a carousel, or turn missing products into an empty accepted menu. A delayed-product fixture reproduced the old fixed-settling-delay miss and passes with readiness enabled.

A fresh ordinary Phili acquisition with the readiness option still observed no products after the bounded wait (HTTP 200, 109 captured requests, no uncaught page errors). It retains console/resource failure evidence rather than identifying every failure as a challenge. Evidence: data/phili-menu-readiness-live.json and its referenced browser capture. The earlier data/phili-runtime-diagnostics.json records the baseline diagnostic capture. This timing correction has not recovered the Phili catalog; provider/bootstrap acquisition remains unresolved.

Latest backend verification: 199 tests passed, with 21 opt-in Chrome cases skipped in that invocation (data/dynamic-pipeline-backend-tests.txt). The four-store production-path job above predates the additional readiness/diagnostic instrumentation; it remains valid evidence for the discovery/context fixes, not a post-readiness all-store acceptance run.

Final installed-Chrome verification after readiness and diagnostics changes: all 23 browser-render/protocol cases passed in data/dynamic-pipeline-browser-final-tests.txt.


### Shadow DOM, native connection capacity and event-stream recovery

The shared native tunnel silently closed connections when its 24 slots were occupied. It now queues for a bounded eight seconds, returns/logs explicit capacity failures, and records peak/active/queued/rejected counts. Native rendering authorizes destinations from validated page requests before opening tunnel connections, preventing unrelated Chrome background services from consuming slots. Public DNS/IP pinning, HTTP(S)-port restrictions, method validation, capture budgets and overall deadlines remain in force. Regression coverage proves queued reuse, explicit refusal and denial before capacity is used.

Two-store acquisition evidence in data/jane-tunnel-cohort.json confirmed both Phili and Aces reached 24 active connections. With page-request authorization, their peaks dropped below the limit, but both hit the rendering deadline. Added worker phase checkpoints identified response_captures as the stalled phase (data/jane-phase-cohort.json). A controlled installed-Chrome integration test reproduced a long-lived Server-Sent Events response blocking completion. Capture now records text/event-stream responses as skipped streams rather than waiting for their bodies to end or recording them as complete finite responses. Subsequent Phili/Aces probes completed HTTP 200, with peaks of 18 and 21 connections, no capacity queues/rejections and one LaunchDarkly event stream skipped each (data/jane-shadow-stream-cohort.json). They still extracted zero products.

An ordinary Chrome inspection of Phili, using the authorized age confirmation, showed a working recreational Jane menu and 759 products in its All products view. Product cards reside in an open shadow root. Readiness, semantic card collection and rendered-document serialization now include open/nested shadow roots, including those within acquired frames. Regression fixtures verify both JSON-LD and visible-card observations in shadow DOM. This closes a source-observation gap; it does not establish native Jane full-menu traversal or make a carousel complete. Source screenshot: frontend/output/phili-all-products-browser.png.

The same source inspection showed a struck-out regular price before the sale price, e.g. 50 dollars followed by 35 dollars per half gram. DOM extraction now distinguishes explicit struck-through prices, skips unresolved multiple-price cards, preserves conditional-price markers and reads fractional masses such as (.5G). Generic structured extraction version 3 retains a unique valid USD strikethrough specification as the regular price and ignores ambiguous/malformed optional specifications. Reference: https://schema.org/StrikethroughPrice . Source raw text remains attached; these observations are not promoted into Best Deals without normal acceptance checks.

The readiness budget is internally configurable and clamped between 250 and 30,000 milliseconds, retaining the 12-second production default and overall renderer deadline. A diagnostic 30-second Phili readiness probe also returned zero products (data/jane-bootstrap-budget-probe.json), so increasing the wait alone is not established as a recovery solution. Current evidence includes blocked client initialization/telemetry requests and console failures; this cohort does not establish that CAPTCHA or HTTP 403 explains the blank automated menu. Do not attribute all regional failures to that mechanism.

Reproduction: scripts/probe_browser_cohort.py accepts repeated --target STORE_ID OBSERVED_URL, --output, optional --workers and --readiness-ms. It uses saved browser settings, reads registry/settings in SQLite read-only mode, and writes acquisition evidence without importing snapshots. No native traversal for Jane/Dutchie or complete regional acceptance was added by this pass.

Verification: 26 installed-Chrome render/protocol tests passed (data/shadow-stream-browser-tests.txt), including the native controlled event-stream integration, open shadow roots and sale-price extraction. The configurable-readiness follow-up passed separately (data/readiness-budget-tests.txt). Full backend verification is recorded in data/shadow-stream-backend-tests.txt. No frontend code or styling changed.

Final backend result for this pass: 206 tests completed successfully, including 24 skipped opt-in browser cases; the separate 26-case installed-Chrome suite passed.
