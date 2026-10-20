"""Treez Ecommerce storefronts whose catalog is the GapCommerce product search API.

The storefront lists its branches in `treezStores` (store UUID, street address, org id); that listing is read over plain
HTTP. The search API itself challenges non-browser clients, so the catalog is read from the browser: the storefront's own
search request, for the selected branch, is replayed from the page with its collapse removed, 100 variants per request,
sorted by id in both directions. Two independent traversals either reconcile to the hit total or the menu stays incomplete.
"""
import copy
import gzip
import hashlib
import json
import re
from pathlib import Path

from backend.completeness import churn_convergence
from backend.domain import inventory_fields

SEARCH = 'https://search-kyrok9udlk.gapcommerceapi.com/product/search'
VERSION = 'gapcommerce-search-2'
PAGE = 100
# The storefront's own recreational query (observed on a live Treez Ecommerce page); the browser replays it without the UI's collapse.
QUERY = {'bool': {'must': [
    {'bool': {'filter': {'range': {'customMinPrice': {'gte': 0, 'lte': 500000}}}}},
    {'bool': {'should': [{'match': {'isAboveThreshold': True}}]}},
    {'bool': {'should': [{'match': {'isHideFromMenu': False}}]}}]}}
DIRECTIONS = ('asc', 'desc')
# The storefront's base filters. A catalog traversal may use only these; a category or promotion query narrows the catalog.
BASE_FIELDS = frozenset(('customMinPrice', 'isAboveThreshold', 'isHideFromMenu'))
STRUCTURE = frozenset(('bool', 'filter', 'range', 'should', 'must', 'match', 'gte', 'lte'))


def store_records(text):
    """The storefront's branch records (`treezStores`), or [] when the page lists none."""
    # The list is serialized inside a Next.js RSC string, so its quotes arrive escaped.
    plain = text.replace('\\"', '"')
    marker = plain.find('"treezStores":[')
    if marker < 0:
        return []
    try:
        value, _ = json.JSONDecoder().raw_decode(plain[marker + len('"treezStores":'):])
    except ValueError:
        return []
    if not isinstance(value, list):
        return []
    return [record for record in value if isinstance(record, dict) and record.get('object_id') and record.get('address1')]


def same_branch(store, record):
    """A registry branch is this record when the street matches and the locality does not contradict it."""
    from backend.locators import addresses_match
    if not store.get('address') or not record.get('address1'):
        return False
    if not addresses_match(store['address'], record['address1']):
        return False
    city, record_city = str(store.get('city') or '').strip().lower(), str(record.get('city') or '').strip().lower()
    return not city or not record_city or city == record_city


def license_of(record):
    return {'ADULT': 'recreational', 'MEDICAL': 'medicinal'}.get(str(record.get('customer_type_allow') or '').strip().upper(), 'unknown')


def observe(url, response, store=None):
    """The endpoint for the registry branch this storefront lists, or None. Without a registry branch, only a
    storefront listing exactly one branch can name the endpoint."""
    records = store_records(response.body.decode('utf-8', errors='replace'))
    chosen = [record for record in records if same_branch(store, record)] if store else (records if len(records) == 1 else [])
    if len(chosen) != 1:
        return None
    record = chosen[0]
    return dict(url=response.url, provider='gapcommerce', provider_store_id=str(record['object_id']), license_type=license_of(record),
                resolution_evidence=dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at,
                                         retailer_name=record.get('name'),
                                         retailer_address=', '.join(str(record.get(key) or '') for key in ('address1', 'city', 'state', 'zip')),
                                         method='Treez Ecommerce storefront store record (treezStores) matched by street address'))


def probe(endpoint, fetcher):
    """Storefront page, its text, and the branch record for the endpoint's store (None when the page lists no such branch)."""
    page = fetcher.get(endpoint['url'])
    text = page.body.decode('utf-8', errors='replace')
    matches = [record for record in store_records(text) if str(record['object_id']) == str(endpoint['provider_store_id'])]
    return page, text, (matches[0] if len(matches) == 1 else None)


def catalog_request(request):
    """True when a search request filters only by the storefront's base filters, so its hits are the whole catalog."""
    must = ((request.get('query') or {}).get('bool') or {}).get('must')
    if not isinstance(must, list) or not must:
        return False
    names = [set(re.findall(r'"([^"]+)"', json.dumps(clause))) - STRUCTURE for clause in must]
    return all(clause_names and clause_names <= BASE_FIELDS for clause_names in names)


