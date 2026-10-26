"""Carrot storefronts (getcarrot.io): the store's own whole-menu product search, replayed from the page and read to its exact total.

The storefront (`<div class="carrot-store-root">`) loads its menu from `api.<region>.getcarrot.io/api/v1/store/search-products?locId=N`,
a Typesense multi-search: `found` is the exact hit count and every hit is one product document with up to N priced options. The API
challenges non-browser clients, so the browser selects the location and replays the page's own unfiltered request (`q=*`), 250
products per page, twice through (see browser_worker `replayCarrotSearch`). A traversal must return every page, one constant total,
and exactly that many unique products; two traversals that agree make the menu complete.

Branch identity: the page's own `store/locations` response names each location's street (`addressLine1`); the endpoint's location
must match the registry street.
"""
import gzip
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from backend.completeness import churn_convergence
from backend.domain import category_of, inventory_fields

VERSION = 'carrot-search-1'
PAGE = 250
MAX_OPTIONS = 12
_MARKERS = ('carrot-store-root', 'getcarrot.io')


def location_id(url):
    """The Carrot location id a storefront URL selects (`?locId=2`), or None."""
    value = parse_qs(urlsplit(url or '').query).get('locId')
    return value[0] if value and value[0].isdigit() else None


def observe(url, response):
    """A Carrot storefront page that selects one location by `locId`, as an endpoint (the reader proves the branch)."""
    text = response.body.decode('utf-8', errors='replace') if isinstance(response.body, bytes) else response.body
    loc = location_id(response.url or url) or location_id(url)
    if not loc or not all(marker in text for marker in _MARKERS):
        return None
    return dict(url=response.url or url, provider='carrot', provider_store_id=loc, license_type='recreational',
                resolution_evidence=dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at,
                                         method='Carrot storefront location id (locId) in the menu URL; the reader proves the branch by the platform street'))


def _evidence_json(root, evidence_id):
    manifest = json.loads((root / 'manifests' / f'{evidence_id}.json').read_text(encoding='utf-8'))
    return json.loads(gzip.decompress((root / manifest['body_path']).read_bytes()).decode('utf-8', errors='replace'))


