# TerpScout Coverage and React Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the core and superpowers:dispatching-parallel-agents for the independent frontend, source discovery, and provider adapter work. Track checked steps here and evidence in `docs/IMPLEMENTATION_PROGRESS.md`.

**Goal:** Replace simulated data with persistent, evidenced discovery and full menu ingestion, presented through a React frontend that retains the original styling.

**Architecture:** SQLite stores source observations, stores, menu endpoints, snapshots, offers, diffs, settings, and jobs. A single FastAPI worker executes durable sync jobs and exposes coverage-aware queries. React/Vite consumes the same-origin API and preserves the original visual identity.

**Tech Stack:** Python 3.13, FastAPI, httpx, APScheduler, SQLite, unittest; React, TypeScript, Vite, Tailwind, React Query, Chart.js, accessible dialogs, browser checks.

**Spec:** `docs/superpowers/specs/2026-10-17-coverage-and-react-design.md`

## Global Constraints

- Initial acceptance region: ZIP 61358, 50 straight-line miles; all five supplied examples and all regional candidates.
- Never fabricate stores, licenses, products, prices, source observations, or successful imports.
- Full snapshots before diffs; partial/failing/empty unvalidated responses cannot remove the last good catalog.
- Registry retrieval stale after 72 hours; accepted menus stale after 12 hours.
- A drop exceeding 30% or an empty snapshot needs independent confirmation at least one minute later.
- Cadences in America/Chicago: 08/20, 07/15/23, or 00/06/12/18. UTC persisted timestamps.
- Decimal weights/prices; strings in JSON; eligibility and source counts explicit.
- Preserve original page/artwork and every retained functional view; no silent demo fallback.
- Illinois first; disclose unsupported territory, identities, providers and inaccessible menus.
- No Git initialization, deployment, or paid service provisioning. Preserve DB backup and durable raw evidence.

## Review Focus

- Branch aliases/relocations must not merge distinct stores or turn medical discounts into medical menus (Task 1/3).
- A successful page fetch with partial pagination must never authorize removals (Task 2/3).
- New failures must remain visible even when the last good snapshot is fresh (Task 2/5).
- Equal-priced offers and mid-pagination catalog changes must not disappear or change data version silently (Task 4).
- Unknown ZIPs, missing mass, conditional prices, and unsupported jurisdiction must not produce confident false rankings (Task 1/2/4/5).

## Shared interfaces

JSON fields use snake_case. Monetary/weight values use decimal strings, nullable when unknown.

`backend.discovery.parse_registry(raw: bytes) -> list[dict]` produces observations:
`{source_key,name,address,city,state,latitude,longitude,serves_medical,raw}`.
`backend.discovery.resolve_location(query: str, fetch: callable) -> dict` returns
`{label,latitude,longitude,precision,source_url,raw}` or raises a descriptive error.
`backend.network.PublicFetcher(evidence_dir: Path)` exposes `get(url)->FetchResult`
with `url,status_code,body,headers,evidence_id,fetched_at`; rejects unsafe targets.

`backend.adapters.resolve_menu(store: dict, fetcher)->list[dict]` returns evidenced endpoint candidates
`{url,provider,provider_store_id,license_type,resolution_evidence}`. Unknown mappings remain unsupported/unresolved.
`backend.adapters.fetch_menu(endpoint: dict, fetcher)->dict` returns
`{items,complete,expected_count,pages,errors,evidence,authoritative_zero,provider,adapter_version}`.
Each item: `{source_id,variant_id,name,brand,category,source_category,subcategory,strain_type,thc_pct,weight_grams,weight_label,regular_price,effective_price,conditional,available,source_url,raw}`.

`backend.storage.Store(db_path: Path, evidence_dir: Path)` owns migrations, discovery import,
regions, endpoints, snapshot application, coverage queries, offer queries, jobs, and settings.
It does not fetch network responses. `backend.service.SyncService(store,fetcher)` orchestrates fetching and commits.

