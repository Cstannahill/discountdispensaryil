import json
from pathlib import Path
import unittest

from backend.adapters import _detect_endpoint,fetch_menu,provider_capabilities
from backend.locators import _known_menu_candidates,addresses_match
from backend.network import FetchResult
from backend.site_discovery import provider_address_matches

ROOT=Path('tests/fixtures/provider_verano')
PAGE='https://zenleafdispensaries.com/locations/st-charles/menu/recreational/menu'
ENDPOINT=dict(url='https://zenleafdispensaries.com/locations/st-charles/menu',provider='verano',provider_store_id='537',license_type='recreational')
STORE=dict(id='x',name='Zen Leaf St. Charles',address='3691 E. Main St.',city='Saint Charles',state='IL',latitude=None,longitude=None)


def response(url,body):
    return FetchResult(url,200,body if isinstance(body,bytes) else body.encode(),{},'evidence-'+url[-12:],'2026-10-19T00:00:00Z')


class Site:
    def __init__(self,mode=None):self.mode,self.calls=mode,[]
    def get(self,url,headers=None):
        self.calls.append(url)
        if url.endswith('/menu-config/st-charles'):
            config=json.loads((ROOT/'menu-config.json').read_text())
            if self.mode=='moved':config['sweedId']=999
            return response(url,json.dumps(config))
        if url=='https://data.zenleafdispensaries.com/catalog/537/recreational':
            catalog=json.loads((ROOT/'catalog.json').read_text())
            if self.mode=='changed' and sum(u.endswith('/recreational') for u in self.calls)==2:catalog['products'][0]['name']='Renamed'
            return response(url,json.dumps(catalog))
        if url=='https://zenleafdispensaries.com/':return response(url,(ROOT/'branch.html').read_text())
        raise AssertionError('unexpected '+url)


class VeranoTests(unittest.TestCase):
    def test_branch_page_names_its_sweed_store_from_the_site_store_list(self):
        endpoint=_detect_endpoint(PAGE,response(PAGE,(ROOT/'branch.html').read_text()))
        self.assertEqual((endpoint['provider'],endpoint['provider_store_id'],endpoint['license_type']),('verano','537','recreational'))
        self.assertEqual(endpoint['url'],ENDPOINT['url'])
        self.assertTrue(provider_address_matches(STORE,endpoint))
        self.assertTrue(provider_capabilities('verano')['native_full_menu'])

    def test_page_for_a_branch_absent_from_the_list_is_not_a_menu(self):
        other='https://zenleafdispensaries.com/locations/nowhere/menu'
        self.assertNotEqual(_detect_endpoint(other,response(other,(ROOT/'branch.html').read_text()))['provider'],'verano')

    def test_two_agreeing_catalog_reads_converge_without_claiming_completion(self):
        result=fetch_menu(ENDPOINT,Site())
        self.assertEqual(result['errors'],[])
        self.assertFalse(result['complete'])
        self.assertEqual(result['convergence']['observed'],len(result['items']))
        self.assertEqual(len(result['items']),37)
        eighth=next(i for i in result['items'] if i['weight_grams']=='7')
        # Promo terms are absent from the catalog, so the shelf price is the comparable one.
        self.assertEqual(eighth['effective_price'],eighth['regular_price']);self.assertFalse(eighth['conditional'])
        self.assertTrue(eighth['raw']['promo_price_terms_unknown'])
        self.assertTrue(all(i['weight_grams'] is None for i in result['items'] if i['source_category']=='Edibles'))

    def test_branch_config_naming_another_store_fails(self):
        result=fetch_menu(ENDPOINT,Site('moved'))
        self.assertEqual(result['items'],[]);self.assertIn('different store',result['errors'][0]['message'])

    def test_identity_change_between_reads_is_not_convergence(self):
        result=fetch_menu(ENDPOINT,Site('changed'))
        self.assertNotIn('convergence',result);self.assertTrue(result['errors'])

    def test_chain_locator_reads_the_flight_store_list(self):
        candidates=_known_menu_candidates(STORE,Site())
        self.assertEqual([(c['status'],c['url']) for c in candidates],[('matched',ENDPOINT['url'])])

    def test_store_list_pin_proves_a_mistyped_registry_street(self):
        store=dict(STORE,address='3700 E. Main St.',latitude=41.9209,longitude=-88.2712)
        candidates=_known_menu_candidates(store,Site())
        self.assertEqual(candidates[0]['status'],'matched')

    def test_route_and_space_spellings_match(self):
        self.assertTrue(addresses_match('740 IL Rte 59','740 Illinois Route 59, Aurora, Illinois'))
        self.assertTrue(addresses_match('1516 N. Naper Blvd, Spc 100','1516 North Naper Boulevard, Naperville, Illinois'))


if __name__=='__main__':
    unittest.main()
