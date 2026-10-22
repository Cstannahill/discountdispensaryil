"""Web search providers behind one `search(query)` interface, so discovery and the verifier do not care who answers.

Order comes from TERPSCOUT_SEARCH_PROVIDER (comma separated: `mcp`, `openrouter`). The default asks the local WebSearch MCP
server first (free, streamable HTTP) and falls back to OpenRouter's web plugin (Exa, paid) when the MCP errors, times out or
returns nothing. Every provider returns `dict(results=[{url,title,snippet}], tokens, usd, engine)`; a fallback answer also
carries `fallback_from` (which provider was skipped and why). Results are leads, never pages (see verifier.py).
"""
import html
import json
import re
import threading
import time
from urllib.parse import urlsplit

MCP_ENGINE = 'websearch-mcp'
PAID_ENGINE = 'openrouter-web-exa'
SNIPPET_CHARS = 600
RESULTS = 5
_TAGS = re.compile(r'<[^>]+>')


def _clean(text, limit):
    return re.sub(r'\s+', ' ', html.unescape(_TAGS.sub('', str(text or ''))).replace('�', '')).strip()[:limit]


class McpSearch:
    """Client for a streamable-HTTP MCP server's `web_search` tool. One session is opened lazily, reused across calls and
    reopened once if the server forgot it (it prunes idle sessions)."""
    engine = MCP_ENGINE

    def __init__(self, url, timeout=20, client=None, max_results=RESULTS):
        import httpx
        self.url, self.max_results = url, max_results
        self._client = client or httpx.Client(timeout=timeout)
        self._session, self._lock, self._id = None, threading.Lock(), 1

    def _rpc(self, payload, session=None):
        headers = {'accept': 'application/json, text/event-stream', 'content-type': 'application/json'}
        if session:
            headers['mcp-session-id'] = session
        return self._client.post(self.url, headers=headers, json=payload)

    def _open(self):
        response = self._rpc(dict(jsonrpc='2.0', id=1, method='initialize', params=dict(
            protocolVersion='2025-03-26', capabilities={}, clientInfo=dict(name='terpscout', version='1'))))
        if response.status_code != 200 or not response.headers.get('mcp-session-id'):
            raise RuntimeError(f'WebSearch MCP initialize HTTP {response.status_code}')
        session = response.headers['mcp-session-id']
        self._rpc(dict(jsonrpc='2.0', method='notifications/initialized'), session)
        return session

    def _session_id(self, renew=False):
        with self._lock:
            if renew or not self._session:
                self._session = self._open()
            return self._session

    def _call(self, query):
        session = self._session_id()
        for attempt in (0, 1):
            with self._lock:
                self._id += 1
                request_id = self._id
            response = self._rpc(dict(jsonrpc='2.0', id=request_id, method='tools/call', params=dict(
                name='web_search', arguments=dict(query=query, max_results=self.max_results))), session)
            if response.status_code == 404 and not attempt:
                session = self._session_id(renew=True)
                continue
            return response

    @staticmethod
    def _message(response):
        text = response.text
        for line in text.splitlines():
            if line.startswith('data:'):
                return json.loads(line[5:])
        return json.loads(text)

    def search(self, query):
        response = self._call(query)
        if response.status_code != 200:
            raise RuntimeError(f'WebSearch MCP HTTP {response.status_code}')
        message = self._message(response)
        if message.get('error'):
            raise RuntimeError('WebSearch MCP error: ' + str(message['error'].get('message'))[:160])
        result = message.get('result') or {}
        text = ''.join(block.get('text', '') for block in result.get('content') or [] if block.get('type') == 'text')
        if result.get('isError'):
            raise RuntimeError('WebSearch MCP tool error: ' + text[:160])
        found = {}
        for item in (json.loads(text).get('results') if text.startswith('{') else None) or []:
            url = item.get('url')
            if isinstance(url, str) and urlsplit(url).scheme in ('http', 'https'):
                found.setdefault(url, dict(url=url, title=_clean(item.get('title'), 160), snippet=_clean(item.get('snippet'), SNIPPET_CHARS)))
        return dict(results=list(found.values())[:self.max_results], tokens=0, usd=0.0, engine=MCP_ENGINE)


class _Paid:
    """The OpenRouter client as a plain search provider."""
    engine = PAID_ENGINE

    def __init__(self, llm):
        self.llm = llm

    def search(self, query):
        return dict(self.llm.search(query), engine=PAID_ENGINE)


class SearchChain:
    """Tries each provider in order; the first with results answers. An error or an empty answer moves on, and the answer
    says which providers were skipped. Anything else (`complete`, `model`, `usd_per_day`, ...) belongs to the LLM."""

    def __init__(self, providers, llm=None):
        self.providers, self.llm = list(providers), llm

    def __getattr__(self, name):
        if name in ('providers', 'llm') or self.llm is None:
            raise AttributeError(name)
        return getattr(self.llm, name)

    def __setattr__(self, name, value):
        # Settings such as usd_per_day live on the LLM, where the other callers read them.
        if name in ('providers', 'llm') or self.__dict__.get('llm') is None:
            return object.__setattr__(self, name, value)
        setattr(self.llm, name, value)

    def search(self, query):
        skipped, empty, error = [], None, None
        for provider in self.providers:
            engine = getattr(provider, 'engine', type(provider).__name__)
            started = time.monotonic()
            try:
                found = provider.search(query)
            except Exception as exc:
                error = exc
                skipped.append(f'{engine}: {type(exc).__name__}: {str(exc)[:120]}')
                continue
            found = dict(found, engine=found.get('engine') or engine, seconds=round(time.monotonic() - started, 3))
            if skipped:
                found['fallback_from'] = '; '.join(skipped)
            if found['results']:
                return found
            skipped.append(f'{engine}: no results')
            empty = dict(found, fallback_from='; '.join(skipped))
        if empty is not None:
            return empty
        raise error


def configure_search(config, llm):
    """The search client for `config`: `llm` itself when only OpenRouter is chosen, else a SearchChain over the chosen
    providers that still exposes the llm's other attributes. `llm` itself when nothing else is usable (None without a key)."""
    names = [n.strip() for n in str(config.get('TERPSCOUT_SEARCH_PROVIDER') or 'mcp,openrouter').split(',') if n.strip()]
    providers = []
    for name in names:
        if name == 'mcp' and config.get('TERPSCOUT_WEBSEARCH_MCP_URL'):
            providers.append(McpSearch(config['TERPSCOUT_WEBSEARCH_MCP_URL'], timeout=float(config.get('TERPSCOUT_WEBSEARCH_MCP_TIMEOUT') or 20)))
        elif name == 'openrouter' and llm is not None:
            providers.append(_Paid(llm))
    if not providers or (llm is not None and len(providers) == 1 and isinstance(providers[0], _Paid)):
        return llm
    return SearchChain(providers, llm)
