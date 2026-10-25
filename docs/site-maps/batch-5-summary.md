# Batch 5 site-map summary (38 stores)

Investigation only: no repo code changed, nothing committed. Per-store maps: `docs/site-maps/<store_id>-<slug>.json` (38 files). Raw evidence: `docs/site-maps/raw/batch-5/` (Chrome survey JSON, seeded and sampler outputs, DB snapshot, and the scripts used). Store list: `batch-5-stores.json`.

Methods:
- Chrome survey (Playwright, installed Chrome) of every store's menu URL: platform, age gate, branch selection, API calls, visible counts.
- `scripts/sample_stores.py --pages 1` on the 15 stores with saved endpoints. Its results are unreliable for Jane, Blaze and Dispense (see cause 4).
- Scratch seeded runs: current `resolve_menu` + `fetch_menu`, seeded with the hand-found URL, web search patched out, DB read-only. Run 1 used one page; run 2 read native providers in full.
- The paid triage re-discovery was denied by the permission layer, so discovery was not re-run from scratch.

## Results (latest evidence per store)

- **17 complete menus** read by the current code: Terrace Moline (Jane), Verilife Ottawa (Jane), Hatch Addison rec and med (Jane 2081 / 501), Verilife Rosemont (Jane), Cannabist Chicago (Jane 1346), Earthmed Rosemont (Jane), Bud & Rita's Avondale and Loop (Joint), Cookies Peoria Heights (Joint), Dispensary 33 West Loop, Windy City Posen, Green Rose Chicago, Green Rose Harwood Heights, Aroma Hill Belvidere, Ivy Hall Streamwood, Mystic Greenz Lincoln (Sweed), Sociale Park Ridge (Blaze).
- **2 readable, graded B by design:** Zen Leaf Lombard (1183) and Naperville (1173), read from the Verano whole-branch catalog.
- **19 not complete:** see causes below.
- **Stale accepted rows:** every accepted row in this batch is older than 12 h (latest 2026-10-19 02:59).

## Causes (primary cause per store)

1. **Discovery: website search is dead; the store never reaches its reader (9 stores read complete once a URL is seeded).** Terrace, Verilife Ottawa, Bud & Rita's Avondale and Loop, Dispensary 33, Windy City, Green Rose Chicago, Cookies (fetch error), Hatch rec (never stored). Fix: replace the fallback search; add chain connectors (Bud & Rita's, Green Rose, Windy City, Mission, Green Releaf, Cannect, Cloud 9); seed registry websites.
2. **Dutchie totals do not reconcile (7 stores):** Ascend Moca Logan (498), Cannect (420), Mission Calumet (462), Mission Illinois (446), Cloud 9 East Peoria (~566), Ascend Springfield (495), and Starbuds (559, where the Joint business on the same site is never probed). Largest single cohort. Fix: paged replay per `docs/DUTCHIE_DIAGNOSIS.md`.
3. **GapCommerce / Treez reader gaps (4 stores):** Be. Oak Forest (classified generic, 20 of ~483 visible), Market 96 (20 of 1086; browser budget), Stash Peru (20 of 1881; browser budget), Jane & Bud's Elgin (24 then page cap; full read not run). The catalog sits in the `search-*.gapcommerceapi.com/product/search` API (from/size paging). Fix: one shared GapCommerce reader.
4. **Sampler false negatives (confirmed):** `sample_stores.py` passes the raw endpoint row without `resolution_json`, as the coordinator flagged. Hatch med: sampler 0 items, `sample_ep.py` 1612 complete. Sociale: sampler 0, seeded full 591. Ascend Springfield: sampler 0, `sample_ep.py` 100 (page-capped). Fix: merge `resolution_json` as `Store.endpoint()` does.
5. **Access gates and blockers (4 stores):** Curaleaf Melrose and Justice (age gate plus a "I agree to Terms" checkbox; the button alone does not pass), Cloud 9 Oswego (retailer site behind a Cloudflare challenge, HTTP 403; not bypassed, though its Dutchie storefront loads in Chrome), Green Releaf Bourbonnais (category pages redirect to a login wall; Villa Park does not).
6. **No reader (2 stores):** Green Releaf Villa Park (own API, 245 prices on page), Nature's Treatment Milan (menu is on a Leafly listing, 1085 products shown; the old menu host `menu-milan.ntillinois.com` does not resolve).
7. **Branch identity (1 store):** River Bluff. "RiverBluff" vs "River Bluff" fails the name match, and the footer street address is outside `identity_text`, so the Jane embed is never read.
8. **Sweed reads stop at 24 with no message (1 store):** Ivy Hall Crystal Lake, both channels. The same reader completes Ivy Streamwood (1104). Cause not isolated.

## Stored-endpoint problems (wrong branch, wrong provider, or missing)

- Zen Leaf Lombard (11 generic rows for other branches) and Naperville (rows for St. Charles and Warrenville): Verano endpoints 540 and 541 are not stored.
- Cannabist Chicago: a stored row points to store 2221, which is Cannabist Villa Park. Jane rec 1346 is not stored.
- Verilife Rosemont: accepted generic B-grade (1035 offers) while the Jane store 7309 on the same page reads complete (1089).
- Hatch: Jane rec 2081 is not stored; the stored rec row is generic (78 items).
- Ivy Streamwood: rec and med both hold 1110 offers. Possibly one catalog counted twice; verify.
- Earthmed: seeding the `menu.earthmed.com` wrapper gives a generic 92-item partial (a regression), because the resolver does not treat that wrapper as Jane store 2740.

## Corrections to the earlier draft of this file

- Ascend Logan and Springfield do **not** redirect `ascendcannabis.com/menu/*` to letsascend; the Dispense menus still render there. Letsascend is a separate Dutchie storefront.
- Starbuds is not only Joint: the site serves a Joint search and the resolver picks a Dutchie embed.
- The "page limit" failures were mostly one-page runs. Full runs completed Bud & Rita's, Hatch, Cannabist, Sociale, Mystic, Ivy Streamwood, Windy City, Dispensary 33, Green Rose, Cookies and Aroma Hill.

## Not verified / caveats

- Be. Oak Forest and Mission Illinois branch identity not proven in this run.
- Cloud 9 East Peoria: the kiosk page shows "COMING SOON"; confirm it is live before treating it as a menu.
- Ascend Logan: one survey click hit a Google sign-in button by mistake (regex since tightened); the Dutchie GraphQL data it captured is still valid.
- Curaleaf: Terms checkbox not ticked by me; the owner's saved `terms_accepted` setting governs the real run.

## Proposed fixes, by reach

1. Discovery (cause 1): seed websites and add chain connectors. Biggest lever: 9 stores complete once a URL is known.
2. Sampler (cause 4): merge `resolution_json` in `sample_stores.py`. Otherwise Jane, Blaze and Dispense results are misleading.
3. Stored endpoints: supersede other-branch rows; prefer Jane or Verano over the generic Rise/Zen Leaf pages; keep Dutchie/Joint/Sweed per license.
4. Dutchie reconciliation (cause 2): 7 stores.
5. GapCommerce reader (cause 3): 4 stores, shared with Jane & Bud's.
6. Gate handler for Curaleaf checkboxes (cause 5); Cloud 9 Oswego: probe the Dutchie storefront by slug when the retailer site is challenged; do not solve the challenge.
7. Refresh the 9 stale accepted rows.
