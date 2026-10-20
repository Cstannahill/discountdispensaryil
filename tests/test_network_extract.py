import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backend.network_extract import extract_products, load_captured, find_product_arrays

JANE = json.loads(Path('tests/fixtures/network_json/jane_multi.json').read_text(encoding='utf-8'))
URL = 'https://www.philidispensary.com/our-menu/'


def flat(count, **changes):
    products = [dict(dict(id=1000 + i, name=f'Flower {i}', brand={'name': 'Brand'}, category='Flower', price=25.0 + i,
                          weight=3.5, unit='g', in_stock=True), **changes) for i in range(count)]
    return {'data': {'products': products, 'total': count + 100}}


class JaneShapeTests(unittest.TestCase):
    def setUp(self):
        self.result = extract_products([(URL, JANE)], URL)

    def test_finds_the_product_collection_and_its_source_total(self):
        self.assertEqual(len(self.result['items']), 11)
        self.assertEqual(self.result['total'], 759)
        self.assertEqual(self.result['collections'][0]['count'], 11)

    def test_weight_price_family_becomes_a_variant_with_regular_and_effective_price(self):
        item = next(i for i in self.result['items'] if i['name'] == 'Bananaconda')
        self.assertEqual((item['variant_id'], item['weight_grams'], item['regular_price'], item['effective_price']),
                         ('eighth_ounce', '3.5', '55', '38.5'))
        self.assertEqual((item['category'], item['brand'], item['available'], item['conditional']), ('flower', 'RYTHM', True, False))
        self.assertEqual(item['source_id'], '1897723')

    def test_half_gram_vape_maps_to_vapes(self):
        item = next(i for i in self.result['items'] if i['name'] == 'Evercrisp')
        self.assertEqual((item['category'], item['weight_grams'], item['effective_price']), ('vapes', '0.5', '35'))

    def test_only_listed_available_weights_are_available(self):
        product = json.loads(json.dumps(JANE['placements'][0]['products'][0]))
        attrs = product['search_attributes']
        attrs['price_gram'], attrs['discounted_price_gram'] = 12, 12
        collection = {'products': [product] * 3, 'nb_hits': 5}
        items = extract_products([(URL, {'placements': [collection]})], URL)['items']
        by = {i['variant_id']: i for i in items}
        self.assertTrue(by['eighth_ounce']['available'])
        self.assertFalse(by['gram']['available'])

    def test_per_unit_prices_and_empty_weight_lists_leave_stock_unknown(self):
        product = json.loads(json.dumps(JANE['placements'][0]['products'][0]))
        product['search_attributes'].update(available_weights=[], price_each=20, discounted_price_each=20)
        for key in ('price_eighth_ounce', 'discounted_price_eighth_ounce'):
            product['search_attributes'].pop(key)
        items = extract_products([(URL, {'p': [product] * 3})], URL)['items']
        self.assertEqual([(i['variant_id'], i['available']) for i in items], [('each', None)])

    def test_cart_total_specials_make_a_price_conditional(self):
        product = json.loads(json.dumps(JANE['placements'][0]['products'][0]))
        product['search_attributes']['applicable_cart_total_special_ids'] = [99]
        items = extract_products([(URL, {'p': [product] * 3})], URL)['items']
        self.assertTrue(items[0]['conditional'])


class GenericShapeTests(unittest.TestCase):
    def test_flat_rest_shape_with_total(self):
        result = extract_products([('https://shop.example/api/products', flat(12))], URL)
        self.assertEqual(len(result['items']), 12)
        self.assertEqual(result['total'], 112)
        item = result['items'][0]
        self.assertEqual((item['name'], item['brand'], item['category'], item['weight_grams'], item['effective_price'], item['available']),
                         ('Flower 0', 'Brand', 'flower', '3.5', '25', True))

    def test_facets_events_and_small_arrays_are_not_products(self):
        noise = {'searchFacets': {'kind': {'flower': 258, 'vape': 119}}, 'events': [{'type': 'view', 'ts': i} for i in range(20)],
                 'rows': [{'name': 'a', 'price': 1}, {'name': 'b', 'price': 2}]}
        self.assertEqual(extract_products([(URL, noise)], URL)['items'], [])
        self.assertEqual(list(find_product_arrays(noise)), [])

    def test_union_across_responses_dedupes_by_identity(self):
        result = extract_products([('https://a.example/p1', flat(10)), ('https://a.example/p2', flat(10))], URL)
        self.assertEqual(len(result['items']), 10)

    def test_ids_are_required_or_the_product_is_skipped(self):
        data = flat(10)
        for p in data['data']['products'][:4]:
            p.pop('id')
        self.assertEqual(len(extract_products([(URL, data)], URL)['items']), 6)

    def test_unknown_price_shape_yields_no_items(self):
        data = {'products': [dict(id=i, name='x', price='call us') for i in range(10)]}
        self.assertEqual(extract_products([(URL, data)], URL)['items'], [])


