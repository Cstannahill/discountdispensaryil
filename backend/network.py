"""Bounded public HTTP fetching with durable, content-addressed evidence.

Default transport pins each new TCP connection to a DNS-validated public IP;
the URL hostname remains the TLS SNI/certificate and HTTP Host identity.
Environment proxies are disabled. A caller-supplied transport is a trusted
external-I/O boundary (used by offline tests) and must provide its own pinning.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from email.utils import parsedate_to_datetime

import httpcore
import httpx

_READ_ONLY_SEARCH_POSTS = {
    'https://search-kyrok9udlk.gapcommerceapi.com/product/search': {'entity-id', 'org-id', 'x-api-key', 'accept', 'content-type'},
    'https://search.iheartjane.com/1/indexes/menu-products-production/query': {'x-algolia-api-key', 'x-algolia-application-id', 'accept', 'content-type'},
    'https://search.iheartjane.com/1/indexes/menu-products-by-price-production/query': {'x-algolia-api-key', 'x-algolia-application-id', 'accept', 'content-type'},
}

# Applied under saved settings: an absent key takes the default, an explicit null (user_agent_token) turns it off.
# Joint storefronts (WordPress plugin) each expose their own read-only product search under a per-site host.
_JOINT_SEARCH_POST = re.compile(r'^https://[a-z0-9.-]+/wp-json/joint-ecommerce/v1/products/[a-z0-9_-]+/_search$')
_JOINT_SEARCH_HEADERS = {'content-type', 'accept', 'origin', 'referer'}
# Jane's storefront search (facet counts, slice ids, and hydration of further ids); the SDK key is the page's public key.
_JANE_SEARCH_POST = re.compile(r'^https://dmerch\.iheartjane\.com/v2/(?:facets|multi|smartpage)\?jdm_api_key=[0-9a-f-]{36}&jdm_source=[a-z]+&jdm_version=[0-9.]+$')
_JANE_SEARCH_HEADERS = {'content-type', 'accept', 'referer'}


def _search_post_headers(url):
    if url in _READ_ONLY_SEARCH_POSTS:
        return _READ_ONLY_SEARCH_POSTS[url]
    if _JOINT_SEARCH_POST.match(url):
        return _JOINT_SEARCH_HEADERS
    if _JANE_SEARCH_POST.match(url):
        return _JANE_SEARCH_HEADERS
    return None


BROWSER_DEFAULTS = {'post_policy': 'platform_reads', 'user_agent_token': 'TerpScout/1.0', 'scroll_menu': True}

_BROWSER_PAGE_HEADERS={'accept','rsc','next-router-state-tree','next-router-prefetch','next-url'}


class FetchError(RuntimeError):
    def __init__(self, message, evidence_id=None):
        super().__init__(message)
        self.evidence_id = evidence_id


class UnsafeTargetError(FetchError):
    pass


def _safe_url(url):
    """Never persist credentials or common query secrets in diagnostics."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ''
        host = f'[{host}]' if ':' in host else host
        port = parts.port
        netloc = host + (f':{port}' if port else '')
        query = [(key, '[redacted]' if any(term in key.lower().replace('-', '_') for term in ('token', 'secret', 'password', 'signature', 'api_key', 'apikey', 'credential', 'authorization')) or key.lower() == 'key' else value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
        return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ''))
    except ValueError:
        return '[invalid URL]'


def _public_addresses(host, port, resolver):
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            records = resolver(host, port, type=socket.SOCK_STREAM)
            addresses = list(dict.fromkeys(record[4][0] for record in records))
        except OSError as exc:
            raise FetchError('Public destination DNS lookup failed') from exc
    else:
        addresses = [str(literal)]
    if not addresses:
        raise UnsafeTargetError('Destination has no public DNS addresses')
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeTargetError('DNS returned an invalid IP address') from exc
        if not ip.is_global or ip.is_multicast or ip.is_unspecified:
            raise UnsafeTargetError('Destination resolves to a non-public IP address')
    return addresses


class _PinnedBackend(httpcore.SyncBackend):
    def __init__(self, resolver):
        self.resolver = resolver

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        host = host.decode('ascii') if isinstance(host, bytes) else host
        addresses = _public_addresses(host, port, self.resolver)
        # Pass a numeric IP to the backend; a later DNS answer cannot redirect
        # this connection to localhost. TLS still sees the original hostname.
        return super().connect_tcp(host=addresses[0], port=port, timeout=timeout, local_address=local_address, socket_options=socket_options)


