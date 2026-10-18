"""Ephemeral public-only SOCKS5 tunnel; Chrome owns HTTP and TLS end to end."""
from contextlib import contextmanager
import ipaddress
import select
import socket
import socketserver
import struct
import threading
import time
from urllib.parse import urlsplit

from .network import FetchError, UnsafeTargetError, _public_addresses


def connect_public(host,port,resolver,connector=socket.create_connection):
    if port not in (80,443):raise UnsafeTargetError('Browser tunnel only permits HTTP(S) ports')
    if not host or any(character in host for character in '/\\@?#%\r\n\t '):
        raise UnsafeTargetError('Invalid browser tunnel hostname')
    addresses=_public_addresses(host,port,resolver)
    # Connect to the validated numeric address, never resolve the hostname again.
    return connector((addresses[0],port),timeout=8),addresses[0]


def _read(sock,size):
    chunks=[]
    while size:
        data=sock.recv(size)
        if not data:raise EOFError('Browser tunnel closed')
        chunks.append(data);size-=len(data)
    return b''.join(chunks)


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads=True
    allow_reuse_address=False
    request_queue_size=128


@contextmanager
def public_browser_proxy(fetcher,max_bytes=64*1024*1024,*,max_connections=24,connection_wait_seconds=8,require_page_request=False):
    if max_connections<1 or connection_wait_seconds<=0:raise ValueError('Browser connection limits must be positive')
    stop=threading.Event();lock=threading.Lock();connections=[];blocked=[];remaining=[max_bytes]
    authorized=set()
    def authorize_url(url):
        parts=urlsplit(url)
        if parts.scheme not in ('http','https') or not parts.hostname:
            raise UnsafeTargetError('Browser page request must use HTTP(S)')
        port=parts.port or (443 if parts.scheme=='https' else 80)
        if port not in (80,443):raise UnsafeTargetError('Browser tunnel only permits HTTP(S) ports')
        with lock:authorized.add((parts.hostname.lower(),port))
    slots=threading.BoundedSemaphore(max_connections)
    capacity=dict(limit=max_connections,wait_seconds=connection_wait_seconds,active=0,peak_active=0,queued=0,rejected=0)

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            acquired=False;upstream=None;host='';port=0
            try:
                self.request.settimeout(10)
                version,count=_read(self.request,2)
                if version!=5 or 0 not in _read(self.request,count):return
                self.request.sendall(b'\x05\x00')
                version,command,reserved,kind=_read(self.request,4)
                if version!=5 or command!=1 or reserved:raise UnsafeTargetError('Only TCP browser connections are permitted')
                if kind==3:host=_read(self.request,_read(self.request,1)[0]).decode('ascii')
                elif kind==1:host=str(ipaddress.ip_address(_read(self.request,4)))
                elif kind==4:host=str(ipaddress.ip_address(_read(self.request,16)))
                else:raise UnsafeTargetError('Invalid browser address type')
                port=struct.unpack('!H',_read(self.request,2))[0]
                with lock:allowed=not require_page_request or (host.lower(),port) in authorized
                if not allowed:raise UnsafeTargetError('Browser connection has no validated page request')
                acquired=slots.acquire(blocking=False)
                if not acquired:
                    with lock:capacity['queued']+=1
                    acquired=slots.acquire(timeout=connection_wait_seconds)
                if not acquired:
                    with lock:capacity['rejected']+=1
                    raise FetchError('Browser connection capacity exhausted after bounded wait')
                with lock:
                    capacity['active']+=1
                    capacity['peak_active']=max(capacity['peak_active'],capacity['active'])
                upstream,address=connect_public(host,port,fetcher.resolver)
                with lock:connections.append(dict(host=host,port=port,address=address))
                self.request.sendall(b'\x05\x00\x00\x01'+b'\x00'*6)
                deadline=time.monotonic()+55
                while not stop.is_set() and time.monotonic()<deadline:
                    if getattr(fetcher,'stop_requested',None) is not None and fetcher.stop_requested.is_set():break
                    readable,_,_=select.select([self.request,upstream],[],[],0.25)
                    for source in readable:
                        data=source.recv(65536)
                        if not data:return
                        with lock:
                            remaining[0]-=len(data)
                            if remaining[0]<0:raise UnsafeTargetError('Browser tunnel byte budget exceeded')
                        (upstream if source is self.request else self.request).sendall(data)
            except (OSError,EOFError,ValueError,FetchError) as exc:
                with lock:blocked.append(dict(host=host,port=port,error=str(exc)))
                try:self.request.sendall(b'\x05\x02\x00\x01'+b'\x00'*6)
                except OSError:pass
            finally:
                if upstream:upstream.close()
                if acquired:
                    with lock:capacity['active']-=1
                    slots.release()

    server=_Server(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.1},daemon=True);thread.start()
    try:
        yield dict(url=f'socks5://127.0.0.1:{server.server_address[1]}',connections=connections,blocked=blocked,capacity=capacity,authorize_url=authorize_url)
    finally:
        stop.set();server.shutdown();server.server_close();thread.join(timeout=2)
