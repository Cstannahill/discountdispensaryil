# Expanded discovery: measured results

Measured on 2026-10-17. This supersedes the original small ZIP-radius acceptance run for the expanded pipeline. The current saved region uses GPS 40.9827, -89.0504 and a 100-mile radius, so its denominator differs from the original ZIP 61358 / 50-mile report.

## What changed

Missing brand connectors now trigger public website search, cached with source evidence. The resolver inspects branch pages, menu links, embeds and provider metadata. Missing street-address text alone no longer rejects a plausible business/locality match; an explicitly contradictory provider address still rejects the wrong branch. Unspecified license context defaults to recreational. Explicit medical menus remain separate.

Blaze and Sweed are joined by a full Dispense adapter. Structured HTML, product cards and JavaScript-rendered pages provide a generic fallback, including embedded menu frames. Partial observations are inspectable independently of the last accepted catalog. Only reconciled full-menu traversals can replace a complete snapshot; featured carousels cannot establish completeness.

The browser supports ordinary age confirmation and terms actions through explicit persistent settings in Menu Sync. These remain unchecked in the current installation. Store cards expose the actual diagnostic and a targeted retry.

## Live measurements

| Measurement | Result |
| --- | ---: |
| Registry stores in the saved 100-mile region | 213 |
| Previously unconfigured-brand locations searched and inspected | 143 |
| Locations with website candidates | 70 |
| Locations with no suitable candidate in that search | 73 |
| Stores with at least one accepted complete menu | 22 |
| Fresh complete menu endpoints, including license channels and alternative providers | 31 |
| Failed/partial menu endpoints | 4 |
| Stores without a resolved menu endpoint | 189 |
| Stored source product identities | 28,021 |
| Stored source variants | 30,056 |
| Comparable source offers | 12,104 |

Counts come from `data/regional-expanded-import.json`, job `9b7f49d85a434dc29c0473831e96d349`. Source identities and variants are endpoint-scoped, not a count of unique products across retailers. A store can expose multiple license channels or alternative providers; 31 menus does not mean 31 stores. For example, Parkway Tilton exposes both Sweed and Dispense, with different observed counts. These are separate source observations, not additive proof of its physical inventory.

The final targeted run selected nine stores whose provider addresses matched registry branches. Eight yielded complete snapshots; Bisa Lina Carol Stream remained partial because its advertised totals were inconsistent. Earlier targeted imports added Mystic Greenz Lincoln (583 variants) through general search and AuraLight Aurora (1,474) through Dispense. The final job remains `partial` because the region is incomplete.

Candidate discovery evidence is in `data/regional-platform-discovery.json`. Explicit wrong-branch candidates were rejected during revalidation, including Altius Orland Hills and Windy City Homewood. Search results are leads, not accepted inventories or evidence of operating status.

## Causes and remaining gaps

The missing coverage is not explained by CAPTCHA alone. `data/access-verification.json` records ordinary age gates for Stash/Trinity, challenge responses for some other sites, TLS failures for Cookies, and accessible pages with unresolved extraction for other brands. Noxx can now resolve menu links, but observed HTTP failures still prevent an accepted inventory. These are different failure classes and are shown as such.

The generic fallback cannot guarantee extraction from every storefront. Unknown JavaScript schemas, request methods, pagination contracts, unavailable search results and inaccessible endpoints still leave gaps. A rendered list without full-menu evidence stays partial. The Illinois registry is the only implemented jurisdiction, and a registry entry does not itself verify current operation. The app cannot yet claim the best deal across every dispensary in the region.

A native Windows crash during background HTML parsing was reproduced with the default worker stack. Configuring an 8 MiB Windows worker stack allowed the same probe and all 143 inspections to finish. This is a tested runtime mitigation, not a claim that a specific upstream Python bug has been established.

## Verification

- Backend: 112 tests discovered; 108 passed, four installed-Chrome integration tests skipped by the default gate. Log: `data/backend-final-tests.txt`.
- Installed-Chrome integration: all four browser tests passed separately, covering JavaScript rendering, embedded frames, visible cards, public-network boundaries and explicit age preferences. Log: `data/browser-fallback-tests.txt`.
- Frontend: 11 tests passed; TypeScript checking and production build passed.
- Live production health: API OK, scheduler running; the final targeted import was persisted by the running application.

Original HTML and the pre-migration database backup remain preserved. All counts above describe measured observations, not exhaustive coverage.
