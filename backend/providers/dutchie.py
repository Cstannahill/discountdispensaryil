"""Observed Dutchie embedded menu: the page's own persisted FilteredProducts query, paged to the platform's exact total.

Dutchie's edge (Cloudflare) refuses our honestly identified HTTP client with 403, for the menu page and its GraphQL API
alike. That refusal is respected, not worked around: the reads run inside the rendered page (installed Chrome owns HTTP;
same origin, GET only, every response captured as evidence; see browser_worker `page_reads`). The operation, its
persisted-query hash, its API path and its client headers are taken from the request the page itself made.

Whole-menu rule: the filter keeps only context/presentation keys (no staffPicks, specials, ids, types or strains). The
storefront also asks the server to drop products whose every option is below its online threshold, but the server
counts them first (Noxx: 1053 advertised, 1042 returned, pages of 98-99). They are read here
(`removeProductsBelowOptionThresholds: false`) and marked unavailable from `optionsBelowThreshold`, so every page is full
and the menu reconciles exactly to `queryInfo.totalCount`.

Order: the default "Featured" order has ties that repeat and drop products across page boundaries (Cloud9 East Peoria:
2 of 1458, the same way on every pass). The page is rendered in the storefront's own "Price low to high" view, whose
query (`sortBy: price`, `isDefaultSort: false`) pages deterministically; its sort keys are kept from the page's query.

Branch identity: the dispensary record the page looks up (ConsumerDispensaries, by the endpoint's id or cName) declares
its street (`location.ln1`) and point. The street must match the registry address and the point must lie within
NEAR_MILES of the registry point; every product must carry that dispensary's id.
"""
import hashlib
import json
import math
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from backend.domain import inventory_fields

VERSION = 'dutchie-filtered-products-1'
MENU = 'https://dutchie.com/embedded-menu/{}/products?sortby=pricelowtohigh'
PAGE = 100
MAX_PAGES = 200
BATCH = 8
NEAR_MILES = 5.0
_STORE_KEY = re.compile(r'^(?:[0-9a-f]{24}|[a-z0-9]+(?:-[a-z0-9]+)*)$')
# Path segments that discovery has mistaken for a dispensary (embed script versions, store experience pages).
_NOT_A_DISPENSARY = frozenset(('v1', 'v2', 'v3', 'api', 'stores', 'embedded-menu', 'experiences', 'dispensary', 'dispensaries'))
_CHALLENGE = re.compile(r'just a moment|attention required|cf-chl|captcha', re.I)


