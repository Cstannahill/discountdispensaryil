"""Observed Jane storefront search (dmerch): every product of one store, read in facet slices that reconcile exactly.

The storefront's own search returns, per filter, the matching ids (up to a 1000-hit window) with attributes for the
first page, and hydrates further ids 60 at a time. The `kind` facet counts sum to the store's total, so each kind is a
slice; a kind larger than the window is split by brand. Every slice must return exactly its facet count.

Branch and license come from the records themselves: each carries its store's `_geoloc` and `store_types`. (Jane's
store-detail API refuses our honestly identified client with 403; that block is respected, not worked around.)
"""
import hashlib
import json
import math
import re
import uuid

from backend.domain import inventory_fields

API = 'https://dmerch.iheartjane.com'
PAGE = 'https://www.iheartjane.com/stores/'
# The storefront's SDK identifies itself with these; the key itself is read from the page.
SOURCE, SDK_VERSION = 'monolith', '2.25.0'
VERSION = 'jane-dmerch-1'
WINDOW = 1000
HYDRATE = 60
# Registry coordinates are approximate for some stores (1-3 mi off the street address). A platform location at the
# registry point proves the branch by itself; a nearby one only together with the branch identity the retailer page
# proved at resolution. Anything farther is another branch (sibling embeds sit 30-300 mi away).
MAX_MILES = 0.35
NEAR_MILES = 5.0


