# TerpScout

Next.js/React/TypeScript frontend (`web/`) with FastAPI, SQLite and APScheduler ingestion. The default application uses persisted observations with no sample-menu fallback.

## Run locally (PowerShell)

Use Python 3.13+ and Node 22.12+ or 24+.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
Set-Location web
npm ci
npm run build
Set-Location ..
.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open [API documentation](http://127.0.0.1:8000/docs). Use one worker; a process lease prevents concurrent ingestion workers sharing this database. Scheduled jobs run while the process is running. Port 8000 avoids the Razer Synapse service commonly occupying port 8080.

For web development, run `npm run dev` in `web/` (port 3000). Keep the backend service bound to localhost: this local application has no multi-user authentication.

## Discovery and full-menu ingestion

- The Illinois public dispensary registry is fetched and parsed in full, then filtered using great-circle distance. ZIP origins are approximate centroids. Stores are not an embedded list of the user's examples.
- Known retailer locators are starting points. Unrecognized brands and unsuccessful known-brand crawls enter evidenced public website search, including a bounded address-based fallback for rebrands. Branch pages and observed menu/embed links are inspected before adoption. Search caches are versioned across restarts. Missing addresses are uncertainty, not contradictions. Unspecified license channels default to recreational; explicit medical channels stay separate.
- Blaze, Sweed and Dispense adapters traverse the full observed catalog twice, checking tenant, license context, pagination, source totals, duplicate variants and normalized inventory stability. Treez uses an evidenced browser/Flight catalog traversal, declared detail links to expand capped variant groups, and bounded reconciliation passes. Accepted snapshots seed the entire catalog; subsequent accepted snapshots produce additions, updates, removals and reactivations.
- Failed/partial responses preserve the last accepted catalog. An empty menu or a drop above 30% additionally requires a matching independent observation at least 60 seconds later. Retry a suspicious import after that interval. Challenges, gates, unknown schemas and identity conflicts never become successful empty menus.
- Medical menus require their own evidenced context. A medical-service flag or patient discount does not establish a medical menu. Unspecified channels default to recreational under the user's requested policy. Unknown mass, dose-only labels, unknown stock and conditional prices remain visible but are excluded from comparable rankings. Prices are pre-tax observations.
- Menus become stale after 12 hours, registry retrievals after 72 hours. New failures remain visible beside retained snapshots. Publication and retrieval dates are separate.

Coverage remains incomplete. The selected Minonk 61760 / 100-mile region contains 190 registry locations, with retained accepted menus for 22 stores at the latest check. Earlier ZIP 61358 / 50-mile and GPS / 100-mile measurements describe different regions and must not be mixed with this denominator. Endpoint counts can include alternative sources and license channels. See [the pipeline audit](docs/PIPELINE_AUDIT_AND_HARDENING.md) and [catalog/source recovery evidence](docs/CATALOG_RECONCILIATION.md). This does **not** establish the best deal across every regional dispensary. Illinois is the only implemented registry; jurisdiction boundary intersections have not been calculated.

See [measured acceptance and per-store gaps](docs/LIVE_ACCEPTANCE.md), [original audit](docs/COVERAGE_AUDIT.md), and [implementation ledger](docs/IMPLEMENTATION_PROGRESS.md).

## Data and operation

`terpscout.db` stores the catalog, observations, snapshots, diffs, jobs and settings in additive `live_*` tables. The pre-migration DB is retained as `terpscout.db.before-live.sqlite3`. Original `index.html` remains intact and is available only as a labeled [legacy simulated reference](http://127.0.0.1:8000/reference/legacy-demo). The former backend entrypoint is archived under `docs/reference/`.

`data/evidence/` retains compressed source responses and manifests with URL, status, time, digest and evidence ID. Snapshots retain traversal manifests and source records. Back up the database and evidence together. There is no automatic evidence pruning yet.

Schedules: 2/day (08:00, 20:00), 3/day (07:00, 15:00, 23:00), or 4/day (00:00, 06:00, 12:00, 18:00), America/Chicago, plus daily registry refresh. Settings persist. Interrupted runs are recorded; a new run retries them. Public network destinations and redirects are validated, DNS destinations pinned, requests bounded, and failures retained. Provider restrictions require an authorized feed, retailer cooperation, or an appropriate human browser step.

## Verification

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests
Set-Location web
npm run typecheck
npm test
npm run build
Set-Location ..
.venv/Scripts/python.exe scripts/live_acceptance.py --zip 61358 --radius 50 --output data/live-acceptance-final.json
```

The last command performs real public requests through the running API and persists measured results. Fixture tests do not establish current access to every provider.

## Expanded discovery and scraper fallback (2026-10-17)

The current pipeline searches websites when there is no brand connector, inspects branch identity and embedded menu platforms, and uses a generic structured HTML/visible-card/JavaScript fallback when needed. Generic extraction captures partial observations even without complete pagination proof; inspect these separately in the menu dialog. A featured carousel's total cannot authorize a full snapshot or removals. Explicitly identified all-products lists require reconciled totals and stable independent traversals.

The additional Dispense adapter was validated against the observed public storefront SDK, venue identity, its in-stock `quantityMin=1` filter and `skip`/`limit`/`count` pagination. It discovered its public SDK configuration from linked retailer scripts and completed 1,474 products across two traversals. Mystic Greenz Lincoln was found through general search without a retailer connector and imported 583 variants through Sweed. These targeted app jobs added 2,057 variants. They do not establish exhaustive regional coverage.

In Menu Sync, **Website discovery & browser fallback** controls JavaScript rendering and ordinary age/terms actions. Age confirmation and terms acceptance start unchecked and are persisted only when the user selects them. Node.js, installed Chrome and the Playwright package installed by `npm ci` are required; `TERPSCOUT_BROWSER_CHANNEL` can select another installed Chromium channel. Browser requests pass through the public fetch boundary, with bounded rendering, domain-scoped cookies, durable sessions under `data/browser-sessions/`, and capture manifests. Keep those local session files private when sharing diagnostic artifacts.

Store cards show actual diagnostic messages and provide a targeted retry. The run API also accepts `store_ids` so troubleshooting one location does not rescan an entire region. `GET /api/v1/menus/{id}/observations` exposes the latest partial extraction separately from accepted products. `GET/PATCH /api/v1/settings/browser` controls browser behavior.

`data/expanded-app-acceptance.json` records the targeted application run; `data/dispense-live-acceptance.json` records the independent Dispense probe. `scripts/scan_website_candidates.py --region-id <saved-region-id> --inspect` audits all previously unconfigured brands and saves website leads/platform evidence. Its results are candidate discovery, not inventory imports. See `docs/DISCOVERY_FALLBACK_RESULTS.md` for measured results and remaining limits.
