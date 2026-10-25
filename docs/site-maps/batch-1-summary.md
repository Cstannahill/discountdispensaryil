# Batch 1 site maps: summary (38 stores)

Investigation only: no code, DB, branch or server changes.

- Store list: `batch-1-stores.json`
- Per-store maps: `<store_id>-<slug>.json`, one per store (38 files, same naming as the other batches)
- Raw pipeline output: `raw/batch-1-triage.json` (current engine, 25 unaccepted stores), `raw/batch-1-sample-accepted*.json` (sample_stores.py, 13 accepted stores)

Browser mapping used real Chrome plus curl. Age-confirm buttons were clicked. Terms checkboxes were not ticked, and no challenge was solved.

## Counts

- 13 of 38 already have an accepted menu. These are not failures.
- 25 have none. Current-engine triage: 15 WORKS (a target was found and read products), 10 NO_TARGET.
- By hand, the menu location and platform were confirmed for 23 of the 25. Village Bucktown has a Dutchie kiosk that I did not probe. The Dispensary Champaign has no menu I could find.
- Platforms across all 38: Dutchie 11, Jane 9, Sweed 6, Cresco/Sunnyside 4, Joint 2, Blaze 2, Treez 1, Verano 1.

## Main finding

Most of the 25 fail before extraction, in discovery and branch identity. Stored state shows "no corroborated branch lead", wrong-branch or wrong-state leads, or directory pages saved as endpoints. Where a native reader was reached, it mostly worked. Zen Leaf West Loop reads through the existing Verano reader in 5 s (1122 items), and only discovery is missing.

## Root causes (a store can appear under two)

**A. Discovery fails although Bing finds the site in its first results (13 stores).** Market 96, Ascend River North, Ascend Tinley Park, Village Bucktown, Zen Leaf West Loop, Viola CHI, Dutchess North Riverside, Mint Forest Park, Maribis Springfield, Maribis Chicago, Sunnyside Schaumburg, Sunnyside Rockford, Bloc Berwyn. The pipeline's search returns unrelated pages for registry names (Ascend Moca returned terravaulthq, toppotshops and an Illinois license PDF). The spend cap also skips some searches.

**B. Chain location lists exist but no connector uses them (about 12 stores).** One fetch of each chain's own list would resolve the branches:
- Ascend: letsascend.com/stores/<slug>, Dutchie white-label. River North is 216 W Ohio St (verified on page). Ascend River North also has a Dispense storefront at ascendcannabis.com (venue 4d9085a00443f996), a second route.
- Maribis: maribisllc.com/stores/maribis-<slug>, Dutchie white-label. The /locations/ index returns 403 to plain HTTP.
- Sunnyside: api.crescolabs.com/p/stores?ids=... returns all Sunnyside branches with addresses in one call (verified).
- Zen Leaf, Revolution, Dutchess, Bloc, Snap Canna, Mint (brand site embeds a Dutchie store).

**C. Dutchie stored as generic or partial (Bloc, Starbuds).** Bloc Berwyn is stored with 292 products against a declared total of 477. Direct replay returns 477 across 5 pages, but only with the `apollo-require-preflight` header (otherwise HTTP 400). Starbuds Burbank is stored as a generic endpoint that fails on its age-gate locator (3 s timeout). The Dutchie path reads it (triage 606). Dispensary ids are in the per-store files.

**D. Cresco/Sunnyside has no native reader (4 stores).** Products come from api.crescolabs.com/p/inventory/op/fifo-inventory per category with a usage_type=recreational total. Cresco store ids: Champaign 86, Rockford 67, Danville 494, Schaumburg 559. Branch is chosen by cookies, not URL. The generic path gives 113 to 118 items and never reconciles. Sunnyside Rockford has a lookyweed.com directory page saved as an endpoint, which should never happen.

