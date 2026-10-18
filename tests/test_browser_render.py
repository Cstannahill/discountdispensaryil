import json
import os
from pathlib import Path
import tempfile
import unittest
import httpx
from backend.network import PublicFetcher


@unittest.skipUnless(os.environ.get('TERPSCOUT_BROWSER_TEST')=='1','Set TERPSCOUT_BROWSER_TEST=1 for installed Chrome integration')
class BrowserRenderTests(unittest.TestCase):

    def test_dom_observations_use_unambiguous_sale_price_and_fractional_mass(self):
        from backend.site_discovery import Page,objects
        from backend.providers.generic import normalize
        with tempfile.TemporaryDirectory() as folder:
            html='<html><body><article aria-label="Example Rosin product card"><a href="/products/rosin"><div aria-label="Details for Example Rosin">Example Rosin</div></a><p>(.5G)</p><s>$50.00</s><p>$35.00/.5g</p></article><article aria-label="Ambiguous product card"><a href="/products/ambiguous">Ambiguous</a><p>$25.00 or $15.00 with membership</p></article></body></html>'
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=html,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            try:
                result=fetcher.render('https://example.com/menu')
                products=[p for p in objects(Page(result.body.decode(),result.url).structured) if p.get('@type')=='Product']
                self.assertEqual(len(products),1)
                item=normalize(products[0],{'url':result.url})[0]
                self.assertEqual(item['name'],'Example Rosin')
                self.assertEqual(item['effective_price'],'35')
                self.assertEqual(item['regular_price'],'50')
                self.assertEqual(item['weight_grams'],'0.5')
            finally:fetcher.close()



    def test_native_event_stream_does_not_block_finite_page_capture(self):
        import socket
        import threading
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from unittest.mock import patch
        from backend.browser_render import _render
        stopped=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path=='/events':
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    self.wfile.write(b'data: {}\n\n');self.wfile.flush();stopped.wait(20);self.close_connection=True
                else:
                    body=b'<html><body>Finite menu document<script>new EventSource("/events")</script></body></html>'
                    self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        real_timer=threading.Timer
        try:
            with tempfile.TemporaryDirectory() as folder:
                fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:(_ for _ in ()).throw(AssertionError('Native traffic must use the controlled test tunnel'))),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',80))])
                fetcher.native_browser_allowed=True
                try:
                    with patch('backend.browser_proxy.connect_public',side_effect=lambda *a,**k:(socket.create_connection(server.server_address,timeout=3),'93.184.216.34')),patch('backend.browser_render.threading.Timer',side_effect=lambda seconds,callback:real_timer(15,callback)):
                        result=fetcher.render('http://example.com/menu')
                    self.assertIn('Finite menu document',result.body.decode())
                    diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                    self.assertTrue(any(row['url'].endswith('/events') for row in diagnostics.get('streaming_responses_skipped',[])))
                finally:fetcher.close()
        finally:stopped.set();server.shutdown();server.server_close();worker.join(timeout=2)



    def test_open_shadow_roots_are_observed_for_readiness_and_product_collection(self):
        from backend.site_discovery import Page,objects
        for structured in [True,False]:
            with self.subTest(structured=structured),tempfile.TemporaryDirectory() as folder:
                markup='<script type="application/ld+json">'+json.dumps({'@type':'Product','sku':'shadow-flower','name':'Shadow Flower','offers':{'price':'25','priceCurrency':'USD'}})+'</script>' if structured else '<article aria-label="Shadow Flower product card"><a href="/products/shadow-flower"><h3>Shadow Flower</h3></a><p>3.5g</p><p>$25.00</p></article>'
                html='<html><body><div id="menu"></div><script>document.getElementById("menu").attachShadow({mode:"open"}).innerHTML='+json.dumps(markup).replace('</',r'<\/')+';</script></body></html>'
                fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=html,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
                fetcher.browser_options={'await_menu':True}
                try:
                    result=fetcher.render('https://example.com/menu')
                    products=[p for p in objects(Page(result.body.decode(),result.url).structured) if p.get('@type')=='Product']
                    self.assertEqual(len(products),1)
                    self.assertEqual(products[0]['name'],'Shadow Flower')
                    diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                    self.assertTrue(diagnostics['menu_readiness']['observed_products'])
                finally:fetcher.close()



    def test_menu_acquisition_waits_for_delayed_declared_products(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            html='<html><body><main>Loading menu</main><script>setTimeout(()=>{let node=document.createElement("script");node.type="application/ld+json";node.textContent=JSON.stringify({"@type":"Product","sku":"late-product","name":"Late Flower"});document.body.append(node);},4000);</script></body></html>'
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=html,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options={'await_menu':True,'menu_readiness_ms':5000}
            try:
                result=fetcher.render('https://example.com/menu')
                from backend.site_discovery import Page,objects
                self.assertTrue(any(item.get('sku')=='late-product' for item in objects(Page(result.body.decode(),result.url).structured)))
                diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                self.assertTrue(diagnostics['menu_readiness']['observed_products'])
                self.assertEqual(diagnostics['menu_readiness']['limit_ms'],5000)
            finally:fetcher.close()



    def test_browser_runtime_errors_are_retained_with_acquisition_evidence(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            html='<html><body>Menu shell<script>console.error("Catalog request fixture failed");throw new Error("Menu bootstrap fixture failed");</script></body></html>'
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=html,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            try:
                result=fetcher.render('https://example.com/menu')
                diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                self.assertTrue(any('Menu bootstrap fixture failed' in message for message in diagnostics.get('page_errors',[])))
                self.assertTrue(any('Catalog request fixture failed' in message for message in diagnostics.get('console_errors',[])))
            finally:fetcher.close()


    def test_catalog_page_recheck_fetches_a_new_document_and_preserves_selected_context(self):
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            def handler(req):
                calls.append(str(req.url))
                script="localStorage.setItem('selectedStore','peru');" if len(calls)==1 else ''
                return httpx.Response(200,text=f'<html><body><main></main><script>{script}document.querySelector("main").textContent=localStorage.getItem("selectedStore")+"-read-{len(calls)}";</script></body></html>',headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            pages=[]
            def observe(response,context):
                pages.append(context['html'])
                return {'reload':True} if len(pages)==1 else {}
            fetcher.render_catalog('https://example.com/menu',observe)
            self.assertEqual(calls,['https://example.com/menu']*2)
            self.assertIn('<main>peru-read-2</main>',pages[1])
            fetcher.close()

    def test_catalog_retries_one_transient_navigation_failure_without_restarting_the_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            def handler(req):
                calls.append(str(req.url))
                if req.url.query and sum('page=2' in url for url in calls)==1:raise httpx.ConnectError('Transient source connection failure')
                body='<html><body>Page two</body></html>' if req.url.query else '<html><body><a href="?page=2">Next</a></body></html>'
                return httpx.Response(200,text=body,headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            pages=[]
            def observe(response,context):
                pages.append(response.url)
                return {'next_url':'https://example.com/menu?page=2'} if len(pages)==1 else {}
            fetcher.render_catalog('https://example.com/menu',observe)
            self.assertEqual(pages,['https://example.com/menu','https://example.com/menu?page=2'])
            self.assertEqual(sum('page=2' in url for url in calls),2)
            self.assertEqual(sum(url=='https://example.com/menu' for url in calls),1)
            fetcher.close()

    def test_catalog_does_not_redownload_analytics_after_branch_selection_and_preserves_failure_diagnostics(self):
        import json
        from backend.network import FetchError
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            def handler(req):
                calls.append(str(req.url))
                if req.url.host=='www.googletagmanager.com':return httpx.Response(200,text='window.telemetryLoaded=true',headers={'content-type':'application/javascript'})
                return httpx.Response(200,text='<html><body><script src="https://www.googletagmanager.com/gtm.js"></script><a href="?page=2">Next</a></body></html>',headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            pages=[]
            def observe(response,context):
                pages.append(response.url)
                return {'next_url':'https://example.com/menu?page=2'} if len(pages)==1 else {'next_url':'https://example.com/not-declared'}
            with self.assertRaises(FetchError) as failure:fetcher.render_catalog('https://example.com/menu',observe)
            self.assertEqual(sum('googletagmanager' in url for url in calls),1)
            diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{failure.exception.evidence_id}.json').read_text())
            self.assertGreater(diagnostics['requests'],0)
            self.assertEqual(diagnostics['request_limit'],5000)
            self.assertGreaterEqual(diagnostics['auxiliary_requests_skipped'],1)
            self.assertIn('tunnel_blocks',diagnostics)
            fetcher.close()

    def test_catalog_can_expand_a_declared_product_link_and_return_without_losing_context(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog='<html><body data-product-url="/product/extra"><main>Catalog</main></body></html>'
            def handler(req):return httpx.Response(200,text='<html><body><main>Expanded variants</main></body></html>' if req.url.path.startswith('/product/') else catalog,headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            pages=[]
            def observe(response,context):
                pages.append(response.url)
                if len(pages)==1:return {'next_url':'https://example.com/product/extra','declared_product':True}
                if len(pages)==2:return {'back':True}
                return {}
            fetcher.render_catalog('https://example.com/menu',observe)
            self.assertEqual(pages,['https://example.com/menu','https://example.com/product/extra','https://example.com/menu'])
            fetcher.close()

    def test_catalog_cannot_navigate_to_an_undeclared_product_url(self):
        from backend.network import FetchError
        with tempfile.TemporaryDirectory() as folder:
            seen=[]
            def handler(req):seen.append(req.url.path);return httpx.Response(200,text='<html><body>Catalog</body></html>',headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            with self.assertRaisesRegex(FetchError,'observed navigation link'):
                fetcher.render_catalog('https://example.com/menu',lambda response,context:{'next_url':'https://example.com/product/not-observed','declared_product':True})
            self.assertNotIn('/product/not-observed',seen)
            fetcher.close()

    def test_catalog_navigation_reuses_browser_and_reports_each_observed_page(self):
        with tempfile.TemporaryDirectory() as folder:
            source='''<html><body><main>Page one</main><a href="?page=2" onclick="event.preventDefault();history.pushState({},'',this.href);document.querySelector('main').textContent='Page two';this.remove()">Next</a></body></html>'''
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text='<html><body><main>Page two</main></body></html>' if req.url.query else source,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            pages=[]
            def observe(response,context):
                pages.append((response.url,context['html']))
                return {'next_url':'https://example.com/menu?page=2'} if len(pages)==1 else {}
            fetcher.render_catalog('https://example.com/menu',observe)
            self.assertEqual(len(pages),2)
            self.assertIn('<main>Page two</main>',pages[1][1])
            self.assertTrue(pages[1][0].endswith('page=2'))
            fetcher.close()

    def test_header_store_popover_with_radio_and_shop_pickup_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            source='''<html><body><div role="dialog" aria-label="Shopping cart">Your bag is empty</div><button style="position:absolute;left:2000px" aria-label="Open store selector and purchase method">Mobile pickup</button><header><button aria-label="Open store selector and purchase method" onclick="document.querySelector('section').hidden=false">Pickup</button><section hidden><h6>Select a pickup location</h6><div><label><input type="radio" name="store" value="other" aria-label="Select store: Stash Peru North - Peru, IL">Other</label><p>99 Other St</p></div><div><label><input type="radio" name="store" value="peru" aria-label="Select store: Stash Peru - Peru, IL">Stash Peru</label><p>1320 38th St</p></div><button onclick="document.querySelector('main').textContent=document.querySelector('input:checked').value;document.querySelector('section').hidden=true">SHOP PICKUP</button></section></header><main>Wrong default</main></body></html>'''
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=source,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options={'target_store':{'id':'peru','name':'Stash - Peru','city':'Peru','address':'1320 38th St'}}
            result=fetcher.render('https://example.com/')
            self.assertIn('<main>peru</main>',result.body.decode())
            fetcher.close()

    def test_location_choice_does_not_guess_between_same_city_branches_or_accept_wrong_address(self):
        with tempfile.TemporaryDirectory() as folder:
            bodies={
                '/ambiguous':'<button>Pontiac North</button><button>Pontiac South</button>',
                '/wrong':'<button>Pontiac - 99 Other St</button>',
                '/absent':'<button>Elk Grove Village</button>',
            }
            def handler(request):
                choices=bodies[request.url.path].replace('<button>','<button onclick="document.body.dataset.wrong=\'true\'">')
                return httpx.Response(200,text='<html><body><div role="dialog" aria-label="Choose location">'+choices+'</div></body></html>',headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options={'target_store':{'city':'Pontiac','address':'1910 W Reynolds St'}}
            for path in bodies:
                result=fetcher.render('https://example.com'+path)
                self.assertNotIn('data-wrong="true"',result.body.decode())
            fetcher.close()

    def test_location_dialog_selects_target_instead_of_first_branch_then_selects_menu_type(self):
        self.assert_location_selection('''<div role="dialog" aria-label="Choose location"><button onclick="choose('elk')">Elk Grove Village - 10 Other St</button><button onclick="choose('pontiac')">Pontiac - 1910 W Reynolds St</button></div>''')

    def test_native_location_dropdown_selects_target(self):
        self.assert_location_selection('''<label>Select location<select onchange="choose(this.value)"><option value="">Choose location</option><option value="elk">Elk Grove Village</option><option value="pontiac">Pontiac</option></select></label>''')

    def assert_location_selection(self,chooser):
        with tempfile.TemporaryDirectory() as folder:
            source='<html><body>'+chooser+'''<main>Wrong default branch</main><script>function choose(value){if(value==='pontiac'){document.querySelector('main').textContent='Pontiac 1910 W Reynolds St';document.querySelector('[role=dialog],label').remove();document.body.insertAdjacentHTML('beforeend',`<div role="dialog" aria-label="Shopping type">Medical or recreational?<button onclick="document.body.dataset.menu='recreational';this.parentElement.remove()">Recreational</button><button>Medical</button></div>`);}else document.body.dataset.wrong='true';}</script></body></html>'''
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=source,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options={'target_store':{'id':'pontiac','city':'Pontiac','address':'1910 W Reynolds St Unit A','name':'Snap Canna - Pontiac'}}
            result=fetcher.render('https://example.com/menu')
            self.assertIn('<main>Pontiac 1910 W Reynolds St</main>',result.body.decode())
            self.assertIn('data-menu="recreational"',result.body.decode())
            self.assertNotIn('data-wrong="true"',result.body.decode())
            fetcher.close()

    def test_shopping_context_gate_selects_recreational_and_continues(self):
        self.assert_menu_context(None,'Recreational')

    def test_shopping_context_gate_respects_explicit_medicinal_endpoint(self):
        self.assert_menu_context('medicinal','Medical')

    def assert_menu_context(self,license_type,expected):
        with tempfile.TemporaryDirectory() as folder:
            source='''<html><body><aside><button onclick="document.body.dataset.unrelated='clicked'">Recreational</button></aside><div role="dialog" aria-label="How are you shopping?"><h2>Are you shopping medical or recreational?</h2><label><input type="radio" name="type" value="Medical">Medical</label><label><input type="radio" name="type" value="Recreational">Recreational</label><button onclick="const choice=document.querySelector('input:checked');if(choice){document.querySelector('main').textContent=choice.value+' menu loaded';document.querySelector('[role=dialog]').remove()}">Start shopping</button></div><main></main></body></html>'''
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=source,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            result=fetcher.render('https://example.com/menu',**({'license_type':license_type} if license_type else {}))
            self.assertIn(f'<main>{expected} menu loaded</main>',result.body.decode())
            self.assertNotIn('data-unrelated="clicked"',result.body.decode())
            fetcher.close()

    def test_authorized_age_confirmation_follows_navigation_with_real_browser_cookie(self):
        with tempfile.TemporaryDirectory() as folder:
            age='''<html><body><button onclick="document.cookie='ageConfirmed=true; path=/'; location.href='/menu'">I'M AT LEAST 21 YEARS OLD</button></body></html>'''
            def handler(request):
                body='<html><body><h1>Authorized menu</h1></body></html>' if 'ageConfirmed=true' in request.headers.get('cookie','') else age
                return httpx.Response(200,text=body,headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options=dict(age_confirmed=True,terms_accepted=True)
            result=fetcher.render('https://example.com/age-gate')
            self.assertIn(b'Authorized menu',result.body)
            result=fetcher.render('https://example.com/menu')
            self.assertIn(b'Authorized menu',result.body)
            fetcher.close()

    def test_large_html_and_many_resources_do_not_deadlock_duplex_pipes(self):
        with tempfile.TemporaryDirectory() as folder:
            source='<html><head>'+''.join(f'<script src="/asset-{i}.js"></script>' for i in range(220))+'</head><body><h1>Large menu</h1><!--'+('x'*300000)+'--></body></html>'
            def handler(request):
                script="document.addEventListener('DOMContentLoaded',()=>document.body.dataset.ready='true');" if request.url.path=='/asset-219.js' else '// resource\n'+(' '*20000)
                return httpx.Response(200,text=source if request.url.path=='/menu' else script,headers={'content-type':'text/html' if request.url.path=='/menu' else 'application/javascript'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            result=fetcher.render('https://example.com/menu')
            self.assertIn(b'Large menu',result.body)
            self.assertIn(b'data-ready="true"',result.body)
            fetcher.close()

    def test_embedded_menu_frames_are_observed(self):
        from backend.providers.generic import extract
        with tempfile.TemporaryDirectory() as folder:
            def handler(request):
                body='<html><body><iframe src="/frame"></iframe></body></html>' if request.url.path=='/menu' else '<html><body><article class="product-card"><h3>Embedded Flower</h3><a href="/products/embedded">Embedded Flower</a><p>$22.00</p></article></body></html>'
                return httpx.Response(200,text=body,headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            result=fetcher.render('https://example.com/menu')
            _,products,_=extract(result.body.decode(),result.url)
            self.assertEqual([p['name'] for p in products],['Embedded Flower'])
            fetcher.close()
    def test_visible_product_cards_are_extracted_when_no_schema_is_published(self):
        from backend.providers.generic import extract
        with tempfile.TemporaryDirectory() as folder:
            source='<html><body><article class="product-card"><h3>Visible Flower</h3><a href="/products/visible-flower">Visible Flower</a><p>$25.00 · 3.5g</p></article></body></html>'
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=source,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            rendered=fetcher.render('https://example.com/menu')
            _,products,totals=extract(rendered.body.decode(),rendered.url)
            self.assertEqual(len(products),1)
            self.assertEqual(products[0]['name'],'Visible Flower')
            self.assertEqual(products[0]['offers']['price'],'25.00')
            self.assertEqual(totals,[])
            fetcher.close()
    def test_age_gate_click_requires_setting_and_does_not_accept_terms(self):
        with tempfile.TemporaryDirectory() as folder:
            source='''<html><body data-age="false"><input type="checkbox" aria-label="I accept terms"><button onclick="document.body.dataset.age='true'">Yes, I am 21 or older</button></body></html>'''
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:httpx.Response(200,text=source,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            first=fetcher.render('https://example.com/menu')
            self.assertIn('data-age="false"',first.body.decode())
            fetcher.browser_options=dict(age_confirmed=True,terms_accepted=False)
            second=fetcher.render('https://example.com/menu')
            self.assertIn('data-age="true"',second.body.decode())
            self.assertNotIn('checked=""',second.body.decode())
            fetcher.close()
    def test_javascript_products_render_through_validated_fetch_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            html='''<html><body><script>let s=document.createElement('script');s.type='application/ld+json';s.textContent=JSON.stringify({'@type':'Product','sku':'browser-product','name':'Rendered flower'});document.body.append(s);fetch('http://127.0.0.1/private').catch(()=>{});</script></body></html>'''
            seen=[]
            def handler(request):seen.append(str(request.url));return httpx.Response(200,text=html,headers={'content-type':'text/html'})
            fetcher=PublicFetcher(Path(folder),transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            result=fetcher.render('https://example.com/menu')
            from backend.site_discovery import Page,objects
            self.assertTrue(any(o.get('sku')=='browser-product' for o in objects(Page(result.body.decode(),result.url).structured)))
            self.assertTrue(all('127.0.0.1' not in u for u in seen))
            self.assertTrue(result.evidence_id)
            fetcher.close()


class BrowserProtocolWaitTests(unittest.TestCase):
    def test_idle_worker_can_finish_after_a_protocol_quiet_period(self):
        import queue
        import threading
        from unittest.mock import Mock
        from backend.browser_render import _next_worker_message
        messages=Mock();messages.get.side_effect=[queue.Empty,queue.Empty,{'type':'result'}]
        process=Mock();process.poll.return_value=None
        self.assertEqual(_next_worker_message(messages,process,threading.Event()),{'type':'result'})
        self.assertEqual(messages.get.call_count,3)

    def test_idle_worker_still_obeys_deadline_and_cancellation(self):
        import queue
        import threading
        from unittest.mock import Mock
        from backend.browser_render import _next_worker_message
        from backend.runtime import PipelineInterrupted
        messages=Mock();messages.get.side_effect=queue.Empty
        process=Mock();process.poll.return_value=None
        deadline=threading.Event();deadline.set()
        self.assertIsNone(_next_worker_message(messages,process,deadline))
        stopped=threading.Event();stopped.set()
        with self.assertRaises(PipelineInterrupted):
            _next_worker_message(messages,process,threading.Event(),stopped)

    def test_exited_worker_does_not_wait_until_deadline(self):
        import queue
        import threading
        from unittest.mock import Mock
        from backend.browser_render import _next_worker_message
        messages=Mock();messages.get.side_effect=queue.Empty
        process=Mock();process.poll.return_value=1
        self.assertIsNone(_next_worker_message(messages,process,threading.Event()))


@unittest.skipUnless(os.environ.get('TERPSCOUT_BROWSER_TEST')=='1','Set TERPSCOUT_BROWSER_TEST=1 for installed Chrome integration')
class MenuPagingTests(unittest.TestCase):
    def test_all_products_entry_and_view_more_load_every_page_and_json_is_retained(self):
        import json
        pages={1:list(range(0,3)),2:list(range(3,6)),3:list(range(6,8))}
        html='''<html><body><button aria-label="All products, unselected" id="all">All products</button><main id="grid">Featured</main>
        <button id="more" hidden>View more</button><script>
        let page=0;const grid=document.getElementById('grid'),more=document.getElementById('more');
        async function load(){page++;const data=await (await fetch('/api/products?page='+page)).json();
          for(const p of data.products){const d=document.createElement('div');d.className='product-card';d.textContent=p.name+' $'+p.price;grid.append(d);}
          if(page>=3)more.remove();else more.hidden=false;}
        document.getElementById('all').addEventListener('click',()=>{grid.textContent='';load();});
        more.addEventListener('click',load);
        </script></body></html>'''
        def handler(request):
            if request.url.path=='/api/products':
                number=int(request.url.params['page'])
                products=[dict(id=1000+i,name=f'Flower {i}',price=20+i,brand='B',category='Flower',weight=3.5,unit='g') for i in pages[number]]
                return httpx.Response(200,json=dict(products=products,total=8),headers={'content-type':'application/json'})
            return httpx.Response(200,text=html,headers={'content-type':'text/html'})
        with tempfile.TemporaryDirectory() as folder:
            fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options={'await_menu':True,'menu_readiness_ms':300,'scroll_menu':True,'transport':'captured_http'}
            try:
                result=fetcher.render('https://example.com/menu')
                diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                self.assertTrue(diagnostics['scroll']['entry']['opened'])
                self.assertGreaterEqual(diagnostics['scroll']['clicks'],2)
                self.assertEqual(len(diagnostics['network_json']),3)
                from backend.network_extract import extract_products,load_captured
                found=extract_products(load_captured(Path(folder)/'evidence',result.evidence_id),'https://example.com/menu')
                self.assertEqual(len({i['source_id'] for i in found['items']}),8)
            finally:fetcher.close()


@unittest.skipUnless(os.environ.get('TERPSCOUT_BROWSER_TEST')=='1','Set TERPSCOUT_BROWSER_TEST=1 for installed Chrome integration')
class OversizedRenderTests(unittest.TestCase):
    def test_a_rendered_menu_over_the_size_limit_is_reduced_to_content_markup(self):
        import json
        svg='<svg viewBox="0 0 10 10">'+'<path d="M0 0L10 10"/>'*200+'</svg>'
        cards=''.join(f'<article data-product-id="p{i}" data-product-name="Flower {i}" data-category="Flower" data-price="{20+i%9}" data-currency="USD" style="color:red;{"x:y;"*50}">{svg}<script>var junk="{"j"*400}";</script><img srcset="{"a.png 1x, "*80}" src="data:image/png;base64,{"A"*500}"><h3>Flower {i}</h3></article>' for i in range(120))
        grow='<script>document.querySelectorAll("article").forEach(a=>{for(let k=0;k<3;k++)a.append(a.querySelector("svg").cloneNode(true));});</script>'
        html=f'<html><head><style>{"h{}"*5000}</style></head><body><main>{cards}</main>{grow}</body></html>'
        with tempfile.TemporaryDirectory() as folder:
            fetcher=PublicFetcher(Path(folder)/'evidence',max_response_bytes=1024*1024,transport=httpx.MockTransport(lambda req:httpx.Response(200,text=html,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options={'transport':'captured_http'}
            try:
                self.assertLess(len(html),1024*1024)
                result=fetcher.render('https://example.com/menu')
                self.assertLess(len(result.body),1024*1024)
                text=result.body.decode()
                self.assertEqual(text.count('data-product-id='),120)
                self.assertNotIn('<svg',text)
                self.assertNotIn('srcset',text)
                diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                self.assertGreater(diagnostics['html_reduced']['from'],diagnostics['html_reduced']['to'])
            finally:fetcher.close()

    def test_a_document_that_is_still_too_large_after_reduction_fails_with_sizes(self):
        html='<html><body><main id="m"></main><script>for(let i=0;i<2000;i++){const a=document.createElement("article");a.dataset.productId="p"+i;a.dataset.productName="N".repeat(900);a.textContent="x";document.getElementById("m").append(a);}</script></body></html>'
        with tempfile.TemporaryDirectory() as folder:
            fetcher=PublicFetcher(Path(folder)/'evidence',max_response_bytes=500*1024,transport=httpx.MockTransport(lambda req:httpx.Response(200,text=html,headers={'content-type':'text/html'})),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_options={'transport':'captured_http'}
            try:
                with self.assertRaisesRegex(Exception,r'exceeds response size limit \(\d+ > 512000 bytes\)'):fetcher.render('https://example.com/menu')
            finally:fetcher.close()


@unittest.skipUnless(os.environ.get('TERPSCOUT_BROWSER_TEST')=='1','Set TERPSCOUT_BROWSER_TEST=1 for installed Chrome integration')
class PagedQueryReplayTests(unittest.TestCase):
    def test_paged_read_queries_are_replayed_from_the_page_and_union_is_extractable(self):
        import socket
        import threading
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from urllib.parse import parse_qs,urlsplit
        from unittest.mock import patch
        from backend.network_extract import extract_products,load_captured
        queries=[]
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def send(self,body,kind):
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def do_GET(self):
                parts=urlsplit(self.path)
                if parts.path=='/graphql':
                    variables=json.loads(parse_qs(parts.query)['variables'][0]);number=variables['page'];queries.append(number)
                    products=[dict(id=f'p{number}-{i}',Name=f'Flower {number}-{i}',Options=['3.5g'],Prices=[30+i],recPrices=[30+i],Status='Active',type='Flower',brandName='B') for i in range(4)]
                    self.send(json.dumps(dict(data=dict(filteredProducts=dict(products=products,queryInfo=dict(totalCount=12,totalPages=3))))).encode(),'application/json')
                else:
                    variables=json.dumps(dict(productsFilter=dict(dispensaryId='d',types=[],strainTypes=[]),page=0,perPage=4))
                    self.send(('<html><body><main>Menu</main><script>fetch("/graphql?operationName=FilteredProducts&variables="+encodeURIComponent(%s),{headers:{"apollo-require-preflight":"true"}})</script></body></html>'%json.dumps(variables)).encode(),'text/html')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        real_timer=threading.Timer
        try:
            with tempfile.TemporaryDirectory() as folder:
                fetcher=PublicFetcher(Path(folder)/'evidence',transport=httpx.MockTransport(lambda req:(_ for _ in ()).throw(AssertionError('Native traffic must use the controlled test tunnel'))),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',80))])
                fetcher.native_browser_allowed=True
                fetcher.browser_options={'await_menu':True,'menu_readiness_ms':300,'scroll_menu':True}
                try:
                    with patch('backend.browser_proxy.connect_public',side_effect=lambda *a,**k:(socket.create_connection(server.server_address,timeout=3),'93.184.216.34')),patch('backend.browser_render.threading.Timer',side_effect=lambda seconds,callback:real_timer(60,callback)):
                        result=fetcher.render('http://example.com/menu')
                    diagnostics=json.loads((Path(folder)/'evidence/browser'/f'{result.evidence_id}.json').read_text(encoding='utf-8'))
                    replay=diagnostics['scroll']['replay'];self.assertEqual((replay['queries'],replay['fetched'],replay['errors'],replay['whole']),(1,2,0,True))
                    self.assertEqual(sorted(set(queries)),[0,1,2])
                    found=extract_products(load_captured(Path(folder)/'evidence',result.evidence_id),'http://example.com/menu')
                    self.assertEqual(len({i['source_id'] for i in found['items']}),12)
                    self.assertEqual(found['total'],12)
                finally:fetcher.close()
        finally:server.shutdown();server.server_close()