def _miles(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 7917.5 * math.asin(math.sqrt(a))


def _quoted(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def api_key(endpoint, fetcher, evidence):
    """The public SDK key the storefront page embeds (`dmSdkApiKey`)."""
    if endpoint.get('public_api_key'):
        return endpoint['public_api_key']
    cached = getattr(fetcher, '_jane_sdk_key', None)
    if cached:
        evidence.extend(cached['evidence'])
        return cached['key']
    response = fetcher.get(PAGE + str(endpoint['provider_store_id']))
    evidence.append(response.evidence_id)
    match = re.search(r'"dmSdkApiKey"\s*:\s*"([0-9a-f-]{36})"', response.body.decode('utf-8', errors='replace'))
    if not match:
        raise ValueError('Jane storefront SDK key could not be located')
    fetcher._jane_sdk_key = dict(key=match[1], evidence=list(evidence))
    return match[1]


def slices(kind_counts, brand_counts):
    """Search filters whose hits each fit the window, with the count each must return. `brand_counts(kind)` is only
    asked for kinds larger than the window."""
    out = []
    for kind, count in sorted(kind_counts.items()):
        if count <= WINDOW:
            out.append(dict(filter='kind:' + _quoted(kind), expected=count))
            continue
        brands = brand_counts(kind)
        if sum(brands.values()) != count:
            raise ValueError(f'Jane brand facet does not reconcile to the {kind} total')
        for brand, size in sorted(brands.items()):
            if size > WINDOW:
                raise ValueError(f'Jane slice {kind}/{brand} exceeds the search window')
            out.append(dict(filter='kind:' + _quoted(kind) + ' AND brand:' + _quoted(brand), expected=size))
    return out


def fetch(endpoint, fetcher):
    from backend.network_extract import _products
    result = dict(provider='jane', adapter_version=VERSION, items=[], complete=False, expected_count=None, pages=[], errors=[], evidence=[],
                  authoritative_zero=False, limits=dict(window=WINDOW, hydrate=HYDRATE, verification_passes=2),
                  count_semantics='kind facet total counts product records; expected_count is expanded weight/price variants')
    try:
        store_id = int(endpoint['provider_store_id'])
        license_type = endpoint.get('license_type') or 'recreational'
        menu_type = 'medical' if license_type == 'medicinal' else 'recreational'
        target = (getattr(fetcher, 'browser_options', None) or {}).get('target_store') or {}
        try:
            origin = (float(target['latitude']), float(target['longitude']))
        except (KeyError, TypeError, ValueError):
            raise ValueError('Jane branch location cannot be proven without registry coordinates')

        def check_store(attrs):
            if menu_type not in (attrs.get('store_types') or []):
                raise ValueError('Jane store does not serve the endpoint license context')
            geo = attrs.get('_geoloc') or {}
            if not isinstance(geo.get('lat'), (int, float)) or not isinstance(geo.get('lng'), (int, float)):
                raise ValueError('Jane record has no store location')
            distance = _miles(origin[0], origin[1], geo['lat'], geo['lng'])
            if distance <= MAX_MILES:
                method = 'platform_location'
            elif distance <= NEAR_MILES and endpoint.get('identity_confidence') in ('matched', 'name_locality'):
                method = 'retailer_page_identity'
            else:
                raise ValueError(f'Menu source belongs to a different location: {distance:.2f} mi from the registry address')
            result['branch_proof'] = dict(method=method, platform_distance_miles=round(distance, 2),
                                          identity_confidence=endpoint.get('identity_confidence'))
        key = api_key(endpoint, fetcher, result['evidence'])
        query = f'?jdm_api_key={key}&jdm_source={SOURCE}&jdm_version={SDK_VERSION}'
        device = 'T' + uuid.uuid4().hex[:20]
        headers = {'content-type': 'application/json', 'accept': 'application/json', 'referer': 'https://www.iheartjane.com/'}

        def post(path, body):
            response = fetcher.post(API + path + query, json=body, headers=headers)
            result['evidence'].append(response.evidence_id)
            return response.json()

        def facet(name, search_filter=None):
            body = dict(appMode='default', janeDeviceId=device, searchFacets=[name], storeId=store_id)
            if search_filter:
                body['searchFilter'] = search_filter
            counts = post('/v2/facets', body)['searchFacets'].get(name) or {}
            if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in counts.values()):
                raise ValueError('Invalid Jane facet count')
            return counts

        passes, pass_items, total = [], [], None
        for traversal in range(2):
            kinds = facet('kind')
            count = sum(kinds.values())
            if total is None:
                total = count
            if count != total:
                raise ValueError('Jane menu total changed between traversals')
            items, seen, records = [], set(), set()
            for part in slices(kinds, lambda kind: facet('brand', 'kind:' + _quoted(kind))):
                placement = dict(disable_ads=True, page_size=HYDRATE, placement='menu_inline_table', search_filter=part['filter'],
                                 search_query='', search_sort='recommendation')
                value = post('/v2/multi', dict(app_mode='default', distinct_id='$device:' + device, jane_device_id=device,
                                               search_attributes=['*'], store_id=store_id, placements=[placement], type='custom'))
                found = value['placements'][0]
                products = found.get('products') or []
                if found.get('nb_hits') != part['expected'] or len(products) != part['expected']:
                    raise ValueError(f"Jane slice {part['filter']} returned {len(products)} of {part['expected']} products")
                missing = [p['object_id'] for p in products if not p.get('search_attributes')]
                hydrated = {}
                for start in range(0, len(missing), HYDRATE):
                    batch = missing[start:start + HYDRATE]
                    page = post('/v2/smartpage', dict(app_mode='default', jane_device_id=device, object_ids=batch, search_attributes=['*']))
                    hydrated.update({p['object_id']: p.get('search_attributes') for p in page.get('products') or [] if p.get('search_attributes')})
                    if any(object_id not in hydrated for object_id in batch):
                        raise ValueError('Jane hydration did not return every requested product')
                full = [dict(p, search_attributes=p.get('search_attributes') or hydrated[p['object_id']]) for p in products]
                if any(int(p.get('store_id', store_id)) != store_id or int(p['search_attributes'].get('store_id', store_id)) != store_id for p in full):
                    raise ValueError('Jane search returned products from another store')
                if full:
                    check_store(full[0]['search_attributes'])
                for product in full:
                    if product['product_id'] in records:
                        raise ValueError('Jane product appeared in two slices')
                    records.add(product['product_id'])
                for item in _products(full, endpoint['url'], license_type):
                    identity = (item['source_id'], item['variant_id'])
                    if identity in seen:
                        raise ValueError('Jane repeated product/variant')
                    seen.add(identity)
                    items.append(item)
                result['pages'].append(dict(traversal=traversal + 1, filter=part['filter'], products=len(products), advertised_total=part['expected'],
                                            hydrated=len(missing)))
            if len(records) != total:
                raise ValueError('Jane slices did not reconcile to the kind facet total')
            if traversal == 0:
                result['items'] = items.copy()
            passes.append(hashlib.sha256(json.dumps(sorted((inventory_fields(i) for i in items), key=lambda i: (i['source_id'], i['variant_id'])), sort_keys=True, default=str).encode()).hexdigest())
            pass_items.append(items)
        convergence = None
        if passes[0] != passes[1]:
            from backend.completeness import churn_convergence
            convergence = churn_convergence(pass_items[0], pass_items[1], kind='churn_tolerant', source_total=total)
            if not convergence:
                raise ValueError('Jane catalog changed across independent full traversals')
        if convergence:
            result.update(complete=False, expected_count=len(pass_items[1]), source_product_count=total, convergence=convergence)
        else:
            result.update(complete=True, expected_count=len(result['items']), source_product_count=total, authoritative_zero=total == 0)
    except Exception as exc:
        result['errors'].append(dict(code='incomplete_jane_menu', message=str(exc)))
    return result
