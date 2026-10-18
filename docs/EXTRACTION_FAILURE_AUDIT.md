# Menu extraction failure audit

Audited 2026-10-17 from a read-only query of `terpscout.db`, `data/page-recheck-regional-search-audit.json`, `docs/JANE_SOURCE_RESEARCH.md`, and the code in `backend/`. Region: Minonk 61760 / 100 mi, 190 registry candidates, 22 with an accepted menu. No new crawl was run. Items marked **(hypothesis)** are inferred from code and evidence and need a probe to confirm.

## 1. Where the 168 uncovered stores are lost

The funnel has three separate leaks. Fixing one does not help the others.

| Stage | Count | Notes |
| --- | ---: | --- |
| Registry candidates in region | 190 | Illinois only |
| No endpoint at all | 146 | Discovery failure (section 2) |
| Endpoint exists, no accepted menu | 22 | Extraction failure (section 3) |
| Accepted menu | 22 | 18 of them stale (>12 h) |

### 2. Discovery failures (146 stores with no endpoint)

Latest resolution record per store:

| Count | Recorded reason | Real class |
| ---: | --- | --- |
| 131 | "No retailer locator connector configured for this brand" | Not a failure reason. It is the absence of a hand-written chain connector. All 131 records are dated 2026-10-17. The later search audit covered only 122 of the unconfigured stores. |
| 10 + 3 + 1 | HTTP error / ConnectError / access challenge | Transport and bot-wall |
| 9 | Retailer requires age/terms confirmation, menu not fetched | Gate (browser option) |
| 9 | Search found no corroborated candidate | Search or matching |
| 9 | Locator did not expose a corroborated branch/menu link | Chain page not understood |
| 8 | Provider found, license context not corroborated | Identity/context |
| 6 + 5 + 3 | No matching address, candidate needs matching, no endpoint | Identity proof |
| 2 | Identity conflict | Rebrand or wrong branch |

Root causes, in order of impact:

1. **Search is a single fragile channel.** `site_discovery.search_websites` scrapes Bing HTML with a `b_algo` regex. DuckDuckGo is effectively dead: of 60 audited DuckDuckGo calls, 51 returned HTTP 202 (bot interstitial) and 9 returned 403. Bing returned 200 for all 181 calls, but 61 of 122 searched stores still produced no candidate. Matching then requires brand words plus city or a cannabis keyword inside the result snippet, so a result whose snippet lacks those words is dropped. There is no search API, no second independent source, and no result-level scoring, only hard filters.
2. **Hand-written chain connectors are the only chain knowledge.** `locators.CONNECTORS` has 17 regexes. Every other brand is searched one store at a time, even though many stores share a brand. Discovering a chain once and enumerating its branches would convert many store-level searches into one.
3. **The 131 "no connector" records may be stale as a diagnosis.** The record does not say whether search ran afterward. Rerunning resolution with search enabled is cheap and would show how many are really unresolved.
4. **Gates stop discovery.** Nine stores stop at age/terms because the page was fetched without a browser. The browser path can handle these when options are enabled; the resolver should escalate automatically instead of recording `blocked`.
5. **Bookkeeping inflates endpoint counts.** 81 of the stored generic endpoints are `superseded` (44 third-party directory pages, 19 filtered/promotion pages, 18 anchor or pagination aliases). They were created, saved, then discarded. The "44 stores with an active endpoint" figure in the status report still contains directory leads. Do not persist leads as endpoints.

### 3. Extraction failures (22 stores with an endpoint, no accepted menu)

Non-superseded failing endpoints, grouped by recorded error:

| Count | Provider | Error | Hosts | Class |
| ---: | --- | --- | --- | --- |
| 22 | generic | No structured products extracted | bloomington.cookies.co, terrabis.co, philidispensary.com | Blank render or unknown schema |
| 21 | generic | Products extracted, but no independently verifiable full-menu total | nueracannabis.com, wheresweed.com, trinitydispensaries.com | **Extraction worked; the completeness gate rejected it** |
| 7 | jane | No structured products extracted | acesdispensary.com, beyond-hello.com, highhavencannabis.com, philidispensary.com | Jane runtime never populates |
| 6 | dutchie | Access challenge (HTTP 403) | dutchie.com | Remote rejection of this session |
| 1 | dutchie | No structured products extracted | dutchie.com | Same family |
| 4 | sweed | Empty/large drop requires confirmation | ivyhalldispensary.com | Working safeguard, waiting on confirmation |
| 4 | sweed | SSR query cache missing | zenleafdispensaries.com | Provider schema drift |
| 2 | sweed | Missing products / inconsistent total | shop.bisalina.com | Reconciliation |
| 1 | sweed | Changed across independent traversals | shop.treehausil.com | Unstable inventory |
| 1 | treez | "Empty" | stashdispensaries.com | Count mismatch, pagination |
| 1 | generic | `locator.click` timeout (30 s) | curaleaf.com | Brittle selector |

Root causes:

