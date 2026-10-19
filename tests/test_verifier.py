import json
from pathlib import Path
import tempfile
import unittest

from backend import verifier
from backend.storage import Store
from tests.test_storage import observation

STORE = dict(id='s1', name='Beyond/Hello - Peoria', address='7620 N IL Rt 91', city='Peoria', state='IL')
LIMITS = dict(steps=8, seconds=60, tokens=40000, usd=0.05, usd_per_day=1.0)
SITE = 'https://bloomwellness.example/peoria/'
PAGE = ('<html><head><script>var x="Now open daily";</script></head><body><h1>Bloom Wellness Peoria</h1>'
        '<p>Bloom Wellness Peoria, formerly Beyond/Hello, is open daily at 7620 N. IL Route 91, Peoria, IL.</p>'
        '<a href="/peoria/menu/">Shop the recreational menu</a></body></html>')
SEARCH_RESULTS = [dict(url=SITE, title='Bloom Wellness Peoria', snippet='Bloom Wellness Peoria, formerly Beyond/Hello, is open daily')]


class Response:
    def __init__(self, url, text, status=200, number=0):
        self.url, self.status_code, self.body = url, status, text.encode()
        self.evidence_id, self.fetched_at = f'ev-{number}', '2026-10-18T22:00:00Z'


class Fetcher:
    def __init__(self, evidence_dir=None):
        self.urls, self.searches, self.evidence_dir = [], [], evidence_dir

    def record_search(self, url, body):
        self.searches.append(json.loads(body))
        return Response(url, body.decode(), number=100 + len(self.searches))

    def get(self, url):
        self.urls.append(url)
        if url == SITE:
            return Response(url, PAGE, number=len(self.urls))
        return Response(url, 'not found', 404, len(self.urls))


class FakeLLM:
    model = 'fake/model'

    def __init__(self, *replies, tokens=100, usd=0.001, search_usd=0.007):
        self.replies, self.tokens, self.usd, self.search_usd, self.seen, self.queries = list(replies), tokens, usd, search_usd, [], []

    def search(self, query):
        self.queries.append(query)
        return dict(results=list(SEARCH_RESULTS), tokens=1600, usd=self.search_usd)

    def complete(self, messages):
        self.seen.append(list(messages))
        reply = self.replies.pop(0) if self.replies else dict(action='search', query='again')
        return dict(text=json.dumps(reply), tokens=self.tokens, usd=self.usd)


def answer(**changes):
    value = dict(action='answer', verdict='renamed', name='Bloom Wellness Peoria', website=SITE, menu_url='https://bloomwellness.example/peoria/menu/',
                 address='7620 N. IL Route 91, Peoria, IL', confidence=0.8, claims=[
                     dict(field='name', value='Bloom Wellness Peoria', url=SITE, quote='Bloom Wellness Peoria, formerly Beyond/Hello'),
                     dict(field='existence', value='open', url=SITE, quote='is open daily at 7620 N. IL Route 91')])
    value.update(changes)
    return value


