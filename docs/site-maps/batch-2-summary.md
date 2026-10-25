# Batch 2 summary: 38 Minonk-region stores

Scope: batch 2 of 5, sorted by registry store id (positions 39-76 of the 190 stores in the 100-mile Minonk region). Store list: `batch-2-stores.json`. One map per store: `<store_id>-<slug>.json`. Raw probe captures: `probes/`.

Read-only investigation. No scraper code changed, nothing committed, no branch switched, no OpenRouter spend. Pipeline data is the latest `live_resolutions` / `live_attempts` row per store. Sample mode was `scripts/sample_stores.py --pages 1` on the 13 stores that have a saved endpoint.

## Counts (latest pipeline attempt)

| Status | Stores | Count |
|---|---|---:|
| works (complete, grade A) | Mint Willowbrook, Cookies Bloomington, Lyfe Rockford, Aroma Hill Hoffman, NuEra Aurora, Phili Bourbonnais | 6 |
| partial or suspicious menu | Trinity Peoria x2, Ivy Hall Montgomery, Supergood Des Plaines, Seven Point Danville, Cloud9 Champaign, Bisa Lina Carol Stream | 7 |
| gated by age/terms | Curaleaf Worth, New Lenox, Westmont | 3 |
| fetch failed | Cookies Chicago | 1 |
| lead only (site found, branch or menu not proven) | Vertical Cary, Verilife Arlington Heights, Schaumburg, North Aurora, Rise Joliet, Sunnyside Naperville, NuEra Chicago, Revolution Normal | 8 |
| no lead | Terrace Milan, Zen Leaf Pilsen, Pekin, Goodies Streamwood, Hi Five Crestwood, Nature's Treatment Galesburg, Windy City Homewood, Nature's Care Rolling Meadows, Key Mt. Zion, BLOC Kedzie, Parkway Forest Park, Lakeshore Romeoville, Grasshopper South Loop | 13 |

Registry flags: Parkway Forest Park appears permanently closed. Hi Five (now Strictly Cannabis) and Revolution (now Bloom Wellness, RISE) were rebranded.

## Sample mode (13 stores with endpoints)

- Products returned: Trinity x2, Ivy Hall, Mint, Supergood, Lyfe, Aroma Hill, Phili, Seven Point, Cloud9, Bisa Lina. Most are one page only (24 items for Sweed), so they are not comparable to totals.
- Zero items, sampler false negatives: NuEra Aurora (the Jane-safe wrapper `sample_ep.py` returns 1153 items, complete) and Cookies Bloomington (baseline complete at 483; the sampler's endpoint choice is unverified).
- Mint, Supergood, Cloud9 and Seven Point went through the generic path in sample mode, which is not the route the saved endpoints use.

## Root causes, most common first

1. **Fallback website search is dead (13 no-lead stores).** Every no-lead store except Parkway has a findable site; Google finds it from the registry name and city. DuckDuckGo returns a bot challenge and Bing collapses the quoted-address query. Fix: query by name + city + "dispensary" and verify the branch from the page's own address, or repair the search provider.

2. **Chain sites are found but never resolved to a branch (8 lead-only stores).** Verilife x3 (the lead is the chain homepage, which has no IL store URLs), NuEra Chicago (lead is a Kentucky subdomain), Sunnyside (lead is a directory page), Rise, Vertical (only menu is the Saint Joseph branch), Revolution (wrong-branch Schaumburg leads). Fix: one connector per chain that reads the state or store list and picks the branch by address. Verilife and NuEra each cover 2-3 stores here.

3. **Totals are not reconciled on platforms that are supported (7 partial).** Dutchie count mismatch (Cloud9, Supergood), Treez with UNKNOWN count (Trinity x2), Sweed count mismatch (Bisa Lina, 3408 items) and suspicious drop (Ivy Hall), and a first-party GraphQL storefront treated as generic (Seven Point). Fix: per-platform declared-total reading and paging, as in `docs/DUTCHIE_DIAGNOSIS.md`. Add Seven Point's proxy as a recognized platform.

4. **Branch proof fails on shared endpoints.** Trinity's two Peoria rows share one storefront URL and endpoint. Supergood attaches embeds from other chain branches. Fix: take the endpoint from the store's own page, scoped by address, and do not attach one endpoint to two registry rows.

5. **Age/terms gate not passed (3 stores, one chain).** Curaleaf Worth, New Lenox and Westmont. A scripted probe could not tick the consent boxes or pass the over-21 button. Fix: one Curaleaf gate handler that clicks the consent labels and state picker, then confirms the redirect. Test in the browser before adding it.

6. **Sampler false negatives.** `scripts/sample_stores.py` passes the raw endpoint row and skips the `resolution_json` merge, so the Jane provider rejects the platform point as a different location (NuEra Aurora: 0 items vs 1153 correct). It also takes the most recent endpoint, which may be the wrong one (Cookies Bloomington). Fix: make the sampler use the sync's endpoint loader. Do not change the Jane provider.

7. **Registry drift.** Parkway Forest Park is closed. Hi Five and Revolution were rebranded, and their registry names do not match what search finds. Fix: brand alias table and a closed-status check in the registry refresh.

8. **Chain directory domain fails.** Cookies Chicago's lead is `cookies.co/stores/`, which gives ConnectError. The brand site `cookieschicago.co` loads. Fix: map chain directory domains to brand domains.

## Already working (no fix needed)

Mint Willowbrook (Dutchie, 657), Cookies Bloomington (JointCommerce, 483), Lyfe Rockford (Sweed, 973), Aroma Hill Hoffman (Sweed, 814 per channel), NuEra Aurora (Jane, 1159), Phili Bourbonnais (Jane, 799 rec / 780 med). Lyfe's resolution row is stale ("no locator connector") even though its endpoint is complete.

## Caveats

- Platform calls for several sites are from signatures or a single probe, not confirmed. Each map lists its `unverified` items.
- Search used Google and Bing in the browser pane because the WebSearch tool was unavailable (model error), not for lead verification.
- Curaleaf was probed on Worth only; New Lenox and Westmont share the flow but were not separately probed.
- Probe captures are in `probes/` (no screenshots committed).