1. **The completeness model only has two outcomes, so the generic path can never pass.** `providers/generic.fetch` requires a JSON-LD `ItemList` whose name matches "all products / full menu" and an `numberOfItems` that equals the traversed parent count. Almost no storefront emits this. That is why 21 endpoints that did extract products still fail ("no verifiable total"). The gate protects against false completeness, but with no intermediate grade the result is zero deals from those stores. Total sources the page does show but the gate ignores: a visible "759 products" counter, category tab counts, Algolia `nbHits`, GraphQL `totalCount`.
2. **Extraction is DOM/JSON-LD only, not network-first.** `generic.extract` reads `application/ld+json` and `data-product-id` attributes. Modern platforms (Jane, Dutchie, Cresco, Weedmaps, Sweed-hosted skins) load products from XHR/GraphQL/Algolia JSON, then render custom elements or shadow DOM. The browser worker already captures responses as evidence but nothing reads them as data. **(hypothesis)** This is why Phili renders 759 products in ordinary Chrome and yields zero here.
3. **The browser's own network policy likely starves the menu.** Browser traffic must pass `PublicFetcher`, which allows POST only to three exact URLs (`_READ_ONLY_SEARCH_POSTS`) and a restricted header set. The status report records that client initialization/telemetry requests were blocked by "the acquisition method policy" on Phili and Aces. Jane and Dutchie menus typically load via POST (Algolia query, GraphQL). **(hypothesis)** A read-only query POST that the page needs is being refused, so the app never initializes. Test: log blocked requests by method and path for a Phili run, then allow one class of body-validated read queries and compare. An exact-URL allowlist cannot scale to "dynamic".
4. **Dutchie and Jane have no native contract.** Jane's public Algolia key route returned a Cloudflare 403 from Python HTTP (a TLS/session fingerprint rejection, not an empty menu). Dutchie 403s are the same family. Ordinary Chrome works, so a real browser session plus in-page `fetch` or response interception is the path that does not depend on the raw HTTP client. Do not try to defeat challenge pages; if Chrome itself is challenged, record `blocked_challenge`.
5. **Provider adapters are brittle by design.** Sweed's "SSR query cache missing" (Zenleaf) and Blaze's `weight_prices` rejection (`normalize_blaze` raises on any unvalidated schema) mean a minor provider change fails the whole menu. Nothing detects drift and self-repairs; each break needs a developer.
6. **Error strings drive control flow.** `service.py` classifies `unsupported` by substring match and stores failures as free text or JSON strings. There is no enumerated failure code, so nothing can route an endpoint to the right fallback automatically. This blocks any tiered design.
7. **Fixed 30 s `locator.click` and regex selectors for gates** (Curaleaf) fail on any site variant. Gate handling is a closed list of known patterns.
8. **Instability is treated as failure.** Tree Haus and Stash fail because two traversals differ while inventory changes live. Required stability (exact equality of two passes) is stricter than real menus allow. Use churn-tolerant reconciliation (for example, accept if >=99% of items match and differences are explained by stock or price changes), labeled with a grade.

### 4. Cross-cutting issues

- **Freshness.** 18 of 22 accepted stores are older than 12 h. The scheduler runs 2 to 4 times a day, and a full pass is slower than the freshness window, so most data is stale by design.
- **Provider coverage is concentrated.** Sweed accounts for 18 of the 22 accepted stores. Jane (5 stores), Dutchie (2), generic/unknown (12) have no accepted menu.
- **Telemetry.** There is no per-store, per-stage outcome table keyed by pipeline version, so coverage cannot be tracked as a metric over time.
- **Policy boundary.** The project stance is no CAPTCHA solving and no evasion. Keep it. Where a site blocks automation outright, the options are an official feed, retailer cooperation, or a human step, and the product should show the store as `blocked` with a reason.

## 5. Failure taxonomy to adopt

Replace free text with a code that selects the next action:

| Code | Meaning | Next action |
| --- | --- | --- |
| `NO_LEAD` | No website candidate | More search channels, chain inference |
| `LEAD_UNVERIFIED` | Site found, branch not proven | Browser branch selection, then agent |
| `GATE_AGE_TERMS` / `GATE_LICENSE` / `GATE_BRANCH` | Known shopping gate | Browser gate handlers |
| `GATE_UNKNOWN` | Modal/overlay not recognized | Agent |
| `CHALLENGE_BLOCKED` | 403 or challenge in an ordinary browser too | Report; no bypass |
| `HTTP_REJECTED` | Raw HTTP rejected, browser untested | Browser tier |
| `RENDER_BLANK` | 200, no products | Network-first capture, policy check, agent |
| `SCHEMA_UNKNOWN` | Product JSON/DOM found, no mapping | Auto-mapper, then agent |
| `PAGINATION_UNKNOWN` | Partial page of a larger set | Scroll/pagination discovery |
| `TOTAL_UNVERIFIABLE` | Items extracted, no source total | Graded completeness |
| `UNSTABLE` | Passes differ | Churn-tolerant reconcile |
| `DRIFT` | Previously working recipe/adapter broke | Re-learn (agent) |
| `BRANCH_MISMATCH` | Menu belongs to another address | Rediscover |

See `docs/ROBUST_EXTRACTION_PLAN.md` for the redesign.
