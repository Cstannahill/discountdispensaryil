import copy
import json
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import unittest
from backend.network import FetchResult
from backend.providers.dispense import fetch,normalize

ROOT=Path('tests/fixtures/provider_dispense')
ENDPOINT=dict(url='https://www.auralightdispensary.com/shop',provider='dispense',provider_store_id='7c6abd7d11c9ad19',license_type='recreational',public_api_key='observed-public-key')


class Fixture:
    def __init__(self,count=1103,mode=None):self.count,self.mode,self.calls=count,mode,0
    def get(self,url,headers=None):
        self.calls+=1
        if not urlsplit(url).path.endswith('/products'):
            value=json.loads((ROOT/'venue.json').read_text())
            if self.mode=='tenant':value['data']['id']='wrong'
        else:
            params=parse_qs(urlsplit(url).query);skip=int(params['skip'][0]);limit=int(params['limit'][0]);records=[]
            source=json.loads((ROOT/'products.json').read_text())['data'][0]
            for i in range(skip,min(skip+limit,self.count)):
                p=copy.deepcopy(source);p.update(id=str(i),_id=str(i));records.append(p)
                if self.mode=='metadata':p['sourceUpdateDate']=self.calls
            if self.mode=='repeat' and skip:records[0]['id']='0'
            if self.mode=='missing' and skip:records.pop()
            value=dict(data=records,count=self.count)
        return FetchResult(url,200,json.dumps(value).encode(),{},'evidence-'+str(self.calls),'2026-10-17T09:00:00Z')


class DispenseTests(unittest.TestCase):
    def test_unmodeled_metadata_churn_does_not_invalidate_stable_inventory(self):
        result=fetch(ENDPOINT,Fixture(50,'metadata'))
        self.assertTrue(result['complete'],result['errors'])

    def test_full_observed_public_catalog_over_thousand_and_two_traversals(self):
        result=fetch(ENDPOINT,Fixture())
        self.assertTrue(result['complete'],result['errors'])
        self.assertEqual(len(result['items']),1103)
        self.assertEqual(len(result['pages']),24)
    def test_missing_repeated_and_wrong_tenant_never_complete(self):
        for mode in ('repeat','missing','tenant'):
            result=fetch(ENDPOINT,Fixture(250,mode));self.assertFalse(result['complete']);self.assertTrue(result['errors'])
    def test_observed_price_mass_and_stock_are_preserved(self):
        product=json.loads((ROOT/'products.json').read_text())['data'][0]
        result=normalize(product,ENDPOINT)[0]
        self.assertEqual(result['weight_grams'],str(product['weightInGrams']))
        self.assertEqual(float(result['effective_price']),product['priceWithDiscounts'])
        self.assertTrue(result['available'])
    def test_dose_is_not_mass_and_conditional_promotions_are_not_unconditional(self):
        product=json.loads((ROOT/'products.json').read_text())['data'][0]
        product.update(weightUnit='MILLIGRAMS',weightInGrams=0.1,discounts=[{'productOfferType':'BOGO'}])
        result=normalize(product,ENDPOINT)[0]
        self.assertIsNone(result['weight_grams']);self.assertTrue(result['conditional'])

    def test_sale_scoped_to_the_variants_own_size_is_unconditional(self):
        product=json.loads((ROOT/'products.json').read_text())['data'][0]
        sale=dict(productOfferType='SALE',weights=['1g'],orderPickUpTypes=[],customerGroups=None,minimumSpend=None)
        product.update(weightFormatted='1g',price=45,priceWithDiscounts=30,discounts=[sale])
        result=normalize(product,ENDPOINT)[0]
        self.assertFalse(result['conditional']);self.assertEqual(float(result['effective_price']),30)
        product.update(weightFormatted='3.5g',discounts=[sale])
        self.assertTrue(normalize(product,ENDPOINT)[0]['conditional'])

if __name__=='__main__':unittest.main()
