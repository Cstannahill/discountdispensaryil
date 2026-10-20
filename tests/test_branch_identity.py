"""A branch is proven by its street and town; a store that changed its brand keeps its registry row and records the new name."""
import unittest

from backend.network import FetchResult
from backend.site_discovery import inspect_page


def page(url, text):
    return FetchResult(url, 200, text.encode(), {}, 'e-' + url[-20:], '2026-10-18T09:00:00Z')


PLAINFIELD = dict(name='Sample Wellness - Plainfield', address='12627 S Route 59', city='Plainfield', state='IL')


class AddressPrimaryIdentityTests(unittest.TestCase):
    def test_street_and_town_prove_a_branch_whose_page_uses_another_brand(self):
        # Same address, new brand on the page, no cannabis words: the location page still identifies the branch.
        found = inspect_page(PLAINFIELD, page('https://example.com/locations/plainfield/',
                                              '<h1>Welcome to our store</h1><p>12627 S Route 59, Plainfield, IL 60544</p>'))
        self.assertEqual('matched', found['identity_status'])

    def test_street_without_town_or_brand_still_proves_nothing(self):
        found = inspect_page(PLAINFIELD, page('https://example.com/', '<p>Visit us at 12627 S Route 59</p>'))
        self.assertNotEqual('matched', found['identity_status'])

    def test_structured_address_with_a_dropped_direction_matches_the_registry(self):
        store = dict(name='Starbuds Hoffman Estates', address='5 E Golf Rd', city='Hoffman Estates', state='IL')
        html = ('<script type="application/ld+json">{"@type":"Store","name":"Starbuds Hoffman Estates",'
                '"url":"https://shop.example.com/stores/hoffman-estates-dispensary/",'
                '"address":{"@type":"PostalAddress","streetAddress":"5 Golf Rd","addressLocality":"Hoffman Estates","addressRegion":"IL"}}'
                '</script><h1>Hoffman Estates</h1>')
        found = inspect_page(store, page('https://shop.example.com/stores/hoffman-estates-dispensary/', html))
        self.assertEqual('matched', found['identity_status'])
        self.assertEqual('Starbuds Hoffman Estates', found['matched_name'])

    def test_a_rebrand_names_the_matched_business_from_its_own_structured_data(self):
        html = ('<script type="application/ld+json">{"@type":"Store","name":"The Joint Dispensary - Plainfield",'
                '"url":"https://example.com/locations/plainfield/",'
                '"address":{"@type":"PostalAddress","streetAddress":"12627 S Route 59","addressLocality":"Plainfield","addressRegion":"IL"}}'
                '</script><h1>Plainfield</h1>')
        found = inspect_page(PLAINFIELD, page('https://example.com/locations/plainfield/', html))
        self.assertEqual('matched', found['identity_status'])
        self.assertEqual('The Joint Dispensary - Plainfield', found['matched_name'])


class RecordedRebrandTests(unittest.TestCase):
    def test_a_recorded_new_name_proves_the_same_store_by_name_and_town(self):
        store = dict(PLAINFIELD, name='Mission - Plainfield', aliases=['The Joint Dispensary - Plainfield'])
        found = inspect_page(store, page('https://example.com/menu/', '<h1>The Joint Dispensary - Plainfield</h1><p>Shop our menu</p>'))
        self.assertEqual('name_locality', found['identity_status'])


if __name__ == '__main__':
    unittest.main()
