import socket
import unittest
from unittest.mock import Mock,patch
from backend.browser_proxy import connect_public,public_browser_proxy
from backend.network import UnsafeTargetError


class BrowserProxyTests(unittest.TestCase):

    def test_background_connections_need_a_validated_page_request_before_using_capacity(self):
        from urllib.parse import urlsplit
        class Fetcher:resolver=staticmethod(socket.getaddrinfo)
        upstream,peer=socket.socketpair()
        def connect(endpoint):
            client=socket.create_connection((endpoint.hostname,endpoint.port),timeout=2)
            client.sendall(b'\x05\x01\x00');self.assertEqual(client.recv(2),b'\x05\x00')
            host=b'example.com';client.sendall(b'\x05\x01\x00\x03'+bytes([len(host)])+host+b'\x01\xbb')
            return client
        try:
            with patch('backend.browser_proxy.connect_public',return_value=(upstream,'93.184.216.34')) as connector:
                with public_browser_proxy(Fetcher(),require_page_request=True) as proxy:
                    endpoint=urlsplit(proxy['url'])
                    with connect(endpoint) as client:self.assertEqual(client.recv(10)[:2],b'\x05\x02')
                    connector.assert_not_called();self.assertEqual(proxy['capacity']['peak_active'],0)
                    proxy['authorize_url']('https://example.com/menu')
                    with connect(endpoint) as client:self.assertEqual(client.recv(10)[:2],b'\x05\x00')
                    connector.assert_called_once();self.assertEqual(proxy['capacity']['peak_active'],1)
        finally:upstream.close();peer.close()



    def test_exhausted_connection_capacity_returns_recorded_socks_failure(self):
        from urllib.parse import urlsplit
        class Fetcher:resolver=staticmethod(socket.getaddrinfo)
        slots=Mock();slots.acquire.return_value=False
        with patch('backend.browser_proxy.threading.BoundedSemaphore',return_value=slots):
            with public_browser_proxy(Fetcher()) as proxy:
                endpoint=urlsplit(proxy['url'])
                with socket.create_connection((endpoint.hostname,endpoint.port),timeout=2) as client:
                    client.sendall(b'\x05\x01\x00');self.assertEqual(client.recv(2),b'\x05\x00')
                    host=b'example.com';client.sendall(b'\x05\x01\x00\x03'+bytes([len(host)])+host+b'\x01\xbb')
                    self.assertEqual(client.recv(10)[:2],b'\x05\x02')
                self.assertTrue(any('connection capacity' in item['error'] for item in proxy['blocked']))
        slots.release.assert_not_called()

    def test_queued_connection_succeeds_when_prior_connection_releases_capacity(self):
        import threading
        from urllib.parse import urlsplit
        class Fetcher:resolver=staticmethod(socket.getaddrinfo)
        pair1=socket.socketpair();pair2=socket.socketpair();clients=[];received=[]
        def handshake(endpoint):
            client=socket.create_connection((endpoint.hostname,endpoint.port),timeout=3);clients.append(client)
            client.sendall(b'\x05\x01\x00');self.assertEqual(client.recv(2),b'\x05\x00')
            host=b'example.com';client.sendall(b'\x05\x01\x00\x03'+bytes([len(host)])+host+b'\x01\xbb')
            return client
        try:
            with patch('backend.browser_proxy.connect_public',side_effect=[(pair1[0],'93.184.216.34'),(pair2[0],'93.184.216.34')]):
                with public_browser_proxy(Fetcher(),max_connections=1,connection_wait_seconds=2) as proxy:
                    endpoint=urlsplit(proxy['url']);first=handshake(endpoint);self.assertEqual(first.recv(10)[:2],b'\x05\x00')
                    second=handshake(endpoint)
                    reader=threading.Thread(target=lambda:received.append(second.recv(10)[:2]));reader.start()
                    first.close();pair1[1].close();reader.join(timeout=3)
                    self.assertFalse(reader.is_alive());self.assertEqual(received,[b'\x05\x00'])
                    self.assertEqual(proxy['capacity']['peak_active'],1)
                    self.assertEqual(proxy['capacity']['rejected'],0)
        finally:
            for client in clients:client.close()
            for sock in pair1+pair2:sock.close()


    def test_connection_is_pinned_to_public_numeric_address(self):
        resolver=Mock(return_value=[(2,1,6,'',('93.184.216.34',443))]);connector=Mock(return_value=object())
        _,address=connect_public('example.com',443,resolver,connector)
        self.assertEqual(address,'93.184.216.34')
        connector.assert_called_once_with(('93.184.216.34',443),timeout=8)

    def test_private_mixed_dns_and_unapproved_ports_are_rejected_before_connect(self):
        for addresses,port in [(['127.0.0.1'],443),(['10.0.0.1'],80),(['169.254.169.254'],80),(['::1'],443),(['93.184.216.34','192.168.1.1'],443),(['93.184.216.34'],22)]:
            with self.subTest(addresses=addresses,port=port):
                connector=Mock();resolver=lambda *a,**k:[(2,1,6,'',(address,port)) for address in addresses]
                with self.assertRaises(UnsafeTargetError):connect_public('example.com',port,resolver,connector)
                connector.assert_not_called()

    def test_socks_handshake_cannot_open_loopback(self):
        from urllib.parse import urlsplit
        class Fetcher:resolver=staticmethod(socket.getaddrinfo)
        with public_browser_proxy(Fetcher()) as proxy:
            endpoint=urlsplit(proxy['url'])
            with socket.create_connection((endpoint.hostname,endpoint.port),timeout=2) as client:
                client.sendall(b'\x05\x01\x00');self.assertEqual(client.recv(2),b'\x05\x00')
                client.sendall(b'\x05\x01\x00\x01\x7f\x00\x00\x01\x00\x50')
                self.assertEqual(client.recv(10)[:2],b'\x05\x02')
