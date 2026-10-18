# Catalog traversal and source recovery

2026-10-17. Implementation and measured boundaries; this is not regional coverage acceptance.

## Shared corrections

The browser now receives the requested physical store and license, selects an unambiguous visible location, and validates the resulting branch context. Sessions are isolated by host, store and license. Ordinary approved age confirmation is reapplied after native catalog navigation. Location selection alone does not prove menu identity.

Menu acquisition supports a browser catalog session: every observed document is captured, parsed in Python, and followed through its actual pagination links. Declared product-detail links can expand variant groups and return to the same catalog page. Native document navigation avoids a reproduced SPA failure where the URL changed to page two while the document still contained page-one inventory. Immutable first-party Next.js assets are reused within the session; inventory documents remain independently fetched.

The Treez adapter parses React Flight records without executing source JavaScript. Each page validates store GUID, license, index, pagination offset, USD context and exact raw inventory total. Listing cards collapse variants, and the inner variant response can itself be capped at five; a six-variant merchandise group was reproduced and is expanded using its declared detail link. Approximate grouped cardinality is not an inventory completeness check.

Identical product overlaps across pages are deduplicated. A changed normalized variant remains a conflict. Every completed traversal records its unique variant count, observed advertised totals and normalized inventory fingerprint. Completion requires two consecutive count-complete matching traversals; three traversals, page counts, request counts, bytes and elapsed time are bounded. Unmodeled source timestamps do not create false inventory differences. Incomplete traversal observations remain inspectable and cannot remove accepted inventory.

If a later verification traversal fails early, the larger earlier traversal is retained as a separate partial observation set, with its traversal number. Passes are never merged to manufacture completeness. Blaze, Sweed and Dispense now use the same inventory-field comparison as Treez; reproduced changing raw timestamps no longer invalidate stable normalized products, while actual inventory differences still fail.

Catalog acquisition skips known advertising/analytics/map hosts after location selection. The prior long run captured about 126 MB from Google Tag Manager and 67 MB from maps.googleapis.com, versus 58 MB from the retailer. These were avoidable repeated resources. Resource failures now preserve worker request limits/counts, capture errors and tunnel blocks, rather than discarding them on failure. A generic navigation failure must not be labeled a CAPTCHA or attributed to a particular budget without diagnostic evidence.

## Discovery fallback

A configured brand root is a candidate, not proof of current ownership. A failed brand crawl now reserves eight of its 24 page slots for independent name/address search. Address search requires the same normalized street, city and cannabis context in the result; the destination is inspected again before adoption. It can find a changed business name without dropping address verification. Search cache strategy revision invalidates earlier positive and negative entries.

This corrects a structural failure: the presence of any brand candidate previously prevented fallback search even if its pages never matched the target branch. RISE's current Illinois locator identifies Bloom Wellness Normal Northbrook (formerly Revolution) at 1609 Northbrook Dr. The old Revolution website's Schaumburg menu is an actual different branch, not a reason to weaken the address check.

## Live evidence

- `data/stash-location-live-probe.txt`: selected Stash Peru at 1320 38th St, with matching rendered branch identity.
- `data/treez-expanded-navigation-progress.json`: first expanded traversal reached 486 variants before the old overlap rejection. Page 21 and page 22 shared nine parent products tied at a $42 sort value. Captures `7989e676839677ec0283983e75ee5e7b47fdd089eba83abbe76535afcd5bbc4b` and `a1e307f2ff33237a1966818215263199baf918a103c32b82e4e10a351ac688b5`. The advertised raw total also changed between 1,635 and 1,636 during this run.
- `data/discovery-reconciliation-live-job.json`: subsequent targeted application validation for Stash, Revolution Normal and Verilife Ottawa. The job result must be checked independently; enqueueing is not successful extraction.
- Address search capture `d94ab5d5f286d94d7fc2e3febf445b6df9ea88bd927cc79cbb5ad2bd4e321dea` returned unrelated basketball results despite the correct query. DuckDuckGo capture `69b52fb00bfbff159fe841c443b7737c6e6338db21c2aa1a7caf69160cb172b3` returned HTTP 202. Those responses did not resolve the rebranded branch. Successful fixture recovery does not establish live search availability.

## Verification and remaining work

The application Python environment passes 178 backend tests, with 18 opt-in browser tests skipped (`data/discovery-reconciliation-backend-tests.txt`). The separate browser suite passes 27 tests (`data/discovery-reconciliation-browser-tests.txt`), including analytics suppression after branch selection, retained failure diagnostics, and a single bounded retry of a transient navigation failure without restarting the traversal. Frontend: 25 tests and production TypeScript/build pass (`frontend/output/discovery-reconciliation-tests.txt`, `frontend/output/discovery-reconciliation-build.txt`). Coverage and directory diagnostics parse persisted JSON into readable messages; repeated coverage failures are grouped by physical store and license/provider, with target details retained. Terminal ANSI formatting is removed from displayed source errors.

## Latest targeted application results

`data/catalog-resource-validation-result.json`, run `63fcf81d148741049bc9bd1712aab578`, pipeline `regional-pipeline-2.47116057cc`:

| Store | Result | Source records |
| --- | --- | ---: |
| Snap Canna Pontiac | Accepted complete | 653 |
| Stash Peru | Partial, no accepted snapshot | 1,616 |
| Tree Haus Morris | Accepted complete | 1,043 |

Snap's accepted rows include 134 eligible vapes, 27 concentrates and 235 flower offers, recorded in `data/snap-current-eligibility.json`. Its older 668-record count is historical, not a fixed catalog size.

