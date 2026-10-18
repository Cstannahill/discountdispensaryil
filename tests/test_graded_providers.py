"""Grade B contracts: a provider may claim convergence only when each pass reconciled and only live churn differs."""
from dataclasses import replace
import copy
import json
import unittest

from backend.network import FetchResult
from backend.providers.generic import fetch as generic_fetch
from backend.providers import dispense
from test_generic_menu import Fixture as GenericFixture
from test_dispense import Fixture as DispenseFixture, ENDPOINT as DISPENSE_ENDPOINT


class CounterFixture(GenericFixture):
    """No structured total; the page itself displays a product count."""
    def __init__(self, count, shown=None, mode='no_total', churn=None):
        super().__init__(count, mode)
        self.shown, self.churn, self.pass_number = shown if shown is not None else count, churn, 1

    def get(self, url):
        result = super().get(url)
        text = result.body.decode()
        if url.endswith('/menu') and len(self.calls) > 1 and self.calls.count(url) > 1:
            self.pass_number = 2
        body = f'<h2>All {self.shown} products</h2>' + text
        if self.churn and len(self.calls) > self.churn['after_calls']:
            body = body.replace('"price": "25"', '"price": "20"') if self.churn['kind'] == 'price' else body.replace('Product 3"', 'Renamed 3"')
        return replace(result, body=body.encode())


ENDPOINT = dict(url='https://example.com/menu', provider='generic', license_type='recreational')


class GenericVisibleCounterTests(unittest.TestCase):
    def test_matching_visible_counter_with_stable_passes_is_convergence_not_completion(self):
        result = generic_fetch(ENDPOINT, CounterFixture(150))
        self.assertFalse(result['complete'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['items']), 150)
        c = result['convergence']
        self.assertEqual((c['kind'], c['passes'], c['agreement'], c['observed'], c['source_total']), ('visible_counter', 2, True, 150, 150))

    def test_displayed_count_that_does_not_match_stays_partial(self):
        result = generic_fetch(ENDPOINT, CounterFixture(150, shown=400))
        self.assertFalse(result['complete'])
        self.assertNotIn('convergence', result)
        self.assertIn('no independently verifiable', result['errors'][0]['message'])

    def test_small_menu_cannot_converge_on_a_counter(self):
        result = generic_fetch(ENDPOINT, CounterFixture(10))
        self.assertNotIn('convergence', result)
        self.assertTrue(result['errors'])

    def test_price_churn_between_passes_is_explained(self):
        result = generic_fetch(ENDPOINT, CounterFixture(150, churn=dict(after_calls=2, kind='price')))
        self.assertEqual(result['errors'], [], result['errors'])
        self.assertEqual(result['convergence']['kind'], 'visible_counter')
        self.assertGreater(result['convergence']['detail']['explained_changes'], 0)

    def test_identity_change_between_passes_is_not_convergence(self):
        result = generic_fetch(ENDPOINT, CounterFixture(150, churn=dict(after_calls=2, kind='rename')))
        self.assertNotIn('convergence', result)
        self.assertIn('changed across', result['errors'][0]['message'])

    def test_structured_total_still_gives_unqualified_completion(self):
        result = generic_fetch(ENDPOINT, GenericFixture(150))
        self.assertTrue(result['complete'])
        self.assertNotIn('convergence', result)


class PriceChurnDispense(DispenseFixture):
    def get(self, url, headers=None):
        result = super().get(url, headers)
        if url.split('?')[0].endswith('/products') and self.calls > 4:
            value = json.loads(result.body)
            value['data'][0]['price'] = '99'
            result = replace(result, body=json.dumps(value).encode())
        return result


class DispenseChurnTests(unittest.TestCase):
    def test_price_churn_between_complete_passes_is_grade_b_convergence(self):
        result = dispense.fetch(DISPENSE_ENDPOINT, PriceChurnDispense(250))
        self.assertFalse(result['complete'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['convergence']['kind'], 'churn_tolerant')

    def test_missing_records_remain_hard_failures(self):
        result = dispense.fetch(DISPENSE_ENDPOINT, DispenseFixture(250, 'missing'))
        self.assertTrue(result['errors'])
        self.assertNotIn('convergence', result)


if __name__ == '__main__':
    unittest.main()
