import json
from pathlib import Path
import unittest

from backend.domain import flower_grade, normalize_offer

LABELS = json.loads((Path(__file__).parent / "fixtures" / "categories" / "labels.json").read_text())


def offer(**changes):
    return dict(dict(source_id="x", name="Thing", category="other", source_category="Thing", weight_grams="1", effective_price="10",
                     conditional=False, available=True), **changes)


class CategoryMap(unittest.TestCase):
    def test_provider_labels_land_in_their_category(self):
        for category, rows in LABELS.items():
            if category in ("vapes", "concentrate", "other"):
                for provider, label in rows:
                    for given in (("other", label) if category != "other" else ("other",)):
                        with self.subTest(provider=provider, label=label, given=given):
                            self.assertEqual(normalize_offer(offer(category=given, source_category=label))["category"], category)

    def test_mapped_labels_become_eligible(self):
        self.assertTrue(normalize_offer(offer(category="other", source_category="Vape Cartridge"))["eligible"])

    def test_forms_that_are_not_concentrate_are_not_ranked(self):
        for name, sub in LABELS["not_concentrate"]:
            with self.subTest(name=name):
                result = normalize_offer(offer(name=name, subcategory=sub, category="concentrate", source_category="Extract"))
                self.assertEqual(result["category"], "other")
                self.assertFalse(result["eligible"])

    def test_real_concentrates_stay_ranked(self):
        for name, sub in LABELS["still_concentrate"]:
            with self.subTest(name=name):
                self.assertEqual(normalize_offer(offer(name=name, subcategory=sub, category="concentrate", source_category="Concentrates"))["category"], "concentrate")

    def test_kaviar_flower_is_infused(self):
        self.assertEqual(flower_grade({"category": "flower", "name": "Kaviar Gold 3.5g", "subcategory": ""}), "infused")


if __name__ == "__main__":
    unittest.main()
