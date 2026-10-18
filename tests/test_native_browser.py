"""Real Chrome through the native public-only tunnel, using a trusted fixture connector."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.browser_proxy import connect_public
from backend.network import PublicFetcher


@unittest.skipUnless(os.environ.get('TERPSCOUT_BROWSER_TEST')=='1','Installed Chrome integration')
class NativeBrowserTests(unittest.TestCase):
    def test_native_http_preserves_status_and_rejects_private_and_write_requests(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(('GET',self.path))
                denied=self.path=='/denied'
                body=('<title>Attention Required! | Cloudflare</title>' if denied else '''<html><body><h1>Native rendered menu</h1><script>fetch('http://127.0.0.1/private').catch(()=>{});fetch('/checkout',{method:'POST',body:'{}'}).catch(()=>{});</script></body></html>''').encode()
                self.send_response(403 if denied else 200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def do_POST(self):seen.append(('POST',self.path));self.send_error(500)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        resolver=lambda *a,**k:[(2,1,6,'',('93.184.216.34',80))]
        # Trusted test I/O replaces the destination socket, after public-address validation.
        def connector(target,timeout):
            if target!=('93.184.216.34',80):raise OSError('Fixture only serves public HTTP port 80')
            return socket.create_connection(server.server_address,timeout=timeout)
        def connect(host,port,resolver):return connect_public(host,port,resolver,connector)
        try:
            with tempfile.TemporaryDirectory() as folder,patch('backend.browser_proxy.connect_public',side_effect=connect):
                fetcher=PublicFetcher(Path(folder)/'evidence',resolver=resolver)
                result=fetcher.render('http://menu.example/menu')
                self.assertEqual(result.status_code,200)
                self.assertIn(b'Native rendered menu',result.body)
                denied=fetcher.render('http://menu.example/denied')
                self.assertEqual(denied.status_code,403)
                self.assertFalse(any(method=='POST' or path=='/private' for method,path in seen))
                fetcher.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=2)
