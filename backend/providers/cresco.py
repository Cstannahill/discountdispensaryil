"""Cresco storefronts (Sunnyside, Cloud 9, Shangri-La): inventory read through the storefront's own public API.

The storefront's JavaScript sends its publishable key (read from the bundle at run time, never stored) with the
store and ordering-app ids and the storefront origin. Inventory pages by category with offset/limit. The first page's
total is the reference; later pages report a higher total that is not yet explained, so a read is partial (grade C)
until the totals reconcile.
"""
from decimal import Decimal
import json
import re
from urllib.parse import quote, urlencode, urlsplit

from backend.domain import GRAMS_PER_OUNCE, inventory_fields

VERSION = 'cresco-inventory-1'
API = 'https://api.crescolabs.com'
CATEGORIES = ('flower', 'vapes', 'edibles', 'prerolls', 'concentrates')
CATEGORY_MAP = {'flower': 'flower', 'vapes': 'vapes', 'concentrates': 'concentrate'}
PAGE = 50
HOSTS = ('www.sunnyside.shop', 'www.cloud9dispensaries.shop', 'shangri-la.sunnyside.shop')


def _host(url):
    host = (urlsplit(url).hostname or '').lower()
    return host


def store_slug(url):
    match = re.search(r'/menu/([a-z0-9-]+)(?:/|$)', urlsplit(url).path)
    return match[1] if match else None


def storefront_key(fetcher, origin):
    """The storefront's publishable API key, read from its own script bundle."""
    home = fetcher.get(origin + '/')
    bundle = re.search(r'src="(/static/js/main\.[a-z0-9]+\.js)"', home.body.decode('utf-8', 'replace'))
    if not bundle:
        raise ValueError('Cresco storefront bundle not found')
    text = fetcher.get(origin + bundle[1]).body.decode('utf-8', 'replace')
    key = re.search(r'API_KEY:"([A-Za-z0-9]{20,})"', text)
    if not key:
        raise ValueError('Cresco storefront key not found in bundle')
    return key[1]


def _headers(key, origin, store_id=None, app_id=None):
    headers = {'x-api-key': key, 'x-client-version': '1', 'origin': origin, 'referer': origin + '/', 'accept': 'application/json'}
    if store_id is not None:
        headers['store_id'] = str(store_id)
    if app_id is not None:
        headers['ordering_app_id'] = str(app_id)
    return headers


def resolve_store(fetcher, origin, key, slug, usage):
    """The ordering app and numeric store id for this storefront slug, from the storefront's own lookups."""
    host = urlsplit(origin).hostname
    query = urlencode(dict(host=host, store_slug=slug, usage_type=usage, country='US'))
    breakdown = json.loads(fetcher.get(f'{API}/p/ordering_apps/op/store-inventory-breakdown?{query}', headers=_headers(key, origin)).body)
    apps = breakdown.get('data') or []
    if len(apps) != 1:
        raise ValueError('Cresco ordering app for this storefront is missing or ambiguous')
    app = apps[0]
    ids = app.get('stores') or []
    if not ids:
        raise ValueError('Cresco ordering app lists no stores')
    listing = json.loads(fetcher.get(f'{API}/p/stores?ids={",".join(str(i) for i in ids)}', headers=_headers(key, origin)).body)
    matches = [s for s in listing.get('data') or [] if s.get('store_slug') == slug and not s.get('deleted') and not s.get('hidden')]
    if len(matches) != 1:
        raise ValueError('Cresco store slug is missing or ambiguous in the ordering app')
    return matches[0]['id'], app['id']


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def normalize(item, endpoint, category):
    from backend.adapters import _decimal as money
    if item.get('id') is None or not item.get('name'):
        raise ValueError('Cresco inventory identity or name missing')
    regular = money(item.get('price_rec'))
    effective = money(item.get('discounted_price')) or regular
    # Source prices arrive as binary floats (28.799999999999997); cents are the unit.
    regular, effective = (None if p is None else format(Decimal(p).quantize(Decimal('0.01')), 'f') for p in (regular, effective))
    weight = _decimal(item.get('bt_weight'))
    grams = str(weight) if weight is not None and weight > 0 else None
    qty = _decimal(item.get('remaining_sellable_qty'))
    applied = item.get('applied_special') or item.get('applied_special_id')
    return dict(source_id=str(item.get('product_id') or item['id']), variant_id=str(item['id']), name=item['name'], brand=item.get('brand'),
                category=CATEGORY_MAP.get(category, 'other'), source_category=category, subcategory=None, strain_type=None,
                thc_pct=None, weight_grams=grams, weight_label=item.get('bt_product_name'),
                regular_price=regular, effective_price=effective, conditional=bool(applied) or effective != regular,
                available=qty is not None and qty > 0, source_url=endpoint['url'], raw=dict(item=item, category=category))


