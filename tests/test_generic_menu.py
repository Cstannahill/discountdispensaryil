from dataclasses import replace
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from backend.network import FetchResult
from backend.providers.generic import fetch


class Fixture:
    def __init__(self,count=1103,mode=None):self.count,self.mode,self.calls=count,mode,[]
    def get(self,url):
        self.calls.append(url)
        page=int(parse_qs(urlsplit(url).query).get('page',['1'])[0])
        records=[{'@type':'Product','sku':str(i),'name':'Product '+str(i),'category':'Flower','weight':{'value':3.5,'unitCode':'GRM'},'offers':{'price':'25','priceCurrency':'USD','availability':'https://schema.org/InStock'},'url':'https://example.com/products/'+str(i)} for i in range((page-1)*100,min(page*100,self.count))]
        if self.mode=='duplicate' and page>1:records[0]['sku']='0'
        data={'@type':'ItemList','name':'All products','numberOfItems':self.count,'itemListElement':records}
        if self.mode=='featured':data['name']='Featured products'
        if self.mode=='no_total':data.pop('numberOfItems')
        text='<script type="application/ld+json">'+json.dumps(data)+'</script>'
        if page*100<self.count:text+=f'<a rel="next" href="?page={page+1}">Next</a>'
        return FetchResult(url,200,text.encode(),{},'evidence-'+str(len(self.calls)),'2026-10-17T09:00:00Z')


