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
from .platforms import brand_key
from .storage import REGISTRY_URL
from .runtime import PIPELINE_VERSION, PipelineInterrupted


NATIVE_PROVIDERS = ('blaze', 'sweed', 'dispense', 'treez', 'gapcommerce', 'joint', 'jane', 'verano')
# Sample runs stop a store's discovery crawl after this many seconds; full runs never budget discovery.
SAMPLE_DISCOVERY_SECONDS = 120
# Sample runs process this many stores at once; full runs stay sequential.
SAMPLE_WORKERS = 4


def discovery_source(endpoint, leads):
    """How this endpoint's website was found: a saved web-search query, an operator or verifier lead, a chain list, a hosted-store id, or a plain crawl."""
    from urllib.parse import urlsplit
    host=lambda url:(urlsplit(url or '').hostname or '').removeprefix('www.')
    evidence=[x for x in endpoint.get('locator_evidence') or [] if isinstance(x,dict)]
    if any('query' in x for x in evidence):return 'llm_web_search'
    same=lambda lead:(lead.get('url') or '').rstrip('/')==endpoint['url'].rstrip('/') or host(lead.get('url'))==host(endpoint['url'])
    if any(lead.get('source')=='operator' and same(lead) for lead in leads):return 'operator'
    if any(lead.get('source')=='verifier' and same(lead) for lead in leads):return 'llm_verifier_lead'
    if evidence:return 'chain_locator'
    details=endpoint.get('resolution_evidence')
    method=(details.get('method') if isinstance(details,dict) else '') or ''
    if any(word in method for word in ('Rise-hosted','Jane hosted','Jane partner','Jane storefront')):return 'provider_id'
    return 'crawl'


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


# A store the verifier checked this recently is not searched again: rebrands and closures move slowly.
VERIFY_HOURS = 24 * 7


def llm_verifier(database):
    """The store verifier for full syncs: web-search research with its daily spend cap. None when no LLM key is configured."""
    from . import verifier
    config = verifier.load_env()
    llm = verifier.llm_from_config(config)
    if llm is None:
        return None
    limits = verifier.budgets(config)
    def check(store, fetcher):
        since = verifier.day_ago()
        folder = fetcher.evidence_dir
        spent = max(database.verifier_spend_since(since), verifier.spend_since(folder, since, 'verifier')) + verifier.spend_since(folder, since, 'discovery')
        return verifier.verify_store(store, fetcher, llm, limits, spent_today=spent)
    return check


