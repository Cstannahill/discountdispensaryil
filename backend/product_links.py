"""Deep links to one product on a dispensary's own menu, built from data already stored on the offer.

Only patterns confirmed against live menus are built; any other provider keeps the store menu link.
Sweed and Verano route by the trailing variant id (the slug before it is cosmetic and redirects to the canonical one)."""
import re
from urllib.parse import urlsplit, quote

SWEED_SKIP_HOSTS = ('curaleaf.com',)
# Rise (Jane-backed) menus: <store>/<id>/<usage>-menu/product/<product id>/<slug>; the slug is cosmetic, the id routes.
RISE_MENU = re.compile(r'^(https?://(?:www\.)?risecannabis\.com/dispensaries/[^/]+/[^/]+/\d+/(?:recreational|medical)-menu)(?:/product/.*)?$')


def _slug(name):
    return re.sub(r'[^a-z0-9]+', '-', str(name or '').lower()).strip('-') or 'item'


def _clean(url):
    parts = urlsplit(url or '')
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip('/')


def product_url(provider, url, license_type, item):
    base = _clean(url)
    if not base:
        return None
    raw = item.get('raw') or {}
    source_id = str(item.get('source_id') or '')
    host = urlsplit(base).netloc.lower().removeprefix('www.')
    if (rise := RISE_MENU.match(base)):
        if source_id:
            return f"{rise.group(1)}/product/{quote(source_id)}/{_slug(item.get('name'))}/"
    elif provider == 'dutchie':
        if host == 'dutchie.com' and re.search(r'/embedded-menu/[0-9a-f]+$', base) and source_id:
            return f"{base}/product/{quote(source_id)}"
    elif provider == 'joint':
        if source_id:
            return f"{base}/?product_page={quote(source_id)}"
    elif provider in ('sweed', 'verano'):
        variant, category = (raw.get('variant') or {}).get('id'), (raw.get('product') or {}).get('category') or {}
        if variant is None or not category.get('id') or not category.get('canonicalName') or host in SWEED_SKIP_HOSTS:
            return None
        if provider == 'verano':
            if not re.search(r'/locations/[^/]+/menu$', base):
                return None
            base += '/' + ('medical' if license_type == 'medicinal' else 'recreational') + '/menu'
        elif not base.endswith('/menu'):
            return None
        return f"{base}/{quote(str(category['canonicalName']))}-{category['id']}/x-{variant}"
    return None


def with_product_url(item, provider, url, license_type):
    """item['source_url'] upgraded to the product page when it is only the store menu."""
    current = item.get('source_url')
    if current and _clean(current) != _clean(url):
        return current
    return product_url(provider, url, license_type, item) or current or url