def _inventory_url(category, usage, offset):
    query = urlencode(dict(inventory_type='retail', require_sellable_quantity='true', include_specials='true', sellable='true',
                           order_by='brand', usage_type=usage, hob_first='true', include_filters='true', include_facets='true',
                           limit=PAGE, category=category, offset=offset))
    return f'{API}/p/inventory/op/fifo-inventory?{query}'


def fetch(endpoint, fetcher):
    result = dict(provider='cresco', adapter_version=VERSION, items=[], complete=False, expected_count=None, pages=[], errors=[],
                  evidence=[], authoritative_zero=False, limits=dict(page=PAGE, concurrency=1),
                  count_semantics='first-page total per category is the reference; later pages report higher totals (unreconciled)')
    try:
        origin = 'https://' + _host(endpoint['url'])
        slug = store_slug(endpoint['url'])
        if not slug:
            raise ValueError('Cresco menu URL has no store slug')
        if endpoint.get('license_type') != 'recreational':
            raise ValueError('Cresco reader is recreational only in this version')
        key = storefront_key(fetcher, origin)
        store_id, app_id = resolve_store(fetcher, origin, key, slug, 'recreational')
        if endpoint.get('provider_store_id') and str(store_id) != str(endpoint['provider_store_id']):
            raise ValueError('Cresco store identity changed')
        headers = _headers(key, origin, store_id, app_id)
        reference = 0
        seen = {}
        for category in CATEGORIES:
            offset, first_total = 0, None
            while True:
                response = fetcher.get(_inventory_url(category, 'recreational', offset), headers=headers)
                result['evidence'].append(response.evidence_id)
                if response.status_code != 200:
                    raise ValueError(f'Cresco inventory HTTP {response.status_code} for {category} at offset {offset}')
                body = json.loads(response.body)
                rows = body.get('data') or []
                total = body.get('total_rows')
                if first_total is None:
                    first_total = total
                result['pages'].append(dict(category=category, offset=offset, count=len(rows), total_rows=total, evidence_id=response.evidence_id))
                for row in rows:
                    item = normalize(row, endpoint, category)
                    key_ = (item['source_id'], item['variant_id'])
                    if key_ not in seen:
                        seen[key_] = item
                if len(rows) < PAGE or offset > 10000:
                    break
                offset += PAGE
            reference += first_total or 0
        result['items'] = list(seen.values())
        result['expected_count'] = reference
        result['source_product_count'] = len({i['source_id'] for i in result['items']})
        if len(result['items']) != reference:
            result['errors'].append(dict(code='incomplete_cresco_menu',
                                         message=f"read {len(result['items'])} unique items; first-page totals sum to {reference}; later page totals disagree"))
        else:
            result['complete'] = False
            result['errors'].append(dict(code='incomplete_cresco_menu', message='later-page totals disagree with first-page totals; graded partial until reconciled'))
    except Exception as exc:
        result['errors'].append(dict(code='incomplete_cresco_menu', message=str(exc), evidence_id=getattr(exc, 'evidence_id', None)))
    return result
