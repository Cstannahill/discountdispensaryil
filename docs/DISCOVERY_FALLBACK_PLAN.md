# Discovery and scraper expansion

The user requested implementation of broad discovery, provider detection and menu scraping fallbacks, and explicitly changed the license rule: unspecified is recreational. This extends the approved coverage design; implementation proceeds under that request without another approval loop.

Pipeline: registry candidate -> known locator or public search -> inspect branch evidence -> observed menu/embed links -> provider detection -> full provider traversal -> structured HTML fallback -> ordinary browser rendering when needed. Unknown brands must enter search rather than stop. A missing address is weaker evidence, not a conflict; a contradictory branch identity remains visible. Noxx's Peoria/East Peoria naming must resolve using its actual branch address and structured data.

Search results are leads, not invented store facts. Retain query/result evidence, score business name, locality and branch address, and reject clearly unrelated results. Cache public searches to avoid repeating them for every scheduled run. Preserve errors for each attempted stage. Prioritize branch links over marketing/category links; follow observed links and embeds, never guessed store IDs.

Generic extraction supports JSON-LD Product/Offer/ItemList records and semantic product markup, pagination and stable source identities. It keeps unknown mass and categories. Two independent stable traversals and independently advertised totals are required for a generic snapshot to authorize removals. Partial extracted observations and their evidence must remain inspectable without erasing a previous full menu. Render JavaScript pages with a bounded browser when static data is absent; browser resource requests must use the validated public fetch boundary.

Age checks should have a user-controlled ordinary-browser flow with durable session state. No forged age assertion or silent terms acceptance. Provider challenges must be distinguished from age gates, missing extractors, connection errors and identity uncertainty. No generic scraper can guarantee completeness for every changing site; tests and live reconciliation establish the actual supported surface.

Verification: regressions for unknown brands/search failure, search redirect decoding, wrong-city results, Noxx branch identity, omitted licenses, medical overrides, provider embeds, generic pagination/duplicates/variants/partial preservation, browser boundary, and live representative multi-brand discovery. Recheck coverage from the running app and report remaining gaps by stage.
