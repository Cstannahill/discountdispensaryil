from pathlib import Path
import tempfile
import unittest
import httpx
from backend.network import PublicFetcher, UnsafeTargetError


class BrowserBoundaryTests(unittest.TestCase):
    def test_job_fetcher_has_an_independent_cookie_jar_and_medical_session_key(self):
        from backend.network import browser_session_key
        with tempfile.TemporaryDirectory() as folder:
            fetcher=PublicFetcher(Path(folder))
            child=fetcher.fork()
            try:
                fetcher.client.cookies.set('context','recreational',domain='example.com')
                self.assertEqual(len(child.client.cookies),0)
                self.assertNotEqual(browser_session_key('example.com'),browser_session_key('example.com','medicinal'))
            finally:child.close();fetcher.close()

    def test_authorized_persisted_browser_cookie_is_used_for_later_menu_reads(self):
        import hashlib,json
        with tempfile.TemporaryDirectory() as folder:
            evidence=Path(folder)/'evidence';sessions=Path(folder)/'browser-sessions';sessions.mkdir()
            state={'cookies':[dict(name='ageConfirmed',value='true',domain='example.com',path='/',secure=True,expires=-1),dict(name='foreign',value='never',domain='other.com',path='/',secure=True,expires=-1)]}
            (sessions/(hashlib.sha256(b'example.com').hexdigest()+'.json')).write_text(json.dumps(state))
            seen=[]
            def handler(request):seen.append(request);return httpx.Response(200,text='ok')
            fetcher=PublicFetcher(evidence,transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.get('https://example.com/menu')
            self.assertNotIn('cookie',seen[-1].headers)
            fetcher.browser_options=dict(enabled=True,age_confirmed=True,terms_accepted=True)
            fetcher.get('https://example.com/menu')
            self.assertEqual(seen[-1].headers['cookie'],'ageConfirmed=true')
            fetcher.get('https://other.com/menu')
            self.assertNotIn('cookie',seen[-1].headers)
            fetcher.close()

    def test_browser_navigation_headers_are_preserved_only_for_the_source_host(self):
        with tempfile.TemporaryDirectory() as folder:
            seen=[]
            def handler(request):
                seen.append(request)
                return httpx.Response(302,headers={'location':'https://other.com/menu'}) if len(seen)==1 else httpx.Response(200,text='ok')
            fetcher=PublicFetcher(Path(folder),transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_get('https://example.com/menu',origin='https://example.com/',headers={'rsc':'1','next-router-state-tree':'observed-state','authorization':'never-forward'})
            self.assertEqual(seen[0].headers['rsc'],'1')
            self.assertNotIn('authorization',seen[0].headers)
            self.assertNotIn('rsc',seen[1].headers)
            self.assertNotIn('next-router-state-tree',seen[1].headers)
            fetcher.close()

    def test_browser_cookie_is_scoped_and_redacted(self):
        with tempfile.TemporaryDirectory() as folder:
            seen=[]
            def handler(request):
                seen.append(request)
                return httpx.Response(200,text='ok')
            fetcher=PublicFetcher(Path(folder),transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            result=fetcher.browser_get('https://example.com/menu',origin='https://example.com/',cookie='ageConfirmed=true')
            self.assertEqual(seen[0].headers['cookie'],'ageConfirmed=true')
            self.assertNotIn('ageConfirmed=true',(Path(folder)/'manifests'/f'{result.evidence_id}.json').read_text())
            with self.assertRaises(UnsafeTargetError):
                fetcher.browser_get('https://other.com/menu',origin='https://example.com/',cookie='secret=1')
            fetcher.close()

    def test_browser_cookie_is_not_forwarded_across_redirect(self):
        with tempfile.TemporaryDirectory() as folder:
            seen=[]
            def handler(request):
                seen.append(request)
                return httpx.Response(302,headers={'location':'https://other.com/menu'}) if len(seen)==1 else httpx.Response(200,text='ok')
            fetcher=PublicFetcher(Path(folder),transport=httpx.MockTransport(handler),resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
            fetcher.browser_get('https://example.com/menu',origin='https://example.com/',cookie='ageConfirmed=true')
            self.assertNotIn('cookie',seen[1].headers)
            fetcher.close()


if __name__=='__main__':unittest.main()
