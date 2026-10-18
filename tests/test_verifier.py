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
SEARCH = ('<ol><li class="b_algo"><h2><a href="https://bloomwellness.example/peoria/">Bloom Wellness Peoria</a></h2>'
          '<p>Formerly Beyond/Hello Peoria</p></li></ol>')


class Response:
    def __init__(self, url, text, status=200, number=0):
        self.url, self.status_code, self.body = url, status, text.encode()
        self.evidence_id, self.fetched_at = f'ev-{number}', '2026-10-18T22:00:00Z'


class Fetcher:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        if 'bing.com' in url:
            return Response(url, SEARCH, number=len(self.urls))
        if url == SITE:
            return Response(url, PAGE, number=len(self.urls))
        return Response(url, 'not found', 404, len(self.urls))


class FakeLLM:
    model = 'fake/model'

    def __init__(self, *replies, tokens=100, usd=0.001):
        self.replies, self.tokens, self.usd, self.seen = list(replies), tokens, usd, []

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
    def run_verifier(self, llm, limits=LIMITS, **kwargs):
        fetcher = Fetcher()
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
        record, _ = self.run_verifier(FakeLLM(usd=0.02), dict(LIMITS, usd=0.05))
        self.assertEqual(('budget_exceeded', 3), (record['status'], record['steps']))
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