**E. Wrong-branch or wrong-state leads become endpoints.**
- nuEra Chicago Southland: 11 generic rows for other nuEra branches (ids 1461 to 1520, 3050, 3057, 7414). Correct Jane ids: rec 6878, med 7415.
- nuEra East Peoria: lead set includes ky.nueracannabis.com (Kentucky). Correct Jane store 1517.
- nuEra DeKalb: stored lead is a 404 (/med-deals/). Correct Jane store 5932.
- Rise Colorado Ave: stored endpoints are Rise Rock Creek (1627 Rock Creek Blvd). The correct store is Jane 1340 (2903 Colorado Ave), which triage reads at 2138 items.
- Revolution Mount Prospect: lead is the Schaumburg branch. The real menu is shop.revcanna.com/mount-prospect/recreational.

**F. Age gate blocks the generic path: Curaleaf Morris.** The menu is Sweed behind curaleaf.com/age-gate. The "I'm over 21" button stays disabled until a state select and two checkboxes are ticked. The generic path times out at 30 s. Fixing this needs a decision that the pipeline may tick the terms checkbox.

**G. Single-store issues.**
- Snap Canna Elk Grove: same Blaze tenant as the accepted Pontiac store. The chain root shows 840 E Higgins Rd next to the /menu/elkgrove link, which would corroborate identity. Hypothesis, not confirmed.
- Market 96 Oswego: the old /shop/oswego page says it is not accepting orders. The live menu is /dispensary/market-96-oswego on a GapCommerce/Treez search.
- Viola CHI: now The Joint Dispensary (Broadview) on Dutchie (dispensaryId 6568ed1d36e2d10009d2dd18). The registry name is stale, and the guessed URL returns 404.
- Village Bucktown: only a Dutchie kiosk (dutchie.com/kiosks/village-bucktown). Not probed. The brand's own pages do not list it.
- The Dispensary Champaign: the Leafly website is thedispensarychampaign.com, which redirects to thedispensaryfulton.com (Fulton and East Dubuque only). The registry record may be stale.
- Maribis Springfield: a ConnectError on one lead. The stores page loads in a browser and over HTTP.
- Ascend River North and Tinley: a license PDF in the search results raised a UTF-8 decode error, which became the stored reason. Non-HTML results should be skipped before decoding.

## Sampler notes

sample_stores.py gives false zeros in two ways, so its 0-item results are not evidence of failure:
- NuEra Pekin (Jane 3050): the sampler does not merge identity_confidence, so the Jane reader rejects the menu as a different location. Run through the corrected wrapper, it reads 1524 items, complete.
- Terrabis Dixon and Plainfield (Joint), Snap Canna Pontiac (Blaze): 0 items at the sample page cap, even at 3 pages. All three have accepted full-sync catalogs (808, 712 and 638 offers). Why the cap yields 0 for these readers is not investigated.

## Accepted stores (13)

Native readers throughout. Ivy Hall Glendale Heights and Peoria show identity_conflict on rediscovery, but the site addresses match the registry, so it is a false conflict. Ivy Hall Glendale also has identical rec and med counts (847 and 847), which may mean the medical endpoint reuses the same catalog. Not verified.

## Suggested order

1. Chain location-list connectors (B): Ascend, Maribis, Sunnyside, Zen Leaf, Revolution, Dutchess, Bloc, Snap Canna. Largest single lever.
2. Cresco reader with store id and chain list (D): 4 stores.
3. Dutchie native reader with Apollo headers and totalCount reconciliation (C, plus Ascend, Mint, Dutchess, Viola).
4. Lead hygiene (E): state filter, skip non-HTML, use the Jane store id linked from the chain page, supersede wrong-branch and directory endpoints.
5. Sampler fix: merge identity context the way Store.endpoint() does, and stop treating page caps as zero-item results.

## Not verified

Curaleaf terms-gate decision. Whether The Dispensary Champaign is still operating. Village Bucktown kiosk. Snap Canna Elk Grove identity. Ivy Hall med and rec counts. Why sample caps return 0 items for Joint and Blaze.
