import json
from pathlib import Path
import unittest
import tempfile
from backend.site_discovery import search_websites, inspect_page, license_context, provider_links
from backend.network import FetchResult


def response(url, text):
    return FetchResult(url, 200, text.encode(), {}, 'source-evidence', '2026-10-17T09:00:00Z')


class DiscoveryFallbackTests(unittest.TestCase):

    def test_retailer_declared_menu_links_are_followed_without_fixed_route_names(self):
        from backend.adapters import resolve_menu
        for menu_path in ['/our-menu/','/plainfield-menu/','/adult-use/','/start-here/']:
            calls=[]
            class Fetcher:
                def get(self,url):
                    calls.append(url)
                    if url.endswith(menu_path):return response(url,'<h1>Example Cannabis Plainfield</h1>1 Main St<script src="https://dutchie.com/api/v3/embedded-menu/example.js"></script>')
                    return response(url,'<h1>Example Cannabis Plainfield</h1>1 Main St<a href="'+menu_path+'">View recreational menu</a><a href="https://unrelated.example/menu">Menu</a><a href="/privacy">Privacy policy</a>')
            menus=resolve_menu(dict(name='Example Cannabis',city='Plainfield',state='IL',address='1 Main St',website='https://retailer.example/'),Fetcher())
            self.assertTrue(any(m['provider']=='dutchie' and not m.get('status') for m in menus),menu_path)
            self.assertIn('https://retailer.example'+menu_path,calls)
            self.assertFalse(any('unrelated.example' in url or '/privacy' in url for url in calls))



    def test_structured_address_with_spelled_out_state_and_street_suffix_matches_the_registry_branch(self):
        schema={'@type':'Store','address':{'streetAddress':'1300 Locke Drive','addressLocality':'Bourbonnais','addressRegion':'Illinois','postalCode':'60914'}}
        page=response('https://www.philidispensary.com/our-menu/','<h1>Phili</h1><script type="application/ld+json">'+json.dumps(schema)+'</script>')
        store=dict(name='Phili Dispensary',address='1300 Locke Dr.',city='Bourbonnais',state='IL')
        self.assertEqual(inspect_page(store,page)['identity_status'],'matched')
        schema['address']['addressRegion']='Indiana'
        page=response(page.url,'<script type="application/ld+json">'+json.dumps(schema)+'</script>')
        self.assertEqual(inspect_page(store,page)['identity_status'],'conflict')

    def test_chain_navigation_is_not_selected_branch_identity(self):
        text='<h1>Example Cannabis</h1><nav>Rutland 1 Main St Chicago 99 Other St</nav><footer>Rutland dispensary 1 Main St</footer>'
        result=inspect_page(dict(name='Example Cannabis',address='1 Main St',city='Rutland',state='IL'),response('https://retailer.example/',text))
        self.assertEqual(result['identity_status'],'candidate')

    def test_same_city_wrong_street_cannot_be_verified_by_navigation(self):
        text='<h1>Example Cannabis Rutland</h1><nav>1 Main St</nav><script type="application/ld+json">'+json.dumps({'@type':'Store','url':'https://retailer.example/menu','address':{'streetAddress':'99 Other St','addressLocality':'Rutland','addressRegion':'IL'}})+'</script>'
        result=inspect_page(dict(name='Example Cannabis',address='1 Main St',city='Rutland',state='IL'),response('https://retailer.example/menu',text))
        self.assertEqual(result['identity_status'],'conflict')

    def test_other_origin_schema_does_not_establish_current_branch(self):
        text='<h1>Example Cannabis</h1><script type="application/ld+json">'+json.dumps({'@type':'Store','url':'https://other.example/menu','address':{'streetAddress':'1 Main St','addressLocality':'Rutland','addressRegion':'IL'}})+'</script>'
        result=inspect_page(dict(name='Example Cannabis',address='1 Main St',city='Rutland',state='IL'),response('https://retailer.example/menu',text))
        self.assertEqual(result['identity_status'],'candidate')



    def test_search_adopts_only_primary_result_anchor_not_auxiliary_links(self):
        class Fetcher:
            def get(self,url):return response(url,'<li class="b_algo"><a href="https://tracking.example/">Preview</a><h2><a href="https://retailer.example/menu">Unique Cannabis dispensary Rutland</a></h2><a href="https://wrong-branch.example/">Other location</a><img src="https://images.example/logo.png"></li>')
        results=search_websites(dict(name='Unique Cannabis',city='Rutland',state='IL'),Fetcher())
        self.assertEqual([item['url'] for item in results],['https://retailer.example/menu'])

    def test_search_cache_preserves_attempt_provenance_across_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            class First:
                evidence_dir=Path(folder)
                def get(self,url):return response(url,'<li class="b_algo"><h2><a href="https://retailer.example/">Unique Cannabis dispensary Rutland</a></h2></li>')
            class Restarted:
                evidence_dir=Path(folder)
                def get(self,url):raise AssertionError('Cache should avoid network')
            store=dict(name='Unique Cannabis',city='Rutland',state='IL');first=First();search_websites(store,first)
            restarted=Restarted();search_websites(store,restarted)
            self.assertEqual(restarted._last_search_attempts,first._last_search_attempts)
            self.assertTrue(restarted._last_search_attempts)

    def test_search_rejects_lookalike_engine_and_social_hosts_only_by_domain_boundary(self):
        from backend.site_discovery import decode_search_url
        self.assertEqual(decode_search_url('https://notbing.com/ck/a?u=a1aHR0cHM6Ly9ldmlsLmV4YW1wbGUv'),'https://notbing.com/ck/a?u=a1aHR0cHM6Ly9ldmlsLmV4YW1wbGUv')
        class Fetcher:
            def get(self,url):return response(url,'<li class="b_algo"><h2><a href="https://notfacebook.com/menu">Unique Cannabis dispensary Rutland</a></h2></li>')
        self.assertEqual([r['url'] for r in search_websites(dict(name='Unique Cannabis',city='Rutland',state='IL'),Fetcher())],['https://notfacebook.com/menu'])

    def test_provider_script_hint_does_not_stop_crawling_before_a_real_catalog_contract(self):
        from backend.adapters import resolve_menu
        from tests.test_adapters import SweedFetcher
        class Fetcher:
            calls=[]
            def get(self,url):
                self.calls.append(url)
                if url.endswith('/menu'):return SweedFetcher(1).get(url)
                return response(url,'<h1>Tree Haus Morris</h1>50 Gore Rd<script src="https://static.sweedpos.com/widget.js"></script><a href="/menu">Shop all</a>')
        fetcher=Fetcher();menus=resolve_menu(dict(name='Tree Haus Morris',city='Morris',state='IL',address='50 Gore Rd',website='https://retailer.example/'),fetcher)
        resolved=[menu for menu in menus if not menu.get('status')]
        self.assertEqual([(menu['provider'],menu['provider_store_id'],menu['url']) for menu in resolved],[('sweed','405','https://retailer.example/menu')])
        self.assertIn('https://retailer.example/menu',fetcher.calls)

    def test_unresolved_native_provider_hint_is_not_published_as_a_menu_target(self):
        from backend.adapters import resolve_menu
        class Fetcher:
            def get(self,url):return response(url,'<h1>Example Dispensary Pontiac</h1>1 Main St<script src="https://static.sweedpos.com/widget.js"></script>')
        menus=resolve_menu(dict(name='Example Dispensary',city='Pontiac',state='IL',address='1 Main St',website='https://retailer.example/'),Fetcher())
        self.assertFalse(any(menu['provider']=='sweed' and not menu.get('status') for menu in menus))
        self.assertTrue(any('contract' in menu.get('reason','').lower() for menu in menus))

    def test_rebranded_retailer_is_found_by_address_after_old_chain_candidates_fail(self):
        from backend.adapters import resolve_menu
        from unittest.mock import patch
        shop=dict(name='Former Brand - Normal',city='Normal',state='IL',address='1609 Northbrook Dr',website='https://former.example/')
        class Fetcher:
            def get(self,url):
                if 'former.example' in url:return response(url,'<h1>Former Brand Schaumburg</h1>')
                return response(url,'<h1>New Owner Cannabis Dispensary Normal IL</h1>1609 Northbrook Drive<script src="https://dutchie.com/api/v3/embedded-menu/new-owner.js"></script>')
        searches=[]
        def search(store,fetcher,**options):
            searches.append(options.get('by_address',False))
            return [dict(url='https://new-owner.example/menu',status='candidate',evidence=[])] if options.get('by_address') else []
        with patch('backend.site_discovery.search_websites',side_effect=search):menus=resolve_menu(shop,Fetcher())
        self.assertIn(True,searches)
        self.assertTrue(any(menu['provider']=='dutchie' and not menu.get('status') for menu in menus),menus)

    def test_address_search_accepts_new_brand_but_requires_exact_street_city_and_cannabis_context(self):
        class Fetcher:
            def get(self,url):return response(url,'<li class="b_algo"><a href="https://new-owner.example/menu">New Owner cannabis dispensary Normal 1609 Northbrook Drive</a></li><li class="b_algo"><a href="https://wrong.example/">Cannabis Normal 99 Other St</a></li><li class="b_algo"><a href="https://dentist.example/">Dentist Normal 1609 Northbrook Dr</a></li>')
        results=search_websites(dict(name='Old Brand - Normal',city='Normal',state='IL',address='1609 Northbrook Dr'),Fetcher(),by_address=True)
        self.assertEqual([item['url'] for item in results],['https://new-owner.example/menu'])

    def test_failed_chain_crawl_reserves_capacity_for_address_recovery(self):
        from backend.adapters import resolve_menu
        from unittest.mock import patch
        calls=[]
        class Fetcher:
            def get(self,url):
                calls.append(url)
                if 'new-owner' in url:return response(url,'<h1>New Owner cannabis dispensary Normal</h1>1609 Northbrook Dr<script src="https://dutchie.com/api/v3/embedded-menu/recovered.js"></script>')
                return response(url,'<h1>Old Brand Chicago</h1>'+''.join(f'<a href="/locations/branch-{n}">Branch</a>' for n in range(40)))
        def search(store,fetcher,**options):return [dict(url='https://new-owner.example/menu',status='candidate',evidence=[])] if options.get('by_address') else []
        with patch('backend.site_discovery.search_websites',side_effect=search):
            menus=resolve_menu(dict(name='Old Brand Normal',city='Normal',state='IL',address='1609 Northbrook Dr',website='https://former.example/'),Fetcher())
        self.assertLessEqual(len(calls),24)
        self.assertTrue(any(menu['provider']=='dutchie' and not menu.get('status') for menu in menus))

    def test_old_positive_search_cache_is_invalidated_by_strategy_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            class Fetcher:
                evidence_dir=Path(folder)
                calls=0
                def get(self,url):
                    self.calls+=1
                    return response(url,'<li class="b_algo"><a href="https://brand.example/menu">Unique Cannabis dispensary Rutland</a></li>')
            shop=dict(name='Unique Cannabis',city='Rutland',state='IL');first=Fetcher()
            search_websites(shop,first)
            cache=next((Path(folder)/'search-cache').glob('*.json'));saved=json.loads(cache.read_text());saved['strategy_version']=2;cache.write_text(json.dumps(saved))
            restarted=Fetcher();self.assertTrue(search_websites(shop,restarted));self.assertGreater(restarted.calls,0)

    def test_promotional_groups_and_product_details_are_not_independent_full_menu_targets(self):
        from backend.adapters import resolve_menu
        shop=dict(name='Stash - Peru',city='Peru',address='1320 38th St',website='https://retailer.example/')
        product='<script type="application/ld+json">'+json.dumps({'@type':'Product','sku':'one','name':'Example'})+'</script>'
        class Fetcher:
            def get(self,url):return response(url,'<h1>Stash Peru</h1>1320 38th St'+product+'<a href="/product-group/promo">Peru promotion</a><a href="/products/one">Product</a><a href="/shop?query=flower">Filtered search</a><a href="/shop">Shop all</a>')
        menus=resolve_menu(shop,Fetcher())
        self.assertEqual([menu['url'] for menu in menus if not menu.get('status')],['https://retailer.example/shop'])

    def test_wrong_default_branch_is_rendered_with_requested_location_before_rejection(self):
        from backend.adapters import resolve_menu
        shop=dict(id='pontiac',name='Snap Canna - Pontiac',city='Pontiac',address='1910 W Reynolds St',state='IL',website='https://retailer.example/menu')
        class Fetcher:
            selected=[]
            def get(self,url):
                return response(url,'<h1>Snap Canna Elk Grove</h1><script type="application/ld+json">'+json.dumps({'@type':'Store','url':url,'address':{'streetAddress':'10 Other St','addressLocality':'Elk Grove Village','addressRegion':'IL'}})+'</script>')
            def render(self,url):
                self.selected.append(self.browser_options['target_store'])
                return response(url,'<h1>Snap Canna Pontiac</h1>1910 W Reynolds St<script src="https://dutchie.com/api/v3/embedded-menu/pontiac.js"></script>')
        fetcher=Fetcher();menus=resolve_menu(shop,fetcher)
        self.assertEqual(fetcher.selected[0]['id'],'pontiac')
        self.assertTrue(any(menu.get('provider')=='dutchie' and not menu.get('status') for menu in menus))
        self.assertFalse(any(menu.get('status')=='identity_conflict' for menu in menus))

    def test_directory_is_a_website_lead_not_a_menu_and_page_anchors_are_not_endpoints(self):
        from backend.adapters import resolve_menu
        shop=dict(name='Stash - Peru',city='Peru',address='1320 38th St',website='https://www.jointcommerce.com/dispensaries/stash-peru/menu')
        class Fetcher:
            calls=[]
            def get(self,url):
                self.calls.append(url)
                if 'jointcommerce' in url:
                    return response(url,'<h1>Stash Peru</h1>1320 38th St<a href="#main-nav">Menu</a><a href="https://www.stashdispensaries.com/">Website</a>')
                return response(url,'<h1>Stash Peru</h1>1320 38th St<a href="/menu">Shop all</a>')
        fetcher=Fetcher(); resolved=resolve_menu(shop,fetcher)
        self.assertTrue(any('stashdispensaries.com/menu' in x['url'] for x in resolved))
        self.assertFalse(any('jointcommerce' in x['url'] and x.get('status') not in ('unresolved','blocked','failed') for x in resolved))
        self.assertFalse(any('#main-nav' in url for url in fetcher.calls))

    def test_ordinary_anchors_share_one_page_but_hash_router_routes_stay_distinct(self):
        from backend.site_discovery import canonical_menu_url
        self.assertEqual(canonical_menu_url('https://example.com/menu#main-nav'),'https://example.com/menu')
        self.assertEqual(canonical_menu_url('https://example.com/#/menu/peru'),'https://example.com/#/menu/peru')

    def test_navigation_city_does_not_override_a_conflicting_branch_address(self):
        text='<h1>Example Dispensary</h1><nav>Rutland Chicago</nav><script type="application/ld+json">'+json.dumps({'@type':'Store','url':'https://example.com/chicago','address':{'streetAddress':'99 Other St','addressLocality':'Chicago','addressRegion':'IL'}})+'</script>'
        result=inspect_page(dict(name='Example Dispensary',address='1 Main St',city='Rutland',state='IL'),response('https://example.com/chicago',text))
        self.assertEqual(result['identity_status'],'conflict')
    def test_compound_brand_and_generic_business_names_can_still_produce_leads(self):
        class Fetcher:
            def get(self,url):
                return response(url,'<li class="b_algo"><h2><a href="https://bisalina.com/">BISALINA cannabis dispensary Joliet</a></h2></li><li class="b_algo"><h2><a href="https://thedispensary.example/fulton">The Dispensary Fulton cannabis menu</a></h2></li>')
        self.assertTrue(search_websites(dict(name='Bisa Lina Joliet',city='Joliet',state='IL'),Fetcher()))
        self.assertTrue(search_websites(dict(name='The Dispensary',city='Fulton',state='IL'),Fetcher()))
    def test_search_results_survive_fetcher_restart_without_repeating_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            body=Path('tests/fixtures/sites/bing-terrabis.html').read_text(encoding='utf-8')
            class First:
                evidence_dir=Path(folder)
                def get(self,url):return response(url,body)
            class Restarted:
                evidence_dir=Path(folder)
                def get(self,url):raise AssertionError('Persisted positive search should avoid a repeated request')
            shop=dict(name='Terrabis Plainfield',city='Plainfield',state='IL')
            first=search_websites(shop,First())
            self.assertTrue(first)
            self.assertEqual(search_websites(shop,Restarted()),first)
    def test_real_search_redirects_decode_into_websites_without_brand_connector(self):
        body = Path('tests/fixtures/sites/bing-terrabis.html').read_text(encoding='utf-8')
        class Fetcher:
            def get(self, url): return response(url, body)
        results = search_websites(dict(name='Terrabis Plainfield', city='Plainfield', state='IL'), Fetcher())
        self.assertTrue(any('terrabis.co' in r['url'] for r in results))
        self.assertFalse(any('bing.com/ck' in r['url'] for r in results))
        self.assertTrue(all(r['evidence'] for r in results))

    def test_noxx_actual_branch_address_matches_despite_url_city_abbreviation(self):
        text = Path('tests/fixtures/sites/noxx-peoria.html').read_text(encoding='utf-8')
        matched = inspect_page(dict(name='Noxx - East Peoria', address='300 S Main St', city='East Peoria', state='IL'),
                               response('https://noxx.com/location/noxx-peoria/', text))
        self.assertEqual(matched['identity_status'], 'matched')
        self.assertTrue(any(x['provider']=='dutchie' and x['provider_store_id']=='65772a69ac53410009424572' for x in matched['endpoints']))

    def test_absent_address_is_not_an_address_conflict_and_explicit_wrong_city_is(self):
        shop=dict(name='Example Dispensary', address='1 Main St', city='Rutland', state='IL')
        result=inspect_page(shop,response('https://example.com/rutland','<h1>Example Dispensary Rutland IL</h1>'))
        self.assertEqual(result['identity_status'],'name_locality')
        text='<script type="application/ld+json">'+json.dumps({'@type':'LocalBusiness','name':'Example Dispensary','url':'https://example.com/chicago','address':{'streetAddress':'99 Other St','addressLocality':'Chicago','addressRegion':'IL'}})+'</script>'
        result=inspect_page(shop,response('https://example.com/chicago',text))
        self.assertEqual(result['identity_status'],'conflict')

    def test_license_defaults_to_recreational_but_explicit_medical_wins(self):
        self.assertEqual(license_context('https://shop.example/menu',''),('recreational','default'))
        self.assertEqual(license_context('https://shop.example/medical-menu',''),('medicinal','explicit'))

    def test_provider_embeds_are_detected_without_carousel_as_full_menu(self):
        found=provider_links('https://example.com', '<script src="https://dutchie.com/api/v3/embedded-menu/abc123/carousels/one.js"></script><iframe src="https://www.iheartjane.com/embed/stores/1234/menu"></iframe>')
        self.assertEqual({x['provider'] for x in found},{'dutchie','jane'})
        self.assertTrue(all('/carousels/' not in x['url'] for x in found))

    def test_search_results_for_unrelated_brand_are_not_adopted(self):
        class Fetcher:
            def get(self,url):return response(url,'<li class="b_algo"><h2><a href="https://unrelated.com/">Unrelated Chicago dentistry</a></h2></li>')
        self.assertEqual(search_websites(dict(name='Unique Cannabis',city='Rutland',state='IL'),Fetcher()),[])

    def test_shared_single_word_is_not_enough_for_a_multiword_brand(self):
        class Fetcher:
            def get(self,url):return response(url,'<li class="b_algo"><h2><a href="https://mysticboarding.com/">Mystic sporting goods</a></h2></li>')
        self.assertEqual(search_websites(dict(name='Mystic Greenz - Lincoln',city='Lincoln',state='IL'),Fetcher()),[])

    def test_provider_api_preconnect_is_not_a_menu_endpoint(self):
        self.assertEqual(provider_links('https://example.com','<link rel="preconnect" href="https://api.dispenseapp.com">'),[])


if __name__=='__main__':unittest.main()


class DutchieEmbedLinkTests(unittest.TestCase):
    def test_v2_embed_script_resolves_to_the_menu_not_the_script_and_never_to_a_version_segment(self):
        text='<script id="dutchie--embed__script" src="https://dutchie.com/api/v2/embedded-menu/64888ad400476b00104ffe4d.js"></script>'
        found=provider_links('https://www.excelleaf.com/menu/',text)
        self.assertEqual([(x['provider'],x['provider_store_id'],x['url']) for x in found],
                         [('dutchie','64888ad400476b00104ffe4d','https://dutchie.com/embedded-menu/64888ad400476b00104ffe4d')])

    def test_v3_carousel_script_still_resolves_to_its_dispensary(self):
        text='<script src="https://dutchie.com/api/v3/embedded-menu/627458da5d75a3008f52fc56/carousels/2b59.js?routeRoot=https%3A%2F%2Fnoxx.com"></script>'
        found=provider_links('https://noxx.com/x/',text)
        self.assertEqual(found[0]['provider_store_id'],'627458da5d75a3008f52fc56')
