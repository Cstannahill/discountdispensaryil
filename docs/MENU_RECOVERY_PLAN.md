# Regional menu recovery

Continuation of the user's approved discovery/fallback implementation, covering the whole saved region rather than one retailer. Current baseline: Minonk 61760, 100 miles, 190 registry stores; 22 with accepted menus, 154 with no endpoint, 14 with extraction failures. Machine-readable baseline: `data/regional-failure-audit.json`.

## Shared corrections

1. Separate catalog entry URLs from pagination URLs and retire aliases without deleting observations. Preserve branch/license/filter context; do not merge different stores or license channels.
2. Support stable identity declared on Schema.org Offer.url and retain partial observations without inventing completeness or stock. Stop one missing product identity from hiding successfully extracted records.
3. Parse observed Next.js Flight JSON without executing scripts. Add a Treez/GapCommerce storefront extractor using observed store selection, search totals, product identities and real paginated page reads. A chain-wide/default context cannot be called a matched branch menu without proof.
4. Audit all regional source failures by stage/provider, including known retailers, and replay discovery with current browser permissions and shared fixes. Record store-level outcomes and before/after counts. A website lead is not an inventory import.
5. Verify first seeding, independent traversals, stable totals, pagination/duplicates, branch isolation, conditional prices, failure preservation and restart. Keep actual challenge responses separate from age gates and extraction defects.

## Research

Treez's documented POS Product API requires an integration organization's client ID/API key and an access token; it is an optional authorized integration path, not an anonymous storefront API. Documentation: https://code.treez.io/docs/product-apis and https://code.treez.io/docs/getting-started . Its Treez Ecommerce help center also documents direct store links, which can establish branch context using ordinary observed retailer navigation. Public storefront HTML/Flight observations remain the available ingestion path in this workspace.

Never represent a full regional best deal until the denominator is actually covered. Report partial recovery and remaining failure stages explicitly.


## Current shared-pipeline follow-up

Search provenance/title-anchor selection, semantic menu navigation, navigation-independent branch matching, and per-page generic source/license/branch checks are implemented and regression-tested. See IMPLEMENTATION_PROGRESS.md and data/dynamic-pipeline-live-result.json for the current four-store production-path acceptance results. Native Jane/Dutchie traversal and complete regional acceptance remain open.