class LoadCapturedTests(unittest.TestCase):
    def test_reads_json_bodies_from_the_render_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = json.dumps(flat(12)).encode()
            sha = hashlib.sha256(body).hexdigest()
            (root / 'bodies' / sha[:2]).mkdir(parents=True)
            (root / 'bodies' / sha[:2] / (sha + '.gz')).write_bytes(gzip.compress(body))
            (root / 'manifests').mkdir()
            (root / 'manifests' / 'e1.json').write_text(json.dumps({'body_path': f'bodies/{sha[:2]}/{sha}.gz', 'status_code': 200}))
            (root / 'browser').mkdir()
            (root / 'browser' / 'render1.json').write_text(json.dumps({'network_json': [
                {'evidence_id': 'e1', 'url': 'https://shop.example/api/products', 'method': 'GET', 'status': 200, 'bytes': len(body)},
                {'evidence_id': 'missing', 'url': 'https://shop.example/x', 'method': 'GET', 'status': 200, 'bytes': 5},
                {'evidence_id': 'e1', 'url': 'https://shop.example/err', 'method': 'GET', 'status': 500, 'bytes': 5}]}))
            captured = load_captured(root, 'render1')
            self.assertEqual([url for url, _ in captured], ['https://shop.example/api/products'])
            self.assertEqual(len(extract_products(captured, URL)['items']), 12)
            self.assertEqual(load_captured(root, 'nope'), [])


if __name__ == '__main__':
    unittest.main()


class LargestCollectionTotalTests(unittest.TestCase):
    def test_a_featured_rows_hit_count_does_not_override_the_catalog_total(self):
        catalog = {'placement': 'menu_inline_table', 'nb_hits': 30, 'products': flat(30)['data']['products']}
        featured = {'placement': 'menu_dynamic_row', 'nb_hits': 31, 'products': flat(5)['data']['products']}
        result = extract_products([(URL, {'placements': [catalog, featured]})], URL)
        self.assertEqual(result['total'], 30)
        self.assertEqual(len(result['items']), 30)


class SkeletonTests(unittest.TestCase):
    def test_id_only_placeholders_do_not_hide_the_hydrated_products(self):
        hydrated = flat(60)['data']['products']
        bare = [{'object_id': str(i), 'product_id': 9000 + i, 'store_id': 1, 'ad_token': 'x'} for i in range(699)]
        data = {'placements': [{'placement': 'menu_inline_table', 'nb_hits': 759, 'products': hydrated + bare}]}
        result = extract_products([(URL, data)], URL)
        self.assertEqual(len(result['items']), 60)
        self.assertEqual(result['total'], 759)

    def test_an_array_that_is_only_placeholders_is_not_a_menu(self):
        bare = [{'object_id': str(i), 'product_id': i} for i in range(50)]
        self.assertEqual(extract_products([(URL, {'p': bare})], URL)['items'], [])


class LastPageTests(unittest.TestCase):
    def test_a_short_last_page_counts_once_its_path_is_a_proven_collection(self):
        full = {'data': {'products': flat(10)['data']['products']}}
        last = {'data': {'products': flat(12)['data']['products'][10:]}}
        result = extract_products([(URL, full), (URL, last)], URL)
        self.assertEqual(len(result['items']), 12)

    def test_a_small_array_alone_is_still_not_a_menu(self):
        self.assertEqual(extract_products([(URL, {'data': {'products': flat(2)['data']['products']}})], URL)['items'], [])


DUTCHIE = json.loads(Path('tests/fixtures/network_json/dutchie_filtered_products.json').read_text(encoding='utf-8'))
DUTCHIE_URL = 'https://dutchie.com/api-1/graphql?operationName=FilteredProducts&variables=' + json.dumps(
    {'productsFilter': {'dispensaryId': 'x', 'types': ['Flower'], 'strainTypes': [], 'subcategories': []}})
DUTCHIE_ALL_URL = 'https://dutchie.com/api-1/graphql?operationName=FilteredProducts&variables=' + json.dumps(
    {'productsFilter': {'dispensaryId': 'x', 'types': [], 'strainTypes': [], 'subcategories': []}})