def render_calls(evidence_dir, render_evidence_id):
    """(locations, [search call, ...]) from one render's captured network: the page's `store/locations` answer, and each
    whole-menu replay in order as dict(page, per_page, value, evidence_id)."""
    root = Path(evidence_dir)
    try:
        diagnostics = json.loads((root / 'browser' / f'{render_evidence_id}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return [], []
    locations, calls = [], []
    for entry in diagnostics.get('network_json') or []:
        url = str(entry.get('url', ''))
        if entry.get('status') != 200 or '.getcarrot.io/api/v1/store/' not in url:
            continue
        try:
            if entry.get('method') == 'GET' and urlsplit(url).path.endswith('/store/locations'):
                locations = _evidence_json(root, entry['evidence_id']).get('locations') or locations
            elif entry.get('method') == 'POST' and urlsplit(url).path.endswith('/store/search-products'):
                searches = json.loads(entry.get('request_body') or '')['searches']
                if len(searches) != 1 or searches[0].get('q') != '*' or searches[0].get('filter_by') or searches[0].get('per_page') != PAGE:
                    continue
                results = _evidence_json(root, entry['evidence_id'])['results']
                calls.append(dict(page=int(searches[0]['page']), url=url, value=results[0], evidence_id=entry['evidence_id']))
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            continue
    return locations, calls


def traversals(calls, loc):
    """Split the replay calls into traversals (a page-1 call starts the next) and reconcile each to its exact total.
    Returns [(documents, total), ...]; raises when a traversal does not add up."""
    mine = [call for call in calls if location_id(call['url']) == str(loc)]
    runs = []
    for call in mine:
        if call['page'] == 1 or not runs:
            runs.append([])
        runs[-1].append(call)
    out = []
    for run in runs:
        totals = {call['value'].get('found') for call in run}
        if len(totals) != 1 or not isinstance(next(iter(totals)), int) or isinstance(next(iter(totals)), bool):
            raise ValueError('Carrot search total is not one exact number across the traversal')
        total = totals.pop()
        pages = sorted(call['page'] for call in run)
        if pages != list(range(1, max(1, math.ceil(total / PAGE)) + 1)):
            raise ValueError(f'Carrot traversal pages are not 1..{max(1, math.ceil(total / PAGE))}: got {pages}')
        documents, seen = [], set()
        for call in sorted(run, key=lambda call: call['page']):
            for hit in call['value'].get('hits') or []:
                document = hit.get('document') or {}
                if str(document.get('locationId')) != str(loc):
                    raise ValueError('Carrot search returned a product from another location')
                if document.get('id') in seen:
                    raise ValueError('Carrot search repeated a product across pages')
                seen.add(document.get('id'))
                documents.append(document)
        if len(documents) != total:
            raise ValueError(f'Carrot catalog did not reconcile to its advertised total: read {len(documents)} of {total} products')
        out.append((documents, total))
    return out


def normalize(document, endpoint):
    """One offer per priced option of the product. `qty` is the product's stock count; the menu does not state whether its prices
    carry tax, so no price is treated as a comparable pre-tax price."""
    from backend.adapters import _decimal
    if document.get('id') is None or not document.get('name'):
        raise ValueError('Carrot product identity/name missing')
    category = document.get('masterCategoryName') or document.get('categorySlug') or 'Unknown'
    options = [(index, document.get(f'option{index}Name'), document.get(f'option{index}Price')) for index in range(1, MAX_OPTIONS + 1)
               if document.get(f'option{index}Price') is not None]
    if not options:
        raise ValueError('Carrot product has no priced option')
    stock = document.get('qty')
    items = []
    for index, label, price in options:
        grams = None
        match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*g\s*', str(label or ''), re.I)
        if match:
            grams = _decimal(match[1])
        elif len(options) == 1 and not label and document.get('unitWeight'):
            grams = _decimal(document['unitWeight'])
        value = _decimal(price)
        items.append(dict(source_id=str(document['id']), variant_id=f"{document['id']}:{index}", name=document['name'], brand=document.get('brand'),
                          category=category_of(category) or 'other', source_category=category, subcategory=document.get('carrotSubcategory'),
                          strain_type=(str(document.get('strain') or '').title() or None), thc_pct=_decimal(document['thcPercentage']) if document.get('thcPercentage') else None,
                          weight_grams=grams, weight_label=label, regular_price=value, effective_price=value, conditional=True,
                          available=stock is None or (isinstance(stock, (int, float)) and stock > 0), source_url=endpoint['url'],
                          raw=dict(product={k: v for k, v in document.items() if k not in ('embedding',) and not re.match(r'option\d+(?:Name|Price|Points)$', k)},
                                   option=dict(index=index, name=label, price=price))))
    return items


def _fingerprint(items):
    rows = sorted((inventory_fields(item) for item in items), key=lambda i: (i['source_id'], i['variant_id']))
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def fetch(endpoint, fetcher):
    import copy
    result = dict(provider='carrot', adapter_version=VERSION, items=[], complete=False, expected_count=None, source_product_count=None, pages=[],
                  errors=[], evidence=[], authoritative_zero=False, limits=dict(page_size=PAGE, verification_passes=2),
                  count_semantics='search found = product documents; expected_count is the priced options observed', price_basis='unstated')
    try:
        loc = str(endpoint.get('provider_store_id') or '')
        if not loc.isdigit():
            raise ValueError('Carrot endpoint has no location id')
        if endpoint.get('license_type') != 'recreational':
            raise ValueError('Carrot search is read for recreational menus only')
        browser = copy.copy(fetcher)
        browser.browser_options = dict(getattr(fetcher, 'browser_options', {}), carrot_search=True, carrot_loc=loc, await_menu=False, scroll_menu=False)
        rendered = browser.render(endpoint['url'], license_type='recreational')
        result['evidence'].append(rendered.evidence_id)
        if rendered.status_code != 200:
            raise ValueError(f'Browser storefront HTTP {rendered.status_code}')
        locations, calls = render_calls(fetcher.evidence_dir, rendered.evidence_id)
        record = next((x for x in locations if str(x.get('id')) == loc and x.get('enabled') != 'Disabled'), None)
        if record is None:
            raise ValueError('Carrot store locations do not list this location')
        from backend.locators import addresses_match
        target = (getattr(fetcher, 'browser_options', None) or {}).get('target_store') or {}
        if not target.get('address'):
            raise ValueError('Carrot branch cannot be proven without a registry street address')
        if not addresses_match(target['address'], record.get('addressLine1') or ''):
            raise ValueError('Menu source belongs to a different street address: ' + str(record.get('addressLine1')))
        runs = traversals(calls, loc)
        if len(runs) < 2:
            raise ValueError(f'Carrot menu was traversed {len(runs)} time(s); two independent traversals are required')
        passes = [[item for document in documents for item in normalize(document, endpoint)] for documents, _ in runs[:2]]
        result['pages'] = [dict(page=call['page'], advertised_total=call['value'].get('found'), evidence_id=call['evidence_id']) for call in calls]
        result['items'] = passes[0].copy()
        result['branch_proof'] = dict(method='platform_address', street=record.get('addressLine1'), location=record.get('name'))
        if _fingerprint(passes[0]) == _fingerprint(passes[1]):
            result.update(complete=True, expected_count=len(passes[0]), source_product_count=runs[0][1], authoritative_zero=runs[0][1] == 0)
        else:
            convergence = churn_convergence(passes[0], passes[1], kind='churn_tolerant', source_total=runs[1][1])
            if not convergence:
                raise ValueError('Carrot catalog changed across independent full traversals')
            result.update(complete=False, expected_count=len(passes[0]), source_product_count=runs[0][1], convergence=convergence)
    except Exception as exc:
        if getattr(exc, 'evidence_id', None):
            result['evidence'].append(exc.evidence_id)
        result['errors'].append(dict(code='incomplete_carrot_menu', message=str(exc)))
    return result