def _miles(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 7917.5 * math.asin(math.sqrt(a))


def whole_menu_filter(observed, dispensary_id, pricing_type):
    """The page's own products filter reduced to context/presentation keys: one dispensary's whole menu."""
    from backend.network_extract import _BENIGN_FILTER_KEYS
    built = {key: value for key, value in (observed or {}).items() if key in _BENIGN_FILTER_KEYS}
    built.update(dispensaryId=dispensary_id, pricingType=pricing_type, types=[], strainTypes=[], subcategories=[], Status='Active',
                 removeProductsBelowOptionThresholds=False)
    return built


def observed_query(observed, operation):
    """The first GET of `operation` the page made against a Dutchie GraphQL path, with its persisted-query hash."""
    for entry in observed or []:
        parts = urlsplit(entry.get('url') or '')
        if parts.scheme != 'https' or parts.hostname not in ('dutchie.com', 'www.dutchie.com') or not parts.path.endswith('/graphql'):
            continue
        values = parse_qs(parts.query)
        if values.get('operationName') != [operation]:
            continue
        try:
            variables, extensions = json.loads(values['variables'][0]), json.loads(values['extensions'][0])
            digest = extensions['persistedQuery']['sha256Hash']
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if not isinstance(variables, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(digest)):
            continue
        if operation == 'FilteredProducts' and not isinstance(variables.get('productsFilter'), dict):
            continue
        return dict(url=entry['url'], origin=f'{parts.scheme}://{parts.netloc}', path=parts.path, variables=variables, extensions=extensions,
                    sha256Hash=digest, headers=dict(entry.get('headers') or {}))
    return None


def _read(query, operation, variables):
    url = query['origin'] + query['path'] + '?' + urlencode(dict(operationName=operation, variables=json.dumps(variables, separators=(',', ':')),
                                                                 extensions=json.dumps(query['extensions'], separators=(',', ':'))))
    return dict(url=url, headers=query['headers'])


def _json(answer, what):
    status, body = answer.get('status'), answer.get('body') or ''
    if status != 200:
        if _CHALLENGE.search(body):
            raise ValueError(f'Access challenge: Dutchie refused the in-page {what} read (HTTP {status}); reported, not bypassed')
        if not status:
            raise ValueError(f"Public fetch failed inside the page for the Dutchie {what} read: {answer.get('error') or 'no response'}")
        raise ValueError(f'Dutchie {what} read returned HTTP {status}')
    value = json.loads(body)
    if value.get('errors'):
        raise ValueError(f'Schema drift: Dutchie {what} query returned errors: ' + '; '.join(str(e.get('message')) for e in value['errors'][:3]))
    return value


def _restricted_sale(product):
    """A sale special with purchase or payment restrictions makes its special price conditional."""
    specials = (product.get('specialData') or {}).get('saleSpecials') or []
    return any(isinstance(s, dict) and (s.get('specialRestrictions') or s.get('paymentRestrictions')) for s in specials)


def prove_branch(dispensary, target):
    if not target.get('address'):
        raise ValueError('Dutchie branch cannot be proven without a registry street address')
    location = dispensary.get('location') or {}
    street = location.get('ln1')
    if not isinstance(street, str) or not street.strip():
        raise ValueError('Dutchie dispensary declares no street address; branch cannot be proven')
    from backend.locators import addresses_match
    if not addresses_match(target['address'], street):
        raise ValueError('Menu source belongs to a different street address: ' + street)
    distance = None
    point = (location.get('geometry') or {}).get('coordinates')
    try:
        distance = _miles(float(target['latitude']), float(target['longitude']), float(point[1]), float(point[0]))
    except (KeyError, IndexError, TypeError, ValueError):
        if str(location.get('city') or '').strip().lower() != str(target.get('city') or '').strip().lower():
            raise ValueError(f"Menu source belongs to a different location: {location.get('city')} is not the registry city")
    if distance is not None and distance > NEAR_MILES:
        raise ValueError(f'Menu source belongs to a different location: {distance:.2f} mi from the registry address')
    return dict(method='platform_address', dispensary_id=str(dispensary.get('id')), cName=dispensary.get('cName'), street=street.strip(),
                city=location.get('city'), platform_distance_miles=round(distance, 2) if distance is not None else None,
                dispensary_status=dispensary.get('status'))


def _traverse(endpoint, target, license_type, result):
    """Reads as a generator: yields lists of page reads, receives their answers in the same order."""
    from backend.network_extract import _products
    from backend.completeness import churn_convergence
    observed = yield
    store_key = str(endpoint['provider_store_id'])
    lookup, query = observed_query(observed, 'ConsumerDispensaries'), observed_query(observed, 'FilteredProducts')
    for name, found in (('ConsumerDispensaries', lookup), ('FilteredProducts', query)):
        if not found:
            raise ValueError(f'Required source query missing: the Dutchie page did not issue its {name} query')
    asked = str((lookup['variables'].get('dispensaryFilter') or {}).get('cNameOrID'))
    if asked != store_key:
        raise ValueError(f'Menu source belongs to a different branch: the page looked up dispensary {asked}, not {store_key}')
    (answer,) = yield [dict(url=lookup['url'], headers=lookup['headers'])]
    found = (_json(answer, 'dispensary').get('data') or {}).get('filteredDispensaries')
    if not isinstance(found, list) or len(found) != 1:
        raise ValueError('Dutchie dispensary lookup did not return exactly one dispensary')
    dispensary = found[0]
    if store_key not in (str(dispensary.get('id')), dispensary.get('cName')):
        raise ValueError(f"Menu source belongs to a different branch: Dutchie dispensary {dispensary.get('id')} ({dispensary.get('cName')})")
    result['branch_proof'] = prove_branch(dispensary, target)
    if not dispensary.get('medicalDispensary' if license_type == 'medicinal' else 'recDispensary'):
        raise ValueError('Dutchie dispensary does not serve the endpoint license context')
    dispensary_id = str(dispensary['id'])
    products_filter = whole_menu_filter(query['variables']['productsFilter'], dispensary_id, 'med' if license_type == 'medicinal' else 'rec')
    extra = {key: value for key, value in query['variables'].items() if key not in ('productsFilter', 'page', 'perPage')}
    result['query'] = dict(operationName='FilteredProducts', sha256Hash=query['sha256Hash'], path=query['path'], per_page=PAGE, products_filter=products_filter)

    def read(number):
        return _read(query, 'FilteredProducts', dict(extra, productsFilter=products_filter, page=number, perPage=PAGE))

    passes, pass_items, total = [], [], None
    for traversal in range(2):
        (first,) = yield [read(0)]
        info = (((_json(first, 'products').get('data') or {}).get('filteredProducts') or {}).get('queryInfo')) or {}
        count, pages = info.get('totalCount'), info.get('totalPages')
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (count, pages)) or pages != math.ceil(count / PAGE):
            raise ValueError('Dutchie queryInfo is not an exact total (inconsistent total)')
        if pages > MAX_PAGES:
            raise ValueError('Dutchie menu exceeds the page limit')
        if total is None:
            total = count
        if count != total:
            raise ValueError('Dutchie menu total changed between traversals')
        answers, rest = {0: first}, list(range(1, pages))
        for start in range(0, len(rest), BATCH):
            batch = rest[start:start + BATCH]
            answers.update(zip(batch, (yield [read(n) for n in batch])))
        items, seen, records = [], set(), set()
        for number in range(max(pages, 1)):
            found = (_json(answers[number], 'products').get('data') or {}).get('filteredProducts') or {}
            products = found.get('products')
            if (found.get('queryInfo') or {}).get('totalCount') != total:
                raise ValueError('Dutchie menu total changed between pages')
            expected = min(PAGE, total - number * PAGE)
            if not isinstance(products, list) or len(products) != expected:
                raise ValueError(f'Dutchie page {number} returned {len(products or [])} of {expected} products; menu does not reconcile to its total {total}')
            for product in products:
                product_id = str(product.get('id') or product.get('_id') or '')
                if str(product.get('DispensaryID')) != dispensary_id:
                    raise ValueError('Menu source belongs to a different branch: Dutchie returned a product of another dispensary')
                if not product_id or product_id in records:
                    raise ValueError('Dutchie pagination repeated or lost a product identity')
                records.add(product_id)
                variants = _products([product], endpoint['url'], license_type)
                excluded = product.get('medicalOnly' if license_type == 'recreational' else 'recOnly') is True
                if not variants and not excluded:
                    raise ValueError(f'Unrecognized schema: Dutchie product {product_id} has no readable price options')
                restricted = _restricted_sale(product)
                for item in variants:
                    if restricted and float(item['effective_price']) < float(item['regular_price']):
                        item['conditional'] = True
                    identity = (item['source_id'], item['variant_id'])
                    if identity in seen:
                        raise ValueError('Dutchie repeated product/variant')
                    seen.add(identity)
                    items.append(item)
            result['pages'].append(dict(traversal=traversal + 1, page=number, products=len(products), advertised_total=total))
        if len(records) != total:
            raise ValueError('Dutchie pages did not reconcile to queryInfo.totalCount (does not reconcile)')
        if traversal == 0:
            result['items'] = items.copy()
        passes.append(hashlib.sha256(json.dumps(sorted((inventory_fields(i) for i in items), key=lambda i: (i['source_id'], i['variant_id'])), sort_keys=True, default=str).encode()).hexdigest())
        pass_items.append(items)
    convergence = None
    if passes[0] != passes[1]:
        # Each traversal reconciled to the same total; live price or stock churn is graded B, not discarded.
        convergence = churn_convergence(pass_items[0], pass_items[1], kind='churn_tolerant', source_total=total)
        if not convergence:
            raise ValueError('Dutchie catalog changed across independent full traversals')
    if convergence:
        result.update(complete=False, expected_count=len(pass_items[1]), source_product_count=total, convergence=convergence)
    else:
        result.update(complete=True, expected_count=len(result['items']), source_product_count=total, authoritative_zero=total == 0)