Frontend/API contracts:
- `GET /api/v1/health` -> `{status,scheduler_running,version}`.
- `POST /api/v1/locations/resolve` body `{query}` -> resolved location above.
- `POST /api/v1/regions` body `{latitude,longitude,label,radius_miles,precision?,source_url?}` -> `{id,...}`.
- `GET /api/v1/regions` -> `{items,active_region_id}`.
- `GET /api/v1/coverage?region_id=&license_type=` -> `{region,source,counts,territory,limitations,endpoints}`;
  counts include `known_stores,menu_endpoints,fresh_menus,stale_menus,failed_menus,unsupported_menus,unresolved_menus,products,eligible_offers`.
- `GET /api/v1/dispensaries?region_id=&license_type=&page=&page_size=` -> `{items,total,page,page_size,data_version}`;
  store fields `{id,name,address,city,state,latitude,longitude,distance_miles,serves_medical,menu_status,product_count,endpoints}`.
- `GET /api/v1/deals?region_id=&license_type=&category=&q=&include_stale=&page=&page_size=&data_version=` -> `{items,total,page,page_size,data_version}`;
  offers `{id,endpoint_id,store_id,store_name,license_type,name,brand,category,source_category,strain_type,thc_pct,weight_grams,weight_label,regular_price,effective_price,price_per_gram,conditional,available,status,last_diff_action,last_seen_at,source_url,freshness,distance_miles}`.
- `GET /api/v1/menus/{id}/products?page=&page_size=&include_removed=&data_version=` -> offers page plus snapshot/count metadata.
- `POST /api/v1/sync/runs` body `{region_id?,discover?:true}` -> HTTP 202 `{id,status,status_url}`.
- `GET /api/v1/sync/runs` -> `{items}`; `GET /api/v1/sync/runs/{id}` -> run with `{id,status,started_at,finished_at,results,error}`.
- `GET/PATCH /api/v1/settings/schedule` -> `{frequency_per_day,timezone,slots,next_run_at}`.
- `GET /api/v1/diffs?region_id=&action=&page=&page_size=` -> `{items,total,page,page_size}`;
  diff `{id,action,store_name,license_type,name,old_price,new_price,created_at,details}`.
- `POST /api/v1/dispensary-suggestions` body `{name,city?,url?}` -> persisted suggestion with explicit pending status.
- `GET /api/v1/catalog/export?region_id=&license_type=` -> safe CSV.
All errors: `{detail:{code,message}}` where application-controlled; HTTP validation errors remain explicit.
No saved region returns empty data and a clear setup state; frontend offers ZIP 61358 as default search input and real discovery action.

## Task 1: Public discovery and geographic resolution

**Files:** Create `backend/discovery.py`, `backend/network.py`, `tests/test_discovery.py`, `tests/test_network.py`.
**Consumes:** Captured registry and source metadata, public network responses.
**Produces:** Shared parser, location resolver and safe evidence-capturing fetcher above.

- [x] Write and run failing tests for duplicate CSV columns, malformed/conflicting rows, all five regional cases, ZIP resolution failure, full-precision radius decisions, and unsafe redirect/DNS targets.
- [x] Implement parsing and geocoding with no guessed fallbacks; persist raw response evidence and validate every redirect/public destination.
- [x] Run unittest tests; capture actual public fetch behavior and failures separately.

## Task 2: Persistent catalog and safe reconciliation

**Files:** Create `backend/storage.py`, `backend/domain.py`, `backend/migrations/001_live_catalog.sql`, `tests/test_storage.py`.
**Consumes:** Source observations and adapter snapshots; no networking.
**Produces:** `Store`, Decimal normalization, transactions, coverage and query methods.

- [x] Write failing tests for initial seeding, changed weight/name/metadata, unchanged observation, partial/empty preservation, confirmed removals, endpoint/license isolation, persistence/restart, reactivation, stale snapshots and new failures.
- [x] Implement non-destructive migration with original DB backup, content provenance, candidate/endpoint identity, regions, jobs/settings, snapshots/offers/diffs and transactions.
- [x] Verify source row accounting and product/category/eligibility counts; run complete storage tests with temporary databases.

## Task 3: Real menu sources and ingestion orchestration

**Files:** Create `backend/adapters.py` (split provider modules if needed), `backend/service.py`, `tests/test_adapters.py`, `tests/test_service.py`; captured fixture manifests under `tests/fixtures/`.
**Consumes:** Shared fetcher/store; real retailer/provider contracts.
**Produces:** Evidenced endpoint resolution, complete paged snapshots, persistent job outcomes.

