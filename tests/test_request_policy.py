import json
import unittest

from backend.request_policy import decide, is_graphql_mutation, POLICIES

PAGE = 'https://www.philidispensary.com/our-menu/'
ALGOLIA = 'https://search.iheartjane.com/1/indexes/menu-products-production/query'


def post(policy, url, body=None, content_type='application/json'):
    return decide(policy, method='POST', url=url, body=json.dumps(body) if not isinstance(body, str) and body is not None else body,
                  content_type=content_type, page_url=PAGE)


class RequestPolicyTests(unittest.TestCase):
    def test_reads_are_always_allowed(self):
        for policy in POLICIES:
            for method in ('GET', 'HEAD', 'OPTIONS'):
                self.assertTrue(decide(policy, method=method, url='https://x.example/a', page_url=PAGE)['allowed'])

    def test_strict_matches_the_original_exact_allowlist(self):
        self.assertTrue(post('strict', ALGOLIA, {'query': ''})['allowed'])
        for url in ('https://events.launchdarkly.com/events/bulk/x', 'https://id.iheartjane.com/1', 'https://api.fpjs.io/'):
            self.assertFalse(post('strict', url, {'a': 1})['allowed'], url)

    def test_unknown_policy_fails_closed_to_strict(self):
        self.assertFalse(post('nonsense', 'https://id.iheartjane.com/1', {'a': 1})['allowed'])

    def test_platform_reads_allows_platform_family_posts_only(self):
        self.assertTrue(post('platform_reads', 'https://id.iheartjane.com/1', {'a': 1})['allowed'])
        self.assertTrue(post('platform_reads', 'https://dutchie.com/api-4/graphql', [{'operationName': 'FilteredProducts', 'query': 'query FilteredProducts { x }'}])['allowed'])
        for url in ('https://events.launchdarkly.com/events/bulk/x', 'https://api.fpjs.io/', 'https://www.google-analytics.com/g/collect',
                    'https://fd-api.cleantalk.org/frontend_data/v2', 'https://evil.example/iheartjane.com'):
            self.assertFalse(post('platform_reads', url, {'a': 1})['allowed'], url)

    def test_lookalike_hosts_are_not_platform_family(self):
        self.assertFalse(post('platform_reads', 'https://iheartjane.com.evil.example/x', {'a': 1})['allowed'])
        self.assertFalse(post('platform_reads', 'https://notiheartjane.com/x', {'a': 1})['allowed'])

    def test_graphql_mutations_and_account_paths_are_never_allowed(self):
        mutation = [{'operationName': 'AddToCart', 'query': 'mutation AddToCart($i: ID!) { addToCart(id: $i) { id } }'}]
        for policy in ('platform_reads', 'diagnostic_posts'):
            self.assertFalse(post(policy, 'https://dutchie.com/api-4/graphql', mutation)['allowed'], policy)
            self.assertFalse(post(policy, 'https://dutchie.com/api/checkout', {'a': 1})['allowed'], policy)
            self.assertFalse(post(policy, 'https://shop.example/account/login', {'a': 1})['allowed'], policy)
            self.assertFalse(post(policy, 'https://dutchie.com/api-4/graphql', {'operationName': 'CreateOrder', 'query': 'query X { y }'})['allowed'], policy)

    def test_oversized_or_non_json_bodies_are_refused_outside_strict(self):
        self.assertFalse(post('platform_reads', 'https://id.iheartjane.com/1', 'x' * 70000)['allowed'])
        self.assertFalse(post('platform_reads', 'https://id.iheartjane.com/1', 'a=1&b=2', 'application/x-www-form-urlencoded')['allowed'])

    def test_json_body_sent_as_text_plain_is_judged_by_its_content(self):
        self.assertTrue(post('platform_reads', 'https://id.iheartjane.com/1', '{"a": 1}', 'text/plain;charset=UTF-8')['allowed'])
        self.assertFalse(post('platform_reads', 'https://id.iheartjane.com/1', 'a=1', 'text/plain')['allowed'])

    def test_diagnostic_posts_allows_other_hosts_but_is_explicitly_a_diagnostic(self):
        decision = post('diagnostic_posts', 'https://events.launchdarkly.com/events/bulk/x', {'a': 1})
        self.assertTrue(decision['allowed'])
        self.assertEqual(decision['rule'], 'diagnostic_posts')

    def test_mutation_detection(self):
        self.assertTrue(is_graphql_mutation('{"query": "mutation { a }"}'))
        self.assertTrue(is_graphql_mutation('[{"query": "query A { a }"}, {"query": "  # c\\n mutation B { b }"}]'))
        self.assertFalse(is_graphql_mutation('{"query": "query Q { mutationCount }"}'))
        self.assertFalse(is_graphql_mutation('not json'))
        self.assertFalse(is_graphql_mutation(None))


if __name__ == '__main__':
    unittest.main()


class TelemetryTests(unittest.TestCase):
    def test_platform_hosts_do_not_get_to_send_tracking_beacons(self):
        for url in ('https://dmerch.iheartjane.com/v2/event/1', 'https://tjs.iheartjane.com/capture', 'https://user-events.iheartjane.com/track/x'):
            self.assertFalse(post('platform_reads', url, {'a': 1})['allowed'], url)
        for url in ('https://dmerch.iheartjane.com/v2/smartpage', 'https://dmerch.iheartjane.com/v2/multi', 'https://dmerch.iheartjane.com/v2/facets'):
            self.assertTrue(post('platform_reads', url, {'a': 1})['allowed'], url)
