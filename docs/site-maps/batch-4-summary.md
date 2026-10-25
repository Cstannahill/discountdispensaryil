# Batch 4 summary (38 stores, registry ids a793... to da94...)

Scope: Minonk 100-mile region, 190 stores sorted by id, 5 batches of 38; this is batch 4 (slice 114-152). Store list: `batch-4-stores.json`. Per-store maps: `batch-4-findings.json`. The per-store `<id>-<slug>.json` files were not written (usage limit reached); the findings file holds the same fields in one document. 13 saved endpoints were sampled with `sample_stores.py --pages 1`; an endpoint-level rerun with merged context (`sample_ep.py`) was started and not read.

## Counts

- Real website and menu platform identified: 37 of 38. Only **Here & Now (Des Plaines)** has no own site (directories only).
- Pipeline today: 8 accepted (all stale > 12 h at 2026-10-19 20:35Z), 5 partial/generic, 7 LEAD_UNVERIFIED, 2 failed, 16 NO_LEAD.
- Platforms: per-store in `batch-4-findings.json`; not tallied here.
- 30 stores have no accepted menu. 15 of the 16 NO_LEAD stores have a findable own site (Google, or a chain URL pattern). 10 of those 15 are on platforms the pipeline already extracts natively (Sweed 4, Jane 5, Joint 1). The other 5 are Dutchie, which is not a native provider.

## Root causes

| Code | Cause | Stores | Fix |
|---|---|---|---|
| S1 | Website search fallback dead (DuckDuckGo challenge, Bing collapses queries) | Bud and Ritas, Consume, NCC, Starbuds WM, SHARE, Spark'd Wicker Park, Mission/Norridge, Prairie South Loop, Prairie Naperville, Mystic Greenz, Lux Leaf, Namaste, WCC Macomb, Happy Cannabis, Hi Rise | Replace the search; or chain connectors keyed by brand. |
| C1 | Deterministic chain URL patterns unused | Sweed: Windy City `/shop/<slug>/menu`, Spark'd `/<slug>/menu`, Mystic `order.mysticgreenz.com/<slug>/menu`, Namaste `shop.namastecannabis.com/<slug>/menu`. Dutchie: Starbuds `starbudsillinois.us/stores/star-buds-<city>`, Dutchess `/stores/<city>-illinois`. Prairie `/shop/store/<jane id>`. | One connector per chain fixes the whole chain (4 Sweed stores here would then use the already-accepted Sweed path). |
| N1 | Registry names differ from public brand | NCC = Nature's Care, SHARE, Namaste Wellness, Lux Leaf (`nlj-dispensary`), Happy Cannabis Co. | Alias table in the registry. |
| N3 | Rebrands | Mission Norridge is now The Joint Dispensary (thejointdispo.com); Beyond/Hello Peoria is now Bloom Wellness (Rise) | Alias plus address proof; refresh stale verifier leads (beyond-hello.com Peoria URLs redirect to the index). |
| W1/W2 | Wrong host saved or probed | Rise Canton endpoint is a directory (wheresweed.com); Starbuds Summit endpoint is shop.starbuds.us not the store page; Cookies probed apex cookies.co (dead) while the menu is cookiesbbrook.com | Reject directory hosts as endpoints; follow store-specific subdomains. |
| L1 | Sibling or wrong-state leads | Mint (Florida/Arizona pages), Starbuds Riverside (Colorado), Dutchess (Lynwood/Oak Park), Sunnyside (Rockford), Cloud 9 (Cresco site, store is on Dutchie) | Rank leads by state/city/address before the identity check. |
| P2 | Treez/GapCommerce routed through generic | Be Blue Island, Stash Orland Hills: UI says "1-20 of 969", search is `POST search-kyrok9udlk.gapcommerceapi.com/product/search`, pipeline gets 20 items and TOTAL_UNVERIFIABLE | Native treez provider for these hosts; use the page total to reconcile. |
| P3 | Dutchie on brand hosts / embeds | Excelleaf (endpoint is the `embedded-menu/<id>.js` script URL, 0 items), Starbuds Summit (RENDER_BLANK, 146 s), Hi Rise, Lux Leaf, Dutchess, Starbuds | Dutchie replay should accept host-proxied `/api-N/graphql` and embed pages; never use the `.js` embed URL as the menu. |
| P1 | Cresco not a full-menu provider | Sunnyside Elmwood Park; Cloud 9 family site | Cresco provider (store-inventory-breakdown per host). |
| B1 | Cloudflare/bot walls in headless Chrome (reported, not evaded) | risecannabis.com (managed challenge), shop.consumeclub.com and menu.naturescarecompany.com (Jane pages 403), dutchie.com direct 403 | Skip the page; use the Jane/Dutchie APIs with a proven store id (High Haven Jane sample is 858/858). |
| BR1 | Default branch is a sibling | Happy Cannabis (default Loves Park, store is Rockford); Hi Rise title says Schaumburg | Branch picker plus platform address proof. |
| R1 | Locator crash | Bloc Forest Park, Rise Lake in the Hills: `locator.count: Frame was detached` | Catch and retry on detached frames. |
| R2 | Operator override without endpoint | Prairie Naperville Jane 6244 (commit e08ebfa) has no endpoint row | Targeted sync. |
| F1 | Accepted but stale | All 8 accepted stores older than 12 h (oldest: Mood Shine, AuraLight 2026-10-18) | Scheduler refresh. |
| D1 | Two accepted endpoints for one store | Parkway Tilton (Sweed 1801 + Dispense 1571) | One authoritative menu per store/channel. |
| T1 | Sampler tooling | `sample_stores.py` passes the raw endpoint row; Dispense needs `script_urls` (AuraLight and Parkway give 0 items, "SDK public key could not be located"); Jane needs `identity_confidence` | Merge `resolution_json` like `Store.endpoint()`. |

## Sample results (pages=1, fingerprint regional-pipeline-2.5609f30e9d)

Sweed Mood Shine, Spark'd South Loop, Windy City Carpentersville, Revolution: 24 of 24 items (1 page). High Haven Jane: 858/858 complete. Noxx Dutchie: 576 items in 129 s. Be and Stash: 20 items each. Rise Canton generic: 9. Starbuds Summit: 0 (147 s). Excelleaf: 0. AuraLight and Parkway Dispense: 0 (T1).

Merged-context rerun (`sample_ep.py`, same code path as the real fetch, 1 page), all 14 saved endpoints: Dispense AuraLight and Parkway each return 100 items (page limit hit, so not a full count), which confirms T1. Starbuds Summit now reports "redirected to a different source hostname; rediscovery required". Excelleaf fails with `ERR_SOCKS_CONNECTION_FAILED` on dutchie.com, which is an environment proxy error, so its result is inconclusive. Noxx returns 628 items with a total that does not reconcile.

## Not done

Per-store `<id>-<slug>.json` files (the findings are in one combined file instead), in-browser confirmation of Bloc Forest Park and Cloud 9 Schaumburg menus, address confirmation for The Joint Norridge, Jane store ids for Consume/NCC/Happy/Rise, and a clean Excelleaf rerun. No code, branch, or commit changes were made. Recon scripts live in the session scratchpad, not the repo.
