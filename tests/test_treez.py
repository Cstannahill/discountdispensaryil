import copy
import json
import unittest
from urllib.parse import parse_qs,urlsplit

from backend.network import FetchResult
from backend.providers.treez import fetch,page_context,variants


def endpoint():return dict(url='https://example.com/shop',provider='treez',provider_store_id='store-1',license_type='recreational')


def source(identity,parent):
    return dict(id=identity,catalogParentId=parent,brand='Brand',category='FLOWER',name='Flower '+identity,slug='flower-'+identity,isActive=True,isAboveThreshold=True,
                productData=dict(size='3.5 g',pricing=dict(priceSell=25,discountedPrice=25,appliedDiscountIds=[]),inventory=[dict(customerType='ALL',availableUnits=10)]))


class CatalogFixture:
    def __init__(self,mode=None):self.mode=mode;self.calls=[]
    def document(self,page):
        groups=[('a',['a1','a2']),('b',['b1'])] if page==0 else [('c',['c1'])]
        if page==1 and self.mode in ('overlap','overlap_conflict','overlap_missing'):
            groups=[('b',['b1'])]+([] if self.mode=='overlap_missing' else groups)
        hits=[]
        for parent,ids in groups:
            children=[dict(_index='product_store-1',_source=source(identity,parent)) for identity in ids]
            for child in children:
                child['_source']['productData']['lastUpdateDate']='unmodeled-'+str(len(self.calls))
                if self.mode=='changing_price':child['_source']['productData']['pricing'].update(priceSell=25+len(self.calls),discountedPrice=25+len(self.calls))
                if self.mode=='overlap_conflict' and page==1 and parent=='b':child['_source']['productData']['pricing']['discountedPrice']=20
            hit=dict(_index='product_store-1',_source=children[0]['_source'],inner_hits=dict(siblings=dict(hits=dict(total=dict(value=len(children),relation='eq'),hits=children))))
            if self.mode=='truncated' and parent=='a':hit['inner_hits']['siblings']['hits']['hits']=children[:1]
            if self.mode=='wrong_index':hit['_index']='product_other-store'
            hits.append(hit)
        data=dict(hits=dict(total=dict(value=5 if self.mode=='wrong_total' or self.mode=='total_drift' and page==0 else 4,relation='eq'),hits=hits),aggregations=dict(productsCount=dict(value=99999)),timed_out=False,_shards=dict(failed=0))
        store=dict(object_id='other-store' if self.mode=='wrong_store' else 'store-1',short_name='store',address1='1 Main St')
        props=dict(selectedStore=store,initialSearchResponse='$2',initialPage=0 if self.mode=='repeated_page' else page,initialSearchFilter='',initialQueryFiltersByFacets={},products=[dict(catalogParentId=hit['_source']['catalogParentId'],url='/product/'+hit['_source']['catalogParentId']) for hit in hits])
        query=dict(queryKey=['products-search','store',None,'',dict(size=2,**{'from':page*2},collapse=dict(field='catalogParentId'))])
        return '\n'.join(key+':'+json.dumps(value) for key,value in [('1',props),('2',data),('3',query)])+'\n'
    def render_catalog(self,url,observe,**options):
        for _ in range(30):
            page=int(parse_qs(urlsplit(url).query).get('page',['1'])[0])-1
            self.calls.append(page)
            response=FetchResult(url,200,self.document(page).encode(),{'content-type':'text/x-component'},'capture-'+str(len(self.calls)),'2026-10-17T14:00:00Z')
            links=[dict(label='Go to page 1',url='https://example.com/shop?page=1')]
            if page==0:links.append(dict(label='Go to next page',url='https://example.com/shop?page=2'))
            decision=observe(response,dict(html='<script type="application/ld+json">{"offers":{"priceCurrency":"USD"}}</script>',links=links))
            if decision.get('reload'):continue
            if not decision.get('next_url'):return
            url=decision['next_url']
        raise AssertionError('Fixture traversal did not terminate')


