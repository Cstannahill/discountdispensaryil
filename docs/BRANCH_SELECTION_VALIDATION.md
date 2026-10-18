# Branch selection and progress corrections

2026-10-17. This is a correction to the shared acquisition/targeting pipeline, not a claim that all regional menus now import.

## Reproduced causes

- The browser received license preferences but no target store. It could not choose Pontiac instead of Elk Grove or Peru instead of Orland Hills before identity validation.
- A location selector can be a header popover rather than an ARIA dialog. Stash uses `Open store selector and purchase method`, store radio controls, and `SHOP PICKUP`.
- Desktop/mobile copies of the selector can both satisfy ordinary visibility checks. The worker must select the unique on-screen control rather than treat two copies as ambiguity or click an off-screen copy.
- The 200-request rendering budget was exhausted by the real storefront. A later successful Stash observation used 450 attempted requests. The budget is now 600; time and byte bounds remain. Diagnostics record requests, the limit, exhaustion, examined choices and selection transitions.
- Discovery returned city-named promotional product groups ahead of the actual `/shop` catalog. Generic product-detail and filtered/group/category pages could become separate full-menu endpoints. They are now excluded from that role; an observed catalog entry takes priority. Historic unsuccessful filtered targets and known directory targets are superseded without deleting their evidence.
- Progress rendered discovery, menu and summary events as indistinguishable store cards. One store now has one summary card, channel/status counts and expandable individual stage details. Legacy menu events recover the license from their immutable endpoint identity, without replacing historical URLs/providers. Mojibake in frontend source text is corrected.

## Current behavior

The requested store's ID, name, street address, city and state flow from the runner through discovery and browser acquisition. Browser sessions are separated by website, store and license. Selection prefers a unique matching street address; a unique locality choice can be used where the chooser provides no address. Same-city ambiguity and explicit conflicting street addresses are left unresolved rather than selecting the first option. Dialogs, native selects and the observed header popover pattern are supported, including embedded frames and location/type prompt ordering.

After selection the resolver inspects the resulting document again. A click alone does not establish branch identity. Generic sources that depended on browser-selected branch context retain that acquisition requirement for both catalog verification passes, so a later static request cannot reset to the chain's default branch.

## Live evidence

- `data/stash-location-live-probe.txt`: actual worker HTTP 200, selection of `Stash Peru - Peru`, visible `1320 38th St, Peru, IL 61354`, identity `matched`; rendered capture `2eadaf369b65b613a8dd325d1d3b6a7285f01359b95ac10562a18be7f9080899`. This verifies location selection, not full inventory.
- `data/branch-context-live-result.json`: earlier four-store cohort, Snap accepted; Stash, Verilife Ottawa and Revolution Normal unresolved before the final popover correction. Do not call that cohort recovered.
- `data/branch-context-stash-final-result.json`: subsequent Stash attempt reached products but exposed promotional-target inflation; `/shop` yielded 20 observed records and no accepted complete snapshot. That result prompted the targeting correction. Promotion observations are not independent menus or a whole-store inventory.
- `data/branch-context-stash-targeting-job.json`: final one-store validation job after targeting correction. Its result is saved separately when finished.

## Verification and limits

Backend suite: 156 tests, with 13 installed-Chrome tests skipped in the default invocation (`data/branch-context-tests.txt`). The separate Chrome/browser boundary suite passes 22 tests (`data/branch-browser-tests.txt`), including same-city address selection, ambiguous/absent/wrong branches, popovers with off-screen duplicates, prompt ordering, embedded frames, and JavaScript needed after more than 200 resources. Frontend: 18 tests, TypeScript and production build pass (`frontend/output/branch-tests.txt`, `frontend/output/branch-build.txt`). The live UI shows one Ivy Hall card with separate medicinal/recreational menus (`frontend/output/branch-progress.png`).

Follow-up: the browser catalog session and Treez Flight traversal/normalization are now implemented and tested. Live catalog reconciliation is still being evaluated; implementation alone is not full-menu acceptance. See [catalog traversal and source recovery](CATALOG_RECONCILIATION.md) for newer verification, the reproduced price-tie pagination overlap, address-based rebrand recovery and live search limitations.

Jane/Dutchie extraction gaps, genuine request/session failures, other custom selector patterns, branch-source authority and final regional acceptance remain open. These changes must not be reported as resolving all 70-plus dispensaries or proving regional best-deal coverage.
