from decimal import Decimal
import unittest

from backend.domain import edible_dose, normalize_offer, unit_value


def edible(name, price='15', **extra):
    item = dict(source_id='1', name=name, category='other', source_category='Edibles', effective_price=price, regular_price=price, conditional=False, available=True)
    item.update(extra)
    return normalize_offer(item)


class EdibleDoseTests(unittest.TestCase):
    def test_package_dose_in_the_name_is_the_total(self):
        for name, dose, count in (('Wyld - Gummies - Pear - 1:1 CBG:THC - 10ct (100mg)', '100', 10), ('Sour Mango - 10PK - 100MG', '100', 10), ('1906 Bliss Drops 20pk 100mg', '100', 20)):
            result = edible(name)
            self.assertEqual((result['category'], result['dose_mg'], result['pack_count']), ('edibles', dose, count), name)
            self.assertTrue(result['eligible'], name)

    def test_price_is_per_10mg_never_per_gram(self):
        result = edible('Gummies 10pk 100mg', '16')
        self.assertEqual(result['price_per_10mg'], '1.60')
        self.assertIsNone(result['price_per_gram'])
        self.assertIsNone(result['weight_grams'])
        self.assertEqual(unit_value(result), Decimal('1.6'))

    def test_small_dose_beside_a_piece_count_is_per_piece(self):
        for name, dose in (('PINK LEMONADE | 10MG | 5PK GUMMIES', '50'), ('Pomegranate | 10mg THC: 10mg CBD | 10pk Gummies', '100'), ('Mints 5mg each 20 pack', '100'), ('KSHN Pouches 10 x 10mg', '100')):
            self.assertEqual(edible(name)['dose_mg'], dose, name)

    def test_only_the_thc_figure_counts(self):
        self.assertEqual(edible('Lemon Lime (125mg CBD/25mg THC)')['dose_mg'], '25')
        self.assertEqual(edible('Gummy 100mg THC/50mg CBN')['dose_mg'], '100')
        self.assertEqual(edible('Gummy | 100mgTHC:20mgCBN')['dose_mg'], '100')
        self.assertEqual(edible('Incredibles 1:1 THC:CBC 100mg (10ct)')['dose_mg'], '100')
        self.assertEqual(edible('Pack 4 pack-12.5mg Hazelnut 50mg')['dose_mg'], '50')

    def test_ambiguous_or_missing_dose_is_not_invented(self):
        for name in ('Peach 2:1 CBD Gummies | 100mg :50mg', 'Chocolate Bar', 'CBD Mints 1000mg CBD 50pk'):
            result = edible(name)
            self.assertIsNone(result['dose_mg'], name)
            self.assertFalse(result['eligible'], name)
            self.assertIn('unknown_or_invalid_dose', result['exclusion_reasons'])
            self.assertIsNone(result['price_per_10mg'])

    def test_provider_fields_beat_the_name(self):
        verano = dict(variant=dict(unitSize=dict(unitAbbr='MG', value=10), unitsInPackage=10))
        self.assertEqual(edible('Rocket Pop Triple Infused', raw=verano)['dose_mg'], '100')
        sweed = dict(product=dict(variants=[dict(id=7, labTests=dict(thc=dict(unitAbbr='MG', value=[50])))]))
        self.assertEqual(edible('Sugar Free Minis', raw=sweed, variant_id='7')['dose_mg'], '50')
        dispense = dict(product=dict(labs=dict(thc=100, thcContentUnit='mg')))
        self.assertEqual(edible('Good Tide Gummies 10pk', raw=dispense)['dose_mg'], '100')

    def test_size_label_and_mg_as_grams_stand_in_when_the_name_is_silent(self):
        self.assertEqual(edible('Good Tide - Guava - Gummy', weight_label='100 MG')['dose_mg'], '100')
        self.assertEqual(edible('Cherry Fruit Chew', weight_grams='0.05', weight_label='.05g')['dose_mg'], '50')
        self.assertIsNone(edible('Capsules RSO', weight_grams='2', weight_label='2.0 grams')['dose_mg'])
        self.assertIsNone(edible('CBD Mint Tin', weight_grams='0.05', weight_label='1000mg CBD 50pk')['dose_mg'])

    def test_implausibly_cheap_doses_are_excluded(self):
        result = edible('Gummies 200mg', '1.75')
        self.assertFalse(result['eligible'])
        self.assertIn('implausible_price_per_dose', result['exclusion_reasons'])

    def test_edible_dose_reports_basis(self):
        self.assertEqual(edible_dose(dict(name='Gummy 100mg 10pk'))[2], 'package')
        self.assertEqual(edible_dose(dict(name='Gummy 5mg 20pk'))[2], 'per_piece_times_count')


from tests.test_storage import StorageTests, item as stored_item


class EdibleRankingTests(StorageTests):
    NOW = "2026-10-17T08:00:00+00:00"
    # Inherited tests would run again; only the edible checks below belong to this class.
    def ids(self, **kw):
        return [r["source_id"] for r in self.db.query_offers(self.region["id"], now=self.NOW, **kw)["items"]]

    def test_edibles_rank_per_10mg_and_stay_out_of_all_categories(self):
        self.apply([stored_item("flower", effective_price="35.00"),
                    stored_item("pricey", category="other", source_category="Edibles", name="Gummies 10pk 100mg", weight_grams=None, weight_label="", effective_price="25.00"),
                    stored_item("cheap", category="other", source_category="Edibles", name="Chews 20pk 100mg", weight_grams=None, weight_label="", effective_price="12.00"),
                    stored_item("nodose", category="other", source_category="Edibles", name="Chocolate", weight_grams=None, weight_label="", effective_price="5.00")])
        self.assertEqual(self.ids(category="edibles"), ["cheap", "pricey"])
        self.assertEqual(self.ids(), ["flower"])
        self.assertEqual(self.ids(category="edibles")[0], "cheap")
        top = self.db.query_offers(self.region["id"], now=self.NOW, category="edibles")["items"][0]
        self.assertEqual((top["dose_mg"], top["price_per_10mg"], top["pack_count"]), ("100", "1.20", 20))
        self.assertEqual(self.db.benchmark(self.region["id"], include_stale=True)["total_offers"], 1)


del StorageTests