class VerifierTests(unittest.TestCase):
    def run_verifier(self, llm, limits=LIMITS, fetcher=None, **kwargs):
        fetcher = fetcher or Fetcher()
        return verifier.verify_store(dict(STORE), fetcher, llm, limits, **kwargs), fetcher

    def test_without_a_key_it_is_not_configured_and_makes_no_request(self):
        self.assertIsNone(verifier.llm_from_config(dict(verifier.DEFAULTS)))
        record, fetcher = self.run_verifier(None)
        self.assertEqual('not_configured', record['status'])
        self.assertEqual([], fetcher.urls)
        self.assertIn('OPENROUTER_API_KEY', record['detail'])

    def test_a_configured_key_selects_the_default_provider_and_model(self):
        llm = verifier.llm_from_config(dict(verifier.DEFAULTS, OPENROUTER_API_KEY='test-key', TERPSCOUT_LLM_MODEL='some/model'))
        self.assertIsInstance(llm, verifier.OpenRouter)
        self.assertEqual('some/model', llm.model)

    def test_env_file_values_and_process_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('# comment\nOPENROUTER_API_KEY="abc"\nVERIFIER_MAX_STEPS=3\n', encoding='utf-8')
            config = verifier.load_env(path)
        self.assertEqual('abc', config['OPENROUTER_API_KEY'])
        self.assertEqual(3, verifier.budgets(config)['steps'])
        self.assertEqual('openrouter', config['TERPSCOUT_LLM_PROVIDER'])

    def test_cited_claims_survive_and_the_verdict_stands_on_them(self):
        llm = FakeLLM(dict(action='search', query='Beyond Hello Peoria'), dict(action='read', url=SITE), answer())
        record, fetcher = self.run_verifier(llm)
        self.assertEqual('verified', record['status'])
        self.assertEqual('renamed', record['verdict'])
        self.assertEqual(2, len(record['claims']))
        self.assertEqual('Bloom Wellness Peoria', record['result']['name'])
        # No claim cites the website or menu fields, so neither value is kept.
        self.assertIsNone(record['result']['website'])
        self.assertIsNone(record['result']['menu_url'])
        self.assertEqual(3, record['steps'])
        self.assertTrue(record['claims'][0]['evidence_id'])
        # Page text reaches the model labelled as untrusted data.
        self.assertIn('untrusted', llm.seen[-1][-1]['content'])
        # The web-plugin search is its own paid request: its fee and tokens count, and its result list is evidence.
        self.assertEqual(['Beyond Hello Peoria'], llm.queries)
        self.assertAlmostEqual(3 * 0.001 + 0.007, record['usd'])
        self.assertEqual(3 * 100 + 1600, record['tokens'])
        self.assertEqual('ev-101', record['evidence'][0])
        self.assertEqual(SITE, fetcher.searches[0]['results'][0]['url'])
        self.assertIn(SITE, llm.seen[1][-1]['content'])

    def test_a_search_result_snippet_is_not_a_read_page(self):
        claims = [dict(field='existence', value='open', url=SITE, quote='Bloom Wellness Peoria, formerly Beyond/Hello, is open daily')]
        llm = FakeLLM(dict(action='search', query='Beyond Hello Peoria'), answer(verdict='exists', claims=claims))
        record, fetcher = self.run_verifier(llm)
        self.assertEqual([], fetcher.urls)
        self.assertEqual(['not a page read in this run'], [c['dropped'] for c in record['dropped']])
        self.assertEqual('unknown', record['verdict'])

    def test_search_fees_count_against_the_store_and_daily_caps_and_are_ledgered(self):
        record, _ = self.run_verifier(FakeLLM(dict(action='search', query='a'), answer(), search_usd=0.05))
        self.assertEqual(('budget_exceeded', 1), (record['status'], record['steps']))
        llm = FakeLLM(dict(action='search', query='a'), answer())
        record, _ = self.run_verifier(llm, dict(LIMITS, usd=5), spent_today=0.9995)
        self.assertEqual(('budget_exceeded', []), (record['status'], llm.queries))
        with tempfile.TemporaryDirectory() as folder:
            record, _ = self.run_verifier(FakeLLM(dict(action='search', query='a'), answer()), fetcher=Fetcher(Path(folder)))
            self.assertAlmostEqual(record['usd'], verifier.spend_since(folder, verifier.day_ago(), 'verifier'))
            self.assertEqual(0.0, verifier.spend_since(folder, verifier.day_ago(), 'discovery'))
            self.assertEqual(0.0, verifier.spend_since(folder, '9999'))

    def test_claims_without_a_quote_on_a_fetched_saved_page_are_dropped(self):
        claims = [dict(field='menu_url', value='https://bloomwellness.example/peoria/menu/', url=SITE, quote='Shop the recreational menu'),
                  dict(field='address', value='1 Fake St', url=SITE, quote='located at 1 Fake Street in Peoria'),
                  dict(field='website', value='https://other.example/', url='https://other.example/', quote='Bloom Wellness Peoria, formerly'),
                  dict(field='existence', value='open', url=SITE, quote='open'),
                  dict(field='existence', value='open', url=SITE, quote='Now open daily, every day')]
        llm = FakeLLM(dict(action='read', url=SITE), answer(verdict='exists', claims=claims))
        record, _ = self.run_verifier(llm)
        self.assertEqual(['menu_url'], [c['field'] for c in record['claims']])
        self.assertEqual(['quote not on page', 'not a page read in this run', 'quote too short', 'quote not on page'],
                         [c['dropped'] for c in record['dropped']])
        # The script text is not page text, and no existence claim survived: the verdict falls back to unknown.
        self.assertEqual('unknown', record['verdict'])
        self.assertEqual('https://bloomwellness.example/peoria/menu/', record['result']['menu_url'])
        self.assertIsNone(record['result']['address'])

    def test_an_unread_page_cannot_support_any_claim(self):
        record, _ = self.run_verifier(FakeLLM(answer()))
        self.assertEqual('unknown', record['verdict'])
        self.assertEqual([], record['claims'])
        self.assertEqual(0.0, record['result']['confidence'])

    def test_step_cap(self):
        record, _ = self.run_verifier(FakeLLM(), dict(LIMITS, steps=3))
        self.assertEqual('budget_exceeded', record['status'])
        self.assertEqual(3, record['steps'])

    def test_spend_token_and_time_caps(self):
        # Each step here is a model call plus a search (0.02 + 0.007), so the 0.05 store cap stops after two.
        record, _ = self.run_verifier(FakeLLM(usd=0.02), dict(LIMITS, usd=0.05))
        self.assertEqual(('budget_exceeded', 2), (record['status'], record['steps']))
        record, _ = self.run_verifier(FakeLLM(tokens=15000), dict(LIMITS, tokens=40000))
        self.assertEqual(('budget_exceeded', 3), (record['status'], record['steps']))
        ticks = iter(range(0, 1000, 25))
        record, _ = self.run_verifier(FakeLLM(), dict(LIMITS, seconds=60), clock=lambda: next(ticks))
        self.assertEqual('budget_exceeded', record['status'])
        self.assertLess(record['steps'], 4)

    def test_daily_spend_cap_stops_before_any_call(self):
        llm = FakeLLM(answer())
        record, fetcher = self.run_verifier(llm, spent_today=1.0)
        self.assertEqual(('budget_exceeded', 0, [], []), (record['status'], record['steps'], llm.seen, fetcher.urls))
        record, _ = self.run_verifier(FakeLLM(usd=0.3), dict(LIMITS, usd=5), spent_today=0.5)
        self.assertEqual(('budget_exceeded', 2), (record['status'], record['steps']))

    def test_model_failure_is_recorded_not_raised(self):
        class Broken:
            model = 'x'
            def complete(self, messages):
                raise RuntimeError('LLM HTTP 500')
        record, _ = self.run_verifier(Broken())
        self.assertEqual('failed', record['status'])
        self.assertIn('500', record['detail'])

    def test_last_step_asks_for_the_answer(self):
        llm = FakeLLM(dict(action='search', query='a'), answer())
        self.run_verifier(llm, dict(LIMITS, steps=2))
        self.assertIn('Final step', llm.seen[-1][-1]['content'])