class DutchieShapeTests(unittest.TestCase):
    def setUp(self):
        self.result = extract_products([(DUTCHIE_URL, DUTCHIE)], 'https://dutchie.com/embedded-menu/x')
        self.by = {(i['name'], i['variant_id']): i for i in self.result['items']}

    def test_parallel_option_and_price_arrays_become_variants_with_recreational_special_price(self):
        item = self.by[('&Shine Pre-Pack - Durban Candy', '1oz')]
        self.assertEqual((item['weight_grams'], item['regular_price'], item['effective_price'], item['category'], item['strain_type']),
                         ('28', '160', '95', 'flower', item['strain_type']))

    def test_multi_option_product_expands_each_option(self):
        quarter = self.by[('Good Green Ground Flower - Hybrid', '1_4oz')]
        half = self.by[('Good Green Ground Flower - Hybrid', '1_2oz')]
        self.assertEqual((quarter['weight_grams'], quarter['regular_price'], quarter['effective_price']), ('7', '40', '30'))
        self.assertEqual((half['weight_grams'], half['regular_price'], half['effective_price']), ('14', '70', '52.5'))

    def test_availability_comes_from_active_status_and_online_thresholds(self):
        self.assertTrue(all(i['available'] is True for i in self.result['items']))
        data = json.loads(json.dumps(DUTCHIE))
        for p in data['data']['filteredProducts']['products']:
            p['optionsBelowThreshold'] = list(p['Options'])
        self.assertTrue(all(i['available'] is False for i in extract_products([(DUTCHIE_URL, data)], URL)['items']))
        for p in data['data']['filteredProducts']['products']:
            p.pop('optionsBelowThreshold')
        self.assertTrue(all(i['available'] is None for i in extract_products([(DUTCHIE_URL, data)], URL)['items']))

    def test_query_info_total_is_read_and_marks_a_filtered_collection(self):
        self.assertEqual(self.result['total'], 272)
        self.assertTrue(self.result['collections'][0]['filtered'])
        self.assertFalse(extract_products([(DUTCHIE_ALL_URL, DUTCHIE)], URL)['collections'][0]['filtered'])

    def test_conflicting_totals_resolve_to_the_larger_so_a_partial_union_cannot_reconcile(self):
        all_page = json.loads(json.dumps(DUTCHIE))
        all_page['data']['filteredProducts']['queryInfo']['totalCount'] = 90
        for p in all_page['data']['filteredProducts']['products']:
            p['_id'] = p['id'] = 'other' + p['id']
        result = extract_products([(DUTCHIE_URL, DUTCHIE), (DUTCHIE_ALL_URL, all_page)], URL)
        self.assertEqual(result['total'], 272)

    def test_medical_license_uses_medical_prices_and_skips_recreational_only_products(self):
        data = json.loads(json.dumps(DUTCHIE))
        data['data']['filteredProducts']['products'][0]['medicalSpecialPrices'] = [88]
        data['data']['filteredProducts']['products'][1]['recOnly'] = True
        items = extract_products([(DUTCHIE_URL, data)], URL, license_type='medicinal')['items']
        first = next(i for i in items if i['name'].startswith('&Shine'))
        self.assertEqual(first['effective_price'], '88')
        self.assertNotIn('Good Green Prepack - Gas Guzzler', {i['name'] for i in items})

    def test_dose_and_unit_options_do_not_invent_package_mass(self):
        data = json.loads(json.dumps(DUTCHIE))
        for p in data['data']['filteredProducts']['products']:
            p['Options'] = ['100mg'] * len(p['Options'])
        self.assertTrue(all(i['weight_grams'] is None for i in extract_products([(DUTCHIE_URL, data)], URL)['items']))


def dutchie_page(url_filter, total, count=4, prefix='x'):
    page = json.loads(json.dumps(DUTCHIE))
    products = page['data']['filteredProducts']['products'][:count]
    for i, p in enumerate(products):
        p['_id'] = p['id'] = f'{prefix}{i}'
    page['data']['filteredProducts'] = dict(products=products, queryInfo=dict(totalCount=total, totalPages=2))
    return ('https://dutchie.com/api-1/graphql?operationName=FilteredProducts&variables=' + json.dumps({'productsFilter': url_filter, 'page': 0}), page)