class _Reader:
    """Drives the traversal from the page-read protocol. The first failure ends the reads and is re-raised after the
    render, so the render's own evidence is always completed."""
    def __init__(self, steps):
        self.steps, self.started, self.done, self.error = steps, False, False, None

    def __call__(self, message):
        if self.done or self.error is not None:
            return dict(reads=[])
        try:
            if not self.started:
                self.started = True
                next(self.steps)
                reads = self.steps.send(message.get('observed') or [])
            else:
                reads = self.steps.send(message.get('results') or [])
        except StopIteration:
            self.done = True
            return dict(reads=[])
        except Exception as exc:
            self.error = exc
            return dict(reads=[])
        return dict(reads=reads)


def fetch(endpoint, fetcher):
    result = dict(provider='dutchie', adapter_version=VERSION, items=[], complete=False, expected_count=None, pages=[], errors=[], evidence=[],
                  authoritative_zero=False, limits=dict(page_size=PAGE, max_pages=MAX_PAGES, verification_passes=2, transport='in_page_reads'),
                  count_semantics='queryInfo.totalCount counts product records; expected_count is expanded option variants of the license menu')
    try:
        store_key = str(endpoint.get('provider_store_id') or '')
        if not _STORE_KEY.match(store_key) or store_key in _NOT_A_DISPENSARY:
            raise ValueError(f'Dutchie endpoint has no dispensary id or cName ({store_key or "none"}); rediscovery required')
        license_type = endpoint.get('license_type') or 'recreational'
        target = (getattr(fetcher, 'browser_options', None) or {}).get('target_store') or {}
        reader = _Reader(_traverse(endpoint, target, license_type, result))
        capture = fetcher.render_reads(MENU.format(store_key), reader, license_type=license_type)
        result['evidence'].append(capture.evidence_id)
        if capture.status_code >= 400:
            body = capture.body.decode('utf-8', errors='replace') if isinstance(capture.body, bytes) else str(capture.body)
            raise ValueError(('Access challenge: ' if _CHALLENGE.search(body) else '') + f'Dutchie menu page returned HTTP {capture.status_code}')
        if reader.error is not None:
            raise reader.error
        if not reader.done:
            raise ValueError('Dutchie page reads ended before both traversals finished')
    except Exception as exc:
        result.update(complete=False)
        result.pop('convergence', None)
        result['errors'].append(dict(code='incomplete_dutchie_menu', message=str(exc)))
    return result
