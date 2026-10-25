import copy
import json
import math
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

from backend.failures import FailureCode, classify
from backend.network import FetchResult
from backend.providers.dutchie import fetch, whole_menu_filter

ROOT = Path('tests/fixtures/provider_dutchie')
PRODUCTS = json.loads((ROOT / 'products.json').read_text(encoding='utf-8'))
DISPENSARY = json.loads((ROOT / 'dispensary.json').read_text(encoding='utf-8'))
OBSERVED = json.loads((ROOT / 'observed.json').read_text(encoding='utf-8'))
DISPENSARY_ID = '65772a69ac53410009424572'
HASH = 'cfbda410fd502c77b467a174a666b809bec1e61c70ee7f75de1aff7440b59bf4'
ENDPOINT = dict(url='https://dutchie.com/embedded-menu/' + DISPENSARY_ID, provider='dutchie', provider_store_id=DISPENSARY_ID, license_type='recreational')
TARGET = dict(name='Noxx - East Peoria', address='300 S Main St', city='East Peoria', state='IL', latitude=40.66587, longitude=-89.58316)


def query(url):
    values = parse_qs(urlsplit(url).query)
    return values['operationName'][0], json.loads(values['variables'][0]), json.loads(values['extensions'][0])


class DutchieFixture:
    """Recorded page queries, dispensary record and product records, served through the page-read protocol: the
    provider asks for same-origin GETs, the 'page' answers them. Counts drive Dutchie's paging (perPage, totalPages)."""
    def __init__(self, total, mode=None, observed=None, products=None):
        self.total, self.mode, self.observed, self.products = total, mode, observed or OBSERVED, products or PRODUCTS
        self.browser_options = {'target_store': TARGET}
        self.rendered, self.reads, self.traversals = [], [], 0

    def product(self, index, traversal):
        record = copy.deepcopy(self.products[index % len(self.products)])
        record.update(id=f'p{index}', _id=f'p{index}', Name=f"{record['Name']} #{index}", DispensaryID=DISPENSARY_ID)
        if self.mode == 'other_dispensary' and index == 3:
            record['DispensaryID'] = '627458da5d75a3008f52fc56'
        if self.mode == 'unreadable' and index == 2:
            record['recPrices'] = record['recPrices'] + [99]
        if self.mode == 'churn' and traversal == 2 and index == 5:
            record['recPrices'] = [p + 1 for p in record['recPrices']]
        return record

    def answer(self, read):
        self.reads.append(read)
        parts = urlsplit(read['url'])
        operation, variables, extensions = query(read['url'])
        if self.mode == 'blocked':
            return dict(url=read['url'], status=403, body='<!DOCTYPE html><title>Attention Required! | Cloudflare</title>')
        if operation == 'ConsumerDispensaries':
            value = copy.deepcopy(DISPENSARY)
            record = value['data']['filteredDispensaries'][0]
            if self.mode == 'other_address':
                record['location'].update(ln1='2440 28th St SE', city='Grand Rapids', state='MI', geometry=dict(coordinates=[-85.6, 42.9]))
            if self.mode == 'far_same_street':
                record['location']['geometry']['coordinates'] = [-87.63, 41.88]
            if self.mode == 'rec_closed':
                record['recDispensary'] = False
            return dict(url=read['url'], status=200, body=json.dumps(value))
        assert operation == 'FilteredProducts' and parts.path.endswith('/graphql'), read['url']
        if self.mode == 'drift':
            return dict(url=read['url'], status=200, body=json.dumps({'errors': [{'message': 'PersistedQueryNotFound'}]}))
        page, per = variables['page'], variables['perPage']
        if page == 0:
            self.traversals += 1
        traversal = self.traversals
        total = self.total + (1 if self.mode == 'changed_total' and traversal == 2 else 0)
        indices = list(range(page * per, min(total, (page + 1) * per)))
        if self.mode == 'short_page' and page == 0:
            indices = indices[:-1]
        if self.mode == 'repeat' and page == 1:
            indices = [0] + indices[1:]
        info = dict(totalCount=total, totalPages=math.ceil(total / per))
        body = dict(data=dict(filteredProducts=dict(products=[self.product(i, traversal) for i in indices], queryInfo=info)))
        return dict(url=read['url'], status=200, body=json.dumps(body))

    def render_reads(self, url, page_reader, *, license_type='recreational'):
        self.rendered.append((url, license_type))
        # The page looks its dispensary up by the id or cName in its own URL.
        key = url.split('/embedded-menu/')[1].split('/')[0]
        observed = [dict(o, url=o['url'].replace('cNameOrID%22%3A%22' + DISPENSARY_ID, 'cNameOrID%22%3A%22' + key)) for o in self.observed]
        message = dict(url=url, observed=observed, results=[])
        for _ in range(500):
            reply = page_reader(message)
            reads = (reply or {}).get('reads') or []
            if not reads:
                break
            assert len(reads) <= 8
            message = dict(url=url, results=[self.answer(read) for read in reads])
        return FetchResult(url, 200, b'<html></html>', {}, 'ev-render', '2026-10-18T09:00:00Z')


