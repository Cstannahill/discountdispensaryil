# Measured live acceptance

Checked at 2026-10-17T08:21:23.778084+00:00. Region: Rutland, IL 61358, 50 straight-line miles from an approximate ZIP centroid.

Overall run: **partial**. 23 registry locations; 5 fresh accepted license-specific menus across four physical stores; 19 stores without resolved imported menus.

Retained 4,542 source product identities (counted separately per menu/license), 4,838 variants, and 1,403 eligible comparable offers. A product appearing in both medical and recreational contexts counts in both menus. These are observed counts, not an estimate of total regional inventory.

## Per-location results

| Registry location | Miles | Menu result | Most recent relevant evidence/outcome |
|---|---:|---|---|
| Snap Canna - Pontiac | 20.9 | recreational: complete | 668 accepted variants |
| Stash - Peru | 26.2 | blocked | Retailer requires age/terms confirmation; menu not fetched |
| Verilife Ottawa | 27.2 | unresolved | Retailer locator did not expose a corroborated branch/menu link |
| Bloom Wellness - Normal | 31.3 | failed | Public endpoint returned HTTP 403 |
| Revolution Dispensary - Normal | 31.4 | unresolved | Menu source address conflicts with registry; License-specific menu context is not corroborated |
| Beyond/Hello  Normal | 32.4 | unresolved | Retailer locator did not expose a corroborated branch/menu link |
| Cookies - Peoria Heights | 32.9 | failed | Public fetch failed: ConnectError |
| High Haven Dispensary | 33.1 | failed | Public endpoint returned HTTP 403 |
| Nuera East Peoria | 33.4 | unresolved | Menu identity has no corroborated matching address |
| Beyond Hello  Bloomington Keaton Place | 33.7 | unresolved | Retailer locator did not expose a corroborated branch/menu link |
| Trinity Compassionate Care Center | 33.7 | blocked | Retailer requires age/terms confirmation; menu not fetched |
| Aroma Hill - Peoria | 34.1 | identity_conflict | Retailer branch address conflicts with registry |
| Cookies - Bloomington | 34.3 | failed | Public fetch failed: ConnectError |
| Ivy Hall - Peoria | 35.4 | recreational: complete; medicinal: complete | 1054 accepted variants; 1054 accepted variants |
| Cloud 9 - East Peoria | 35.6 | unresolved | Retailer locator did not expose a corroborated branch/menu link |
| Beyond/Hello - Peoria | 35.7 | unresolved | Retailer locator did not expose a corroborated branch/menu link |
| Noxx - East Peoria | 36.0 | unresolved | Menu identity has no corroborated matching address |
| Trinity Compassionate Care Centers | 36.5 | blocked | Retailer requires age/terms confirmation; menu not fetched |
| Curaleaf  Morris | 41.6 | blocked | Retailer requires age/terms confirmation; menu not fetched |
| NuEra Pekin | 42.4 | unresolved | Menu identity has no corroborated matching address |
| Tree Haus Morris | 42.6 | recreational: complete | 1035 accepted variants |
| Pekin Local Dispensary & Supply | 42.8 | unresolved | Menu identity has no corroborated matching address |
| Tree Haus - Diamond | 46.6 | recreational: complete | 1027 accepted variants |

## Provider validation and remaining work

- Snap Canna Pontiac: observed Blaze tenant and pickup JSON:API pages, 668 records across seven pages, repeated independently. No product seeds.
- Sweed: public server-rendered query cache and observed full-menu links. Every page verifies store identity, license, requested page, advertised total, variant identity and stable second traversal. Ivy Hall has distinct verified medical/recreational contexts. Tree Haus listing totals can include a repeated parent product with distinct variants; source parents and variants are counted separately.
- Blank source names are retained with stable source identity and raw evidence, quarantined from rankings. Missing identity, missing pages and changed traversal boundaries reject the snapshot. Unknown categories/mass and conditional prices remain inspectable.
- Stash Peru: public storefront has an age/terms gate; independently examined GapCommerce product search returned HTTP 403. No validated complete traversal.
- Cloud 9 East Peoria: registry location is represented. A normal browser executes the site but reaches an age/qualified-patient assertion plus terms/cookie agreement. No assertion was made for the user. Public locator resolution does not yet establish a full branch menu.
- Beyond/Hello: Normal, Bloomington Keaton Place and Peoria are distinct registry records. Current public locator responses did not corroborate usable branch/menu endpoints. Retailer-versus-registry relocations/rebrands remain unresolved; do not automatically merge an old address or infer a medical menu from a patient discount.
- Jane and GapCommerce requests examined during research returned access challenges/403. A browser can sometimes complete ordinary JavaScript or provide a legitimate human interaction; reliable unattended ingestion still needs an accessible public contract or authorized feed. No CAPTCHA or gate bypass is implemented.
- Aroma Hill and some other branches have retailer/registry address conflicts. Preserve those conflicts instead of binding an unrelated default branch. Several sites require stronger branch-link discovery or a browser-backed connector even when they are publicly viewable.
- Registry completeness and current operating status are unverified. Illinois is the only registry connector; jurisdiction intersections are not computed. Nineteen unresolved stores mean regional best-deal coverage remains unmet.

## Evidence and reproduction

- `data/live-acceptance-final.json`: exact API region, job outcomes, coverage and stores.
- `data/evidence/`: compressed public responses and capture manifests; snapshots in SQLite retain page/count/error manifests.
- `tests/fixtures/provider_*`: observed fixtures and independent provider probe results; `data/probes/ivy/` contains the separate Ivy traversal probe.
- Run `scripts/live_acceptance.py` against the running API to refresh this evidence, then `scripts/write_acceptance_summary.py` to regenerate this document.
- Tests and browser evidence are summarized in `docs/IMPLEMENTATION_PROGRESS.md`. Passing tests do not imply that inaccessible providers are covered.
