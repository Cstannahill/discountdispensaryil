"""Transactional live catalog. Network failures never masquerade as snapshots."""
from contextlib import contextmanager, closing
from decimal import Decimal
import json
import math
from pathlib import Path
import sqlite3
import uuid

from .completeness import grade_for, valid_convergence
from .domain import age_hours, digest, distance_miles, instant, normalize_offer, utcnow

REGISTRY_URL = "https://public.data.illinois.gov/t/Public/views/DispensaryMap/Map.csv?:showVizHome=no"


class Store:
    def __init__(self, db_path, evidence_dir):
        self.db_path, self.evidence_dir = Path(db_path), Path(evidence_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        existed = self.db_path.exists()
        with self.connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if existed and version == 0 and tables:
                backup_path = self.db_path.with_name(self.db_path.name + ".before-live.sqlite3")
                if not backup_path.exists():
                    with closing(sqlite3.connect(backup_path)) as backup:
                        conn.backup(backup)
            if version > 1:
                raise RuntimeError("Database schema is newer than this application")
            conn.executescript((Path(__file__).parent / "migrations/001_live_catalog.sql").read_text())
            conn.executescript((Path(__file__).parent / "migrations/002_store_work.sql").read_text())
            conn.executescript((Path(__file__).parent / "migrations/003_attempts_leads.sql").read_text())
            conn.executescript((Path(__file__).parent / "migrations/004_store_platforms.sql").read_text())
            # SQLite has no ADD COLUMN IF NOT EXISTS; the converged-grade timestamp is separate from last_success_at
            # so that grade B never counts as an accepted (grade A) menu.
            if 'last_converged_at' not in {row[1] for row in conn.execute("PRAGMA table_info(live_endpoints)")}:
                conn.execute("ALTER TABLE live_endpoints ADD COLUMN last_converged_at TEXT")
            for key, value in (("data_version", 0), ("frequency_per_day", 4)):
                conn.execute("INSERT OR IGNORE INTO live_settings VALUES (?,?)", (key, json.dumps(value)))

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def setting(self, key, default=None):
        with self.connection() as conn:
            row = conn.execute("SELECT value FROM live_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def record_store_work(self,job_id,report):
        with self.connection() as conn:
            conn.execute('INSERT INTO live_store_work VALUES (?,?,?,?,?,?) ON CONFLICT(job_id,store_id) DO UPDATE SET pipeline_version=excluded.pipeline_version,status=excluded.status,report_json=excluded.report_json,updated_at=excluded.updated_at',
                         (job_id,report['store_id'],report['pipeline_version'],report['status'],json.dumps(report),utcnow()))

    def pipeline_report(self,region_id=None):
        from .runtime import PIPELINE_VERSION
        from .adapters import provider_capabilities
        stores=self.stores_in_region(region_id)
        with self.connection() as conn:
            work={row['store_id']:dict(row) for row in conn.execute('SELECT * FROM live_store_work ORDER BY updated_at,rowid').fetchall()}
        rows=[];counts={key:0 for key in ('not_attempted_current_pipeline','accepted','extraction_incomplete','source_unresolved')}
        for store in stores:
            latest=work.get(store['id']);report=json.loads(latest['report_json']) if latest else None
            current=bool(latest and latest['pipeline_version']==PIPELINE_VERSION)
            stage='not_attempted_current_pipeline' if not current else 'accepted' if report['accepted_snapshots'] else 'extraction_incomplete' if report['menu_targets_attempted'] else 'source_unresolved'
            counts[stage]+=1
            rows.append(dict(store_id=store['id'],store_name=store['name'],stage=stage,
                             accepted_menu_available=any(endpoint['last_success_at'] for endpoint in store['endpoints']),
                             latest_work=report,latest_work_at=latest['updated_at'] if latest else None,
                             providers=[dict(provider=endpoint['provider'],**provider_capabilities(endpoint['provider'])) for endpoint in store['endpoints']]))
        return dict(region=self.region(region_id),pipeline_version=PIPELINE_VERSION,total_stores=len(stores),counts=counts,stores=rows)

    def set_setting(self, key, value):
        with self.connection() as conn:
            conn.execute("INSERT INTO live_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    @staticmethod
    def _bump(conn):
        conn.execute("UPDATE live_settings SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT) WHERE key='data_version'")

    def import_registry(self, rows, evidence_id, published_at=None, now=None):
        now = now or utcnow()
        if not rows:
            raise ValueError("empty_registry_requires_review")
        seen = set()
        for row in rows:
            if not all(row.get(k) for k in ("source_key", "name", "address", "city", "state")):
                raise ValueError("invalid_registry_identity")
            if row["source_key"] in seen:
                raise ValueError("duplicate_registry_identity")
            seen.add(row["source_key"])
        with self.connection() as conn:
            conn.execute("INSERT INTO live_sources VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET evidence_id=excluded.evidence_id,published_at=excluded.published_at,last_success_at=excluded.last_success_at,last_attempt_at=excluded.last_attempt_at,status='ok',row_count=excluded.row_count,error=NULL",
                         ("illinois-map", REGISTRY_URL, evidence_id, published_at, now, now, "ok", len(rows), None,))
            conn.execute("UPDATE live_stores SET source_present=0")
            for row in rows:
                store_id = digest(["illinois-map", row["source_key"]])[:24]
                medical = None if row.get("serves_medical") is None else int(row["serves_medical"])
                raw = json.dumps(row.get("raw", row), ensure_ascii=True)
                conn.execute("INSERT INTO live_source_observations(source_id,source_key,observed_at,evidence_id,raw_json) VALUES (?,?,?,?,?)",
                             ("illinois-map", row["source_key"], now, evidence_id, raw))
                conn.execute("""INSERT INTO live_stores(id,source_key,name,address,city,state,latitude,longitude,serves_medical,source_evidence,observed_at,raw_json)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET
                  name=excluded.name,address=excluded.address,city=excluded.city,state=excluded.state,
                  latitude=excluded.latitude,longitude=excluded.longitude,serves_medical=excluded.serves_medical,
                  source_present=1,source_evidence=excluded.source_evidence,observed_at=excluded.observed_at,raw_json=excluded.raw_json""",
                             (store_id, row["source_key"], row["name"], row["address"], row["city"], row["state"],
                              row.get("latitude"), row.get("longitude"), medical, evidence_id, now, raw))
            self._bump(conn)
        return {"imported": len(rows), "evidence_id": evidence_id}

    def source(self, now=None):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM live_sources WHERE id='illinois-map'").fetchone()
        if not row:
            return {"status": "not_imported", "row_count": 0, "last_success_at": None, "published_at": None, "error": None}
        result = dict(row)
        result["freshness"] = "fresh" if age_hours(result["last_success_at"], now or utcnow()) <= 72 else "stale"
        return result

    def record_source_failure(self, message, now=None):
        now = now or utcnow()
        with self.connection() as conn:
            conn.execute("INSERT INTO live_sources(id,url,last_attempt_at,status,error) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,status=excluded.status,error=excluded.error",
                         ("illinois-map", REGISTRY_URL, now, "failed", str(message)))

    def create_region(self, latitude, longitude, label, radius_miles, precision="coordinates", source_url=None):
        if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("invalid_coordinates")
        if radius_miles not in (1, 5, 25, 50, 100):
            raise ValueError("invalid_radius")
        region = dict(id=digest([latitude, longitude, radius_miles])[:24], latitude=latitude, longitude=longitude,
                      label=str(label)[:300], radius_miles=radius_miles, precision=precision,
                      source_url=source_url, created_at=utcnow())
        with self.connection() as conn:
            conn.execute("INSERT OR IGNORE INTO live_regions VALUES (:id,:latitude,:longitude,:label,:radius_miles,:precision,:source_url,:created_at)", region)
            conn.execute("INSERT INTO live_settings VALUES ('active_region_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(region["id"]),))
        return region

    def region(self, region_id=None):
        region_id = region_id or self.setting("active_region_id")
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM live_regions WHERE id=?", (region_id,)).fetchone()
        if region_id and row is None:
            raise ValueError("unknown_region")
        return dict(row) if row else None

    def regions(self):
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM live_regions ORDER BY created_at DESC").fetchall()
        return {"items": [dict(row) for row in rows], "active_region_id": self.setting("active_region_id")}

    def endpoints(self, store_id=None):
        with self.connection() as conn:
            sql = "SELECT e.*,s.name AS store_name FROM live_endpoints e JOIN live_stores s ON s.id=e.store_id"
            rows = conn.execute(sql + " WHERE e.status!='superseded'" + (" AND store_id=?" if store_id else ""), (store_id,) if store_id else ()).fetchall()
        return [dict(row) for row in rows]

    def retire_discovery_only_endpoints(self):
        """Retain old evidence/history while excluding directory and anchor aliases."""
        from .site_discovery import canonical_menu_url, catalog_entry_url, is_directory_url, menu_document_scope
        changed=0
        with self.connection() as conn:
            for row in conn.execute("SELECT * FROM live_endpoints WHERE status!='superseded'").fetchall():
                canonical=canonical_menu_url(row['url'])
                if row['provider']=='generic':canonical=catalog_entry_url(canonical)
                reason=None
                if is_directory_url(row['url']):
                    reason='Third-party directory retained as discovery evidence; not a retailer menu'
                elif row['provider']=='generic' and not row['last_success_at'] and menu_document_scope(row['url'])=='filtered':
                    reason='Filtered product/promotion page retained as evidence; not an independent full menu'
                elif canonical!=row['url']:
                    other=conn.execute('SELECT id FROM live_endpoints WHERE store_id=? AND url=? AND license_type=?',
                                       (row['store_id'],canonical,row['license_type'])).fetchone()
                    if other:reason='Document-anchor or pagination alias of menu '+other['id']
                    else:
                        conn.execute('UPDATE live_endpoints SET url=? WHERE id=?',(canonical,row['id']))
                        changed+=1
                if reason:
                    conn.execute("UPDATE live_endpoints SET status='superseded',last_error=? WHERE id=?",(reason,row['id']))
                    changed+=1
            if changed:self._bump(conn)
        return changed

    def supersede_endpoint(self, endpoint_id, reason):
        """Retire a menu endpoint without deleting it (history and evidence stay). An endpoint that holds active
        accepted offers is refused: hiding accepted inventory needs a deliberate decision, not a cleanup call."""
        with self.connection() as conn:
            row = conn.execute("SELECT status FROM live_endpoints WHERE id=?", (endpoint_id,)).fetchone()
            if not row:
                raise ValueError("unknown_menu")
            if conn.execute("SELECT 1 FROM live_offers WHERE endpoint_id=? AND status='active' LIMIT 1", (endpoint_id,)).fetchone():
                raise ValueError("endpoint_has_active_offers")
            conn.execute("UPDATE live_endpoints SET status='superseded',last_error=? WHERE id=?", (str(reason), endpoint_id))
            self._bump(conn)

    def endpoint(self, endpoint_id):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM live_endpoints WHERE id=?", (endpoint_id,)).fetchone()
        if not row:
            raise ValueError("unknown_menu")
        result = json.loads(row["resolution_json"])
        result.update(dict(row))
        return result

    def save_endpoint(self, store_id, endpoint):
        from .site_discovery import canonical_menu_url, catalog_entry_url
        endpoint=dict(endpoint,url=(catalog_entry_url if endpoint.get('provider')=='generic' else canonical_menu_url)(endpoint['url']))
        license_type = endpoint.get("license_type")
        if license_type not in ("recreational", "medicinal"):
            raise ValueError("unresolved_license_context")
        identity = digest([store_id, endpoint["url"], license_type])[:24]
        with self.connection() as conn:
            by_url=conn.execute('SELECT id FROM live_endpoints WHERE store_id=? AND url=? AND license_type=?',
                                (store_id,endpoint['url'],license_type)).fetchone()
            if by_url:identity=by_url['id']
            tenant = conn.execute("SELECT id FROM live_endpoints WHERE store_id=? AND provider=? AND provider_store_id=? AND license_type=?",
                                  (store_id,endpoint.get('provider'),endpoint.get('provider_store_id'),license_type)).fetchone() if endpoint.get('provider_store_id') else None
            if tenant:
                identity = tenant['id']
                conn.execute("UPDATE live_endpoints SET url=? WHERE id=?", (endpoint['url'],identity))
            existing = conn.execute("SELECT provider,provider_store_id FROM live_endpoints WHERE id=?", (identity,)).fetchone()
            conn.execute("""INSERT INTO live_endpoints(id,store_id,url,provider,provider_store_id,license_type,resolution_json,status)
              VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(store_id,url,license_type) DO UPDATE SET
              provider=excluded.provider,provider_store_id=excluded.provider_store_id,resolution_json=excluded.resolution_json""",
                         (identity, store_id, endpoint["url"], endpoint.get("provider", "unsupported"),
                          endpoint.get("provider_store_id"), license_type, json.dumps(endpoint, default=str), endpoint.get("status", "pending")))
            if existing and (existing["provider"] != endpoint.get("provider", "unsupported") or existing["provider_store_id"] != endpoint.get("provider_store_id")):
                conn.execute("UPDATE live_endpoints SET status='pending',last_success_at=NULL,last_error='Provider context changed; reimport required',pending_fingerprint=NULL,pending_since=NULL WHERE id=?", (identity,))
                self._bump(conn)
        return self.endpoint(identity)

    def record_resolution(self, store_id, status, message, evidence=None):
        with self.connection() as conn:
            conn.execute("INSERT INTO live_resolutions(store_id,status,message,evidence_json,created_at) VALUES (?,?,?,?,?)",
                         (store_id, status, str(message), json.dumps(evidence or []), utcnow()))

    def stores_in_region(self, region_id=None, license_type=None):
        region = self.region(region_id)
        if region is None:
            return []
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM live_stores").fetchall()
            product_counts = dict(conn.execute("SELECT e.store_id,COUNT(*) FROM live_offers o JOIN live_endpoints e ON e.id=o.endpoint_id WHERE o.status='active' AND e.status!='superseded'" + (" AND e.license_type=?" if license_type else "") + " GROUP BY e.store_id", (license_type,) if license_type else ()).fetchall())
            resolutions = {r["store_id"]: dict(r) for r in conn.execute("SELECT * FROM live_resolutions ORDER BY id").fetchall()}
        endpoints = self.endpoints()
        result = []
        for row in rows:
            store = dict(row)
            if store["latitude"] is None or store["longitude"] is None:
                continue
            distance = distance_miles(region["latitude"], region["longitude"], store["latitude"], store["longitude"])
            if distance > region["radius_miles"]:
                continue
            menus = [e for e in endpoints if e["store_id"] == store["id"] and (not license_type or e["license_type"] == license_type)]
            # Unknown medical context stays visible; a registry 'No' is not invented into a menu.
            if license_type == "medicinal" and store["serves_medical"] == 0 and not menus:
                continue
            store["serves_medical"] = None if store["serves_medical"] is None else bool(store["serves_medical"])
            store.update(distance_miles=round(distance, 3), endpoints=menus,
                         menu_status=menus[0]["status"] if menus else resolutions.get(store["id"], {}).get("status", "unresolved"),
                         resolution=resolutions.get(store["id"]), product_count=product_counts.get(store["id"], 0))
            store.pop("raw_json", None)
            result.append(store)
        return sorted(result, key=lambda s: (s["distance_miles"], s["id"]))

    def record_attempt(self, *, store_id, pipeline_version, stage, tier, status, endpoint_id=None, provider=None, license_type=None,
                       code=None, grade=None, items=None, seconds=None, detail=None, evidence_id=None, job_id=None, now=None):
        """One row per resolution or menu attempt, keyed by pipeline version, so coverage is a measurable series."""
        if grade is None:
            grade = grade_for(status, bool(items))
        with self.connection() as conn:
            conn.execute("INSERT INTO live_attempts(job_id,store_id,endpoint_id,pipeline_version,stage,tier,provider,license_type,status,code,grade,items,seconds,detail,evidence_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (job_id, store_id, endpoint_id, pipeline_version, stage, tier, provider, license_type, status,
                          getattr(code, 'value', code), grade, items, seconds, (str(detail)[:2000] if detail is not None else None), evidence_id, now or utcnow()))

    def attempts(self, store_id=None, pipeline_version=None, limit=200):
        sql, args = "SELECT * FROM live_attempts WHERE 1=1", []
        for column, value in (("store_id", store_id), ("pipeline_version", pipeline_version)):
            if value:
                sql += f" AND {column}=?"
                args.append(value)
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()]

    def record_lead(self, store_id, url, source, reason=None, evidence=None):
        """A website lead (directory page, search result, locator link) is evidence, never a menu endpoint."""
        with self.connection() as conn:
            conn.execute("INSERT INTO live_leads(store_id,url,source,reason,evidence_json,created_at) VALUES (?,?,?,?,?,?) ON CONFLICT(store_id,url) DO UPDATE SET source=excluded.source,reason=excluded.reason,evidence_json=excluded.evidence_json",
                         (store_id, url, source, reason, json.dumps(evidence or [], default=str), utcnow()))

    def leads(self, store_id):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM live_leads WHERE store_id=? ORDER BY id", (store_id,)).fetchall()]

    def record_platforms(self, store_id, rows, source='resolver', now=None):
        """Platforms seen on a store's pages. The latest observation of (store, platform, url) wins."""
        now = now or utcnow()
        with self.connection() as conn:
            for row in rows:
                conn.execute("INSERT INTO live_store_platforms (store_id,platform,url,status,source,evidence_id,observed_at) VALUES (?,?,?,?,?,?,?) "
                             "ON CONFLICT(store_id,platform,url) DO UPDATE SET status=excluded.status,source=excluded.source,evidence_id=excluded.evidence_id,observed_at=excluded.observed_at",
                             (store_id, row['platform'], row.get('url') or '', row.get('status') or 'observed', source, row.get('evidence_id'), now))

    def store_platforms(self, store_id=None):
        with self.connection() as conn:
            sql = "SELECT * FROM live_store_platforms" + (" WHERE store_id=?" if store_id else "") + " ORDER BY store_id,platform,url"
            return [dict(row) for row in conn.execute(sql, (store_id,) if store_id else ()).fetchall()]

    def stage_report(self, region_id=None, pipeline_version=None, now=None):
        """Attribute every regional store to one stage and one failure code. Attempts from other
        pipeline versions are shown but flagged as not current."""
        now = now or utcnow()
        stores = self.stores_in_region(region_id)
        with self.connection() as conn:
            latest = {}
            for row in conn.execute("SELECT * FROM live_attempts ORDER BY id").fetchall():
                latest.setdefault(row["store_id"], []).append(dict(row))
        from .platforms import KNOWN, brand_key
        observed = {}
        for row in self.store_platforms():
            # A platform seen only on a page proven to be another branch does not describe this store.
            if row["status"] != "identity_conflict":observed.setdefault(row["store_id"], set()).add(row["platform"])
        brands = {store["id"]: brand_key(store["name"], store.get("city")) for store in stores}
        brand_sizes = {}
        for brand in brands.values():brand_sizes[brand] = brand_sizes.get(brand, 0) + 1
        by_stage, by_code, by_platform, by_brand, rows = {}, {}, {}, {}, []
        for store in stores:
            endpoints = store["endpoints"]
            accepted = [e for e in endpoints if e["last_success_at"]]
            converged = [e for e in endpoints if e.get("last_converged_at")]
            attempts = latest.get(store["id"], [])
            current = [a for a in attempts if pipeline_version and a["pipeline_version"] == pipeline_version]
            pool = current or attempts
            failing = [a for a in pool if a["status"] not in ("complete", "converged")]
            last = (failing or pool or [None])[-1]
            if accepted:
                stage, code = "accepted", None
            elif converged:
                stage, code = "converged", None
            elif not attempts:
                stage, code = "not_attempted", None
            elif last["stage"] == "resolution" and not endpoints:
                stage, code = "discovery_failed", last["code"]
            else:
                stage, code = "extraction_failed", last["code"]
            by_stage[stage] = by_stage.get(stage, 0) + 1
            if code:
                by_code[code] = by_code.get(code, 0) + 1
            platforms = sorted(observed.get(store["id"], set()) | {e["provider"] for e in endpoints if e["provider"] in KNOWN})
            for platform in platforms:
                counts = by_platform.setdefault(platform, {});counts[stage] = counts.get(stage, 0) + 1
            if brand_sizes[brands[store["id"]]] > 1:
                counts = by_brand.setdefault(brands[store["id"]], {});counts[stage] = counts.get(stage, 0) + 1
            rows.append(dict(store_id=store["id"], store_name=store["name"], stage=stage, code=code,
                             current=bool(current), providers=sorted({e["provider"] for e in endpoints}),
                             platforms=platforms, brand=brands[store["id"]],
                             fresh=any(e["last_success_at"] and age_hours(e["last_success_at"], now) < 12 for e in endpoints),
                             last_attempt_at=last["created_at"] if last else None, detail=last["detail"] if last else None))
        return dict(region=self.region(region_id), pipeline_version=pipeline_version, total_stores=len(stores),
                    by_stage=by_stage, by_code=by_code, by_platform=by_platform, by_brand=by_brand, stores=rows)

    def record_endpoint_failure(self, endpoint_id, status, error, now=None):
        with self.connection() as conn:
            conn.execute("UPDATE live_endpoints SET status=?,last_attempt_at=?,last_error=? WHERE id=?",
                         (status, now or utcnow(), str(error), endpoint_id))

    def apply_snapshot(self, endpoint_id, snapshot, now=None):
        now = now or utcnow()
        normalized, errors, seen = [], list(snapshot.get("errors") or []), set()
        for raw in snapshot.get("items", []):
            try:
                item = normalize_offer(raw)
                key = (item["source_id"], item["variant_id"])
                if key in seen:
                    errors.append("duplicate_variant_identity")
                seen.add(key)
                normalized.append(item)
            except (ValueError, TypeError) as exc:
                errors.append(str(exc))
        expected = snapshot.get("expected_count")
        if expected is not None and expected != len(normalized):
            errors.append("expected_count_mismatch")
        if not snapshot.get("pages"):
            errors.append("missing_traversal_evidence")
        if not snapshot.get("evidence"):
            errors.append("missing_source_evidence")
        status = "complete" if snapshot.get("complete") is True and not errors else "partial"
        convergence = snapshot.get("convergence")
        if (status == "partial" and normalized and not errors and snapshot.get("complete") is not True and
                valid_convergence(convergence) and convergence["observed"] == len(normalized)):
            status = "converged"
        fingerprint = digest(sorted(normalized, key=lambda x: (x["source_id"], x["variant_id"])))
        snapshot_id = uuid.uuid4().hex
        with self.connection() as conn:
            endpoint_row = conn.execute("SELECT * FROM live_endpoints WHERE id=?", (endpoint_id,)).fetchone()
            if not endpoint_row:
                raise ValueError("unknown_menu")
            endpoint = dict(endpoint_row)
            if snapshot.get("provider") != endpoint["provider"]:
                errors.append("snapshot_provider_context_mismatch")
                status = "partial"
            previous = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM live_offers WHERE endpoint_id=?", (endpoint_id,)).fetchall()}
            active_count = sum(row["status"] == "active" for row in previous.values())
            suspicious = not normalized or (active_count > 0 and len(normalized) < active_count * 0.7)
            if status == "complete" and suspicious:
                candidates = conn.execute("SELECT observed_at,manifest_json FROM live_snapshots WHERE endpoint_id=? AND status='suspicious' AND fingerprint=? ORDER BY observed_at", (endpoint_id, fingerprint)).fetchall()
                confirmed = any(60 <= age_hours(r["observed_at"], now)*3600 and
                                (normalized or (snapshot.get("authoritative_zero") is True and json.loads(r["manifest_json"]).get("authoritative_zero") is True)) for r in candidates)
                if not confirmed:
                    status = "suspicious"
                    errors.append("empty_or_large_drop_requires_independent_confirmation")
                    if endpoint.get("pending_fingerprint") != fingerprint:
                        conn.execute("UPDATE live_endpoints SET pending_fingerprint=?,pending_since=? WHERE id=?", (fingerprint, now, endpoint_id))
            if status == "converged":
                converged_active = sum(row["status"] == "active" and json.loads(row["payload_json"]).get("completeness") == "B" for row in previous.values())
                if converged_active and len(normalized) < converged_active * 0.7:
                    status = "partial"
                    errors.append("converged_snapshot_large_drop")
            grade = grade_for(status, bool(normalized))
            manifest = {k: v for k, v in snapshot.items() if k != "items"}
            manifest["grade"] = grade
            if normalized and status not in ('complete', 'converged'):
                relative=Path('partial-observations')/(snapshot_id+'.json')
                path=self.evidence_dir/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(normalized,ensure_ascii=True),encoding='utf-8')
                manifest['partial_items_path']=relative.as_posix()
            conn.execute("INSERT INTO live_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                         (snapshot_id, endpoint_id, now, status, fingerprint, len(snapshot.get("items", [])), expected, json.dumps(manifest, default=str), json.dumps(errors)))
            conn.execute("UPDATE live_endpoints SET status=?,last_attempt_at=?,last_error=? WHERE id=?",
                         (status, now, "; ".join(e if isinstance(e, str) else json.dumps(e) for e in errors) or None, endpoint_id))
            changes = {"added": 0, "updated": 0, "removed": 0}
            if status == "converged":
                conn.execute("UPDATE live_endpoints SET last_converged_at=? WHERE id=?", (now, endpoint_id))
            # Grade B writes offers only where no grade A catalog exists; it never edits an accepted catalog.
            if status == "complete" or (status == "converged" and not endpoint.get("last_success_at")):
                incoming = set()
                for item in normalized:
                    if status == "converged":
                        item["completeness"] = "B"
                    offer_id = digest([endpoint_id, item["source_id"], item["variant_id"]])[:32]
                    incoming.add(offer_id)
                    old = previous.get(offer_id)
                    old_payload = json.loads(old["payload_json"]) if old else None
                    # Raw response ordering and unmodeled metadata must not generate false price/product events.
                    comparable = lambda p: {k: v for k, v in p.items() if k != "raw"}
                    action = "added" if not old or old["status"] == "removed" else "updated" if comparable(old_payload) != comparable(item) else "verified"
                    conn.execute("""INSERT INTO live_offers VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                      payload_json=excluded.payload_json,status='active',last_diff_action=excluded.last_diff_action,
                      last_seen_at=excluded.last_seen_at,snapshot_id=excluded.snapshot_id""",
                                 (offer_id, endpoint_id, item["source_id"], item["variant_id"], json.dumps(item, sort_keys=True), "active", action, now, now, snapshot_id))
                    if action != "verified":
                        changes[action] += 1
                        conn.execute("INSERT INTO live_diffs(endpoint_id,offer_id,action,created_at,snapshot_id,old_json,new_json,details_json) VALUES (?,?,?,?,?,?,?,?)",
                                     (endpoint_id, offer_id, action.upper(), now, snapshot_id, json.dumps(old_payload) if old_payload else None, json.dumps(item), json.dumps({"reactivated": bool(old and old["status"] == "removed")})))
                for offer_id, old in previous.items():
                    if old["status"] == "active" and offer_id not in incoming and (status == "complete" or json.loads(old["payload_json"]).get("completeness") == "B"):
                        conn.execute("UPDATE live_offers SET status='removed',last_diff_action='removed',snapshot_id=? WHERE id=?", (snapshot_id, offer_id))
                        conn.execute("INSERT INTO live_diffs(endpoint_id,offer_id,action,created_at,snapshot_id,old_json,new_json,details_json) VALUES (?,?,?,?,?,?,?,?)",
                                     (endpoint_id, offer_id, "REMOVED", now, snapshot_id, old["payload_json"], None, "{}"))
                        changes["removed"] += 1
                if status == "complete":
                    conn.execute("UPDATE live_endpoints SET snapshot_id=?,last_success_at=?,pending_fingerprint=NULL,pending_since=NULL WHERE id=?", (snapshot_id, now, endpoint_id))
                else:
                    conn.execute("UPDATE live_endpoints SET snapshot_id=? WHERE id=?", (snapshot_id, endpoint_id))
                self._bump(conn)
        return {"id": snapshot_id, "status": status, "grade": grade, "source_count": len(snapshot.get("items", [])), "errors": errors, **changes}

    def _offer_rows(self, region_id, license_type=None, now=None):
        now = now or utcnow()
        stores = {s["id"]: s for s in self.stores_in_region(region_id)}
        with self.connection() as conn:
            rows = conn.execute("SELECT o.*,e.store_id,e.license_type,e.last_success_at,e.last_converged_at,e.url,e.provider FROM live_offers o JOIN live_endpoints e ON e.id=o.endpoint_id WHERE e.status!='superseded'").fetchall()
        result = []
        for row in rows:
            if row["store_id"] not in stores or (license_type and row["license_type"] != license_type):
                continue
            item = json.loads(row["payload_json"])
            store = stores[row["store_id"]]
            item.pop("raw", None)
            item.setdefault("completeness", "A")
            item.update({k: row[k] for k in ("id", "endpoint_id", "store_id", "license_type", "status", "last_diff_action", "last_seen_at", "snapshot_id")})
            verified_at = row["last_converged_at"] if item["completeness"] == "B" else row["last_success_at"]
            item.update(store_name=store["name"], distance_miles=store["distance_miles"],
                        freshness="fresh" if age_hours(verified_at, now) < 12 else "stale")
            item["source_url"] = item.get("source_url") or row["url"]
            result.append(item)
        return result

    def _paginate(self, items, page=1, page_size=50, data_version=None):
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("invalid_pagination")
        version = str(self.setting("data_version", 0))
        if data_version is not None and str(data_version) != version:
            raise ValueError("refresh_required")
        return {"items": items[(page-1)*page_size:page*page_size], "total": len(items), "page": page, "page_size": page_size, "data_version": version}

    def query_offers(self, region_id=None, license_type=None, category=None, q="", include_stale=False, page=1, page_size=50, data_version=None, now=None, strain_type=None, action=None, include_unverified=False):
        version_before = str(self.setting("data_version", 0))
        # Grade B (converged, not reconciled to a source total) is labeled and excluded unless requested.
        items = [r for r in self._offer_rows(region_id, license_type, now) if r["eligible"] and r["status"] == "active" and (include_stale or r["freshness"] == "fresh") and (include_unverified or r["completeness"] == "A")]
        if category and category != "all":
            items = [r for r in items if r["category"] == category]
        if q:
            items = [r for r in items if q.casefold() in " ".join(str(r.get(k) or "") for k in ("name", "brand", "store_name", "subcategory")).casefold()]
        items = self._filter_changes(items, strain_type, action)
        items.sort(key=lambda r: (Decimal(r["effective_price"])/Decimal(r["weight_grams"]), r["distance_miles"], r["id"]))
        result = self._paginate(items, page, page_size, data_version)
        if result["data_version"] != version_before:
            raise ValueError("refresh_required")
        return result

    def query_catalog(self, region_id=None, license_type=None, category=None, q="", include_stale=True,
                      include_removed=False, page=1, page_size=50, data_version=None, now=None, strain_type=None, action=None):
        version_before = str(self.setting("data_version", 0))
        items = [r for r in self._offer_rows(region_id, license_type, now)
                 if (include_removed or r["status"] == "active") and (include_stale or r["freshness"] == "fresh")]
        if category and category != "all":
            items = [r for r in items if r["category"] == category]
        if q:
            items = [r for r in items if q.casefold() in " ".join(str(r.get(k) or "") for k in ("name", "brand", "store_name")).casefold()]
        items = self._filter_changes(items, strain_type, action)
        items.sort(key=lambda r: (r["name"].casefold(), r["id"]))
        result = self._paginate(items, page, page_size, data_version)
        if result["data_version"] != version_before:
            raise ValueError("refresh_required")
        return result

    @staticmethod
    def _filter_changes(items, strain_type, action):
        if strain_type and strain_type.lower() != "all":
            items = [r for r in items if str(r.get("strain_type") or "").casefold() == strain_type.casefold()]
        if action and action.lower() != "all":
            allowed = {"added", "updated"} if action.lower() == "changes" else {action.lower()}
            items = [r for r in items if r["last_diff_action"] in allowed]
        return items

    def benchmark(self, region_id=None, license_type=None, include_stale=False):
        version = str(self.setting('data_version',0))
        items = [r for r in self._offer_rows(region_id,license_type) if r['status']=='active' and r['eligible'] and
                 r['completeness']=='A' and (include_stale or r['freshness']=='fresh')]
        groups = {}
        for offer in items:
            key = (offer['store_id'],offer['category'])
            group = groups.get(key)
            value = Decimal(offer['effective_price'])/Decimal(offer['weight_grams'])
            if group is None:
                groups[key] = dict(store_id=offer['store_id'],store_name=offer['store_name'],category=offer['category'],
                                   price_per_gram=offer['price_per_gram'],best_offer_id=offer['id'],offer_count=1,_value=value)
            else:
                group['offer_count'] += 1
                if value < group['_value']:
                    group.update(price_per_gram=offer['price_per_gram'],best_offer_id=offer['id'],_value=value)
        for group in groups.values():
            group.pop('_value')
        if str(self.setting('data_version',0)) != version:
            raise ValueError('refresh_required')
        return dict(items=sorted(groups.values(),key=lambda r:(r['store_name'],r['category'])),total_offers=len(items),data_version=version)

    def menu_observations(self, endpoint_id, page=1, page_size=25):
        endpoint=self.endpoint(endpoint_id)
        with self.connection() as conn:
            latest=conn.execute('SELECT * FROM live_snapshots WHERE endpoint_id=? ORDER BY observed_at DESC,rowid DESC LIMIT 1',(endpoint_id,)).fetchone()
            name=conn.execute('SELECT name FROM live_stores WHERE id=?',(endpoint['store_id'],)).fetchone()[0]
        items=[]
        if latest:
            manifest=json.loads(latest['manifest_json'])
            relative=manifest.get('partial_items_path')
            if relative:
                path=(self.evidence_dir/relative).resolve()
                if path.is_relative_to(self.evidence_dir.resolve()) and path.exists():
                    for item in json.loads(path.read_text(encoding='utf-8')):
                        item.pop('raw',None)
                        item.update(id=digest([endpoint_id,item['source_id'],item['variant_id']])[:24],endpoint_id=endpoint_id,
                                    store_id=endpoint['store_id'],store_name=name,license_type=endpoint['license_type'],
                                    status='partial_observation',freshness='unverified',last_seen_at=latest['observed_at'])
                        items.append(item)
        result=self._paginate(items,page,page_size)
        result.update(status=latest['status'] if latest else 'not_attempted',errors=json.loads(latest['errors_json']) if latest else [])
        return result

    def menu_products(self, endpoint_id, page=1, page_size=50, include_removed=False, data_version=None, now=None, offer_id=None):
        version_before = str(self.setting("data_version", 0))
        endpoint = self.endpoint(endpoint_id)
        # A menu is inspectable even if the user's current region changed.
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM live_offers WHERE endpoint_id=? ORDER BY id", (endpoint_id,)).fetchall()
            source = conn.execute("SELECT name FROM live_stores WHERE id=?", (endpoint["store_id"],)).fetchone()
            snap = conn.execute("SELECT * FROM live_snapshots WHERE id=?", (endpoint["snapshot_id"],)).fetchone()
        items = []
        for row in rows:
            if offer_id and row["id"] != offer_id:
                continue
            if not include_removed and row["status"] != "active":
                continue
            item = json.loads(row["payload_json"])
            item.pop("raw", None)
            item.setdefault("completeness", "A")
            item.update({k: row[k] for k in ("id", "endpoint_id", "status", "last_seen_at", "last_diff_action", "snapshot_id")})
            verified_at = endpoint.get("last_converged_at") if item["completeness"] == "B" else endpoint["last_success_at"]
            item.update(store_id=endpoint["store_id"], store_name=source[0], license_type=endpoint["license_type"],
                        freshness="fresh" if age_hours(verified_at, now or utcnow()) < 12 else "stale")
            items.append(item)
        result = self._paginate(items, page, page_size, data_version)
        if result["data_version"] != version_before:
            raise ValueError("refresh_required")
        metadata = dict(snap) if snap else None
        if metadata:
            metadata["errors"] = json.loads(metadata.pop("errors_json"))
            metadata["manifest"] = json.loads(metadata.pop("manifest_json"))
        public_menu = {k: endpoint.get(k) for k in ("id", "store_id", "url", "provider", "provider_store_id", "license_type", "status", "last_attempt_at", "last_success_at", "last_error")}
        result.update(menu=public_menu, snapshot=metadata, total_products=len({i["source_id"] for i in items}),
                      total_variants=len(items), eligible_offers=sum(i["eligible"] and i["status"] == "active" for i in items))
        return result

    def coverage(self, region_id=None, license_type=None, now=None):
        now = now or utcnow()
        region = self.region(region_id)
        stores = self.stores_in_region(region_id, license_type)
        endpoints = [dict(e) for s in stores for e in s["endpoints"]]
        for e in endpoints:
            e["freshness"] = "fresh" if age_hours(e["last_success_at"], now) < 12 else "stale" if e["last_success_at"] else "not_imported"
        offers = self._offer_rows(region_id, license_type, now)
        source = self.source(now)
        with self.connection() as conn:
            unresolved_coordinates = conn.execute("SELECT COUNT(*) FROM live_stores WHERE source_present=1 AND (latitude IS NULL OR longitude IS NULL)").fetchone()[0]
        counts = dict(known_stores=len(stores), menu_endpoints=len(endpoints),
                      fresh_menus=sum(e["freshness"] == "fresh" and e['status']=='complete' for e in endpoints),
                      fresh_accepted_snapshots=sum(e['freshness']=='fresh' for e in endpoints),
                      stores_with_accepted_menus=sum(any(e['last_success_at'] for e in store['endpoints']) for store in stores),
                      stores_with_converged_menus=sum(any(e.get('last_converged_at') for e in store['endpoints']) and not any(e['last_success_at'] for e in store['endpoints']) for store in stores),
                      stores_with_fresh_menus=sum(any(e['last_success_at'] and age_hours(e['last_success_at'],now)<12 for e in store['endpoints']) for store in stores),
                      stale_menus=sum(e["freshness"] == "stale" for e in endpoints),
                      failed_menus=sum(e["status"] in ("failed", "partial", "suspicious", "interrupted") for e in endpoints),
                      unsupported_menus=sum(e["status"] == "unsupported" for e in endpoints),
                      unresolved_menus=sum(not s["endpoints"] for s in stores),
                      unresolved_coordinates=unresolved_coordinates,
                      products=len({(r["endpoint_id"], r["source_id"]) for r in offers if r["status"] == "active"}),
                      total_variants=sum(r["status"] == "active" for r in offers),
                      eligible_offers=sum(r["status"] == "active" and r["eligible"] and r["freshness"] == "fresh" for r in offers))
        limitations = ["Registry candidates are not proof that every operating store is known.",
                       "Illinois registry coverage only. Medical service flags require separate menu verification."]
        if source["status"] != "ok" or source.get("freshness") == "stale":
            limitations.append("The registry has not been retrieved successfully within its freshness window.")
        if counts["unresolved_menus"] or counts["failed_menus"] or counts["unsupported_menus"]:
            limitations.append("Menu coverage is incomplete; rankings cover successfully observed comparable offers only.")
        try:
            from .discovery import territory_scope
            territory = territory_scope(region["latitude"], region["longitude"], region["radius_miles"]) if region else {"status": "no_region"}
        except ImportError:
            territory = {"supported_jurisdictions": ["IL"], "status": "boundary_not_verified", "message": "Jurisdiction boundary coverage not verified."}
        territory.setdefault("status", territory.get("boundary_status", "not_evaluated"))
        territory.setdefault("message", " ".join(territory.get("limitations", [])))
        return dict(region=region, source=source, counts=counts, territory=territory, limitations=limitations, endpoints=endpoints)

    def diffs(self, region_id=None, action=None, page=1, page_size=50):
        store_ids = {s["id"] for s in self.stores_in_region(region_id)}
        with self.connection() as conn:
            rows = conn.execute("SELECT d.*,e.store_id,e.license_type,s.name AS store_name FROM live_diffs d JOIN live_endpoints e ON e.id=d.endpoint_id JOIN live_stores s ON s.id=e.store_id ORDER BY d.id DESC").fetchall()
        items = []
        for row in rows:
            if row["store_id"] not in store_ids or (action and action.lower() != "all" and row["action"] != action.upper()):
                continue
            old, new = json.loads(row["old_json"] or "null"), json.loads(row["new_json"] or "null")
            items.append(dict(id=row["id"], action=row["action"], store_name=row["store_name"], license_type=row["license_type"],
                              name=(new or old)["name"], old_price=old.get("effective_price") if old else None,
                              new_price=new.get("effective_price") if new else None, created_at=row["created_at"],
                              details=json.loads(row["details_json"]), snapshot_id=row["snapshot_id"]))
        return self._paginate(items, page, page_size)

    def enqueue(self, payload):
        job = dict(id=uuid.uuid4().hex, status="queued", created_at=utcnow(), started_at=None, finished_at=None,
                   payload_json=json.dumps(payload), results_json="[]", error=None)
        with self.connection() as conn:
            conn.execute("INSERT INTO live_jobs VALUES (:id,:status,:created_at,:started_at,:finished_at,:payload_json,:results_json,:error)", job)
        return self.job(job["id"])

    def update_job(self, job_id, status, results=None, error=None):
        with self.connection() as conn:
            conn.execute("UPDATE live_jobs SET status=?,started_at=CASE WHEN ?='running' THEN COALESCE(started_at,?) ELSE started_at END,finished_at=CASE WHEN ? IN ('succeeded','partial','failed','interrupted') THEN ? ELSE finished_at END,results_json=COALESCE(?,results_json),error=? WHERE id=?",
                         (status, status, utcnow(), status, utcnow(), json.dumps(results) if results is not None else None, error, job_id))

    def job(self, job_id):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM live_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError("unknown_run")
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["results"] = json.loads(result.pop("results_json"))
        # Endpoint identity includes its license. Enrich legacy stage records
        # without changing stored history or substituting current URLs/providers.
        needed=list({event['endpoint_id'] for event in result['results'] if isinstance(event,dict) and event.get('stage')=='menu' and event.get('endpoint_id') and not event.get('license_type')})
        licenses={}
        if needed:
            with self.connection() as conn:
                for start in range(0,len(needed),900):
                    batch=needed[start:start+900]
                    licenses.update((row['id'],row['license_type']) for row in conn.execute('SELECT id,license_type FROM live_endpoints WHERE id IN ('+','.join('?' for _ in batch)+')',batch))
            for event in result['results']:
                if isinstance(event,dict) and event.get('stage')=='menu' and event.get('endpoint_id') in licenses:
                    event.setdefault('license_type',licenses[event['endpoint_id']])
        result["status_url"] = "/api/v1/sync/runs/" + result["id"]
        return result

    def jobs(self, page=1, page_size=25):
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError('invalid_pagination')
        with self.connection() as conn:
            total = conn.execute('SELECT COUNT(*) FROM live_jobs').fetchone()[0]
            ids = [r[0] for r in conn.execute("SELECT id FROM live_jobs ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                                             (page_size,(page-1)*page_size)).fetchall()]
        return dict(items=[self.job(identity) for identity in ids], total=total, page=page, page_size=page_size)

    def recover_jobs(self):
        with self.connection() as conn:
            conn.execute("UPDATE live_jobs SET status='interrupted',finished_at=?,error='Process stopped during run; retry creates a new attempt' WHERE status IN ('queued','running')", (utcnow(),))

    def suggest(self, name, city=None, url=None):
        row = dict(id=uuid.uuid4().hex, name=name, city=city, url=url, status="pending_review", created_at=utcnow())
        with self.connection() as conn:
            conn.execute("INSERT INTO live_suggestions VALUES (:id,:name,:city,:url,:status,:created_at)", row)
        return row