def products_read(fixture):
    return [query(r['url']) + (r,) for r in fixture.reads if 'operationName=FilteredProducts' in r['url']]


class DutchieTests(unittest.TestCase):
    def test_full_menu_reconciles_to_the_query_total_over_two_traversals(self):
        fixture = DutchieFixture(250)
        result = fetch(ENDPOINT, fixture)
        self.assertTrue(result['complete'], result['errors'])
        self.assertEqual(result['source_product_count'], 250)
        self.assertEqual(fixture.traversals, 2)
        self.assertEqual(len(result['pages']), 6)
        self.assertEqual(len({i['source_id'] for i in result['items']}), 250)
        self.assertEqual(result['expected_count'], len(result['items']))
        self.assertIn('ev-render', result['evidence'])
        self.assertEqual(fixture.rendered, [('https://dutchie.com/embedded-menu/' + DISPENSARY_ID + '/products?sortby=pricelowtohigh', 'recreational')])

    def test_the_persisted_query_hash_path_and_headers_come_from_the_page_own_query(self):
        observed = copy.deepcopy(OBSERVED)
        for entry in observed:
            if 'operationName=FilteredProducts' in entry['url']:
                entry['url'] = entry['url'].replace(HASH, 'ab' * 32).replace('/api-1/', '/api-2/')
        fixture = DutchieFixture(120, observed=observed)
        result = fetch(ENDPOINT, fixture)
        self.assertTrue(result['complete'], result['errors'])
        reads = products_read(fixture)
        self.assertTrue(reads)
        for _, _, extensions, read in reads:
            self.assertEqual(extensions['persistedQuery']['sha256Hash'], 'ab' * 32)
            self.assertEqual(urlsplit(read['url']).path, '/api-2/graphql')
            self.assertEqual(read['headers'].get('apollographql-client-name'), 'Marketplace (production)')
        self.assertEqual(result['query']['sha256Hash'], 'ab' * 32)

    def test_reads_keep_the_storefront_explicit_sort_from_the_page_query(self):
        # The default "Featured" order ties: Cloud9 East Peoria repeated 2 and dropped 2 of 1458 products across page
        # boundaries. The storefront's own "Price low to high" view pages deterministically, so the page is rendered there.
        fixture = DutchieFixture(150)
        self.assertTrue(fetch(ENDPOINT, fixture)['complete'])
        observed = query(next(o['url'] for o in OBSERVED if 'operationName=FilteredProducts' in o['url']))[1]['productsFilter']
        self.assertEqual((observed['sortBy'], observed['isDefaultSort']), ('price', False))
        for _, variables, _, _ in products_read(fixture):
            self.assertEqual((variables['productsFilter']['sortBy'], variables['productsFilter']['sortDirection'], variables['productsFilter']['isDefaultSort']), ('price', 1, False))

    def test_a_page_that_never_issued_its_product_query_is_drift_not_a_guess(self):
        observed = [o for o in OBSERVED if 'operationName=FilteredProducts' not in o['url']]
        result = fetch(ENDPOINT, DutchieFixture(10, observed=observed))
        self.assertFalse(result['complete'])
        self.assertEqual(classify(result['errors'][0]['message']), FailureCode.DRIFT)

    def test_whole_menu_reads_drop_narrowing_filters_and_keep_products_below_option_thresholds(self):
        # The storefront hides products whose every option is below its online threshold *after* counting them,
        # so its own query returns 1042 of an advertised 1053. Keeping them (marked unavailable) reconciles exactly.
        observed_filter = dict(productIds=['x'], dispensaryId='other', pricingType='rec', types=['Flower'], strainTypes=['Indica'],
                               subcategories=['shake'], staffPicks=True, isOnSpecial=True, Status='Active', isDefaultSort=True, sortDirection=1,
                               removeProductsBelowOptionThresholds=True, platformType='ONLINE_MENU', bypassOnlineThresholds=False)
        built = whole_menu_filter(observed_filter, DISPENSARY_ID, 'med')
        self.assertEqual(built['dispensaryId'], DISPENSARY_ID)
        self.assertEqual(built['pricingType'], 'med')
        self.assertEqual((built['types'], built['strainTypes'], built['subcategories']), ([], [], []))
        self.assertFalse(built['removeProductsBelowOptionThresholds'])
        for key in ('productIds', 'staffPicks', 'isOnSpecial'):
            self.assertNotIn(key, built)
        fixture = DutchieFixture(30)
        fetch(ENDPOINT, fixture)
        for _, variables, _, _ in products_read(fixture):
            self.assertEqual(variables['productsFilter']['dispensaryId'], DISPENSARY_ID)
            self.assertFalse(variables['productsFilter']['removeProductsBelowOptionThresholds'])
            self.assertEqual(variables['perPage'], 100)

    def test_branch_is_proven_by_the_platform_declared_street_address(self):
        result = fetch(ENDPOINT, DutchieFixture(10))
        self.assertEqual(result['branch_proof']['method'], 'platform_address')
        self.assertEqual(result['branch_proof']['dispensary_id'], DISPENSARY_ID)
        self.assertEqual(result['branch_proof']['street'], '300 S Main St')
        # A slug endpoint is the same dispensary when the platform says that slug is its cName.
        slug = fetch(dict(ENDPOINT, provider_store_id='noxx-peoria', url='https://dutchie.com/embedded-menu/noxx-peoria'), DutchieFixture(10))
        self.assertTrue(slug['complete'], slug['errors'])

    def test_wrong_branch_is_refused_as_a_branch_mismatch(self):
        for mode in ('other_address', 'far_same_street'):
            result = fetch(ENDPOINT, DutchieFixture(10, mode=mode))
            self.assertFalse(result['complete'], mode)
            self.assertEqual(classify(result['errors'][0]['message']), FailureCode.BRANCH_MISMATCH, mode)
        other = fetch(dict(ENDPOINT, provider_store_id='627458da5d75a3008f52fc56'), DutchieFixture(10))
        self.assertFalse(other['complete'])
        self.assertEqual(classify(other['errors'][0]['message']), FailureCode.BRANCH_MISMATCH)

    def test_branch_cannot_be_proven_without_a_registry_address(self):
        fixture = DutchieFixture(10)
        fixture.browser_options = {'target_store': dict(TARGET, address=None)}
        self.assertIn('cannot be proven', fetch(ENDPOINT, fixture)['errors'][0]['message'])

    def test_license_context_is_the_dispensary_own(self):
        result = fetch(ENDPOINT, DutchieFixture(10, mode='rec_closed'))
        self.assertFalse(result['complete'])
        self.assertEqual(classify(result['errors'][0]['message']), FailureCode.GATE_LICENSE)
        fixture = DutchieFixture(10)
        medical = fetch(dict(ENDPOINT, license_type='medicinal'), fixture)
        self.assertTrue(medical['complete'], medical['errors'])
        self.assertEqual(fixture.rendered[0][1], 'medicinal')
        self.assertEqual({v['productsFilter']['pricingType'] for _, v, _, _ in products_read(fixture)}, {'med'})

    def test_prices_weights_specials_and_thresholds_come_from_the_record(self):
        result = fetch(ENDPOINT, DutchieFixture(len(PRODUCTS)))
        self.assertTrue(result['complete'], result['errors'])
        items = {(PRODUCTS[int(i['source_id'][1:])]['Name'], i['weight_label']): i for i in result['items']}
        shake = [i for (name, label), i in items.items() if label == '1/4oz' and i['category'] == 'flower']
        self.assertEqual(len(shake), 1)
        self.assertEqual(shake[0]['weight_grams'], '7')
        self.assertEqual(float(shake[0]['regular_price']), 40)
        self.assertEqual(float(shake[0]['effective_price']), 30)
        self.assertFalse(shake[0]['conditional'])
        below = [i for i in result['items'] if PRODUCTS[int(i['source_id'][1:])]['optionsBelowThreshold']]
        self.assertTrue(below)
        self.assertTrue(all(i['available'] is False for i in below))

    def test_a_sale_special_with_restrictions_is_a_conditional_price(self):
        restricted = copy.deepcopy(PRODUCTS)
        for record in restricted:
            for special in (record.get('specialData') or {}).get('saleSpecials') or []:
                special['specialRestrictions'] = {'minimumQuantity': 2}
        result = fetch(ENDPOINT, DutchieFixture(len(restricted), products=restricted))
        on_sale = [i for i in result['items'] if float(i['effective_price']) < float(i['regular_price'])]
        self.assertTrue(on_sale)
        self.assertTrue(all(i['conditional'] for i in on_sale))

    def test_short_repeated_foreign_or_unreadable_pages_never_complete(self):
        for mode in ('short_page', 'repeat', 'other_dispensary', 'unreadable', 'changed_total', 'drift'):
            result = fetch(ENDPOINT, DutchieFixture(150, mode=mode))
            self.assertFalse(result['complete'], mode)
            self.assertTrue(result['errors'], mode)
        self.assertEqual(classify(fetch(ENDPOINT, DutchieFixture(150, mode='short_page'))['errors'][0]['message']), FailureCode.COUNT_MISMATCH)
        self.assertEqual(classify(fetch(ENDPOINT, DutchieFixture(150, mode='changed_total'))['errors'][0]['message']), FailureCode.UNSTABLE)

    def test_a_refused_read_is_reported_not_worked_around(self):
        fixture = DutchieFixture(10, mode='blocked')
        result = fetch(ENDPOINT, fixture)
        self.assertFalse(result['complete'])
        self.assertEqual(classify(result['errors'][0]['message']), FailureCode.CHALLENGE_BLOCKED)
        self.assertEqual(len(fixture.reads), 1)

    def test_price_churn_between_traversals_is_graded_converged_not_complete(self):
        result = fetch(ENDPOINT, DutchieFixture(150, mode='churn'))
        self.assertFalse(result['complete'])
        self.assertEqual(result['convergence']['kind'], 'churn_tolerant')
        self.assertEqual(result['source_product_count'], 150)
        self.assertFalse(result['errors'])

    def test_dutchie_endpoints_are_read_by_the_native_provider(self):
        from backend.adapters import fetch_menu, provider_capabilities
        from backend.service import NATIVE_PROVIDERS
        self.assertTrue(provider_capabilities('dutchie')['native_full_menu'])
        self.assertIn('dutchie', NATIVE_PROVIDERS)
        result = fetch_menu(ENDPOINT, DutchieFixture(10))
        self.assertEqual(result['adapter_version'], 'dutchie-filtered-products-1')
        self.assertTrue(result['complete'], result['errors'])

    def test_a_non_dispensary_path_segment_is_not_rendered(self):
        fixture = DutchieFixture(10)
        result = fetch(dict(ENDPOINT, provider_store_id='v2', url='https://dutchie.com/api/v2/embedded-menu/64888ad400476b00104ffe4d.js'), fixture)
        self.assertFalse(result['complete'])
        self.assertEqual(fixture.rendered, [])


if __name__ == '__main__':
    unittest.main()