class ModelSelectionTests(unittest.TestCase):
    CONFIG = dict(verifier.DEFAULTS, OPENROUTER_API_KEY='test-key', TERPSCOUT_LLM_MODELS=' ~z-ai/glm-flash-latest, xiaomi/mimo-v2.6-flash ,')

    def test_model_list_and_per_run_override(self):
        self.assertEqual(['~z-ai/glm-flash-latest', 'xiaomi/mimo-v2.6-flash', verifier.DEFAULTS['TERPSCOUT_LLM_MODEL']],
                         verifier.models(self.CONFIG))
        self.assertEqual('xiaomi/mimo-v2.6-flash', verifier.llm_from_config(self.CONFIG, 'xiaomi/mimo-v2.6-flash').model)
        self.assertEqual(verifier.DEFAULTS['TERPSCOUT_LLM_MODEL'], verifier.llm_from_config(self.CONFIG).model)

    def test_batch_variants_are_refused_before_any_call(self):
        llm = FakeLLM(answer())
        llm.model = 'anthropic/claude-haiku-5.5:batch'
        fetcher = Fetcher()
        record = verifier.verify_store(dict(STORE), fetcher, llm, LIMITS)
        self.assertEqual(('unsupported_model', [], []), (record['status'], llm.seen, fetcher.urls))
        self.assertIn('Batch API', record['detail'])
        self.assertEqual('unsupported_model', verifier.verify_store(dict(STORE), fetcher, None, LIMITS, model='x/y:batch')['status'])

    def test_openrouter_request_and_json_mode_fallback(self):
        class Reply:
            def __init__(self, status, body=None):
                self.status_code, self._body = status, body
            def json(self):
                return self._body
        class Client:
            def __init__(self):
                self.bodies, self.headers = [], []
            def post(self, url, headers, json):
                self.bodies.append(json); self.headers.append(headers)
                if 'response_format' in json:
                    return Reply(400)
                return Reply(200, dict(choices=[dict(message=dict(content='{"action":"search","query":"x"}'))], usage=dict(total_tokens=42, cost=0.0003)))
        client = Client()
        llm = verifier.OpenRouter('test-key', 'xiaomi/mimo-v2.6-flash', client=client)
        self.assertEqual(dict(text='{"action":"search","query":"x"}', tokens=42, usd=0.0003), llm.complete([dict(role='user', content='hi')]))
        llm.complete([dict(role='user', content='again')])
        # JSON mode is tried once; after a 400 the model is asked for JSON by prompt only.
        self.assertEqual(['response_format' in body for body in client.bodies], [True, False, False])
        self.assertEqual({'xiaomi/mimo-v2.6-flash'}, {body['model'] for body in client.bodies})
        self.assertEqual('Bearer test-key', client.headers[0]['authorization'])

    def test_openrouter_web_plugin_search_reads_annotations(self):
        class Client:
            def post(self, url, headers, json):
                self.body = json
                notes = [dict(type='url_citation', url_citation=dict(url=SITE, title='Bloom', content='x' * 900)),
                         dict(type='url_citation', url_citation=dict(url=SITE, title='duplicate')),
                         dict(type='url_citation', url_citation=dict(url='javascript:alert(1)', title='bad'))]
                reply = dict(choices=[dict(message=dict(content='', annotations=notes))], usage=dict(total_tokens=1650, cost=0.00723))
                return type('Reply', (), dict(status_code=200, json=lambda self: reply))()
        client = Client()
        found = verifier.OpenRouter('test-key', 'some/model', client=client).search('Bloom Peoria')
        self.assertEqual([dict(id='web', engine='exa', max_results=5)], client.body['plugins'])
        self.assertEqual('Bloom Peoria', client.body['messages'][-1]['content'])
        self.assertEqual([SITE], [r['url'] for r in found['results']])
        self.assertEqual(verifier.SNIPPET_CHARS, len(found['results'][0]['snippet']))
        self.assertEqual((1650, 0.00723), (found['tokens'], found['usd']))

    def test_comparison_counts_and_disagreements(self):
        one = verifier.verify_store(dict(STORE), Fetcher(), FakeLLM(dict(action='read', url=SITE), answer()), LIMITS)
        other_llm = FakeLLM(dict(action='read', url=SITE), answer(verdict='exists'))
        other_llm.model = 'other/model'
        two = verifier.verify_store(dict(STORE), Fetcher(), other_llm, LIMITS)
        three = verifier.verify_store(dict(STORE, id='s2'), Fetcher(), other_llm, dict(LIMITS, steps=1))
        summary = verifier.compare([one, two, three])
        self.assertEqual({'renamed': 1}, summary['models']['fake/model']['verdicts'])
        self.assertEqual({'verified': 1, 'budget_exceeded': 1}, summary['models']['other/model']['statuses'])
        self.assertEqual(2, summary['models']['fake/model']['kept_claims'])
        self.assertEqual({'s1': {'fake/model': 'renamed', 'other/model': 'exists'}}, summary['disagreements'])
        self.assertIsNotNone(one['seconds'])


class VerificationStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name)
        self.db = Store(path / 't.db', path / 'evidence')
        self.db.import_registry([observation()], 'source-evidence', '2026-10-08', now='2026-10-17T06:00:00+00:00')
        self.region = self.db.create_region(40.9844, -89.0388, 'ZIP 61358', 50)
        self.shop = self.db.stores_in_region(self.region['id'])[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_verdict_is_stored_reported_and_a_cited_menu_becomes_only_a_lead(self):
        claims = [dict(field='menu_url', value='https://x.example/menu/', url=SITE, quote='Shop the recreational menu')]
        llm = FakeLLM(dict(action='read', url=SITE), answer(claims=claims + answer()['claims'], menu_url='https://x.example/menu/'))
        record = verifier.verify_store(dict(self.shop), Fetcher(), llm, LIMITS)
        self.db.record_verification(record, now='2026-10-18T22:00:00+00:00')
        self.assertEqual(['https://x.example/menu/'], [lead['url'] for lead in self.db.leads(self.shop['id'])])
        self.assertEqual('verifier', self.db.leads(self.shop['id'])[0]['source'])
        self.assertEqual([], self.db.endpoints(self.shop['id']))
        row = self.db.stage_report(self.region['id'])['stores'][0]
        self.assertEqual('renamed', row['verification']['verdict'])
        self.assertEqual(3, row['verification']['claims'])
        self.assertAlmostEqual(0.002, self.db.verifier_spend_since('2026-10-18T00:00:00+00:00'))
        self.assertEqual(self.shop['name'], self.db.stores_in_region(self.region['id'])[0]['name'])

    def test_each_verdict_keeps_its_model_cost_tokens_and_time(self):
        for model in ('a/one', 'b/two', 'a/one'):
            llm = FakeLLM(dict(action='read', url=SITE), answer(), tokens=500, usd=0.004)
            llm.model = model
            self.db.record_verification(verifier.verify_store(dict(self.shop), Fetcher(), llm, LIMITS))
        rows = self.db.verifications(latest=False)
        self.assertEqual(['a/one', 'b/two', 'a/one'], [row['model'] for row in rows])
        self.assertEqual({(1000, 0.008)}, {(row['tokens'], row['usd']) for row in rows})
        self.assertTrue(all(row['seconds'] is not None for row in rows))
        latest = {row['model']: row['id'] for row in self.db.verifications(per_model=True)}
        self.assertEqual({'a/one': rows[2]['id'], 'b/two': rows[1]['id']}, latest)
        self.assertEqual(1, len(self.db.verifications()))

    def test_unverified_runs_do_not_appear_in_the_stage_report(self):
        record = verifier.verify_store(dict(self.shop), Fetcher(), FakeLLM(), dict(LIMITS, steps=1))
        self.db.record_verification(record)
        self.assertIsNone(self.db.stage_report(self.region['id'])['stores'][0]['verification'])

    def test_eligibility_follows_discovery_failure_codes(self):
        rows = [dict(store_id='a', stage='discovery_failed', code='NO_LEAD'), dict(store_id='b', stage='discovery_failed', code='TRANSPORT_ERROR'),
                dict(store_id='c', stage='extraction_failed', code='LEAD_UNVERIFIED'), dict(store_id='d', stage='discovery_failed', code='BRANCH_MISMATCH')]
        self.assertEqual(['a', 'd'], [row['store_id'] for row in verifier.eligible(rows)])


if __name__ == '__main__':
    unittest.main()
