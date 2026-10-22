"""Each saved endpoint records how its website was found, so LLM dependence can be counted rather than inferred."""
import unittest

from backend.service import discovery_source


class DiscoverySourceTests(unittest.TestCase):
    def test_a_saved_web_search_query_marks_the_endpoint_as_llm_web_search(self):
        endpoint = dict(url='https://shop.example/menu', locator_evidence=[dict(query='"1 Main St" Town IL dispensary menu', url='https://openrouter.ai/x')])
        self.assertEqual('llm_web_search', discovery_source(endpoint, []))

    def test_a_verifier_lead_on_the_same_host_marks_the_endpoint_as_a_verifier_lead(self):
        leads = [dict(source='verifier', url='https://shop.example/')]
        self.assertEqual('llm_verifier_lead', discovery_source(dict(url='https://www.shop.example/menu', locator_evidence=[]), leads))

    def test_an_operator_lead_is_operator_seeded_and_beats_a_verifier_lead(self):
        leads = [dict(source='verifier', url='https://shop.example/'), dict(source='operator', url='https://shop.example/menu')]
        self.assertEqual('operator', discovery_source(dict(url='https://shop.example/menu', locator_evidence=[]), leads))

    def test_a_chain_list_page_marks_the_endpoint_as_chain_locator(self):
        endpoint = dict(url='https://chain.example/stores/a', locator_evidence=[dict(url='https://chain.example/stores', evidence_id='e1')])
        self.assertEqual('chain_locator', discovery_source(endpoint, []))

    def test_a_hosted_store_id_in_the_menu_url_is_a_provider_id(self):
        endpoint = dict(url='https://rise.example/x/6926/menu', locator_evidence=[], resolution_evidence=dict(method='Rise-hosted Jane store id in the menu URL'))
        self.assertEqual('provider_id', discovery_source(endpoint, []))

    def test_anything_else_is_a_crawl(self):
        self.assertEqual('crawl', discovery_source(dict(url='https://shop.example/menu', locator_evidence=[]), []))


if __name__ == '__main__':
    unittest.main()
