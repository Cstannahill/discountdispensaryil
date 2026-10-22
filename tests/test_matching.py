import unittest

from backend.matching import flag_outliers, group_offers, product_key


def offer(store, name, brand, price, grams=3.5, category="flower", **extra):
    return {**dict(id=f"{store}:{name}:{grams}", store_id=store, store_name=store, name=name, brand=brand, category=category,
                   weight_grams=str(grams), effective_price=str(price), flower_grade="whole" if category == "flower" else None,
                   distance_miles=1.0), **extra}


class ProductKeyTests(unittest.TestCase):
    def test_same_product_across_menu_styles(self):
        a = product_key(offer("a", "Pastries #34 Popcorn", "Simply Herb", 38))
        b = product_key(offer("b", "Simply Herb - Pastries #34 Popcorn (3.5g)", "Simply Herb™", 40))
        c = product_key(offer("c", "PASTRIES #34 popcorn | 3.5g", "simply herb", 41))
        self.assertIsNotNone(a)
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_vape_form_words_and_strain_letter_do_not_split_products(self):
        a = product_key(offer("a", "WTF Extracts - AIO Distillate - Fruit Punch (S) (1.0g)", "WTF Extracts", 35, 1, "vapes"))
        b = product_key(offer("b", "Fruit Punch Cartridge", "WTF Extracts", 33, 1, "vapes"))
        self.assertEqual(a, b)

    def test_size_category_and_brand_keep_products_apart(self):
        base = product_key(offer("a", "Gush Mints", "Simply Herb", 24))
        self.assertNotEqual(base, product_key(offer("a", "Gush Mints", "Simply Herb", 40, 7)))
        self.assertNotEqual(base, product_key(offer("a", "Gush Mints", "Other Brand", 24)))
        self.assertNotEqual(base, product_key(offer("a", "Gush Mints", "Simply Herb", 24, 3.5, "concentrate")))
        self.assertNotEqual(base, product_key(offer("a", "Gush Mints Shake", "Simply Herb", 24, flower_grade="shake")))
        self.assertNotEqual(product_key(offer("a", "Mints", "Simply Herb", 24)), product_key(offer("a", "Gush", "Simply Herb", 24)))

    def test_generic_or_brandless_names_have_no_key(self):
        self.assertIsNone(product_key(offer("a", "Sativa", "InHouse", 30, 1, "concentrate")))
        self.assertIsNone(product_key(offer("a", "Gush Mints", "", 24)))
        self.assertIsNone(product_key(offer("a", "Simply Herb 3.5g", "Simply Herb", 24)))


class OutlierTests(unittest.TestCase):
    def test_price_far_below_other_stores_is_flagged(self):
        offers = [offer("a", "Velvet Ropes", "Superflux", 7.2), offer("b", "Velvet Ropes", "Superflux", 55), offer("c", "Velvet Ropes", "Superflux", 50)]
        flagged = {o["store_id"] for o in flag_outliers(offers) if o["price_outlier"]}
        self.assertEqual(flagged, {"a"})

    def test_ordinary_spread_is_kept(self):
        offers = [offer("a", "Velvet Ropes", "Superflux", 30), offer("b", "Velvet Ropes", "Superflux", 55)]
        self.assertFalse(any(o["price_outlier"] for o in flag_outliers(offers)))

    def test_unmatched_product_is_never_flagged(self):
        offers = [offer("a", "Solo", "Brand", 1), offer("b", "Other", "Brand", 50)]
        self.assertFalse(any(o["price_outlier"] for o in flag_outliers(offers)))

    def test_store_whose_comparable_prices_are_mostly_outliers_is_suspect_throughout(self):
        offers = []
        for i in range(6):
            offers += [offer("bad", f"Gelato {i}x", "Brand", 6), offer("g1", f"Gelato {i}x", "Brand", 40), offer("g2", f"Gelato {i}x", "Brand", 42)]
        offers.append(offer("bad", "Unmatched thing", "Brand", 5))
        flagged = flag_outliers(offers)
        self.assertTrue(all(o["price_outlier"] for o in flagged if o["store_id"] == "bad"))
        self.assertFalse(any(o["price_outlier"] for o in flagged if o["store_id"] != "bad"))

    def test_input_is_not_mutated(self):
        offers = [offer("a", "Velvet Ropes", "Superflux", 7.2), offer("b", "Velvet Ropes", "Superflux", 55)]
        flag_outliers(offers)
        self.assertNotIn("price_outlier", offers[0])


class GroupTests(unittest.TestCase):
    def test_groups_rank_by_cheapest_and_list_every_store(self):
        offers = [offer("a", "Gush Mints", "Simply Herb", 30), offer("b", "Gush Mints", "Simply Herb", 24), offer("b", "Solo", "Simply Herb", 10)]
        groups = group_offers(offers, min_stores=2)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual((g["best"]["store_id"], g["store_count"]), ("b", 2))
        self.assertEqual([o["store_id"] for o in g["offers"]], ["b", "a"])
        self.assertEqual(g["savings_vs_highest_pct"], 20.0)

    def test_one_store_listing_the_product_twice_counts_once(self):
        offers = [offer("a", "Gush Mints", "Simply Herb", 30), offer("a", "Gush Mints", "Simply Herb", 28)]
        self.assertEqual(group_offers(offers, min_stores=2), [])
        self.assertEqual(group_offers(offers, min_stores=1)[0]["store_count"], 1)


if __name__ == "__main__":
    unittest.main()