def search_responses(evidence_dir, render_evidence_id):
    """The storefront's product-search responses from one render: each with the id order and offset of its request."""
    root = Path(evidence_dir)
    try:
        diagnostics = json.loads((root / 'browser' / f'{render_evidence_id}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    found = []
    for entry in diagnostics.get('network_json') or []:
        if entry.get('status') != 200 or entry.get('method') != 'POST' or not str(entry.get('url', '')).startswith(SEARCH):
            continue
        try:
            request = json.loads(entry.get('request_body') or '')
            manifest = json.loads((root / 'manifests' / f"{entry['evidence_id']}.json").read_text(encoding='utf-8'))
            value = json.loads(gzip.decompress((root / manifest['body_path']).read_bytes()).decode('utf-8', errors='replace'))
            direction = request['sort'][0]['_id']
            offset = int(request['from'])
            if not catalog_request(request):
                continue
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            continue
        found.append(dict(direction=direction, offset=offset, value=value, evidence_id=entry['evidence_id']))
    return found


def normalize(source, endpoint):
    from backend.providers.treez import normalize as treez_normalize
    # An uncollapsed hit is a variant: it is its own parent group and its own item.
    return treez_normalize(source, source, endpoint)


def fingerprint(items):
    ordered = sorted(items, key=lambda item: (item['source_id'], item['variant_id']))
    return hashlib.sha256(json.dumps([inventory_fields(item) for item in ordered], sort_keys=True).encode()).hexdigest()


def traversal(responses, direction, store_id, endpoint):
    """One id-ordered traversal, reconciled to its hit total. Raises when the pages do not add up."""
    pages = {}
    for response in responses:
        if response['direction'] != direction:
            continue
        if pages.setdefault(response['offset'], response) is not response:
            raise ValueError('GapCommerce search page was captured twice with different responses')
    if not pages:
        raise ValueError(f'Storefront search was not replayed in {direction} id order')
    items, seen, parents, totals = [], set(), set(), set()
    for offset in sorted(pages):
        value = pages[offset]['value']
        block = value.get('hits') or {}
        count = block.get('total') or {}
        if count.get('relation') != 'eq' or isinstance(count.get('value'), bool) or not isinstance(count.get('value'), int):
            raise ValueError('GapCommerce search total is not exact')
        totals.add(count['value'])
        for hit in block.get('hits') or []:
            if hit.get('_index') != 'product_' + store_id:
                raise ValueError('GapCommerce hit belongs to another store index')
            item = normalize(hit.get('_source') or {}, endpoint)
            identity = (item['source_id'], item['variant_id'])
            if identity in seen:
                raise ValueError('GapCommerce repeated product/variant identity')
            seen.add(identity)
            parents.add(item['source_id'])
            items.append(item)
    if len(totals) != 1:
        raise ValueError('GapCommerce search total changed during the traversal')
    total = totals.pop()
    if len(items) != total:
        raise ValueError(f'GapCommerce catalog did not reconcile to its advertised total: observed {len(items)} of {total} variants')
    return items, total, len(parents)


def fetch(endpoint, fetcher, probed=None):
    result = dict(provider=endpoint.get('provider', 'gapcommerce'), adapter_version=VERSION, items=[], complete=False, expected_count=None,
                  source_product_count=None, pages=[], errors=[], evidence=[], authoritative_zero=False,
                  limits=dict(page_size=PAGE, max_pages=int(endpoint.get('max_pages', 1000)), verification_passes=2),
                  count_semantics='Exact uncollapsed search hit total counts variants; expected_count is the variants observed')
    try:
        page, text, record = probed or probe(endpoint, fetcher)
        result['evidence'].append(page.evidence_id)
        if page.status_code != 200:
            raise ValueError(f'Storefront HTTP {page.status_code}')
        if record is None:
            raise ValueError("Storefront does not list this endpoint's store")
        if endpoint.get('license_type') != 'recreational':
            raise ValueError('GapCommerce search is read for recreational menus only')
        from backend.locators import addresses_match
        target = (getattr(fetcher, 'browser_options', None) or {}).get('target_store') or {}
        if target.get('address') and not addresses_match(target['address'], record.get('address1', '')):
            raise ValueError('Menu source belongs to a different street address: ' + str(record.get('address1')))
        store_id = str(record['object_id'])
        entity = str(record.get('mso_store_entity_id') or store_id)
        # The browser selects the branch and runs the page's own search for it; the replay carries that request's headers.
        browser = copy.copy(fetcher)
        browser.browser_options = dict(getattr(fetcher, 'browser_options', {}), gap_search=True, gap_entity=entity, await_menu=False, scroll_menu=False)
        rendered = browser.render(endpoint['url'], license_type='recreational')
        result['evidence'].append(rendered.evidence_id)
        if rendered.status_code != 200:
            raise ValueError(f'Browser storefront HTTP {rendered.status_code}')
        responses = search_responses(fetcher.evidence_dir, rendered.evidence_id)
        passes = {direction: traversal(responses, direction, store_id, endpoint) for direction in DIRECTIONS}
        for direction in DIRECTIONS:
            result['pages'].extend(dict(traversal=direction, offset=entry['offset'], advertised_total=entry['value'].get('hits', {}).get('total', {}).get('value'),
                                        evidence_id=entry['evidence_id']) for entry in responses if entry['direction'] == direction)
        first, second = passes['asc'], passes['desc']
        result['items'] = first[0].copy()
        if fingerprint(first[0]) == fingerprint(second[0]):
            result.update(complete=True, expected_count=len(first[0]), source_product_count=first[2], authoritative_zero=first[1] == 0)
        else:
            # Live price or stock churn between traversals is graded B, not discarded; each traversal reconciled on its own.
            convergence = churn_convergence(first[0], second[0], kind='churn_tolerant', source_total=second[1])
            if not convergence:
                raise ValueError('GapCommerce catalog changed across independent full traversals')
            result.update(complete=False, expected_count=len(first[0]), source_product_count=first[2], convergence=convergence)
    except Exception as exc:
        if getattr(exc, 'evidence_id', None):
            result['evidence'].append(exc.evidence_id)
        result['errors'].append(dict(code='incomplete_gapcommerce_menu', message=str(exc)))
    return result
