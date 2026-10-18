import unittest
from backend.completeness import (visible_total, churn_tolerant_equal, valid_convergence, grade_for, counts_reconcile,
                                  MIN_CONVERGED_ITEMS)


def row(identity, **changes):
    return dict(dict(source_id=identity, variant_id='base', name='Flower ' + identity, brand='B', category='flower',
                     weight_grams='3.5', regular_price='40.00', effective_price='35.00', available=True,
                     eligible=True, exclusion_reasons=[], price_per_gram='10.00', raw={'x': identity}), **changes)


def menu(n, **changes):
    return {(f'p{i}', 'base'): row(f'p{i}', **changes) for i in range(n)}


class VisibleTotalTests(unittest.TestCase):
    def test_reads_common_phrasings(self):
        self.assertEqual(visible_total('<h2>759 products</h2>'), 759)
        self.assertEqual(visible_total('Showing 1-48 of 1,204 results'), 1204)
        self.assertEqual(visible_total('Displaying 1 to 24 of 310 items'), 310)

    def test_takes_the_largest_so_category_counts_do_not_win(self):
        self.assertEqual(visible_total('All 759 products Flower 120 products Vapes 80 products'), 759)

    def test_absent_or_implausible_returns_none(self):
        self.assertIsNone(visible_total('Welcome to our dispensary'))
        self.assertIsNone(visible_total('0 products'))
        self.assertIsNone(visible_total(''))

    def test_script_and_style_text_is_ignored(self):
        self.assertIsNone(visible_total('<script>var s="500 products"</script><p>hello</p>'))


class ChurnTests(unittest.TestCase):
    def test_identical_menus_agree(self):
        ok, detail = churn_tolerant_equal(menu(200), menu(200))
        self.assertTrue(ok)
        self.assertEqual(detail['membership_changes'], 0)

    def test_price_and_stock_changes_on_shared_items_are_explained(self):
        a, b = menu(200), menu(200)
        b[('p3', 'base')] = row('p3', effective_price='30.00', price_per_gram='8.57')
        b[('p4', 'base')] = row('p4', available=False, eligible=False, exclusion_reasons=['unavailable_or_unknown_stock'])
        ok, detail = churn_tolerant_equal(a, b)
        self.assertTrue(ok)
        self.assertEqual(detail['explained_changes'], 2)

    def test_identity_field_change_is_not_explained(self):
        a, b = menu(200), menu(200)
        b[('p3', 'base')] = row('p3', name='Different product')
        self.assertFalse(churn_tolerant_equal(a, b)[0])

    def test_membership_difference_within_one_percent(self):
        a, b = menu(200), menu(200)
        del b[('p1', 'base')]
        b[('new', 'base')] = row('new')
        self.assertTrue(churn_tolerant_equal(a, b)[0])
        for i in range(2, 6):
            del b[(f'p{i}', 'base')]
        self.assertFalse(churn_tolerant_equal(a, b)[0])

    def test_small_menus_get_no_membership_slack(self):
        a, b = menu(50), menu(50)
        del b[('p1', 'base')]
        self.assertFalse(churn_tolerant_equal(a, b)[0])


class ConvergenceTests(unittest.TestCase):
    good = dict(kind='visible_counter', passes=2, agreement=True, source_total=300, observed=300)

    def test_requires_known_kind_two_passes_and_agreement(self):
        self.assertTrue(valid_convergence(self.good))
        for bad in (None, {}, dict(self.good, kind='guess'), dict(self.good, passes=1), dict(self.good, agreement=False),
                    dict(self.good, observed=MIN_CONVERGED_ITEMS - 1)):
            self.assertFalse(valid_convergence(bad), bad)

    def test_counts_reconcile_exact_or_one_percent(self):
        self.assertTrue(counts_reconcile(759, 759))
        self.assertTrue(counts_reconcile(1000, 995))
        self.assertFalse(counts_reconcile(1000, 950))
        self.assertTrue(counts_reconcile(1000, 1000))
        self.assertFalse(counts_reconcile(40, 39))

    def test_grades(self):
        self.assertEqual(grade_for('complete', True), 'A')
        self.assertEqual(grade_for('converged', True), 'B')
        self.assertEqual(grade_for('partial', True), 'C')
        self.assertEqual(grade_for('partial', False), 'D')
        self.assertEqual(grade_for('suspicious', True), 'C')


if __name__ == '__main__':
    unittest.main()