class WholeCatalogTotalTests(unittest.TestCase):
    base = {'dispensaryId': 'd', 'pricingType': 'rec', 'Status': 'Active', 'strainTypes': [], 'subcategories': [], 'sortBy': 'popularSortIdx'}

    def test_unknown_narrowing_flags_are_not_a_whole_menu(self):
        staff = dutchie_page(dict(self.base, types=[], staffPicks=True), 19, prefix='s')
        flower = dutchie_page(dict(self.base, types=['Flower']), 50, prefix='f')
        edible = dutchie_page(dict(self.base, types=['Edible']), 30, prefix='e')
        result = extract_products([staff, flower, edible], URL)
        self.assertEqual(result['total'], 80)
        self.assertTrue(all(c['filtered'] for c in result['collections']))

    def test_categories_sum_to_the_total_without_a_whole_menu_query(self):
        flower = dutchie_page(dict(self.base, types=['Flower']), 50, prefix='f')
        flower_page2 = dutchie_page(dict(self.base, types=['Flower']), 50, prefix='g')
        edible = dutchie_page(dict(self.base, types=['Edible']), 30, prefix='e')
        self.assertEqual(extract_products([flower, flower_page2, edible], URL)['total'], 80)

    def test_a_whole_menu_total_larger_than_the_category_sum_is_kept(self):
        whole = dutchie_page(dict(self.base, types=[]), 120, prefix='w')
        flower = dutchie_page(dict(self.base, types=['Flower']), 50, prefix='f')
        self.assertEqual(extract_products([whole, flower], URL)['total'], 120)

    def test_a_category_whose_products_never_arrived_cannot_be_summed_into_the_total(self):
        flower = dutchie_page(dict(self.base, types=['Flower']), 50, prefix='f')
        edible = dutchie_page(dict(self.base, types=['Edible']), 30, prefix='e')
        self.assertEqual(extract_products([flower, edible], URL)['total'], 80)
        self.assertIsNone(extract_products([flower, edible], URL, category_gaps=1)['total'])


class UncapturedCategoryTests(unittest.TestCase):
    def test_visited_product_pages_without_a_response_are_reported_and_other_visits_are_not(self):
        from backend.network_extract import uncaptured_categories
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'browser').mkdir()
            visited = [dict(link='https://m.example/embedded-menu/s/products/flower', pages=0, captured=True),
                       dict(link='https://m.example/embedded-menu/s/products/edibles', pages=0, captured=False),
                       dict(link='https://m.example/embedded-menu/s/collections/back', pages=0, captured=False),
                       dict(link='https://m.example/embedded-menu/s/products/topicals', pages=0)]
            (Path(folder) / 'browser' / 'render1.json').write_text(json.dumps(dict(scroll=dict(explore=dict(visited=visited)))), encoding='utf-8')
            self.assertEqual(uncaptured_categories(folder, 'render1'), ['https://m.example/embedded-menu/s/products/edibles'])
            self.assertEqual(uncaptured_categories(folder, 'missing'), [])


class IdHydrationCategoryTotalTests(unittest.TestCase):
    base = WholeCatalogTotalTests.base

    def test_an_id_chunk_query_contributes_its_categorys_total(self):
        flower = dutchie_page(dict(self.base, types=['Flower']), 50, prefix='f')
        chunk = dutchie_page(dict(self.base, types=['Topicals'], productIds=['a', 'b']), 4, prefix='t')
        result = extract_products([flower, chunk], URL)
        self.assertEqual(result['total'], 54)
        self.assertEqual({c['category'] for c in result['collections']}, {'Flower', 'Topicals'})


class RowsTotalTests(unittest.TestCase):
    def page(self, category, start, count, rows):
        products = [dict(id=f'{category}{start + i}', name=f'{category} {start + i}', brand='B', price=20 + i, weight=3.5, unit='g', in_stock=True) for i in range(count)]
        return (f'https://api.example.com/p/inventory?category={category}&limit=50&offset={start}', {'rows': rows, 'data': products})

    def test_a_root_level_rows_count_is_the_declared_total(self):
        result = extract_products([self.page('flower', 0, 12, 12)], URL)
        self.assertEqual((len(result['items']), result['total']), (12, 12))

    def test_category_query_parameters_partition_the_total(self):
        pages = [self.page('flower', 0, 10, 25), self.page('flower', 10, 10, 25), self.page('vapes', 0, 10, 15)]
        result = extract_products(pages, URL)
        self.assertEqual(result['total'], 40)
        self.assertEqual({c['category'] for c in result['collections']}, {'flower', 'vapes'})