class TreezTests(unittest.TestCase):
    def test_overlapping_page_is_rechecked_within_each_traversal_and_missing_variant_is_recovered(self):
        class Recovering(CatalogFixture):
            def __init__(self):super().__init__();self.reads=0
            def document(self,page):
                if page==1:self.reads+=1
                self.mode='overlap_missing' if page==1 and self.reads%2 else None
                return super().document(page)
        fixture=Recovering();result=fetch(endpoint(),fixture)
        self.assertTrue(result['complete'],result['errors'])
        self.assertEqual(fixture.calls,[0,1,1,0,1,1])
        self.assertEqual(len(result['items']),4)
        self.assertEqual([entry['page_recheck'] for entry in result['pages']],[0,0,1,0,0,1])

    def test_permanently_overlapping_page_rechecks_are_bounded_and_do_not_manufacture_completeness(self):
        fixture=CatalogFixture('overlap_missing');result=fetch(endpoint(),fixture)
        self.assertFalse(result['complete'])
        self.assertEqual(fixture.calls,[0,1,1,1]*3)
        self.assertEqual(len(result['items']),3)
        self.assertEqual(len(result['traversals']),3)

    def test_failed_verification_preserves_the_larger_traversal_without_merging_passes(self):
        class Interrupted(CatalogFixture):
            def document(self,page):
                if len(self.calls)==4:raise ValueError('Source connection failed during verification')
                return super().document(page)
        result=fetch(endpoint(),Interrupted())
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']),4)
        self.assertEqual(result['partial_items_traversal'],1)

    def test_identical_cross_page_overlap_is_deduplicated_but_conflicts_and_gaps_cannot_complete(self):
        result=fetch(endpoint(),CatalogFixture('overlap'))
        self.assertTrue(result['complete'],result['errors'])
        self.assertEqual(len(result['items']),4)
        self.assertEqual(result['pages'][1]['duplicate_variants'],1)
        for mode in ('overlap_conflict','overlap_missing'):
            with self.subTest(mode=mode):
                result=fetch(endpoint(),CatalogFixture(mode))
                self.assertFalse(result['complete'])
                self.assertTrue(result['errors'])

    def test_truncated_groups_expand_via_declared_detail_and_return_to_the_same_catalog_page(self):
        class DetailFixture(CatalogFixture):
            def render_catalog(self,url,observe,**options):
                history=[]
                for _ in range(30):
                    self.calls.append(url)
                    detail=urlsplit(url).path.startswith('/product/')
                    if detail:
                        siblings=[dict(id=identity,catalogParentId='a',name='Flower '+identity,size=['3.5 g'],qty=10,enabled=True,in_stock=True,variants=[dict(id=identity,price=2500,salePrice=2500)],pricing={},path_slug='flower-'+identity) for identity in ('a1','a2')]
                        body='1:'+json.dumps(dict(catalogParentId='a',siblings=siblings))+'\n';links=[]
                    else:
                        page=int(parse_qs(urlsplit(url).query).get('page',['1'])[0])-1
                        body=self.document(page);links=[dict(label='Go to page 1',url='https://example.com/shop?page=1')]
                        if page==0:links.append(dict(label='Go to next page',url='https://example.com/shop?page=2'))
                    response=FetchResult(url,200,body.encode(),{},'capture-'+str(len(self.calls)),'2026-10-17T14:00:00Z')
                    decision=observe(response,dict(html='<script type="application/ld+json">{"offers":{"priceCurrency":"USD"}}</script>',links=links,store_labels=['Pickup\n1 Main St']))
                    if decision.get('back'):url=history.pop();continue
                    if not decision.get('next_url'):return
                    history.append(url);url=decision['next_url']
                raise AssertionError('Expansion loop')
        fixture=DetailFixture('truncated');result=fetch(endpoint(),fixture)
        self.assertTrue(result['complete'],result['errors'])
        self.assertEqual(result['expected_count'],4)
        self.assertEqual(sum('/product/' in url for url in fixture.calls),2)

    def test_all_pages_and_expanded_variants_reconcile_without_trusting_approximate_cardinality(self):
        fixture=CatalogFixture();result=fetch(endpoint(),fixture)
        self.assertTrue(result['complete'],result['errors'])
        self.assertEqual(fixture.calls,[0,1,0,1])
        self.assertEqual(result['expected_count'],4)
        self.assertEqual(result['source_product_count'],3)
        self.assertEqual(result['items'][0]['weight_grams'],'3.5')
        self.assertFalse(result['items'][0]['conditional'])

    def test_wrong_store_wrong_index_truncated_variants_repeated_page_and_missing_records_stay_partial(self):
        for mode in ('wrong_store','wrong_index','truncated','repeated_page','wrong_total','total_drift'):
            with self.subTest(mode=mode):
                result=fetch(endpoint(),CatalogFixture(mode))
                self.assertFalse(result['complete'])
                self.assertTrue(result['errors'])

    def test_unstable_prices_are_bounded_and_partial_observations_survive(self):
        fixture=CatalogFixture('changing_price');result=fetch(endpoint(),fixture)
        self.assertFalse(result['complete'])
        self.assertEqual(len(fixture.calls),6)
        self.assertEqual(len(result['items']),4)

    def test_full_menu_traversal_cannot_silently_use_a_medical_context(self):
        result=fetch(dict(endpoint(),license_type='medicinal'),CatalogFixture())
        self.assertFalse(result['complete'])
        self.assertIn('license changed',result['errors'][0]['message'])

    def test_applied_customer_condition_is_excluded_but_unapplied_promotions_do_not_poison_regular_price(self):
        from backend.providers.treez import normalize
        product=source('a1','a');product['productData']['discounts']=[dict(discountId='medical',discountConditions=[dict(type='Customer Group',value='MEDICAL')],discountAffinity='Cart')]
        self.assertFalse(normalize(product,product,endpoint())['conditional'])
        product['productData']['pricing'].update(discountedPrice=20,appliedDiscountIds=['medical'])
        self.assertTrue(normalize(product,product,endpoint())['conditional'])
