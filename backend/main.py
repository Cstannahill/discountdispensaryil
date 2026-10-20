"""TerpScout local API, durable ingestion worker, and built React application."""
from contextlib import asynccontextmanager
import csv
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import threading
from typing import Literal
from urllib.parse import urlsplit

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .network import PublicFetcher
from .service import SyncService
from .storage import Store

BASE_DIR = Path(__file__).resolve().parent.parent
POLL_SCHEDULES = {2: ["08:00", "20:00"], 3: ["07:00", "15:00", "23:00"], 4: ["00:00", "06:00", "12:00", "18:00"]}
License = Literal["recreational", "medicinal"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocationInput(InputModel):
    query: str = Field(min_length=1, max_length=200)


class RegionInput(InputModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    label: str = Field(min_length=1, max_length=300)
    radius_miles: Literal[1, 5, 25, 50, 100] = 50
    precision: str = Field(default="explicit_coordinates", max_length=100)
    source_url: str | None = Field(default=None, max_length=2000)


class RunInput(InputModel):
    region_id: str | None = None
    discover: bool = True
    resolve_sources: bool = False
    store_ids: list[str] | None = Field(default=None,min_length=1,max_length=300)
    # Sample run: read this many pages per category on every endpoint and write no menu state (see service.import_target).
    sample_pages: int | None = Field(default=None,ge=1,le=5)


class ScheduleInput(InputModel):
    frequency_per_day: Literal[2, 3, 4]


class BrowserInput(InputModel):
    enabled: bool = True
    age_confirmed: bool = False
    terms_accepted: bool = False
    transport: Literal['native','captured_http'] = 'native'
    # Which POSTs a rendered page may make. 'diagnostic_posts' is deliberately not selectable here.
    post_policy: Literal['strict','platform_reads'] = 'platform_reads'
    # Optional honest product token (for example TerpScout/1.0) that replaces Chrome's HeadlessChrome token.
    user_agent_token: str | None = Field(default='TerpScout/1.0', pattern=r'^[A-Za-z0-9._-]{1,40}(?:/[A-Za-z0-9._-]{1,12})?$')
    # Page through "load more" / infinite-scroll menus during menu extraction (not during website discovery).
    scroll_menu: bool = True


class SuggestionInput(InputModel):
    name: str = Field(min_length=1, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)


class RuntimeLease:
    """OS-owned lock is released after a crash; a second local worker fails fast."""
    def __init__(self, path):
        self.file = open(path, "a+b")
        if self.file.tell() == 0:
            self.file.write(b"\0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError("TerpScout already has a worker for this database; use one Uvicorn worker") from exc

    def close(self):
        self.file.close()


def create_app(*, db_path=None, evidence_dir=None, fetcher=None, enable_scheduler=True, execute_jobs=True):
    db_path = Path(db_path or os.environ.get("TERPSCOUT_DB", BASE_DIR / "terpscout.db"))
    evidence_dir = Path(evidence_dir or os.environ.get("TERPSCOUT_EVIDENCE", BASE_DIR / "data/evidence"))
    scheduler = BackgroundScheduler(timezone="America/Chicago")
    schedule_lock = threading.Lock()

    def trigger(frequency):
        return CronTrigger(hour=",".join(slot.split(":")[0] for slot in POLL_SCHEDULES[frequency]), minute=0, timezone="America/Chicago")

    def enqueue_scheduled(discover=False):
        now = datetime.now(timezone.utc).astimezone(scheduler.timezone)
        slot = ("discovery:" if discover else "menus:") + now.strftime("%Y-%m-%dT%H")
        with schedule_lock:
            if app.state.store.setting("last_schedule_slot:" + str(discover)) == slot:
                return
            app.state.store.set_setting("last_schedule_slot:" + str(discover), slot)
            app.state.service.submit(dict(region_id=app.state.store.scheduled_region_id(), discover=discover))

    @asynccontextmanager
    async def lifespan(app):
        if int(os.environ.get("WEB_CONCURRENCY", "1")) > 1:
            raise RuntimeError("TerpScout requires one worker for durable scheduling")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        lease = RuntimeLease(db_path.with_name(db_path.name + ".worker.lock")) if enable_scheduler else None
        try:
            app.state.store = Store(db_path, evidence_dir)
            app.state.store.retire_discovery_only_endpoints()
            app.state.fetcher = fetcher or PublicFetcher(evidence_dir)
            app.state.service = SyncService(app.state.store, app.state.fetcher)
            app.state.store.recover_jobs()
            frequency = app.state.store.setting("frequency_per_day", 4)
            if enable_scheduler:
                scheduler.add_job(enqueue_scheduled, trigger(frequency), id="menu-sync", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=3600)
                scheduler.add_job(enqueue_scheduled, CronTrigger(hour=3, minute=0, timezone="America/Chicago"), kwargs={"discover": True}, id="registry-refresh", max_instances=1, coalesce=True)
                scheduler.start()
            yield
        finally:
            if scheduler.running:
                scheduler.shutdown(wait=True)
            if hasattr(app.state, "service"):
                app.state.service.close()
            if hasattr(app.state, 'fetcher') and hasattr(app.state.fetcher, 'close'):
                app.state.fetcher.close()
            if lease:
                lease.close()

    app = FastAPI(title="TerpScout coverage and menu API", version="3.0.0", lifespan=lifespan,
                  description="Persisted source observations, complete menu imports, and coverage-aware price comparisons.")
    app.state.scheduler = scheduler

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        code = str(exc)
        status = 409 if code == "refresh_required" else 404 if code.startswith("unknown_") else 400
        return JSONResponse(status_code=status, content={"detail": {"code": code, "message": code.replace("_", " ")}})

    @app.middleware("http")
    async def origin_guard(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme not in ("http", "https") or parsed.netloc != request.headers.get("host"):
                    return JSONResponse(status_code=403, content={"detail": {"code": "foreign_origin", "message": "Administration requires the same origin"}})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.get("/api/v1/health")
    def health():
        from .domain import digest
        with app.state.store.connection() as conn:
            latest=conn.execute('SELECT id,status,results_json FROM live_jobs ORDER BY created_at DESC,id DESC LIMIT 1').fetchone()
        return {"status": "ok", "version": "3.0.0", "scheduler_running": scheduler.running,
                "source_status": app.state.store.source()["status"], "single_worker": True,
                "data_revision":digest([app.state.store.setting('data_version',0),dict(latest) if latest else None])}

    @app.post("/api/v1/locations/resolve")
    def resolve(body: LocationInput):
        try:
            return app.state.service.resolve_location(body.query)
        except Exception as exc:
            return JSONResponse(status_code=400, content={"detail": {"code": "location_unresolved", "message": str(exc)}})

    @app.get("/api/v1/regions")
    def regions():
        return app.state.store.regions()

    @app.get('/api/v1/pipeline/report')
    def pipeline_report(region_id: str | None=None):
        return app.state.store.pipeline_report(region_id)

    @app.get('/api/v1/pipeline/stages')
    def pipeline_stages(region_id: str | None=None, all_versions: bool=False):
        from .runtime import PIPELINE_VERSION
        return app.state.store.stage_report(region_id, None if all_versions else PIPELINE_VERSION)

    @app.get('/api/v1/stores/{store_id}/attempts')
    def store_attempts(store_id: str, limit: int=Query(50, ge=1, le=500)):
        return dict(items=app.state.store.attempts(store_id=store_id, limit=limit), leads=app.state.store.leads(store_id))

    @app.post("/api/v1/regions")
    def add_region(body: RegionInput):
        return app.state.store.create_region(**body.model_dump())

    @app.get("/api/v1/coverage")
    def coverage(region_id: str | None = None, license_type: License | None = None):
        return app.state.store.coverage(region_id, license_type)

    @app.get("/api/v1/dispensaries")
    def dispensaries(region_id: str | None = None, license_type: License | None = None,
                     page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), data_version: str | None = None):
        return app.state.store._paginate(app.state.store.stores_in_region(region_id, license_type), page, page_size, data_version)

    @app.get("/api/v1/deals")
    def deals(region_id: str | None = None, license_type: License | None = None, category: str | None = None,
              q: str = Query("", max_length=300), include_stale: bool = False, page: int = Query(1, ge=1),
              page_size: int = Query(50, ge=1, le=200), data_version: str | None = None, strain_type: str | None = None, action: str | None = None,
              include_unverified: bool = False, flower_grade: Literal["whole", "smalls", "shake", "infused", "all"] = "whole", promo: Literal["bogo"] | None = None):
        return app.state.store.query_offers(region_id, license_type, category, q, include_stale, page, page_size, data_version, strain_type=strain_type, action=action, include_unverified=include_unverified, flower_grade=flower_grade, promo=promo)

    @app.get("/api/v1/catalog")
    def catalog(region_id: str | None = None, license_type: License | None = None, category: str | None = None,
                q: str = Query("", max_length=300), include_stale: bool = True, include_removed: bool = False,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), data_version: str | None = None, strain_type: str | None = None, action: str | None = None):
        return app.state.store.query_catalog(region_id, license_type, category, q, include_stale, include_removed, page, page_size, data_version, strain_type=strain_type, action=action)

    @app.get('/api/v1/benchmark')
    def benchmark(region_id: str | None = None, license_type: License | None = None, include_stale: bool = False):
        return app.state.store.benchmark(region_id,license_type,include_stale)

    @app.get("/api/v1/menus/{endpoint_id}/products")
    def menu_products(endpoint_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                      include_removed: bool = False, data_version: str | None = None, offer_id: str | None = None):
        return app.state.store.menu_products(endpoint_id, page, page_size, include_removed, data_version, offer_id=offer_id)

    @app.get('/api/v1/menus/{endpoint_id}/observations')
    def partial_observations(endpoint_id: str, page: int = Query(1,ge=1),page_size: int = Query(25,ge=1,le=200)):
        return app.state.store.menu_observations(endpoint_id,page,page_size)

    @app.get('/api/v1/settings/browser')
    def browser_settings():
        return app.state.store.setting('browser_options',BrowserInput().model_dump())

    @app.patch('/api/v1/settings/browser')
    def update_browser_settings(body: BrowserInput):
        options=body.model_dump()
        app.state.store.set_setting('browser_options',options)
        app.state.service.fetcher.browser_options=options
        return options

    def enqueue(body):
        if body.region_id:
            app.state.store.region(body.region_id)
        if body.store_ids:
            valid={s['id'] for s in app.state.store.stores_in_region(body.region_id)}
            if not set(body.store_ids)<=valid:
                raise ValueError('Requested store does not belong to the selected region')
        payload = app.state.service.prepare_payload(body.model_dump())
        return app.state.service.submit(payload) if execute_jobs else app.state.store.enqueue(payload)

    @app.post("/api/v1/sync/runs", status_code=202)
    def sync(body: RunInput = RunInput()):
        return enqueue(body)

    @app.post("/api/v1/sync/trigger", status_code=202)
    def legacy_sync(frequency_per_day: Literal[2, 3, 4] = 4):
        update_schedule(ScheduleInput(frequency_per_day=frequency_per_day))
        return enqueue(RunInput())

    @app.get("/api/v1/sync/runs")
    def jobs(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
        return app.state.store.jobs(page, page_size)

    @app.get("/api/v1/sync/runs/{job_id}")
    def job(job_id: str):
        return app.state.store.job(job_id)

    def schedule_state():
        frequency = app.state.store.setting("frequency_per_day", 4)
        job = scheduler.get_job("menu-sync") if scheduler.running else None
        return dict(frequency_per_day=frequency, timezone="America/Chicago", slots=POLL_SCHEDULES[frequency],
                    next_run_at=job.next_run_time.astimezone(timezone.utc).isoformat() if job and job.next_run_time else None,
                    scheduler_running=scheduler.running)

    @app.get("/api/v1/settings/schedule")
    def get_schedule():
        return schedule_state()

    @app.patch("/api/v1/settings/schedule")
    def update_schedule(body: ScheduleInput):
        app.state.store.set_setting("frequency_per_day", body.frequency_per_day)
        if scheduler.running:
            scheduler.reschedule_job("menu-sync", trigger=trigger(body.frequency_per_day))
        return schedule_state()

    @app.get("/api/v1/diffs")
    def diffs(region_id: str | None = None, action: str | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
        return app.state.store.diffs(region_id, action, page, page_size)

    @app.post("/api/v1/dispensary-suggestions", status_code=201)
    def suggestion(body: SuggestionInput):
        return app.state.store.suggest(**body.model_dump())

    @app.get("/api/v1/catalog/export")
    def export(region_id: str | None = None, license_type: License | None = None, category: str | None = None,
               q: str = Query("", max_length=300), include_stale: bool = True, include_removed: bool = False):
        rows, page, version = [], 1, None
        while True:
            batch = app.state.store.query_catalog(region_id, license_type, category, q, include_stale,
                                                 include_removed, page, 200, version)
            rows.extend(batch['items'])
            version = batch['data_version']
            if len(rows) >= batch['total']:
                break
            page += 1
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        keys = ["id", "store_name", "license_type", "name", "brand", "category", "source_category", "weight_grams",
                "effective_price", "price_per_gram", "eligible", "status", "freshness", "last_seen_at", "source_url"]
        writer.writerow(keys)
        for row in rows:
            values = [str(row.get(k) if row.get(k) is not None else "") for k in keys]
            writer.writerow(["'" + v if v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values])
        return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="terpscout-catalog.csv"'})

    @app.websocket("/wyvrn/Synapse")
    async def ignore_razer(websocket: WebSocket):
        await websocket.close(code=1000)

    @app.get("/reference/legacy-demo", include_in_schema=False)
    def legacy_reference():
        text = (BASE_DIR / "index.html").read_text(encoding="utf-8")
        banner = '<aside style="position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#78350f;color:white;padding:12px;text-align:center">LEGACY VISUAL REFERENCE — simulated stores, products and sync events. Not live data.</aside>'
        return HTMLResponse(text.replace("</body>", banner + "</body>"))

    build = BASE_DIR / "frontend/dist"
    if (build / "assets").exists():
        app.mount("/assets", StaticFiles(directory=build / "assets"), name="assets")
    if (build / "artwork").exists():
        app.mount("/artwork", StaticFiles(directory=build / "artwork"), name="artwork")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": {"code": "unknown_api", "message": "Unknown API route"}})
        candidate = (build / path).resolve()
        if candidate.is_relative_to(build.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if (build / "index.html").exists():
            return FileResponse(build / "index.html")
        return JSONResponse(status_code=503, content={"detail": {"code": "frontend_not_built", "message": "Run npm ci and npm run build in frontend/, then restart the API."}})

    return app


app = create_app()
