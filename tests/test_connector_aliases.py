"""A store that changed brand is looked up on its current brand's locator, not only on the registry brand's."""
import unittest

from backend.locators import connector_for


class ConnectorForStoreTests(unittest.TestCase):
    def test_a_recorded_rebrand_selects_its_locator_before_the_registry_name(self):
        store = dict(name='Beyond/Hello - Peoria', aliases=[dict(name='Bloom Wellness - Peoria')])
        self.assertEqual('https://risecannabis.com/dispensaries/illinois/', connector_for(store))

    def test_the_registry_name_selects_its_locator_without_a_rebrand(self):
        self.assertEqual('https://beyond-hello.com/illinois-dispensaries/', connector_for(dict(name='Beyond/Hello - Peoria')))

    def test_a_brand_with_no_locator_has_none(self):
        self.assertIsNone(connector_for(dict(name='Sample Wellness - Plainfield')))


if __name__ == '__main__':
    unittest.main()
