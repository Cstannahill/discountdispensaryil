# CLAUDE.md

TerpScout: finds the best cannabis deals ($/g) near a location by ingesting full dispensary menus. FastAPI + SQLite + APScheduler backend, React/TS/Vite frontend, Node/Playwright (installed Chrome) browser fallback. Illinois registry is the only candidate source today. See `PROJECT_STATUS_REPORT.md` for current measured coverage (22 of 190 regional stores have an accepted menu) and `docs/` for history; do not trust older counts in other docs.

## Commands (Windows, PowerShell; always use the project venv)

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000   # single worker only
cd frontend; npm run dev          # :5173, proxies /api to :8000
.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:TERPSCOUT_BROWSER_TEST='1'; .venv\Scripts\python.exe -m unittest discover -s tests -p test_browser_render.py -v   # opt-in real Chrome
cd frontend; npm test; npm run build
.venv\Scripts\python.exe scripts/probe_browser_cohort.py --target <store_id> <url> --output data/x.json   # acquisition probe, never accepts catalogs
.venv\Scripts\python.exe scripts/sample_stores.py <store_id ...> --pages 1     # fast troubleshooting sample, writes nothing
.venv\Scripts\python.exe scripts/platform_census.py --region <region_id> [--write]   # platform census from evidence (live_store_platforms)
.venv\Scripts\python.exe scripts/verify_stores.py [<store_id ...>] [--eligible --region <id> --limit 10] [--model <id>|all ...] [--write] | --compare   # LLM store verifier (needs OPENROUTER_API_KEY in .env)
```

Normal work goes through `POST /api/v1/sync/runs` (`region_id`, `store_ids`, `discover`, `resolve_sources`). Python 3.13+, Node 22.12+.

## Pipeline map (`backend/`)

registry (`discovery.py`) -> candidate stores (`storage.py`) -> website/menu discovery (`locators.py` chain connectors, `site_discovery.py` search + branch identity + platform links) -> `adapters.resolve_menu` -> endpoint (provider + store id + license) -> `adapters.fetch_menu` dispatches to `providers/{sweed,dispense,treez,generic}.py` or Blaze inline -> `storage.apply_snapshot` (accept / partial / suspicious) -> offers.

- `service.py`: orchestration. Retained accepted endpoints refresh first, independent of rediscovery. Per-store locks, bounded regional + targeted executors.
- `network.py` `PublicFetcher`: all HTTP (SSRF-safe, DNS pinned, evidence recorded, POST only to an exact allowlist `_READ_ONLY_SEARCH_POSTS`). `browser_render.py` + `browser_worker.cjs` + `browser_proxy.py` + `browser_locations.cjs`: Chrome through the same boundary; age/terms/license/branch controls.
- `runtime.py`: `PIPELINE_VERSION` source fingerprint; results from older fingerprints are not current-engine results.
- Provider support: native full-menu = blaze, sweed, dispense, treez, joint, jane (jane needs `provider_store_id`). dutchie, cresco, and unknown sites go through the generic structured/DOM path, which rarely satisfies the completeness gate.
- Census: `backend/platforms.py` signatures; the resolver tags pages with platforms, `live_store_platforms` stores them, and `/api/v1/pipeline/stages` reports `by_platform` / `by_brand`. Fix by platform or chain, not by store (docs/PLATFORM_FIRST_PLAN.md).
- Verifier: `verifier.py` researches questionable stores (NO_LEAD / LEAD_UNVERIFIED / BRANCH_MISMATCH) with a budgeted LLM search/read loop. Claims survive only with a quote found in a page it fetched; verdicts go to `live_store_verifications` and the stage report's `verification`; cited URLs become `live_leads`. It never edits the registry or endpoints. Web search (verifier and website discovery) is OpenRouter's web plugin (Exa, 5 results); search results are leads, never citable pages. All LLM spend goes to `data/evidence/llm-spend.jsonl`; verifier and production discovery spend share `VERIFIER_MAX_USD_PER_DAY`, while sample and triage searches (purpose `sample`) are ledgered but not counted. Provider pluggable (`PROVIDERS`), OpenRouter default, config in `.env` (see `.env.example`).
- Evidence: `data/evidence/` (gz bodies + manifests) is part of the audit trail; back up with `terpscout.db`. `index.html` and `terpscout.db.before-live.sqlite3` are preserved originals; never edit.

## Invariants (do not weaken)

- Incomplete/failed imports never replace an accepted catalog or authorize removals. Empty menu or >30% drop needs independent confirmation 60s+ later.
- Completeness is graded (`backend/completeness.py`). A = reconciled total + two stable traversals (only A authorizes removals of A offers, sets `last_success_at`). B = `converged` (visible counter or churn-tolerant passes): labeled, own `last_converged_at`, excluded from `/deals` unless `include_unverified`. C = partial, inspect-only. Never relabel a lower grade as A.
- Failures are `FailureCode` values (`backend/failures.py`); every menu/resolution attempt is recorded in `live_attempts`. Website leads go in `live_leads`, never `live_endpoints`.
- A challenge/403/blank page is a failure, never an empty menu. Do not solve CAPTCHAs or evade bot detection; report the block.
- Unknown mass/stock/dose-only labels are never invented. Prices are pre-tax; conditional prices are not comparable. Omitted license context = recreational; medical needs its own evidence.
- Branch identity must be proven (address or corroborated locality) and rechecked through extraction. Search results and directories are leads, not menus.
- Freshness: menus 12h, registry 72h.
- Prefer shared, provider-level fixes over per-store exceptions. Capture regression fixtures under `tests/fixtures/`.

## Conventions

- Existing backend style is dense: short names, minimal whitespace around `=`, single-line `if x:stmt`, 4-space indent. Match the surrounding file; do not reformat.
- Tests are `unittest` in `tests/` with recorded fixtures; add a failing test first for each shared defect.
- Do not edit backend source while a long sync is running under the uvicorn reload watcher; it interrupts jobs.
- App binds to localhost only (no auth). Keep browser session files in `data/browser-sessions/` private.
- Secrets (LLM keys, etc.) go in `.env` (git-ignored); never in code, evidence, or docs.

## Active plans

- `docs/EXTRACTION_FAILURE_AUDIT.md`: measured causes of menu failures.
- `docs/ROBUST_EXTRACTION_PLAN.md`: tiered crawl/parse redesign, hardened fallback, and the LLM browsing-agent third fallback (OpenRouter default; Gemini/local via `.env`).
- `docs/PHASE3_PHILI_EXPERIMENT.md`: why Phili rendered blank (HeadlessChrome token + obsolete POST allowlist), the opt-in `post_policy` / `user_agent_token` / `scroll_menu` browser settings, and the network-first extractor (`backend/network_extract.py`).
- `docs/PLATFORM_FIRST_PLAN.md`: measured platform/chain census of failures and the plan to fix by platform, chain, and directory instead of per store.
- `docs/DUTCHIE_DIAGNOSIS.md`: why Dutchie menus failed (not a challenge), the paged-query replay, whole-menu total rules, and the platform-declared branch address check.
