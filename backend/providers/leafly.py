"""Leafly-hosted dispensary menus: the listing's own paged menu (leafly.com/dispensary-info/<slug>/menu).

Used only when a store has no other menu source; a Leafly listing otherwise stays a discovery lead. The page embeds its
data as Next.js JSON. The listing page names the dispensary (id, street address, pin, price basis) and each /menu page
carries one page of products plus the exact catalog total, so a full menu reconciles without guessing.
"""
from decimal import Decimal
import hashlib
import json
import re
from urllib.parse import urlsplit

from backend.domain import GRAMS_PER_OUNCE, inventory_fields

VERSION = 'leafly-menu-1'
BASE = 'https://www.leafly.com/dispensary-info/'
CATEGORIES = {'flower': 'flower', 'concentrate': 'concentrates', 'cartridge': 'vapes'}
TAX_EXCLUSIVE = 'tax_exclusive_pricing'
_LISTING = re.compile(r'https?://(?:www\.)?leafly\.com/dispensary-info/([^/?#"\'<>\s\\]+)', re.I)


def slug_from(url):
    parts = urlsplit(url or '')
    host = (parts.hostname or '').lower()
    if host != 'leafly.com' and not host.endswith('.leafly.com'):
        return None
    match = re.match(r'/dispensary-info/([^/?#]+)', parts.path)
    return match[1] if match else None


def listing_url(slug):
    return BASE + slug


def menu_url(slug):
    return BASE + slug + '/menu'


def listing_links(text):
    """Distinct Leafly dispensary listings a retailer page links to (its menu, deals and review pages count once)."""
    return list(dict.fromkeys(listing_url(slug) for slug in _LISTING.findall(text or '')))


def page_props(response):
    from backend.adapters import _next_data
    text = response.body.decode('utf-8', errors='replace') if isinstance(response.body, bytes) else response.body
    return _next_data(text)


def dispensary_identity(props):
    """The listing's own dispensary record, or None unless it names an id and a street address."""
    record = props.get('dispensary') if isinstance(props, dict) else None
    if not isinstance(record, dict) or not record.get('id') or not record.get('address1'):
        return None
    return record


def observe(url, response):
    record = dispensary_identity(page_props(response))
    slug = slug_from(url)
    if not record or not slug:
        return None
    place = (record.get('locations') or [{}])[0]
    details = dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at, retailer_name=record.get('name'),
                   retailer_address=record['address1'], retailer_city=record.get('city'),
                   method='Leafly dispensary listing (id, street address and map pin from the page data)')
    if place.get('lat') is not None and place.get('lon') is not None:
        details['platform_location'] = dict(lat=place['lat'], lng=place['lon'])
    return dict(url=menu_url(slug), provider='leafly', provider_store_id=str(record['id']), license_type='recreational',
                license_basis='leafly_variant_flag', resolution_evidence=details)


def normalize(product, endpoint, tax_exclusive):
    """One offer per variant of the endpoint's license menu. Leafly carries a recreational and a medical variant on the
    same product; only the endpoint's own is an offer. A listed sale is not the shelf price, and a menu whose prices
    include tax is not comparable with the pre-tax menus, so both stay out of the effective price."""
    from backend.adapters import _decimal
    if product.get('menuItemId') is None or not product.get('name') or not isinstance(product.get('variants'), list):
        raise ValueError('Leafly product identity/name/variants missing')
    medical = endpoint.get('license_type') == 'medicinal'
    category = product.get('productCategory') or 'Unknown'
    stock = product.get('stockQuantity')
    items = []
    for variant in product['variants']:
        if variant.get('id') is None:
            raise ValueError('Leafly variant identity missing')
        if bool(variant.get('medical')) != medical:
            continue
        quantity, unit = _decimal(variant.get('quantity')), str(variant.get('unit') or '').lower()
        weight = quantity if unit == 'g' else _decimal(Decimal(quantity) * GRAMS_PER_OUNCE) if unit == 'oz' and quantity else None
        price = _decimal(variant.get('price'))
        taxed = product.get('priceIncludesTax') is True or not tax_exclusive
        items.append({'source_id': str(product['menuItemId']), 'variant_id': str(variant['id']), 'name': product['name'], 'brand': product.get('brandName'),
                      'category': CATEGORIES.get(category.lower(), 'other'), 'source_category': category, 'subcategory': None, 'strain_type': None,
                      'thc_pct': _decimal(product.get('thcContent')) if product.get('thcUnit') == 'percent' else None,
                      'weight_grams': weight, 'weight_label': variant.get('displayQuantity'),
                      'regular_price': price, 'effective_price': price, 'conditional': taxed,
                      # A product on the live menu is orderable unless its own stock count says none is left.
                      'available': stock is None or (isinstance(stock, (int, float)) and stock > 0),
                      'source_url': endpoint['url'],
                      'raw': {'product': {k: v for k, v in product.items() if k != 'variants'}, 'variant': variant}})
    return items