class SyncService:
    def __init__(self, store, fetcher, *, resolver=resolve_menu, menu_fetcher=fetch_menu, verifier=None):
        from .runtime import configure_worker_stack
        configure_worker_stack()
        self.store, self._base_fetcher = store, fetcher
        self._contexts=threading.local()
        self.resolver, self.menu_fetcher, self.verify = resolver, menu_fetcher, verifier
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

    def _record_rebrand(self,store,endpoint):
        """A verified branch page that names a different business at the registry street records that name and its page."""
        from .site_discovery import rebrand_name
        details=endpoint.get('resolution_evidence')
        name=rebrand_name(store,details) if isinstance(details,dict) else None
        if name:
            # Telemetry-like bookkeeping: a failed write must never fail the menu import.
            page=details.get('evidence') or {}
            try:self.store.record_identity(store['id'],'rebrand',name,page.get('url') or endpoint['url'],page.get('evidence_id'),'resolver')
            except Exception:pass

    def _verify_store(self,store,results):
        """Ask the store verifier for a store no run has accepted: a new name or a closure is recorded with its source, and
        its cited pages become leads. Returns the store with its current names and status. Full syncs only."""
        if self.verify is None or self.store.verified_within(store['id'],VERIFY_HOURS):return store
        try:
            record=self.verify(store,self.fetcher)
        except PipelineInterrupted:raise
        except Exception as exc:
            results.append(dict(stage='verification',store_id=store['id'],store_name=store['name'],status='failed',error=str(exc)))
            return store
        if record is None:return store
        self.store.record_verification(record)
        results.append(dict(stage='verification',store_id=store['id'],store_name=store['name'],status=record.get('status'),verdict=record.get('verdict'),detail=record.get('detail')))
        return dict(store,**self.store.identity(store['id']))

    def _process_store_unlocked(self,store,results,force_resolution=False):
        started=time.monotonic();attempted=set();accepted=0;had_failure=False;stages=[];read_ok=set()
        if store.get('operating_status')=='closed':
            # Verified closed by evidence: nothing is resolved or read, and it is recorded rather than counted as a failure.
            results.append(dict(stage='store_summary',store_id=store['id'],store_name=store['name'],pipeline_version=PIPELINE_VERSION,status='closed',
                                menu_targets_attempted=0,accepted_snapshots=0,seconds=round(time.monotonic()-started,3),stages=[]))
            return False
        retained=[self.store.endpoint(endpoint['id']) for endpoint in store['endpoints'] if endpoint.get('last_success_at')]
        # Saved menus no run has accepted yet (pending, partial, converged) are read on every run, as accepted ones are.
        saved=[endpoint for endpoint in (self.store.endpoint(found['id']) for found in store['endpoints'] if not found.get('last_success_at')) if has_menu_contract(endpoint)]
        sample=getattr(self._contexts,'sample_pages',None)
        if sample and not retained:
            # A sample reads any saved endpoint that is a menu contract before it pays for discovery; discovery runs only if none reads.
            retained,saved=saved,[]

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
            sample_pages=getattr(self._contexts,'sample_pages',None)
            try:
                if endpoint['provider']=='unsupported':raise ValueError('Unsupported menu provider')
                if sample_pages:
                    # Sample: read the first pages of every category, record what came back, and write nothing about the menu.
                    incoming=self.menu_fetcher(dict(endpoint,max_pages=sample_pages),self.fetcher)
                    self._check_stop()
                    for event in results:
                        if event.get('stage')=='menu_progress' and event.get('endpoint_id')==endpoint['id']:event['status']='sampled'
                    results.append(dict(stage='menu_sample',store_id=store['id'],store_name=store['name'],endpoint_id=endpoint['id'],provider=endpoint['provider'],license_type=endpoint['license_type'],url=endpoint['url'],work_origin=origin,
                                        items=len(incoming.get('items') or []),pages=len(incoming.get('pages') or []),complete=incoming.get('complete'),
                                        declared_total=incoming.get('expected_count') or incoming.get('source_count'),errors=[e.get('code') for e in incoming.get('errors') or []][:3]))
                    return bool(incoming.get('items'))
                incoming=self.menu_fetcher(endpoint,self.fetcher)
                self._check_stop()
                outcome=self.store.apply_snapshot(endpoint['id'],incoming)
                detail=_error_text(outcome.get('errors'))
                self._attempt(store,stage='menu',tier=_tier(endpoint['provider']),endpoint_id=endpoint['id'],provider=endpoint['provider'],
                              license_type=endpoint['license_type'],status=outcome['status'],grade=outcome.get('grade'),
                              code=None if outcome['status'] in ('complete','converged') else classify(detail),
                              items=outcome.get('source_count'),seconds=round(time.monotonic()-attempt_started,3),detail=detail or None)
                accepted+=outcome['status']=='complete'
                # A menu that still loaded and held items: the store is alive at this endpoint, accepted or not.
                if outcome.get('source_count'):read_ok.add(endpoint['id'])
                had_failure=had_failure or outcome['status']!='complete'
                # The platform's own coordinates place this menu at another branch: retire it so sibling menus found on a
                # chain page are not re-read every sync. supersede_endpoint refuses a menu that holds accepted offers.
                if outcome['status']!='complete' and 'belongs to a different location' in (detail or '') and not endpoint.get('last_success_at'):
                    try:self.store.supersede_endpoint(endpoint['id'],detail)
                    except ValueError:pass
                results.append(dict(stage='menu',store_id=store['id'],store_name=store['name'],endpoint_id=endpoint['id'],provider=endpoint['provider'],license_type=endpoint['license_type'],url=endpoint['url'],work_origin=origin,**outcome))
                for event in results:
                    if event.get('stage')=='menu_progress' and event.get('endpoint_id')==endpoint['id']:event['status']=outcome['status']
                return outcome['status']=='complete'
            except PipelineInterrupted:raise
            except Exception as exc:
                self._check_stop()
                status='unsupported' if 'unsupported' in str(exc).lower() else 'failed'
                if sample_pages:
                    results.append(dict(stage='menu_sample',store_id=store['id'],store_name=store['name'],endpoint_id=endpoint['id'],provider=endpoint['provider'],license_type=endpoint['license_type'],url=endpoint['url'],work_origin=origin,status=status,error=str(exc)))
                    return False
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
        saved_ok=True
        for endpoint in saved:
            saved_ok=import_target(endpoint,'saved_endpoint') and saved_ok
        if saved:stages.append(dict(stage='saved_refresh',targets=len(saved),complete=saved_ok))

        if not retained or not retained_ok or force_resolution:
            # The weekly LLM check is for a store the programmatic pull cannot vouch for: no saved menu both loaded and
            # proved its branch. A saved endpoint that still reads items and proved its branch needs no search.
            vouched=any(endpoint['id'] in read_ok and endpoint.get('identity_confidence') in ('matched','name_locality') for endpoint in saved)
            if not retained and not sample and not vouched:
                store=self._verify_store(store,results)
                if store.get('operating_status')=='closed':
                    results.append(dict(stage='store_summary',store_id=store['id'],store_name=store['name'],pipeline_version=PIPELINE_VERSION,status='closed',
                                        menu_targets_attempted=0,accepted_snapshots=0,seconds=round(time.monotonic()-started,3),stages=[]))
                    return False
            self._check_stop();resolution_start=time.monotonic();failures=[];targets={}
            try:
                # Pages the store verifier cited or an operator seeded are crawl seeds; the resolver still has to prove the branch on them.
                leads=[lead['url'] for lead in self.store.leads(store['id']) if lead['source'] in ('verifier','operator')]
                resolver_store=dict(store,lead_urls=leads) if leads else store
                if sample:resolver_store=dict(resolver_store,discovery_seconds=SAMPLE_DISCOVERY_SECONDS)
                resolved=self.resolver(resolver_store,self.fetcher)
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
                    if self.store.platform_store_owner(endpoint.get('provider'),endpoint.get('provider_store_id'),store['id']):
                        # The platform's store is already another registry store's menu: a sibling branch found on a chain page, not this branch.
                        failure=dict(status='identity_conflict',error='Platform store is already bound to a different registry store; not this branch',url=endpoint['url'],evidence=endpoint.get('resolution_evidence'))
                        failures.append(failure)
                        results.append(dict(stage='resolution',store_id=store['id'],store_name=store['name'],**failure))
                        continue
                    self._record_rebrand(store,endpoint)
                    endpoint['discovery_source']=discovery_source(endpoint,self.store.leads(store['id']))
                    saved_endpoint=self.store.save_endpoint(store['id'],endpoint)
                    # A retired endpoint (wrong branch, duplicate) stays retired when discovery finds it again.
                    if saved_endpoint.get('status')=='superseded':continue
                    targets[saved_endpoint['id']]=saved_endpoint
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
                            status='sampled' if sample else 'partial' if had_failure else 'complete',menu_targets_attempted=len(attempted),accepted_snapshots=accepted,
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

    def _process_store_for_job(self,job_id,store,results,payload,lock):
        started=time.monotonic()
        try:
            failed=self._process_store(store,results,payload.get('resolve_sources',False))
        except PipelineInterrupted:raise
        except Exception as exc:
            self._check_stop();failed=True
            attempts=[r for r in results if r.get('store_id')==store['id'] and r.get('stage')=='menu']
            results.append(dict(stage='store_summary',store_id=store['id'],store_name=store['name'],pipeline_version=PIPELINE_VERSION,
                                status='failed',menu_targets_attempted=len(attempts),accepted_snapshots=sum(r.get('status')=='complete' for r in attempts),
                                seconds=round(time.monotonic()-started,3),stages=[],error=str(exc),evidence_id=getattr(exc,'evidence_id',None)))
        with lock:
            summary=next(r for r in reversed(results) if r.get('stage')=='store_summary' and r.get('store_id')==store['id'])
            self.store.record_store_work(job_id,summary)
            self.store.update_job(job_id,"running",results)
        return failed

    def _run_sample_stores(self,job_id,stores,results,payload):
        # Sample runs process several stores at once. Each worker gets its own fetcher client and job context, as the job thread
        # has, and stores of one chain never overlap, because chains share hosts and rate limits.
        job_fetcher=self.fetcher;lock=threading.Lock();chain_locks={}
        def work(store):
            fork=getattr(job_fetcher,'fork',None)
            self._contexts.fetcher=fork() if callable(fork) else copy.copy(job_fetcher)
            self._contexts.job_id=job_id;self._contexts.sample_pages=payload.get('sample_pages')
            try:
                self._check_stop()
                with self._lock_for(chain_locks,brand_key(store['name'],store.get('city'))):
                    return self._process_store_for_job(job_id,store,results,payload,lock)
            finally:
                if callable(fork):self._contexts.fetcher.close()
                del self._contexts.fetcher,self._contexts.job_id
        with ThreadPoolExecutor(max_workers=SAMPLE_WORKERS,thread_name_prefix='terpscout-sample') as pool:
            return any(list(pool.map(work,stores)))

    def _run(self,job_id):
        with self._lock_for(self.job_locks,job_id):
            job = self.store.job(job_id)
            if job["status"] != "queued":
                return job
            self.store.update_job(job_id, "running")
            results, had_failure = [], False
            payload = self.prepare_payload(job["payload"])
            self.fetcher.browser_options=self.store.setting('browser_options',dict(enabled=True,age_confirmed=False,terms_accepted=False))
            # A sample run reads the first pages of each category (per endpoint) and writes no menu state; see import_target.
            self._contexts.sample_pages=payload.get('sample_pages')
            if self._contexts.sample_pages:self.fetcher.browser_options=dict(self.fetcher.browser_options,sample_pages=self._contexts.sample_pages,await_menu=True,scroll_menu=True)
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
                if payload.get('sample_pages'):
                    had_failure=self._run_sample_stores(job_id,stores,results,payload) or had_failure
                else:
                    for store in stores:
                        self._check_stop()
                        had_failure=self._process_store_for_job(job_id,store,results,payload,threading.Lock()) or had_failure
                self.store.update_job(job_id, "partial" if had_failure else "succeeded", results)
            except PipelineInterrupted as exc:
                self.store.update_job(job_id,'interrupted',results,str(exc))
            except Exception as exc:
                self.store.update_job(job_id, "failed", results, str(exc))
            return self.store.job(job_id)
