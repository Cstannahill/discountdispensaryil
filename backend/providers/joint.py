"""Observed joint-ecommerce (WordPress) storefront: the page's business identity and its public product search.

The storefront's own search (Elasticsearch-style) is read with the same filters the page uses: one business, one menu
type, not deleted. Its hit total is exact, so a full menu reconciles without visible-page guessing.
"""
from decimal import Decimal
import hashlib
import json
import re
from urllib.parse import urlsplit

from backend.domain import inventory_fields
from backend.site_discovery import Page, license_context, objects

SEARCH = '/wp-json/joint-ecommerce/v1/products/ecommerce-production/_search'
VERSION = 'joint-search-1'
PAGE = 100
WINDOW = 10000
CATEGORIES = {'FLOWER': 'flower', 'CONCENTRATES': 'concentrate', 'VAPORIZERS': 'vapes'}


def current_store(text):
    """The storefront's own store config (`jointEcommerce.currentStore = {...}`), when the page embeds it."""
    marker = re.search(r'jointEcommerce\.currentStore\s*=\s*', text)
    if not marker:
        return None
    value, _ = json.JSONDecoder().raw_decode(text[marker.end():])
    return value if isinstance(value, dict) else None


def joint_store(text, url):
    """Business id, name and street address for the page, or None unless exactly one business is identified."""
    store = current_store(text)
    if store and store.get('joint_business_id'):
        return dict(id=str(store['joint_business_id']), name=store.get('display_name') or store.get('name'),
                    address=store.get('address_1'), method='jointEcommerce.currentStore')
    ids = set(re.findall(r'stores\\?/(\d+)', text))
    if len(ids) != 1:
        return None
    page = Page(text, url)
    business = next((o for o in objects(page.structured) if o.get('@type') == 'LocalBusiness' and str(o.get('@id', '')).endswith('/stores/' + next(iter(ids)))), None)
    if not business:
        return None
    address = business.get('address') or {}
    return dict(id=next(iter(ids)), name=business.get('name'), address=address.get('streetAddress'), method='LocalBusiness store schema')


def observe(url, response):
    text = response.body.decode('utf-8', errors='replace')
    store = joint_store(text, response.url)
    if not store:
        return None
    context, basis = license_context(url, text)
    return dict(url=response.url, provider='joint', provider_store_id=store['id'], license_type=context, license_basis=basis,
                resolution_evidence=dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at,
                                         retailer_name=store['name'], retailer_address=store['address'],
                                         method='Observed joint-ecommerce storefront business identity (' + store['method'] + ')'))


def normalize(product, endpoint, menu='RECREATIONAL'):
    from backend.adapters import _decimal
    from backend.network_extract import _option_grams
    if not product.get('jointId'):
        raise ValueError('Joint product identity missing')
    category = product.get('category') or 'unknown'
    conditional_product = bool(product.get('applicableSpecials'))
    result = []
    for variant in product.get('variants') or []:
        if variant.get('menuType') != menu:
            continue
        if not variant.get('jointId'):
            raise ValueError('Joint variant identity missing')
        option = variant.get('option') or ''
        quantity = _decimal(variant.get('quantity'))
        special = variant.get('specialPrice')
        result.append(dict(source_id=str(product['jointId']), variant_id=str(variant['jointId']), name=product.get('name') or '',
                           brand=product.get('brandName'), category=CATEGORIES.get(category, 'other'), source_category=category,
                           subcategory=product.get('subCategory'), strain_type=product.get('strainType'), thc_pct=None,
                           weight_grams=_option_grams(option), weight_label=option or None,
                           regular_price=_decimal(variant.get('price')),
                           effective_price=_decimal(special if special is not None else variant.get('price')),
                           conditional=bool(conditional_product or variant.get('appliedSpecials')),
                           available=quantity is not None and Decimal(quantity) > 0, source_url=endpoint['url'],
                           raw=dict(product=product, variant=variant)))
    return result