Stash's first traversal had a constant exact raw total of 1,635 but only 1,616 unique variants. The second traversal reached page 66 before navigation to page 67 timed out. The larger first-pass observation set was retained, with no accepted inventory removals. Failure capture `6649fe1f1bc54204de60d0e6c022f883945874945b26bf855b91ba7b34d22aaa` records 1,999 of 5,000 requests, 172,141,104 captured bytes, and 795 auxiliary requests skipped. Neither recorded request/capture limit was exhausted; there was no observed CAPTCHA response. Tunnel diagnostics include host connection aborts. This does not establish the root cause of every earlier navigation failure.

A later focused native-browser probe loaded pages 66 and 67 with HTTP 200 and matching Peru/recreational context (`data/treez-failed-navigation-recheck.json`). Navigation now retries one transient failure, bounded by the existing overall deadline. That focused probe verifies reachability and context, not a complete catalog or recovery of all regional stores.

The larger regional failure set remains open. Unknown/changed provider schemas, Jane/Dutchie access and extraction, other selector patterns, imperfect search results, source authority, rebrands, jurisdiction coverage and final all-store acceptance are separate concerns. A directory listing, a few parsed cards, or a successful store-selection click does not prove a full menu. Partial records are not currently ranked as accepted Best Deals inventory.

## Source pagination research and next contract

The first complete Stash traversal followed 78 pages, encountered 13 duplicate variants and retained 1,622 unique variants against changing totals of 1,635–1,636. The missing-count gap is exactly the duplicated-variant count. Captured sort values show price-only ordering. This is consistent with the upstream search engine's documented warning: a non-unique tie-breaker can miss or duplicate hits across pages. The observed response/query format is Elasticsearch-compatible; this evidence does not independently identify its deployment or configuration.

Primary references: [Elastic pagination and tie-breakers](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results) and [collapse/search_after restrictions](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/collapse-search-results). A collapsed catalog cannot simply be given a generic `search_after` token: the documented collapse contract requires sorting and collapsing on the same field. The retailer's current price sort does not satisfy that rule.

The durable acquisition preference is a supported provider/retailer feed with store/license identity, stable unique ordering or cursor, complete variant expansion and a source total. When only the storefront is available, first-party documents remain useful observations, but repeated offset pagination is bounded and audited. Exhaustive source-declared partitions could reduce large tied-price groups, but require independent proof that every partition and variant was covered; this is not yet implemented. Increasing retry counts alone does not establish completeness.

Per-offer validity and whole-menu completeness also need separate read models. Verified partial prices can be useful without authorizing removals or claiming exhaustive rankings. At present partial records are available through the menu observations inspector, while Best Deals still uses accepted catalogs. A future partial-offer path must carry explicit provenance/completeness labels, apply normal price/mass/stock checks, handle overlap with accepted variants, and preserve the accepted snapshot/removal contract. It must not be implemented by relabeling a partial snapshot complete.

For website discovery, the current public HTML search engines returned unusable results even in an independent native-browser probe (`data/search-browser-research.txt`). An explicit reliable search service and an indexed, evidenced retailer branch directory are preferable to adding repeated browser retries to every unsuccessful query. Those integrations and a fresh all-store acceptance pass remain outstanding.


### Catalog traversal and provider-contract correction, 2026-10-17

Treez now rechecks overlapping pages at most twice per page, within the existing three-pass/900-second limits. Store, license, page index and variant consistency checks still apply on every read. Independent exact-count, stable-inventory verification remains required for acceptance. The UI reports overlap rechecks explicitly. Regression fixtures cover both recovered overlaps and persistent gaps.

The next live Stash run (1dfb18538d654fad9126e1f378dec146) retained 1,619 observed variants against 1,635 advertised variants. A later pass failed with `Empty`; its captured browser diagnostic reports timeout=false and exit_code=null. This was the Python message queue's 55-second idle timeout, not evidence of a CAPTCHA. The protocol now polls for cancellation while respecting the existing overall rendering deadline, allowing the worker's bounded navigation retries to finish. No complete Stash snapshot was published. Evidence: data/page-recheck-live-result.json.

A regional website-search audit completed 122 unconfigured-brand candidates: 61 had website leads and 61 had none. Of 112 without accepted catalogs, 56 had leads. These are unverified leads, not recovered stores or menus. A 15-store inspection cohort found Jane targets, HTTP/session failures, identity gaps and a separate false-resolution defect: a Sweed script reference without a tenant ID could stop discovery at a landing page. The resolver now continues crawling after platform-only hints, and the sync service independently rejects those hints before persistence/extraction. Tests use synthetic source fixtures. Evidence: data/page-recheck-regional-search-audit.json, data/page-recheck-platform-cohort.json, data/provider-contract-tests.txt, data/provider-service-tests.txt.

Validation after the provider and protocol corrections: 187 backend tests completed successfully (19 opt-in browser cases skipped in that invocation), recorded in data/pipeline-contract-final-tests.txt. The page-recheck frontend changes passed 25 tests and a production build (frontend/output/page-recheck-tests.txt and page-recheck-build.txt). Regional completeness, reliable search, rebrand matching and additional full-provider acquisition remain open; retained accepted catalogs and physical registry stores are preserved.

The separate installed-Chrome browser-render suite passed all 21 cases after the protocol correction, including catalog rechecks, transient navigation recovery, location selection and shopping-context dialogs (data/pipeline-contract-browser-tests.txt). A fresh complete live retailer traversal after this protocol correction remains unverified.