- [x] Inspect actual providers for the five named stores and other regional candidates; record URLs, IDs, raw schemas, pagination and completion evidence. No invented generic contracts.
- [x] Write/run failing fixture tests including >1,000 items, duplicate/repeated/missing pages, mixed variants, unknown categories, dose-vs-mass and conditional price handling.
- [x] Implement adapters only for observed sources; represent remaining failures explicitly. Run live cross-checks independently of fixtures.
- [x] Implement one durable job path for discovery, endpoint resolution and fetch/reconciliation; serialize endpoints, recover interrupted jobs, handle large/empty revalidation without blocking a minute in a request.
- [x] Test retry/idempotency and failure evidence with real SQLite and external-I/O doubles at the fetch boundary.

## Task 4: Same-origin API and scheduling

**Files:** Modify `backend/main.py`; create `backend/api_models.py`, `tests/test_api.py`, `requirements.txt`.
**Consumes:** Store/SyncService and the contracts above.
**Produces:** Typed API, persistent schedule, production frontend serving, compatibility trigger.

- [x] Write failing API tests for queued 202 sync, actual configuration persistence, Decimal pagination/ranking, freshness filters, CSV safety, invalid data versions and unknown input.
- [x] Implement app factory with injectable DB/evidence/fetcher paths, single-worker lease, backend executor, persistent schedule and startup recovery.
- [x] Serve Vite build assets and retain the original page only as an explicit visual reference. No default demo success.
- [x] Run full backend unittest suite and same-origin production-route probes.

## Task 5: React frontend preserving existing appearance

**Files:** Create `frontend/` React/TS/Vite project and browser/component tests; extract artwork to `frontend/public/` without editing `index.html`.
**Consumes:** Shared API JSON contracts.
**Produces:** All retained views using real data, persistent watchlist, explicit coverage and import state.

- [x] Capture baseline desktop/mobile appearance and extract original image assets.
- [x] Add meaningful tests for API failure/empty/partial states and watchlist persistence before implementing those flows.
- [x] Build shell, filters, coverage summary, deals/benchmark, directory/radar, full paged menu inspector, catalog/export, sync/history, calculator and dialogs.
- [x] Use React Query, accessible dialogs and Chart.js; preserve exact palette and existing styling; no fabricated initial data or mock fallback.
- [x] Run typecheck, tests, production build, and browser checks against the real API; compare desktop/mobile screenshots.

## Task 6: Integration, live acceptance and documentation

**Files:** Update `README.md`, `docs/IMPLEMENTATION_PROGRESS.md`; add reproducible runtime verification scripts and live acceptance report.
**Consumes:** All prior outputs.
**Produces:** Reviewable local runtime and an honest completed/remaining acceptance record.

- [x] Run all tests/build checks and fix reproduced defects with regression tests.
- [x] Run live ZIP 61358/50-mile discovery and inspect all candidates; prove each named case is represented independently of custom seeds.
- [x] Reconcile live products/page totals for supported providers and preserve explicit unresolved/blocked provider states.
- [x] Review concurrency, freshness, stale source behavior, evidence durability, SSRF boundaries and schema/upgrade behavior.
- [x] Document setup/run commands, production frontend serving, source limitations and measured coverage. Do not label incomplete regional ingestion complete.

## Execution decisions

The user's explicit instruction, "Approved. Move on to implementation", authorizes execution after this plan is written; another planning approval request would repeat authorization already given. Independent source parsing, provider research/adapters, and frontend work use the parallel-agent skill; the primary agent implements persistence/orchestration/API and integrates tests. No Git commits/worktrees are possible in this non-Git workspace; retain progress/evidence files instead of initializing Git.

## Acceptance outcome

Implementation steps above were executed; these checkmarks do not assert exhaustive menu coverage. The final live run is partial: 23 registry stores, five complete menus across four stores, 19 unresolved stores. See `docs/LIVE_ACCEPTANCE.md` for per-store access and identity gaps. Provider schema/access acceptance remains unmet for inaccessible sources; jurisdiction boundaries are explicitly unverified. Primary-agent review was used because subagent quota was exhausted. API models remain colocated in `backend/main.py` rather than a separate `api_models.py`; network-free persistence and adapter boundaries are retained.