def _fingerprint(items):
    rows = sorted((inventory_fields(item) for item in items), key=lambda i: (i['source_id'], i['variant_id']))
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def fetch(endpoint, fetcher):
    result = dict(provider='leafly', adapter_version=VERSION, items=[], complete=False, expected_count=None, pages=[], errors=[], evidence=[],
                  authoritative_zero=False, limits=dict(max_pages=int(endpoint.get('max_pages', 500)), verification_passes=2),
                  count_semantics='the menu total counts product records; expected_count is the license menu variants of those products')
    try:
        if endpoint.get('license_type') not in ('recreational', 'medicinal'):
            raise ValueError('unverified Leafly license context')
        slug = slug_from(endpoint['url'])
        if not slug:
            raise ValueError('Leafly endpoint is not a dispensary listing')
        home = fetcher.get(listing_url(slug))
        result['evidence'].append(home.evidence_id)
        if home.status_code != 200:
            raise ValueError(f'Leafly listing HTTP {home.status_code}')
        record = dispensary_identity(page_props(home))
        if not record or str(record['id']) != str(endpoint['provider_store_id']):
            raise ValueError('Leafly listing identity does not match the endpoint')
        target = (getattr(fetcher, 'browser_options', None) or {}).get('target_store') or {}
        if target.get('address'):
            from backend.locators import addresses_match
            if not addresses_match(target['address'], record['address1']):
                raise ValueError('Menu source belongs to a different street address: ' + record['address1'])
        tax_exclusive = record.get('menuTaxPricing') == TAX_EXCLUSIVE
        result['price_basis'] = record.get('menuTaxPricing') or 'unstated'
        base, max_pages = menu_url(slug), result['limits']['max_pages']
        passes, pass_items, drift, total, convergence = [], [], [], None, None
        for traversal in range(2):
            items, seen, records, page, page_size, totals = [], set(), 0, 1, None, set()
            while True:
                if page > max_pages:
                    raise ValueError('Leafly menu page limit reached')
                response = fetcher.get(f'{base}?page={page}')
                result['evidence'].append(response.evidence_id)
                if response.status_code != 200:
                    raise ValueError(f'Leafly menu HTTP {response.status_code} at page {page}')
                data = page_props(response).get('menuData')
                rows = data.get('menuItems') if isinstance(data, dict) else None
                count = data.get('totalItems') if isinstance(data, dict) else None
                if not isinstance(rows, list) or not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    raise ValueError('Leafly menu page has no product list or total')
                if page_size is None:
                    page_size = len(rows)
                totals.add(count)
                total = count
                if any(str(row.get('dispensaryId')) != str(endpoint['provider_store_id']) for row in rows):
                    raise ValueError('Leafly menu returned products from another dispensary')
                for row in rows:
                    records += 1
                    if row.get('menuItemId') in seen:
                        # The live listing moved under the read: the same product on two pages means another was missed.
                        drift.append(dict(traversal=traversal + 1, page=page, kind='repeated_product', product=row.get('menuItemId')))
                        continue
                    seen.add(row.get('menuItemId'))
                    items.extend(normalize(row, endpoint, tax_exclusive))
                result['pages'].append(dict(traversal=traversal + 1, page=page, products=len(rows), advertised_total=count, evidence_id=response.evidence_id))
                if traversal == 0:
                    result['items'] = items.copy()
                if records >= count or len(rows) < page_size or not rows:
                    break
                page += 1
            if len(totals) > 1:
                drift.append(dict(traversal=traversal + 1, kind='total_changed', totals=sorted(totals)))
            # Live inventory moves while the pages are read; a few products' difference (within 1%) is churn, never a reconciled read.
            if records != total:
                if abs(records - total) > total // 100:
                    raise ValueError(f'Leafly menu did not reconcile: read {records} products, advertised {total}')
                drift.append(dict(traversal=traversal + 1, kind='count_off', read=records, advertised=total))
            if len(seen) < records and records - len(seen) > total // 100:
                raise ValueError('Leafly menu repeated too many products')
            passes.append(_fingerprint(items))
            pass_items.append(items)
        if passes[0] != passes[1] or drift:
            from backend.completeness import churn_convergence
            convergence = churn_convergence(pass_items[0], pass_items[1], kind='churn_tolerant', source_total=total)
            if not convergence:
                raise ValueError('Leafly menu changed across independent full traversals')
            if drift:
                convergence['page_drift'] = drift
        if convergence:
            result.update(complete=False, expected_count=len(pass_items[1]), source_product_count=total, convergence=convergence)
        else:
            result.update(complete=True, expected_count=len(result['items']), source_product_count=total, authoritative_zero=total == 0)
    except Exception as exc:
        result['errors'].append(dict(code='incomplete_leafly_menu', message=str(exc)))
    return result
