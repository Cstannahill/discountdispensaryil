import json
import unittest

import httpx

from backend.websearch import McpSearch, SearchChain, configure_search


def sse(payload):
    return httpx.Response(200, headers={'content-type': 'text/event-stream', 'mcp-session-id': 'sess-1'},
                          text='event: message\ndata: ' + json.dumps(payload) + '\n\n')


def tool_reply(results):
    return {'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text', 'text': json.dumps(dict(query='q', results=results))}]}}


class Server:
    """Streamable-HTTP MCP double: initialize hands out a session id, tools/call returns the given results."""
    def __init__(self, results=(), status=200, forget_session_once=False):
        self.results, self.status, self.calls, self.forget = list(results), status, [], forget_session_once

    def __call__(self, request):
        body = json.loads(request.content)
        self.calls.append((body.get('method'), request.headers.get('mcp-session-id'), body.get('params')))
        if body['method'] == 'initialize':
            return sse({'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': '2025-03-26'}})
        if body['method'] == 'notifications/initialized':
            return httpx.Response(202)
        if self.forget:
            self.forget = False
            return httpx.Response(404, json={'error': {'message': 'Session not found'}})
        if self.status != 200:
            return httpx.Response(self.status)
        return sse(tool_reply(self.results))


def mcp(server, **kw):
    return McpSearch('http://localhost:9565/mcp', client=httpx.Client(transport=httpx.MockTransport(server)), **kw)


ITEM = dict(title='Zen Leaf <strong>Elmhurst</strong>', url='https://zenleafdispensaries.com/locations/elmhurst', snippet='Open daily � now')


class McpSearchTests(unittest.TestCase):

    def test_results_are_normalized_free_and_tagged_with_the_engine(self):
        server = Server([ITEM, dict(ITEM, url='https://zenleafdispensaries.com/locations/elmhurst'), dict(title='x', url='ftp://nope')])
        found = mcp(server).search('"Zen Leaf" Elmhurst')
        self.assertEqual(['https://zenleafdispensaries.com/locations/elmhurst'], [r['url'] for r in found['results']])
        self.assertEqual('Zen Leaf Elmhurst', found['results'][0]['title'])
        self.assertNotIn('�', found['results'][0]['snippet'])
        self.assertEqual((0, 0.0, 'websearch-mcp'), (found['tokens'], found['usd'], found['engine']))
        call = [c for c in server.calls if c[0] == 'tools/call'][0]
        self.assertEqual(('web_search', '"Zen Leaf" Elmhurst'), (call[2]['name'], call[2]['arguments']['query']))
        self.assertEqual('sess-1', call[1])

    def test_the_session_is_reused_and_reopened_when_the_server_forgot_it(self):
        server = Server([ITEM], forget_session_once=True)
        client = mcp(server)
        client.search('a'); client.search('b')
        self.assertEqual(2, [c[0] for c in server.calls].count('initialize'))
        self.assertEqual(2, [c[0] for c in server.calls].count('tools/call') - 1)

    def test_http_errors_and_tool_errors_raise(self):
        with self.assertRaises(RuntimeError):
            mcp(Server(status=500)).search('a')

        def tool_error(request):
            body = json.loads(request.content)
            if body['method'] == 'tools/call':
                return sse({'jsonrpc': '2.0', 'id': 2, 'result': {'isError': True, 'content': [{'type': 'text', 'text': 'no provider'}]}})
            return Server()(request)
        with self.assertRaises(RuntimeError):
            McpSearch('http://x/mcp', client=httpx.Client(transport=httpx.MockTransport(tool_error))).search('a')


class Fallback:
    engine = 'openrouter-web-exa'
    model = 'fake/model'
    def __init__(self, results=(), fail=False):
        self.results, self.fail, self.queries = list(results), fail, []
    def search(self, query):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError('boom')
        return dict(results=self.results, tokens=1600, usd=0.0072)
    def complete(self, messages):
        return dict(text='{}', tokens=1, usd=0.0)


class Primary:
    engine = 'websearch-mcp'
    def __init__(self, results=(), exc=None):
        self.results, self.exc, self.queries = list(results), exc, []
    def search(self, query):
        self.queries.append(query)
        if self.exc:
            raise self.exc
        return dict(results=self.results, tokens=0, usd=0.0, engine='websearch-mcp')


class ChainTests(unittest.TestCase):

    def test_the_mcp_answers_first_and_the_paid_search_is_never_called(self):
        mcp_, paid = Primary([ITEM]), Fallback([ITEM])
        found = SearchChain([mcp_, paid]).search('q')
        self.assertEqual(('websearch-mcp', 0.0), (found['engine'], found['usd']))
        self.assertEqual([], paid.queries)

    def test_error_timeout_or_empty_answer_falls_back_and_says_why(self):
        for primary in (Primary(exc=RuntimeError('down')), Primary(exc=httpx.ReadTimeout('slow')), Primary([])):
            paid = Fallback([ITEM])
            found = SearchChain([primary, paid]).search('q')
            self.assertEqual(['q'], paid.queries)
            self.assertEqual(0.0072, found['usd'])
            self.assertIn('websearch-mcp', found['fallback_from'])

    def test_all_providers_failing_raises_the_last_error_and_all_empty_returns_empty(self):
        with self.assertRaises(RuntimeError):
            SearchChain([Primary(exc=RuntimeError('a')), Fallback(fail=True)]).search('q')
        self.assertEqual([], SearchChain([Primary([]), Fallback([])]).search('q')['results'])

    def test_other_attributes_come_from_the_llm(self):
        chain = SearchChain([Primary()], llm=Fallback())
        self.assertEqual('fake/model', chain.model)
        self.assertEqual('{}', chain.complete([])['text'])


class ConfigTests(unittest.TestCase):
    BASE = dict(TERPSCOUT_SEARCH_PROVIDER='mcp,openrouter', TERPSCOUT_WEBSEARCH_MCP_URL='http://localhost:9565/mcp',
                TERPSCOUT_WEBSEARCH_MCP_TIMEOUT='20')

    def test_provider_order_comes_from_config(self):
        llm = Fallback()
        chain = configure_search(self.BASE, llm)
        self.assertEqual(['websearch-mcp', 'openrouter-web-exa'], [p.engine for p in chain.providers])
        self.assertEqual(['openrouter-web-exa', 'websearch-mcp'], [p.engine for p in configure_search(dict(self.BASE, TERPSCOUT_SEARCH_PROVIDER='openrouter,mcp'), llm).providers])
        self.assertIs(llm, configure_search(dict(self.BASE, TERPSCOUT_SEARCH_PROVIDER='openrouter'), llm))

    def test_mcp_alone_works_without_an_openrouter_key_and_none_means_unconfigured(self):
        chain = configure_search(self.BASE, None)
        self.assertEqual(['websearch-mcp'], [p.engine for p in chain.providers])
        self.assertIsNone(configure_search(dict(self.BASE, TERPSCOUT_SEARCH_PROVIDER='openrouter'), None))


if __name__ == '__main__':
    unittest.main()