def fetch(endpoint, fetcher):
    result = dict(provider='joint', adapter_version=VERSION, items=[], complete=False, expected_count=None, pages=[], errors=[], evidence=[],
                  authoritative_zero=False, limits=dict(page_size=PAGE, max_pages=int(endpoint.get('max_pages', 1000)), verification_passes=2),
                  count_semantics='Public search total counts product records; expected_count is expanded variants of the license menu type')
    try:
        parts = urlsplit(endpoint['url'])
        origin = f'{parts.scheme}://{parts.netloc}'
        page = fetcher.get(endpoint['url'])
        result['evidence'].append(page.evidence_id)
        store = joint_store(page.body.decode('utf-8', errors='replace'), page.url)
        if not store or store['id'] != str(endpoint['provider_store_id']):
            raise ValueError('Joint storefront business identity does not match the endpoint')
        target = (getattr(fetcher, 'browser_options', None) or {}).get('target_store') or {}
        if target.get('address') and store.get('address'):
            from backend.locators import addresses_match
            if not addresses_match(target['address'], store['address']):
                raise ValueError('Menu source belongs to a different street address: ' + store['address'])
        menu = 'MEDICAL' if endpoint.get('license_type') == 'medicinal' else 'RECREATIONAL'
        headers = {'content-type': 'application/json', 'accept': 'application/json', 'origin': origin, 'referer': endpoint['url']}
        business_filter = [{'bool': {'should': [{'term': {'businessId': store['id']}}]}},
                           {'bool': {'should': [{'term': {'menuType': menu}}]}},
                           {'bool': {'must_not': [{'term': {'isDeleted': True}}]}}]
        passes, pass_items, total, convergence = [], [], None, None
        for traversal in range(2):
            items, seen, records, offset = [], set(), 0, 0
            while True:
                if offset >= WINDOW or len(result['pages']) >= result['limits']['max_pages']:
                    raise ValueError('Joint search page limit reached')
                # itemsSold alone has ties that reorder between requests; the product id makes each page stable.
                body = {'query': {'bool': {'filter': business_filter}}, 'from': offset, 'size': PAGE,
                        'sort': [{'itemsSold': 'desc'}, {'jointId': 'asc'}]}
                response = fetcher.post(origin + SEARCH, json=body, headers=headers)
                result['evidence'].append(response.evidence_id)
                value = response.json()
                hits = value['hits']['hits']
                count = value['hits']['total']
                if count.get('relation') != 'eq' or not isinstance(count.get('value'), int):
                    raise ValueError('Joint search total is not exact')
                if total is None:
                    total = count['value']
                if total != count['value']:
                    raise ValueError('Joint search total changed between pages')
                if any(str(hit['_source'].get('businessId')) != store['id'] for hit in hits):
                    raise ValueError('Joint search returned products from another business')
                if not hits:
                    raise ValueError('Joint search page is empty before the advertised total')
                for hit in hits:
                    records += 1
                    for item in normalize(hit['_source'], endpoint, menu):
                        identity = (item['source_id'], item['variant_id'])
                        if identity in seen:
                            raise ValueError('Joint repeated product/variant page')
                        seen.add(identity)
                        items.append(item)
                result['pages'].append(dict(traversal=traversal + 1, offset=offset, products=len(hits), advertised_total=total,
                                            evidence_id=response.evidence_id))
                # Keep what the first traversal has read so far: a capped or failed read is incomplete, but its products are real.
                if traversal == 0:result['items'] = items
                offset += len(hits)
                if offset >= total:
                    break
            if records != total:
                raise ValueError('Joint search did not reconcile to its advertised total')
            if traversal == 0:
                result['items'] = items.copy()
            fingerprint = hashlib.sha256(json.dumps(sorted((inventory_fields(item) for item in items), key=lambda i: (i['source_id'], i['variant_id'])), sort_keys=True).encode()).hexdigest()
            passes.append(fingerprint)
            pass_items.append(items)
        if passes[0] != passes[1]:
            # Each traversal reconciled to the same advertised total; live price or stock churn is graded B, not discarded.
            from backend.completeness import churn_convergence
            convergence = churn_convergence(pass_items[0], pass_items[1], kind='churn_tolerant', source_total=total)
            if not convergence:
                raise ValueError('Joint catalog changed across independent full traversals')
        if convergence:
            result.update(complete=False, expected_count=len(pass_items[1]), source_product_count=total, convergence=convergence)
        else:
            result.update(complete=True, expected_count=len(result['items']), source_product_count=total, authoritative_zero=total == 0)
    except Exception as exc:
        result['errors'].append(dict(code='incomplete_joint_menu', message=str(exc)))
    return result
