"""One evidenced discovery/import path for both scheduled and manual runs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
import re
import copy
import threading
import time

from .adapters import fetch_menu, resolve_menu, has_menu_contract
from .discovery import parse_registry, resolve_location, REGISTRY_SOURCE_PAGE
from .domain import age_hours, utcnow
from .failures import FailureCode, classify
from .storage import REGISTRY_URL
from .runtime import PIPELINE_VERSION, PipelineInterrupted


NATIVE_PROVIDERS = ('blaze', 'sweed', 'dispense', 'treez', 'joint', 'jane')


def _tier(provider):
    return 'native' if provider in NATIVE_PROVIDERS else 'structured'


def _error_text(errors):
    return '; '.join(e if isinstance(e, str) else str(e.get('message') or e) for e in (errors or []))


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden, self.chunks = 0, []
    def handle_starttag(self,tag,attrs):
        if tag in ('head','script','style'):
            self.hidden += 1
    def handle_endtag(self,tag):
        if tag in ('head','script','style'):
            self.hidden = max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:
            self.chunks.append(data)


class SyncService:
    def __init__(self, store, fetcher, *, resolver=resolve_menu, menu_fetcher=fetch_menu):
        from .runtime import configure_worker_stack
        configure_worker_stack()
        self.store, self._base_fetcher = store, fetcher
        self._contexts=threading.local()
        self.resolver, self.menu_fetcher = resolver, menu_fetcher
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="terpscout-sync")
        self.target_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='terpscout-target')
        self.state_lock=threading.Lock()
        self.job_locks={};self.store_locks={};self.active_submissions={}
        self.stop_requested=threading.Event()
        self.fetcher.stop_requested=self.stop_requested

    def close(self):
        self.stop_requested.set()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.target_executor.shutdown(wait=True,cancel_futures=True)

    @property
    def fetcher(self):
        return getattr(self._contexts,'fetcher',self._base_fetcher)

    def _lock_for(self,locks,key):
        with self.state_lock:return locks.setdefault(key,threading.Lock())

    def prepare_payload(self,payload):
        payload=dict(payload)
        if not payload.get('region_id') and payload.get('scope_mode')!='bootstrap':
            region=self.store.region()
            if region:payload['region_id']=region['id']
            else:payload['scope_mode']='bootstrap'
        payload['pipeline_version']=PIPELINE_VERSION
        return payload

    def _check_stop(self):
        if self.stop_requested.is_set():raise PipelineInterrupted('Worker stopped; retained snapshots are unchanged')

    def submit(self, payload):
        import json
        payload=self.prepare_payload(payload)
        if payload.get('store_ids'):payload['store_ids']=sorted(set(payload['store_ids']))
        payload.setdefault('discover',True);payload.setdefault('resolve_sources',False)
        key=json.dumps(payload,sort_keys=True)
        with self.state_lock:
            existing=self.active_submissions.get(key)
            if existing:
                job=self.store.job(existing)
                if job['status'] in ('queued','running'):return job
            job=self.store.enqueue(payload)
            self.active_submissions[key]=job['id']
            executor=self.target_executor if payload.get('store_ids') else self.executor
            executor.submit(self.run,job['id'])
            return job

    def resolve_location(self, query):
        key = "geocode:" + query.strip().casefold()
        cached = self.store.setting(key)
        if cached and age_hours(cached.get("cached_at"), utcnow()) < 24 * 30:
            return dict(cached, cached=True)
        result = resolve_location(query, self.fetcher.get)
        result["cached_at"] = utcnow()
        self.store.set_setting(key, result)
        return result

    def refresh_registry(self):
        published_at = None
        source_page_evidence = None
        try:
            page = self.fetcher.get(REGISTRY_SOURCE_PAGE)
            source_page_evidence = page.evidence_id
            visible = VisibleText()
            visible.feed(page.body.decode('utf-8',errors='replace'))
            match = re.search(r"Dispensaries updated as of\s*(\d{1,2}/\d{1,2}/\d{4})", ' '.join(visible.chunks),re.I)
            if match:
                published_at = datetime.strptime(match[1], "%m/%d/%Y").date().isoformat()
        except Exception:
            # Page metadata is optional; CSV fetch/parse validity is not.
            pass
        response = self.fetcher.get(REGISTRY_URL)
        if response.status_code != 200:
            raise ValueError(f"Registry returned HTTP {response.status_code}")
        rows = parse_registry(response.body)
        result = self.store.import_registry(rows, response.evidence_id, published_at)
        result["source_page_evidence"] = source_page_evidence
        return result

    def _process_store(self,store,results,force_resolution=False):
        with self._lock_for(self.store_locks,store['id']):
            self._check_stop()
            # A queued store may have been resolved by a targeted job meanwhile.
            store=dict(store,endpoints=self.store.endpoints(store['id']))
            self.fetcher.browser_options=dict(getattr(self.fetcher,'browser_options',{}),target_store={key:store.get(key) for key in ('id','name','address','city','state','latitude','longitude')})
            return self._process_store_unlocked(store,results,force_resolution)

    def _attempt(self,store,**fields):
        # Telemetry must never fail an import.
        try:
            self.store.record_attempt(store_id=store['id'],pipeline_version=PIPELINE_VERSION,job_id=getattr(self._contexts,'job_id',None),**fields)
        except Exception:pass

    def _process_store_unlocked(self,store,results,force_resolution=False):
        started=time.monotonic();attempted=set();accepted=0;had_failure=False;stages=[]
        retained=[self.store.endpoint(endpoint['id']) for endpoint in store['endpoints'] if endpoint.get('last_success_at')]

        def import_target(endpoint,origin):
            nonlocal accepted,had_failure
            self._check_stop()
            key=(endpoint['id'],endpoint['url'],endpoint.get('provider_store_id'),endpoint['license_type'])
            if key in attempted:return True
            attempted.add(key)
            def progress(counts):
                self._check_stop()
                event=dict(stage='menu_progress',store_id=store['id'],store_name=store['name'],endpoint_id=endpoint['id'],provider=endpoint['provider'],license_type=endpoint['license_type'],status='running',**counts)
                index=next((i for i,value in enumerate(results) if value.get('stage')=='menu_progress' and value.get('endpoint_id')==endpoint['id']),None)
                if index is None:results.append(event)
                else:results[index]=event
                job_id=getattr(self._contexts,'job_id',None)
                if job_id:self.store.update_job(job_id,'running',results)
            self.fetcher.progress_callback=progress
            attempt_started=time.monotonic()
            try:
                if endpoint['provider']=='unsupported':raise ValueError('Unsupported menu provider')
                incoming=self.menu_fetcher(endpoint,self.fetcher)
                self._check_stop()
                outcome=self.store.apply_snapshot(endpoint['id'],incoming)
                detail=_error_text(outcome.get('errors'))
                self._attempt(store,stage='menu',tier=_tier(endpoint['provider']),endpoint_id=endpoint['id'],provider=endpoint['provider'],
                              license_type=endpoint['license_type'],status=outcome['status'],grade=outcome.get('grade'),
                              code=None if outcome['status'] in ('complete','converged') else classify(detail),
                              items=outcome.get('source_count'),seconds=round(time.monotonic()-attempt_started,3),detail=detail or None)
                accepted+=outcome['status']=='complete'
                had_failure=had_failure or outcome['status']!='complete'
                results.append(dict(stage='menu',store_id=store['id'],store_name=store['name'],endpoint_id=endpoint['id'],provider=endpoint['provider'],license_type=endpoint['license_type'],url=endpoint['url'],work_origin=origin,**outcome))
                for event in results:
                    if event.get('stage')=='menu_progress' and event.get('endpoint_id')==endpoint['id']:event['status']=outcome['status']
                return outcome['status']=='complete'
            except PipelineInterrupted:raise
            except Exception as exc:
                self._check_stop()
                status='unsupported' if 'unsupported' in str(exc).lower() else 'failed'
                self._attempt(store,stage='menu',tier=_tier(endpoint['provider']),endpoint_id=endpoint['id'],provider=endpoint['provider'],
                              license_type=endpoint['license_type'],status=status,code=classify(str(exc)),items=0,
                              seconds=round(time.monotonic()-attempt_started,3),detail=str(exc),evidence_id=getattr(exc,'evidence_id',None))
                self.store.record_endpoint_failure(endpoint['id'],status,str(exc))
                had_failure=True
                results.append(dict(stage='menu',store_id=store['id'],store_name=store['name'],endpoint_id=endpoint['id'],provider=endpoint['provider'],license_type=endpoint['license_type'],url=endpoint['url'],status=status,error=str(exc),work_origin=origin,evidence_id=getattr(exc,'evidence_id',None)))
                return False
            finally:self.fetcher.progress_callback=None

        # Refresh accepted sources before any slow or unavailable locator/search.
        retained_ok=True
        for endpoint in retained:
            retained_ok=import_target(endpoint,'retained_endpoint') and retained_ok
        if retained:stages.append(dict(stage='retained_refresh',targets=len(retained),complete=retained_ok))

        if not retained or not retained_ok or force_resolution:
            self._check_stop();resolution_start=time.monotonic();failures=[];targets={}
            try:
                # Pages the store verifier cited are crawl seeds; the resolver still has to prove the branch on them.
                leads=[lead['url'] for lead in self.store.leads(store['id']) if lead['source']=='verifier']
                resolved=self.resolver(dict(store,lead_urls=leads) if leads else store,self.fetcher)
                self._check_stop()
                # Census input: which menu platforms this store's pages showed, including rejected (wrong-branch) pages.
                self.store.record_platforms(store['id'],[dict(platform=name,url=found.get('url'),status=found.get('status') or 'observed',
                                                              evidence_id=found['resolution_evidence'].get('evidence_id') if isinstance(found.get('resolution_evidence'),dict) else None)
                                                         for found in resolved for name in found.get('platforms') or []])
                from .site_discovery import is_directory_url, menu_document_scope
                for endpoint in resolved:
                    if endpoint.get('status') in ('blocked','failed','identity_conflict','unresolved') or endpoint.get('license_type') not in ('recreational','medicinal') or not has_menu_contract(endpoint):
                        failure=dict(status=endpoint.get('status') or 'unresolved',error=endpoint.get('reason') or ('Menu provider/store/catalog contract unresolved' if not has_menu_contract(endpoint) else 'Menu license/source context unresolved'),url=endpoint.get('url'),evidence=endpoint.get('resolution_evidence'))
                        failures.append(failure)
                        results.append(dict(stage='resolution',store_id=store['id'],store_name=store['name'],**failure))
                        if failure['url']:self.store.record_lead(store['id'],failure['url'],'resolver',failure['error'],[failure['evidence']])
                        continue
                    # Directory listings and filtered/promotion pages are website leads, not menu endpoints.
                    if is_directory_url(endpoint['url']) or (endpoint.get('provider')=='generic' and menu_document_scope(endpoint['url'])=='filtered'):
                        reason='Third-party directory is a discovery lead, not a retailer menu' if is_directory_url(endpoint['url']) else 'Filtered product/promotion page is not an independent full menu'
                        self.store.record_lead(store['id'],endpoint['url'],'resolver',reason,[endpoint.get('resolution_evidence')])
                        failures.append(dict(status='unresolved',error=reason,url=endpoint['url'],evidence=endpoint.get('resolution_evidence')))
                        continue
                    saved=self.store.save_endpoint(store['id'],endpoint)
                    # A retired endpoint (wrong branch, duplicate) stays retired when discovery finds it again.
                    if saved.get('status')=='superseded':continue
                    targets[saved['id']]=saved
                if not targets and not failures:
                    failures.append(dict(status='unresolved',error='No corroborated public menu endpoint was found'))
                    results.append(dict(stage='resolution',store_id=store['id'],store_name=store['name'],**failures[-1]))
            except PipelineInterrupted:raise
            except Exception as exc:
                self._check_stop()
                failures.append(dict(status='failed',error=str(exc),evidence_id=getattr(exc,'evidence_id',None)))
                results.append(dict(stage='resolution',store_id=store['id'],store_name=store['name'],**failures[-1]))
            first=failures[0] if failures else None
            self._attempt(store,stage='resolution',tier='discovery',status='matched' if targets else (first['status'] if first else 'unresolved'),
                          code=None if targets else classify(first and first.get('error'),resolution_status=first and first.get('status')),
                          items=len(targets),seconds=round(time.monotonic()-resolution_start,3),detail=(first or {}).get('error'),
                          provider=None)
            evidence=dict(pipeline_version=PIPELINE_VERSION,failures=failures,menu_targets=list(targets))
            if targets:
                self.store.record_resolution(store['id'],'matched',f'Resolved {len(targets)} canonical menu target(s)',evidence)
            elif retained:
                self.store.record_resolution(store['id'],'matched','Retained accepted source; rediscovery unresolved',evidence)
            else:
                self.store.record_resolution(store['id'],failures[0]['status'],failures[0]['error'],evidence)
            had_failure=had_failure or bool(failures)
            stages.append(dict(stage='source_resolution',seconds=round(time.monotonic()-resolution_start,3),targets=len(targets),failures=len(failures)))
            for endpoint in targets.values():import_target(endpoint,'source_discovery')
        self._check_stop()
        results.append(dict(stage='store_summary',store_id=store['id'],store_name=store['name'],pipeline_version=PIPELINE_VERSION,
                            status='partial' if had_failure else 'complete',menu_targets_attempted=len(attempted),accepted_snapshots=accepted,
                            seconds=round(time.monotonic()-started,3),stages=stages))
        return had_failure

    def run(self, job_id):
        # Jobs have separate HTTP clients; same-store acquisition/publication is serialized.
        fork=getattr(self._base_fetcher,'fork',None)
        self._contexts.fetcher=fork() if callable(fork) else copy.copy(self._base_fetcher)
        self._contexts.job_id=job_id
        try:return self._run(job_id)
        finally:
            if callable(fork):self._contexts.fetcher.close()
            del self._contexts.fetcher
            del self._contexts.job_id

    def _run(self,job_id):
        with self._lock_for(self.job_locks,job_id):
            job = self.store.job(job_id)
            if job["status"] != "queued":
                return job
            self.store.update_job(job_id, "running")
            results, had_failure = [], False
            payload = self.prepare_payload(job["payload"])
            self.fetcher.browser_options=self.store.setting('browser_options',dict(enabled=True,age_confirmed=False,terms_accepted=False))
            try:
                self._check_stop()
                region = None if payload.get('scope_mode')=='bootstrap' else self.store.region(payload.get("region_id"))
                if region is None:
                    location = self.resolve_location("61358")
                    region = self.store.create_region(location["latitude"], location["longitude"], location["label"], 50,
                                                      location["precision"], location.get("source_url"))
                if payload.get("discover", True):
                    try:
                        imported = self.refresh_registry()
                        results.append(dict(stage="discovery", status="complete", **imported))
                    except Exception as exc:
                        self.store.record_source_failure(str(exc))
                        results.append(dict(stage="discovery", status="failed", error=str(exc), evidence_id=getattr(exc, "evidence_id", None)))
                        had_failure = True
                stores = self.store.stores_in_region(region["id"])
                if payload.get('store_ids'):
                    stores=[s for s in stores if s['id'] in set(payload['store_ids'])]
                if not stores:
                    had_failure = True
                    results.append(dict(stage="coverage", status="unresolved", error="No registry candidates have been resolved in this region"))
                for store in stores:
                    self._check_stop()
                    started=time.monotonic()
                    try:
                        had_failure=self._process_store(store,results,payload.get('resolve_sources',False)) or had_failure
                    except PipelineInterrupted:raise
                    except Exception as exc:
                        self._check_stop();had_failure=True
                        attempts=[r for r in results if r.get('store_id')==store['id'] and r.get('stage')=='menu']
                        results.append(dict(stage='store_summary',store_id=store['id'],store_name=store['name'],pipeline_version=PIPELINE_VERSION,
                                            status='failed',menu_targets_attempted=len(attempts),accepted_snapshots=sum(r.get('status')=='complete' for r in attempts),
                                            seconds=round(time.monotonic()-started,3),stages=[],error=str(exc),evidence_id=getattr(exc,'evidence_id',None)))
                    self.store.record_store_work(job_id,results[-1])
                    self.store.update_job(job_id, "running", results)
                self.store.update_job(job_id, "partial" if had_failure else "succeeded", results)
            except PipelineInterrupted as exc:
                self.store.update_job(job_id,'interrupted',results,str(exc))
            except Exception as exc:
                self.store.update_job(job_id, "failed", results, str(exc))
            return self.store.job(job_id)
