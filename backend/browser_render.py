"""Bounded Chrome subprocess with all browser network traffic proxied to PublicFetcher."""
import base64
import copy
import hashlib
import json
import os
import queue
from pathlib import Path
import shutil
import subprocess
import threading
from urllib.parse import urlsplit


_SECRET_FIELD=__import__('re').compile(r'(?i)("(?:[\w-]*(?:api[_-]?key|token|secret|password|authorization)[\w-]*)"\s*:\s*)"[^"]*"')


def _redact_body(body):
    return _SECRET_FIELD.sub(r'\1"[redacted]"',body[:8192]) if isinstance(body,str) else None


def _note_json(network_json,evidence_id,url,method,status,content_type,size,post_body):
    """Summarise a finite JSON response the page loaded so extraction can read it back from evidence."""
    kind=(content_type or '').split(';')[0].strip().lower()
    if (kind.endswith('json') or kind=='application/x-ndjson') and len(network_json)<400:
        from .network import _safe_url
        network_json.append(dict(evidence_id=evidence_id,url=_safe_url(url),method=method,status=status,content_type=kind,bytes=size,request_body=_redact_body(post_body)))


def _close_streams(streams):
    for stream in streams:
        try:stream.close()
        except OSError:pass  # Windows broken-pipe flush must not mask the cause.



def _next_worker_message(messages, process, timed_out, stop_requested=None):
    """Wait within the overall deadline, allowing bounded browser navigation retries."""
    from .runtime import PipelineInterrupted
    while True:
        if stop_requested is not None and stop_requested.is_set():
            raise PipelineInterrupted('Worker stopped during browser acquisition')
        try:
            return messages.get(timeout=1)
        except queue.Empty:
            if timed_out.is_set() or process.poll() is not None:
                return None


def render(url,fetcher,options=None,page_handler=None):
    options=dict(options or {},catalog_navigation=page_handler is not None)
    if options.get('transport','native')=='native' and getattr(fetcher,'native_browser_allowed',False):
        from .browser_proxy import public_browser_proxy
        with public_browser_proxy(fetcher,max_bytes=(256 if page_handler else 64)*1024*1024,require_page_request=True) as proxy:
            return _render(url,fetcher,options,proxy,page_handler)
    return _render(url,fetcher,options,page_handler=page_handler)


