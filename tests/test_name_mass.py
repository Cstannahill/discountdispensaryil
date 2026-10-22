import json
from pathlib import Path
import unittest

from backend.domain import normalize_offer
from backend.network_extract import extract_products

URL = 'https://www.iheartjane.com/stores/1/menu'
JANE = json.loads(Path('tests/fixtures/network_json/jane_name_mass.json').read_text(encoding='utf-8'))


def offer(name, grams, price='25'):
    return normalize_offer(dict(source_id='1', name=name, category='vapes', weight_grams=grams, effective_price=price, regular_price=price, conditional=False, available=True))


class NameMassTests(unittest.TestCase):
    def test_a_name_dose_that_disagrees_with_the_option_label_excludes_the_offer(self):
        result = offer('Happy Hour [300mg]', '0.5', '12.5')
        self.assertFalse(result['eligible'])
        self.assertIn('conflicting_package_mass', result['exclusion_reasons'])

    def test_a_name_gram_pack_that_disagrees_excludes_the_offer(self):
        for name in ('Velvet Ropes [4g]', 'Velvet Ropes [2.5g]', 'Velvet Ropes (4 g)', 'Velvet Ropes [4 Grams]'):
            self.assertIn('conflicting_package_mass', offer(name, '0.5', '120')['exclusion_reasons'], name)

    def test_agreeing_or_absent_name_mass_stays_eligible(self):
        for name, grams in (('Cart [500mg]', '0.5'), ('Cart [1g]', '1'), ('Cart [.5g]', '0.5'), ('Flower 3.5g bag', '3.5'), ('Cart', '1'), ('Mix [1g] (3.5g)', '3.5')):
            result = offer(name, grams)
            self.assertTrue(result['eligible'], name)
            self.assertNotIn('conflicting_package_mass', result['exclusion_reasons'])

    def test_a_pipe_delimited_trailing_mass_is_the_stated_package(self):
        self.assertIn('conflicting_package_mass', offer('Blue Dream Cartridge ( H ) | .5g', '0.05', '17.55')['exclusion_reasons'])
        self.assertTrue(offer('Blue Dream Cartridge ( H ) | .5g', '0.5', '17.55')['eligible'])
        self.assertTrue(offer('Gummies 10pk | 100mg THC', '3.5')['eligible'])

    def test_a_package_under_a_tenth_of_a_gram_in_a_priced_category_is_a_label_error(self):
        for name in ('AIRO PURPLE PINA COLADA LIVE ROSIN POD', 'Relief RSO', 'KANHA OG BLACKBERRY CARTRIDGE'):
            self.assertIn('implausible_package_mass', offer(name, '0.05', '40')['exclusion_reasons'], name)
        for grams in ('0.1', '0.3', '0.5', '1', '3.5'):
            self.assertNotIn('implausible_package_mass', offer('Cart', grams)['exclusion_reasons'], grams)

    def test_unbracketed_doses_are_not_package_mass(self):
        self.assertTrue(offer('Gummies 100mg THC', '3.5')['eligible'])

    def test_jane_half_gram_price_on_a_300mg_name_is_excluded_end_to_end(self):
        items = {i['name']: normalize_offer(dict(i, conditional=False, available=True)) for i in extract_products([(URL, JANE)], URL)['items']}
        self.assertIn('conflicting_package_mass', items['Happy Hour [300mg]']['exclusion_reasons'])
        self.assertIn('conflicting_package_mass', items['Velvet Ropes [4g]']['exclusion_reasons'])
        self.assertTrue(items['Plain Cart']['eligible'])


if __name__ == '__main__':
    unittest.main()