class GenericMenuTests(unittest.TestCase):

    def test_explicit_strikethrough_specification_preserves_regular_price(self):
        from backend.providers.generic import normalize
        p={'sku':'sale','name':'Sale Flower','offers':{'price':'35','priceCurrency':'USD','priceSpecification':[{'price':'50','priceCurrency':'USD','priceType':'https://schema.org/StrikethroughPrice'}]}}
        item=normalize(p,self.endpoint())[0]
        self.assertEqual(item['regular_price'],'50');self.assertEqual(item['effective_price'],'35')
        p['offers']['priceSpecification'].append({'price':'60','priceCurrency':'USD','priceType':'https://schema.org/StrikethroughPrice'})
        self.assertEqual(normalize(p,self.endpoint())[0]['regular_price'],'35')
        for malformed in [17,True,'incorrect']:
            p['offers']['priceSpecification']=malformed
            self.assertEqual(normalize(p,self.endpoint())[0]['regular_price'],'35')



    def test_traversal_rejects_wrong_branch_before_collecting_its_products(self):
        class BranchFixture(Fixture):
            browser_options={'target_store':dict(name='Example Cannabis',city='Rutland',state='IL',address='1 Main St')}
            def get(self,url):
                r=super().get(url);street='99 Other St' if 'page=2' in url else '1 Main St'
                schema={'@type':'Store','url':url,'address':{'streetAddress':street,'addressLocality':'Rutland','addressRegion':'IL'}}
                return replace(r,body=r.body+('<script type="application/ld+json">'+json.dumps(schema)+'</script>').encode())
        result=fetch(self.endpoint(),BranchFixture(150))
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']),100)
        self.assertIn('branch',result['errors'][0]['message'].lower())

    def test_redirects_and_explicit_license_changes_do_not_publish_catalogs(self):
        for destination in ['https://other.example/menu','https://example.com/menu/medical']:
            class RedirectFixture(Fixture):
                def get(self,url):
                    r=super().get(url);return replace(r,url=destination)
            result=fetch(self.endpoint(),RedirectFixture(3))
            self.assertFalse(result['complete'],destination)
            self.assertEqual(result['items'],[])

    def test_raw_metadata_changes_do_not_make_stable_inventory_partial(self):
        class MetadataFixture(Fixture):
            def get(self,url):
                r=super().get(url)
                body=r.body.replace(b'"name": "Product 0"',('"trackingTimestamp": '+str(len(self.calls))+', "name": "Product 0"').encode())
                return replace(r,body=body)
        result=fetch(self.endpoint(),MetadataFixture(3))
        self.assertTrue(result['complete'],result['errors'])


    def test_browser_selected_branch_context_is_preserved_for_both_catalog_passes(self):
        class BrowserBranch(Fixture):
            def get(self,url):raise AssertionError('Static HTML would reset the selected branch')
            def render(self,url,**options):return Fixture.get(self,url)
        fixture=BrowserBranch(3)
        result=fetch(dict(self.endpoint(),requires_browser_context=True),fixture)
        self.assertTrue(result['complete'],result['errors'])
        self.assertEqual(len(fixture.calls),2)

    def test_offer_url_is_a_declared_stable_product_identity(self):
        from backend.providers.generic import normalize
        product={'@type':'Product','name':'Observed Flower','offers':{'url':'https://example.com/product/flower','price':'25','priceCurrency':'USD'}}
        item=normalize(product,self.endpoint())[0]
        self.assertEqual(item['source_id'],'https://example.com/product/flower')
        self.assertEqual(item['source_url'],'https://example.com/product/flower')
        self.assertIsNone(item['available'])

    def test_carousel_total_is_not_a_full_menu_completeness_proof(self):
        result=fetch(self.endpoint(),Fixture(3,'featured'))
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']),3)
    def endpoint(self):return dict(url='https://example.com/menu',provider='generic',license_type='recreational')
    def test_generic_structured_catalog_over_thousand_requires_all_pages_and_two_passes(self):
        result=fetch(self.endpoint(),Fixture())
        self.assertTrue(result['complete'],result['errors'])
        self.assertEqual(len(result['items']),1103)
        self.assertEqual(len(result['pages']),24)
        self.assertEqual(result['items'][0]['weight_grams'],'3.5')
    def test_unadvertised_total_retains_observations_but_cannot_authorize_removals(self):
        result=fetch(self.endpoint(),Fixture(150,'no_total'))
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']),150)
    def test_duplicate_pages_and_page_limits_are_partial(self):
        for fixture,extra in [(Fixture(250,'duplicate'),{}),(Fixture(250),{'max_pages':1})]:
            result=fetch(dict(self.endpoint(),**extra),fixture)
            self.assertFalse(result['complete'])
            self.assertTrue(result['errors'])
    def test_marketing_page_is_not_a_successful_empty_menu(self):
        class Marketing:
            def get(self,url):return FetchResult(url,200,b'<h1>Welcome</h1>',{},'e','2026-10-17T09:00:00Z')
        result=fetch(self.endpoint(),Marketing())
        self.assertFalse(result['complete'])
        self.assertFalse(result['authoritative_zero'])
    def test_multiple_offers_preserve_variant_identity_and_unknown_mass(self):
        from backend.providers.generic import normalize
        product={'@type':'Product','sku':'edible','name':'Gummies 100mg','category':'Edibles','offers':[{'sku':'one','price':'10','priceCurrency':'USD'},{'sku':'two','price':'15','priceCurrency':'USD'}]}
        items=normalize(product,self.endpoint())
        self.assertEqual(len(items),2)
        self.assertNotEqual(items[0]['variant_id'],items[1]['variant_id'])
        self.assertIsNone(items[0]['weight_grams'])


if __name__=='__main__':unittest.main()

class AcceptedStreetMismatchTests(unittest.TestCase):
    def test_named_exceptions_record_both_addresses_so_they_can_be_revisited(self):
        from backend.providers.generic import ACCEPTED_STREET_MISMATCHES
        self.assertEqual(set(ACCEPTED_STREET_MISMATCHES), {'a9b8267a1dc370dc2b19cd77', '8ce3f490d5c2e8700b3ed175'})
        self.assertIn('310 E North Ave', ACCEPTED_STREET_MISMATCHES['a9b8267a1dc370dc2b19cd77'])
        self.assertIn('1132 Lake St', ACCEPTED_STREET_MISMATCHES['8ce3f490d5c2e8700b3ed175'])