def _render(url,fetcher,options=None,proxy=None,page_handler=None):
    from .runtime import PipelineInterrupted
    if getattr(fetcher,'stop_requested',None) is not None and fetcher.stop_requested.is_set():
        raise PipelineInterrupted('Worker stopped before browser acquisition')
    options=dict(options or {},max_html_chars=int(fetcher.max_response_bytes*0.4))
    resources=copy.copy(fetcher)
    resources.max_attempts=1
    resources.timeout_seconds=min(8,fetcher.timeout_seconds)
    resources.max_run_seconds=min(10,fetcher.max_run_seconds)
    if options.get('enabled') is False:
        raise ValueError('JavaScript browser fallback is disabled in ingestion settings')
    fetcher._validate(url)
    node=shutil.which('node')
    if not node:raise RuntimeError('Browser fallback requires Node.js and Chrome')
    worker=Path(__file__).with_name('browser_worker.cjs')
    process=subprocess.Popen([node,str(worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    timed_out=threading.Event()
    def expire():
        timed_out.set()
        if process.poll() is None:process.kill()
    deadline_seconds=900 if page_handler else 90 if options.get('sample_pages') else 320 if options.get('await_menu') and options.get('scroll_menu') else 50
    timer=threading.Timer(deadline_seconds,expire);timer.start()
    evidence=[];result=None;blocked=[];worker_diagnostics={}
    decisions=[];network_json=[]
    messages=queue.Queue();stderr=[]
    # Drain stdout independently of writing large response bodies to stdin.
    # Otherwise a page emitting many requests fills both Windows pipes and
    # neither process can read the response/request needed to make progress.
    def read_messages():
        try:
            for line in process.stdout:messages.put(json.loads(line))
        except Exception as exc:messages.put(dict(type='error',message=f'Browser protocol failed: {exc}'))
        finally:messages.put(None)
    def read_errors():
        for line in process.stderr:
            if sum(len(part) for part in stderr)<16000:stderr.append(line)
    readers=[threading.Thread(target=read_messages,daemon=True),threading.Thread(target=read_errors,daemon=True)]
    for reader in readers:reader.start()
    from .network import browser_session_key
    session_path=fetcher.evidence_dir.parent/'browser-sessions'/browser_session_key(urlsplit(url).hostname,options.get('license_type','recreational'),(options.get('target_store') or {}).get('id'))
    try:storage_state=json.loads(session_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):storage_state=None
    def send(message):
        process.stdin.write(json.dumps(message)+'\n');process.stdin.flush()
    try:
        send(dict(type='start',url=url,options=options,storage_state=storage_state,native_proxy=proxy['url'] if proxy else None))
        while True:
            message=_next_worker_message(messages,process,timed_out,getattr(fetcher,'stop_requested',None))
            if message is None:break
            if message['type']=='progress':
                worker_diagnostics.update(message.get('diagnostics') or {})
                continue
            if message['type']=='error':
                worker_diagnostics=message.get('diagnostics') or {}
                raise RuntimeError(message['message'])
            if message['type']=='result':result=message;break
            if message['type']!='request':continue
            # The result can already be queued behind late resource requests.
            # Drain it even if Chrome/Node finished before those replies.
            if process.poll() is not None:continue
            reply=dict(id=message['id'])
            try:
                if message['method']=='DOCUMENT':
                    if page_handler is None:raise ValueError('Unrequested catalog document')
                    resources._validate(message['url'])
                    html=message['html'];source=message.get('flight') or html
                    body=source.encode('utf-8')
                    if max(len(body),len(html.encode('utf-8')))>fetcher.max_response_bytes:raise ValueError('Catalog document exceeds response size limit')
                    response=resources._record(message['url'],message['status'],body,{'content-type':'text/x-component' if message.get('flight') else 'text/html'},attempt=1,method='BROWSER_CATALOG_PAGE')
                    evidence.append(response.evidence_id)
                    reply.update(page_handler(response,dict(html=html,links=message.get('links',[]),store_labels=message.get('store_labels',[]))) or {})
                    send(reply);continue
                if message['method']=='VALIDATE':
                    from .request_policy import decide
                    resources._validate(message['url'])
                    method=message['request_method']
                    decision=decide(options.get('post_policy','strict'),method=method,url=message['url'],body=message.get('post_data'),
                                    content_type=message.get('content_type'),page_url=url)
                    if method!='GET' and len(decisions)<300:
                        parts=urlsplit(message['url'])
                        decisions.append(dict(method=method,host=parts.hostname,path=parts.path[:80],allowed=decision['allowed'],rule=decision['rule']))
                    if not decision['allowed']:
                        raise ValueError('Browser request is not a supported public read-only request ('+decision['reason']+')')
                    if proxy:proxy['authorize_url'](message['url'])
                    reply['allowed']=True
                    send(reply);continue
                if message['method']=='CAPTURE':
                    body=base64.b64decode(message['body'])
                    if len(body)>fetcher.max_response_bytes:raise ValueError('Browser response capture exceeds size limit')
                    status=message['status']
                    response=resources._record(message['url'],status,body,message.get('response_headers',{}),attempt=1,
                                               error=f'HTTP {status}' if status>=400 else None,method=message['request_method'],
                                               request_headers=message.get('headers'),request_body_sha256=message.get('request_body_sha256'))
                    evidence.append(response.evidence_id);reply['captured']=True
                    _note_json(network_json,response.evidence_id,message['url'],message['request_method'],status,(message.get('response_headers') or {}).get('content-type',''),len(body),message.get('post_data'))
                    send(reply);continue
                if message['method']=='GET':
                    cookie=message.get('cookie','') if urlsplit(message['url']).hostname==urlsplit(url).hostname else ''
                    response=resources.browser_get(message['url'],origin=url,cookie=cookie,headers=message.get('headers'))
                elif message['method']=='POST':
                    # Only already validated public read-only searches can use
                    # POST. A rendered page cannot authorize arbitrary actions.
                    from .network import _READ_ONLY_SEARCH_POSTS
                    allowed=_READ_ONLY_SEARCH_POSTS.get(message['url'],set())
                    headers={key:value for key,value in message.get('headers',{}).items() if key in allowed}
                    response=resources.post(message['url'],json=json.loads(message.get('body') or '{}'),headers=headers)
                else:raise ValueError('Browser request method is not a read-only fetch')
                evidence.append(response.evidence_id)
                _note_json(network_json,response.evidence_id,message['url'],message['method'],response.status_code,response.headers.get('content-type',''),len(response.body),message.get('body'))
                reply.update(status=response.status_code,headers={k:v for k,v in response.headers.items() if k in ('content-type','cache-control','access-control-allow-origin')},body=base64.b64encode(response.body).decode())
            except Exception as exc:
                blocked.append(dict(url=message['url'],error=str(exc),evidence_id=getattr(exc,'evidence_id',None)))
                reply['error']=str(exc)
            try:send(reply)
            except (OSError,BrokenPipeError):continue
        if not result:
            detail=f'{deadline_seconds}-second rendering deadline exceeded' if timed_out.is_set() else f'worker exited with code {process.poll()}'
            raise RuntimeError('Browser rendering did not finish: '+detail+(' · '+''.join(stderr)[:500] if stderr else ''))
        if result.get('storage_state'):
            session_path.parent.mkdir(parents=True,exist_ok=True)
            fetcher._atomic(session_path,json.dumps(result['storage_state']).encode())
        if result.get('screenshot'):
            fetcher._atomic(fetcher.evidence_dir/'browser'/f"{hashlib.sha256(result['html'].encode()).hexdigest()}.png",base64.b64decode(result['screenshot']))
        body=result['html'].encode()
        if len(body)>fetcher.max_response_bytes:raise ValueError(f'Rendered page exceeds response size limit ({len(body)} > {fetcher.max_response_bytes} bytes)')
        status=result.get('status',200)
        capture=fetcher._record(result['url'],status,body,{'content-type':'text/html'},attempt=1,
                                error=f'HTTP {status}' if status>=400 else None,complete=True,previous_evidence_ids=evidence,method='BROWSER_RENDER')
        fetcher._atomic(fetcher.evidence_dir/'browser'/f'{capture.evidence_id}.json',json.dumps(dict(html_reduced=result.get('html_reduced'),scroll=result.get('scroll'),age_decisions=result.get('age_decisions',[]),request_decisions=decisions,network_json=network_json,post_policy=options.get('post_policy','strict'),phase=worker_diagnostics.get('phase'),streaming_responses_skipped=result.get('streaming_responses_skipped',[]),menu_readiness=result.get('menu_readiness'),page_errors=result.get('page_errors',[]),console_errors=result.get('console_errors',[]),request_evidence=evidence,blocked_requests=blocked,options=options,requests=result['requests'],auxiliary_requests_skipped=result.get('auxiliary_requests_skipped',0),captured_bytes=result.get('captured_bytes',0),navigation_retries=result.get('navigation_retries',[]),transport='native_public_tunnel' if proxy else 'captured_http',connections=proxy['connections'] if proxy else [],tunnel_blocks=proxy['blocked'] if proxy else [],tunnel_capacity=proxy.get('capacity') if proxy else None,capture_errors=result.get('capture_errors',[]),context_transitions=result.get('context_transitions',[]),location_decisions=result.get('location_decisions',[]),request_limit=result.get('request_limit'),request_limit_exceeded=result.get('request_limit_exceeded',False))).encode())
        return capture
    except Exception as exc:
        from .network import FetchError
        message=str(exc) or type(exc).__name__
        tunnel_blocks=proxy['blocked'] if proxy else []
        budget_errors=[block['error'] for block in tunnel_blocks if 'budget exceeded' in block.get('error','')]
        if budget_errors:message+=' · '+budget_errors[-1]
        capture=fetcher._record(url,None,b'',{},attempt=1,error=message,complete=False,previous_evidence_ids=evidence,method='BROWSER_RENDER')
        fetcher._atomic(fetcher.evidence_dir/'browser'/f'{capture.evidence_id}.json',json.dumps(dict(**worker_diagnostics,request_decisions=decisions,network_json=network_json,post_policy=options.get('post_policy','strict'),error=message,timeout=timed_out.is_set(),exit_code=process.poll(),request_evidence=evidence,blocked_requests=blocked,transport='native_public_tunnel' if proxy else 'captured_http',connections=proxy['connections'] if proxy else [],tunnel_blocks=tunnel_blocks,tunnel_capacity=proxy.get('capacity') if proxy else None)).encode())
        raise FetchError(message,capture.evidence_id) from exc
    finally:
        timer.cancel()
        if process.poll() is None:process.kill()
        process.wait(timeout=5)
        for reader in readers:reader.join(timeout=2)
        _close_streams((process.stdin,process.stdout,process.stderr))