class _CoreStream(httpx.SyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    def __iter__(self):
        yield from self.stream

    def close(self):
        self.stream.close()


class _PinnedTransport(httpx.BaseTransport):
    def __init__(self, resolver):
        self.pool = httpcore.ConnectionPool(ssl_context=ssl.create_default_context(), network_backend=_PinnedBackend(resolver), retries=0, max_connections=4)

    def handle_request(self, request):
        core_request = httpcore.Request(method=request.method, url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host, port=request.url.port, target=request.url.raw_path), headers=request.headers.raw, content=request.stream, extensions=request.extensions)
        response = self.pool.handle_request(core_request)
        return httpx.Response(response.status, headers=response.headers, stream=_CoreStream(response.stream), extensions=response.extensions)

    def close(self):
        self.pool.close()


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    body: bytes
    headers: dict
    evidence_id: str
    fetched_at: str

    def json(self):
        return json.loads(self.body)


def browser_session_key(host,license_type='recreational',store_id=None):
    # Retain existing recreational sessions; never reuse them for medical menus.
    identity=host if license_type=='recreational' else host+'\0'+license_type
    if store_id:identity+='\0'+str(store_id)
    return hashlib.sha256(identity.encode()).hexdigest()+'.json'


class PublicFetcher:
    def __init__(self, evidence_dir: Path, *, max_attempts=3, max_redirects=5, max_response_bytes=25 * 1024 * 1024, timeout_seconds=20, max_run_seconds=120, max_retry_delay=30, resolver=socket.getaddrinfo, transport=None, sleeper=time.sleep):
        if max_attempts < 1 or max_redirects < 0 or max_response_bytes < 1 or timeout_seconds <= 0 or max_run_seconds <= 0 or max_retry_delay < 0:
            raise ValueError('Fetch limits must be positive (redirects/retry delay may be zero)')
        self.evidence_dir = Path(evidence_dir)
        self.resolver, self.sleeper = resolver, sleeper
        self.native_browser_allowed=transport is None
        self._transport_override=transport
        self.max_attempts, self.max_redirects = max_attempts, max_redirects
        self.max_response_bytes, self.timeout_seconds = max_response_bytes, timeout_seconds
        self.max_run_seconds, self.max_retry_delay = max_run_seconds, max_retry_delay
        self.client = httpx.Client(transport=transport or _PinnedTransport(resolver), trust_env=False, follow_redirects=False,
                                   timeout=timeout_seconds, headers={'User-Agent': 'TerpScout/1.0 public source evidence capture', 'Accept-Encoding': 'identity'})

    def close(self):
        self.client.close()

    def fork(self):
        """Independent client/cookie jar for one job; limits and evidence remain shared."""
        fork=PublicFetcher(self.evidence_dir,max_attempts=self.max_attempts,max_redirects=self.max_redirects,
                           max_response_bytes=self.max_response_bytes,timeout_seconds=self.timeout_seconds,
                           max_run_seconds=self.max_run_seconds,max_retry_delay=self.max_retry_delay,
                           resolver=self.resolver,transport=self._transport_override,sleeper=self.sleeper)
        fork.stop_requested=getattr(self,'stop_requested',None)
        fork.browser_options=dict(getattr(self,'browser_options',{}))
        return fork

    def _validate(self, url):
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise UnsafeTargetError('Invalid destination URL') from exc
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise UnsafeTargetError('Only absolute public HTTP(S) destinations are permitted')
        if parts.username is not None or parts.password is not None:
            raise UnsafeTargetError('Credential-bearing destinations are forbidden')
        if port not in (None, 80, 443):
            raise UnsafeTargetError('Only standard public HTTP(S) ports are permitted')
        _public_addresses(parts.hostname, port or (443 if parts.scheme == 'https' else 80), self.resolver)

    def _atomic(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.capture-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _record(self, url, status, body, headers, *, attempt, error=None, complete=True, request_headers=None, previous_evidence_ids=None, method='GET', request_body_sha256=None):
        sha = hashlib.sha256(body).hexdigest()
        body_path = Path('bodies') / sha[:2] / (sha + '.gz')
        self._atomic(self.evidence_dir / body_path, gzip.compress(body, mtime=0))
        fetched_at = datetime.now(timezone.utc).isoformat()
        diagnostic_headers = {'content-type', 'content-length', 'content-encoding', 'content-range', 'etag', 'last-modified', 'date',
                              'location', 'retry-after', 'cache-control', 'expires', 'vary', 'accept-ranges', 'server',
                              'x-total-count', 'x-page-count', 'x-pagination-total'}
        safe_headers = {k.lower(): v for k, v in headers.items() if k.lower() in diagnostic_headers}
        if 'location' in safe_headers:
            safe_headers['location'] = _safe_url(urljoin(url, safe_headers['location']))
        manifest = {'url': _safe_url(url), 'status_code': status, 'body_sha256': sha, 'body_path': body_path.as_posix(), 'body_bytes': len(body),
                    'headers': safe_headers, 'request_headers': {key: '[redacted]' for key in (request_headers or {})}, 'method': method,
                    'request_body_sha256': request_body_sha256, 'fetched_at': fetched_at, 'attempt': attempt, 'error': error, 'complete': complete,
                    'limits': {'max_attempts': self.max_attempts, 'max_redirects': self.max_redirects, 'max_response_bytes': self.max_response_bytes,
                               'timeout_seconds': self.timeout_seconds, 'max_run_seconds': self.max_run_seconds, 'max_retry_delay': self.max_retry_delay},
                    'body_representation': 'decoded HTTP entity bytes', 'previous_evidence_ids': list(previous_evidence_ids or [])}
        data = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode('utf-8')
        evidence_id = hashlib.sha256(data).hexdigest()
        self._atomic(self.evidence_dir / 'manifests' / (evidence_id + '.json'), data)
        return FetchResult(_safe_url(url), status or 0, body, safe_headers, evidence_id, fetched_at)

    def _delay(self, headers, attempt):
        value = headers.get('retry-after')
        try:
            delay = float(value)
        except (ValueError, TypeError):
            try:
                delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = 2 ** (attempt - 1)
        return max(0, min(delay, self.max_retry_delay))

    def get(self, url, headers=None) -> FetchResult:
        options=getattr(self,'browser_options',{})
        if options.get('enabled',True) and options.get('age_confirmed'):
            parts=urlsplit(url);host=parts.hostname or ''
            session=self.evidence_dir.parent/'browser-sessions'/browser_session_key(host,options.get('license_type','recreational'),(options.get('target_store') or {}).get('id'))
            try:state=json.loads(session.read_text(encoding='utf-8'))
            except (OSError,ValueError):state={}
            cookies=[]
            for cookie in state.get('cookies',[]):
                domain=cookie.get('domain','').lstrip('.')
                path=cookie.get('path','/')
                if not (host==domain or host.endswith('.'+domain)):continue
                if not (parts.path==path or parts.path.startswith(path if path.endswith('/') else path+'/')):continue
                if cookie.get('secure') and parts.scheme!='https':continue
                if cookie.get('expires',-1)>0 and cookie['expires']<time.time():continue
                cookies.append(cookie['name']+'='+cookie['value'])
            if cookies:
                return self._request('GET',url,headers=dict(headers or {},cookie='; '.join(cookies)),browser_origin=url)
        return self._request('GET', url, headers=headers)

    def browser_get(self, url, *, origin, cookie='', headers=None):
        headers={key.lower():value for key,value in (headers or {}).items() if key.lower() in _BROWSER_PAGE_HEADERS}
        if urlsplit(origin).hostname != urlsplit(url).hostname:
            if cookie:raise UnsafeTargetError('Browser cookie cannot cross source hostnames')
            headers={}
        if cookie:headers['cookie']=cookie
        return self._request('GET',url,headers=headers or None,browser_origin=origin)

    def render(self,url,*,license_type=None):
        from .browser_render import render
        options={**BROWSER_DEFAULTS,**getattr(self,'browser_options',{})}
        if license_type is not None:options['license_type']=license_type
        return render(url,self,options=options)

    def render_catalog(self,url,page_handler,*,license_type='recreational'):
        from .browser_render import render
        options=dict({**BROWSER_DEFAULTS,**getattr(self,'browser_options',{})},license_type=license_type)
        return render(url,self,options=options,page_handler=page_handler)

    def record_search(self, url, body) -> FetchResult:
        """Save web-search results fetched by the keyed LLM client as evidence. Only the result list is stored; the
        request, its headers and the key never reach this boundary."""
        return self._record(url, 200, body, {'content-type': 'application/json'}, attempt=1, method='POST')
    def render_reads(self,url,page_reader,*,license_type='recreational'):
        """Render `url` and let `page_reader` drive same-origin GET reads from inside the page (see browser_worker page_reads)."""
        from .browser_render import render
        options=dict({**BROWSER_DEFAULTS,**getattr(self,'browser_options',{})},license_type=license_type)
        return render(url,self,options=options,page_reader=page_reader)

    def post(self, url, *, json, headers=None) -> FetchResult:
        """Only explicitly observed public read-only search URLs are permitted.

        This is not a general POST client; orders, logins, redirects, and other
        hosts/paths are refused. Publishable storefront header values are never
        diagnostic metadata. Search responses retain the same evidence rules.
        """
        if _search_post_headers(url) is None:
            raise ValueError('POST is permitted only for explicitly observed read-only product search endpoints')
        return self._request('POST', url, headers=headers, json_payload=json)

    def _request(self, method, url, headers=None, json_payload=None, browser_origin=None) -> FetchResult:
        from .runtime import PipelineInterrupted
        if getattr(self,'stop_requested',None) is not None and self.stop_requested.is_set():
            raise PipelineInterrupted('Worker stopped before public request')
        request_headers = {key.lower(): value for key, value in (headers or {}).items()}
        allowed_headers = {'x-store', 'accept', 'content-type'} if method == 'GET' else _search_post_headers(url)
        if method=='GET' and urlsplit(url).hostname=='api.dispenseapp.com':
            allowed_headers=allowed_headers | {'api-key'}
        # Cresco storefronts send their publishable storefront key and store/app ids on every read (see backend/providers/cresco.py).
        if method=='GET' and urlsplit(url).hostname=='api.crescolabs.com':
            allowed_headers=allowed_headers | {'x-api-key','x-client-version','store_id','ordering_app_id','origin','referer'}
        if browser_origin and method=='GET' and urlsplit(url).hostname==urlsplit(browser_origin).hostname:
            allowed_headers=allowed_headers | {'cookie'} | _BROWSER_PAGE_HEADERS
        if any(key not in allowed_headers for key in request_headers):
            raise ValueError('Request contains a header not allowed for this public source')
        request_kwargs = {'json': json_payload} if method == 'POST' else {}
        body_sha = hashlib.sha256(json.dumps(json_payload, sort_keys=True).encode()).hexdigest() if method == 'POST' else None
        started = time.monotonic()
        current, redirects = url, 0
        previous_evidence_ids = []
        while True:
            for attempt in range(1, self.max_attempts + 1):
                if getattr(self,'stop_requested',None) is not None and self.stop_requested.is_set():
                    raise PipelineInterrupted('Worker stopped before public request attempt')
                status, headers, body = None, {}, bytearray()
                try:
                    self._validate(current)
                    remaining = self.max_run_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        raise FetchError('Fetch run time limit exceeded')
                    self.client.cookies.clear()
                    with self.client.stream(method, current, headers=request_headers, timeout=min(self.timeout_seconds, remaining), **request_kwargs) as response:
                        status, headers = response.status_code, dict(response.headers)
                        for chunk in response.iter_bytes():
                            if time.monotonic() - started > self.max_run_seconds:
                                raise FetchError('Fetch run time limit exceeded')
                            room = self.max_response_bytes - len(body)
                            body.extend(chunk[:room])
                            if len(chunk) > room:
                                raise FetchError('Response size limit exceeded')
                    result = self._record(current, status, bytes(body), headers, attempt=attempt,
                                          error=f'HTTP {status}' if status >= 400 else None, request_headers=request_headers, previous_evidence_ids=previous_evidence_ids,
                                          method=method, request_body_sha256=body_sha)
                    previous_evidence_ids.append(result.evidence_id)
                except UnsafeTargetError as exc:
                    result = self._record(current, status, bytes(body), headers, attempt=attempt, error=str(exc), complete=False, request_headers=request_headers, previous_evidence_ids=previous_evidence_ids, method=method, request_body_sha256=body_sha)
                    raise UnsafeTargetError(str(exc), result.evidence_id) from exc
                except (FetchError, httpx.HTTPError, httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError, OSError) as exc:
                    message = str(exc) if isinstance(exc, FetchError) else f'Public fetch failed: {type(exc).__name__}'
                    result = self._record(current, status, bytes(body), headers, attempt=attempt, error=message, complete=False, request_headers=request_headers, previous_evidence_ids=previous_evidence_ids, method=method, request_body_sha256=body_sha)
                    previous_evidence_ids.append(result.evidence_id)
                    if isinstance(exc, FetchError) or attempt == self.max_attempts:
                        raise FetchError(message, result.evidence_id) from exc
                    self.sleeper(min(self._delay(headers, attempt), max(0, self.max_run_seconds - (time.monotonic() - started))))
                    continue
                if status in (301, 302, 303, 307, 308):
                    if method == 'POST':
                        raise FetchError('Read-only search POST redirects are forbidden', result.evidence_id)
                    if redirects >= self.max_redirects or not headers.get('location'):
                        raise FetchError('Redirect limit exceeded or redirect location missing', result.evidence_id)
                    target = urljoin(current, headers['location'])
                    if urlsplit(target).hostname != urlsplit(current).hostname:
                        request_headers.pop('cookie',None)
                        if browser_origin:
                            for key in _BROWSER_PAGE_HEADERS:request_headers.pop(key,None)
                    current = target
                    redirects += 1
                    break
                if status in (408, 429, 500, 502, 503, 504) and attempt < self.max_attempts:
                    self.sleeper(min(self._delay(headers, attempt), max(0, self.max_run_seconds - (time.monotonic() - started))))
                    continue
                if status >= 400:
                    raise FetchError(f'Public endpoint returned HTTP {status}', result.evidence_id)
                return result
