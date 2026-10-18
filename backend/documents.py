"""Shared HTML acquisition; an HTTP client's rejection is not a store verdict."""
import re
from .network import FetchError


class SourceAccessError(FetchError):
    pass


def access_kind(response):
    text=response.body.decode('utf-8',errors='replace')
    if re.search(r'<title>[^<]*(?:just a moment|attention required)',text,re.I) or ('cf-chl-' in text and 'cloudflare' in text.lower()):
        return 'access_challenge'
    if 'age-gate' in response.url or re.search(r'<h[12][^>]*>[^<]*confirm you are at least 21',text,re.I):
        return 'age_confirmation'
    return 'http_error' if response.status_code>=400 else 'document'


def read_document(url,fetcher,*,license_type=None):
    options=getattr(fetcher,'browser_options',{})
    browser=options.get('enabled',True) and hasattr(fetcher,'render')
    def render():
        return fetcher.render(url,**({'license_type':license_type} if license_type else {}))
    rendered=False
    try:response=fetcher.get(url)
    except FetchError as exc:
        if not browser or not re.search(r'HTTP (?:403|503)\b',str(exc)):raise
        response=render();rendered=True
    if access_kind(response)=='age_confirmation' and browser and options.get('age_confirmed') and not rendered:
        response=render();rendered=True
    elif not rendered and browser and response.status_code in (403,429,503):
        # A raw HTTP client rejection is not a verdict on the store: look once through the
        # ordinary browser. A challenge there is still reported, never bypassed.
        response=render();rendered=True
    kind=access_kind(response)
    if kind=='access_challenge':
        raise SourceAccessError(f'Access challenge in this acquisition session (HTTP {response.status_code}); browser/session access is unresolved',response.evidence_id)
    if response.status_code>=400:
        raise SourceAccessError(f'HTML source returned HTTP {response.status_code}',response.evidence_id)
    return response
