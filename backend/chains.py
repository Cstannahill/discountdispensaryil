"""Chain location lists: a retailer's own published branch list, matched to registry stores by street.

A list answers discovery for its chain. A store on the list gets its branch's menu: a Dutchie dispensary id from the
branch's own page, a Jane store id the chain publishes, or the branch's menu page. A store the list does not carry
is an answer too ('absent' or 'not matched'), so no open-web search follows and no wrong-branch lead is saved.
Each menu is still checked by its reader: Dutchie by the menu's own address, Jane by the platform's coordinates.
"""
import html
import json
import re

from .documents import read_document
from .locators import _get, addresses_match, _street
from .network import FetchError

ASCEND_LIST = 'https://letsascend.com/wp-json/ascend-store-mapper/v1/locations'
IVY_LIST = 'https://ivyhalldispensary.com/locations/'
NUERA_LIST = 'https://nueracannabis.com/dispensaries/'
VERILIFE_LIST = 'https://www.verilife.com/locations'
CRESCO_LIST = 'https://api.crescolabs.com/p/stores'
SUNNYSIDE_ORIGIN = 'https://www.sunnyside.shop'
# Brand words a registry name carries that a NuEra city title does not.
NAME_NOISE = {'nuera', 'nu', 'era', 'cannabis', 'dispensary', 'by', 'the', 'il', 'illinois'}
# Registry streets an operator corrected to the chain's own list (accepted 2026-10-20). The registry row keeps its address
# until the registry is corrected; the Dutchie street exception for the same store is in providers/generic.py.
CORRECTED_STREETS = {
    '9e28e567467f2723fb75e2d0': ('5650 S Archer Ave', 'Midway by Ascend: registry 5648 S Archer Ave; the Ascend list and its branch page say 5650'),
}


def _words(text):
    return re.findall(r'[a-z0-9]+', html.unescape(text or '').lower())


def _evidence(response):
    return dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at)


def _cand(status, url, reason, evidence, **extra):
    return dict(status=status, url=url, reason=reason, evidence=[evidence], chain_list=True, **extra)


def _ascend_branches(text):
    branches = []
    for feature in json.loads(text).get('features') or []:
        p = feature.get('properties') or {}
        branches.append(dict(name=p.get('store_name') or p.get('title') or '', street=p.get('address_1') or '',
                             state=p.get('state') or '', url=p.get('shop_url')))
    return branches


def _ivy_branches(text):
    start = text.index('var locations_data')
    rows, _ = json.JSONDecoder().raw_decode(text[text.index('[', start):])
    return [dict(name=r.get('name') or '', street=r.get('street') or '', state=r.get('state') or '', url=r.get('shop_url'))
            for r in rows]


def _verilife_branches(text):
    branches = []
    for part in text.split('name="leftLocation"')[1:]:
        title = re.search(r'class="amlocator-title">([^<]*)<', part)
        lines = [html.unescape(line).strip() for line in re.findall(r'<div>([^<]*)</div>', part)][:2]
        link = re.search(r'href="([^"]+)" ?class="view-full-store"', part)
        if not title or len(lines) < 2:
            continue
        city, _, region = lines[1].partition(',')
        state = 'IL' if re.search(r'\bIllinois\b', region) else region.split(',')[0].strip()
        branches.append(dict(name=html.unescape(title[1]).strip(), street=lines[0], city=city.strip(), state=state, url=link[1] if link else None))
    return branches


def _nuera_entries(text):
    start = text.index('"hjb_store_url_ids"')
    found, _ = json.JSONDecoder().raw_decode(text[text.index('{', start):])
    entries = []
    for entry in found.values():
        match = re.match(r'\s*(.+?)\s*\(\s*(med|medical|rec|recreational)\s*\)\s*$', entry.get('title') or '', re.I)
        if match:
            entries.append(dict(city=match[1], license='medicinal' if match[2].lower().startswith('med') else 'recreational',
                                store_id=str(entry['id']), url=entry.get('url')))
    return entries


def _shop_url_menu(branch, evidence, fetcher):
    return [_cand('matched', branch['url'], 'Chain location list: branch street matches the registry; its menu page is read next', evidence)]


def _ascend_menu(branch, evidence, fetcher):
    try:
        page = read_document(branch['url'], fetcher)
    except FetchError as exc:
        return [_cand('failed', branch['url'], f'Ascend branch page unavailable: {exc}', dict(url=branch['url'], evidence_id=exc.evidence_id))]
    text = page.body.decode('utf-8', errors='replace')
    dispensaries = set(re.findall(r'"dispensaryId"\s*:\s*"([0-9a-f]{24})"', text))
    address = re.search(r'"address"\s*:\s*"([^",]+)', text)
    if address and not addresses_match(branch['street'], address[1]):
        return [_cand('identity_conflict', None, f"Ascend branch page names {address[1]}, not the list street {branch['street']}", _evidence(page))]
    if len(dispensaries) != 1:
        return [_cand('matched', branch['url'], 'Ascend location list: branch street matches; the page is read for its menu', _evidence(page))]
    dispensary = dispensaries.pop()
    menu = f'https://dutchie.com/embedded-menu/{dispensary}'
    endpoint = dict(url=menu, provider='dutchie', provider_store_id=dispensary, license_type='recreational', license_basis='chain_list',
                    identity_confidence='matched', platforms=['dutchie'],
                    resolution_evidence=dict(url=branch['url'], method='Ascend location list street, branch page Dutchie dispensary id',
                                             evidence_id=page.evidence_id, retailer_address=branch['street']))
    return [_cand('matched', menu, 'Ascend location list: branch street matches; the branch page names this Dutchie dispensary', _evidence(page), endpoint=endpoint)]


def _verilife_menu(branch, evidence, fetcher):
    try:
        page = fetcher.get(branch['url'])
    except FetchError as exc:
        if re.search(r'HTTP (?:403|503)\b', str(exc)):
            # The branch is confirmed on verilife.com; its menu is on Rise, which refuses this client. Not worked around.
            return [_cand('blocked', branch['url'], 'Verilife list confirms this branch; its menu redirects to risecannabis.com, which refused this client (HTTP 403)', dict(url=branch['url'], evidence_id=exc.evidence_id))]
        return [_cand('failed', branch['url'], f'Verilife branch page unavailable: {exc}', dict(url=branch['url'], evidence_id=exc.evidence_id))]
    return [_cand('unresolved', branch['url'], 'Verilife branch page loads, but names no Jane store id or menu link', _evidence(page))]


def _nuera_menus(store, entries, evidence):
    wanted = [word for word in _words(store.get('name')) if word not in NAME_NOISE]
    menus = [entry for entry in entries if _words(entry['city']) == wanted]
    out = []
    for entry in menus:
        kind = 'medical' if entry['license'] == 'medicinal' else 'recreational'
        endpoint = dict(url=entry['url'], provider='jane', provider_store_id=entry['store_id'], license_type=entry['license'], license_basis='chain_list',
                        identity_confidence='name_locality', platforms=['jane'],
                        resolution_evidence=dict(url=entry['url'], method='NuEra location list: Jane store id for this city and license', evidence_id=evidence.get('evidence_id')))
        out.append(_cand('matched', entry['url'], f"NuEra location list names Jane store {entry['store_id']} ({kind}) for this city; the Jane reader checks its coordinates", evidence, endpoint=endpoint))
    return out


def _near(address, street):
    a, b = _street(address), _street(street)
    return len(a) > 2 and len(b) > 2 and a[0].isdigit() and b[0].isdigit() and a[0] != b[0] and a[1:] == b[1:]


def _by_street(store, label, branches, evidence, fetcher, menu):
    state = (store.get('state') or 'IL').upper()
    address = store.get('address') or ''
    local = [b for b in branches if (b.get('state') or '').upper() in (state, 'ILLINOIS' if state == 'IL' else state)]
    hits = [b for b in local if addresses_match(address, b['street'])]
    if hits:
        return [candidate for branch in hits for candidate in menu(branch, evidence, fetcher)]
    near = next((b for b in local if _near(address, b['street'])), None)
    if near:
        return [_cand('unresolved', None, f"{label} lists {near['name']} at {near['street']}, not the registry street {address}; not matched", evidence)]
    return [_cand('unresolved', None, f"Branch absent from {label}'s published location list (closed, renamed or moved?)", evidence, store_list=True)]


# (name pattern, label, list URL, parser, matcher, branch menu). A name matcher receives the rows and the store.
def _sunnyside_branches(text):
    branches = []
    for row in json.loads(text).get('data') or []:
        if row.get('hidden') or row.get('deleted') or not re.search(r'sunny\s*side', row.get('name') or '', re.I):
            continue
        branches.append(dict(name=row.get('name') or '', street=row.get('address') or '', state=row.get('state') or '',
                             url=f"{SUNNYSIDE_ORIGIN}/menu/{row['store_slug']}" if row.get('store_slug') else None))
    return branches


def _sunnyside_list(fetcher, list_url):
    """Cresco's store list needs the storefront's publishable key, which the storefront's own script carries. It is
    read from that script on each run, the way the storefront reads it, and never stored."""
    home = _get(fetcher, SUNNYSIDE_ORIGIN + '/')
    bundle = re.search(r'src="(/static/js/main\.[a-z0-9]+\.js)"', home.body.decode('utf-8', errors='replace'))
    if not bundle:
        raise ValueError('Sunnyside storefront bundle not found')
    script = _get(fetcher, SUNNYSIDE_ORIGIN + bundle[1]).body.decode('utf-8', errors='replace')
    key = re.search(r'API_KEY[:=]\s*"([^"]+)"', script)
    if not key:
        raise ValueError('Sunnyside storefront key not found in its script')
    headers = {'x-api-key': key[1], 'x-client-version': '1', 'origin': SUNNYSIDE_ORIGIN, 'referer': SUNNYSIDE_ORIGIN + '/', 'accept': 'application/json'}
    return fetcher.get(list_url, headers=headers)


CHAINS = [
    (r'\bascend\b', 'Ascend', ASCEND_LIST, _ascend_branches, 'street', _ascend_menu, None),
    (r'ivy\s*hall', 'Ivy Hall', IVY_LIST, _ivy_branches, 'street', _shop_url_menu, None),
    (r'nu\s*era', 'NuEra', NUERA_LIST, _nuera_entries, 'city', None, None),
    (r'\bverilife\b', 'Verilife', VERILIFE_LIST, _verilife_branches, 'street', _verilife_menu, None),
    (r'sunny\s*side', 'Sunnyside', CRESCO_LIST, _sunnyside_branches, 'street', _shop_url_menu, _sunnyside_list),
]


def chain_candidates(store, fetcher):
    """Discovery candidates from the store's chain location list, or None when no published list covers the store."""
    name = store.get('name') or ''
    for pattern, label, list_url, parse, matcher, menu, load in CHAINS:
        if not re.search(pattern, name, re.I):
            continue
        if store.get('id') in CORRECTED_STREETS:
            store = dict(store, address=CORRECTED_STREETS[store['id']][0])
        try:
            # Locator pages share the five-minute locator cache, so a sync reads each list once per store run.
            response = load(fetcher, list_url) if load else _get(fetcher, list_url)
            evidence = _evidence(response)
            rows = parse(response.body.decode('utf-8', errors='replace'))
        except Exception as exc:
            return [_cand('failed', None, f'{label} location list unavailable: {exc}', dict(url=list_url, evidence_id=getattr(exc, 'evidence_id', None)))]
        if matcher == 'city':
            found = _nuera_menus(store, rows, evidence)
            return found or [_cand('unresolved', None, f"Branch absent from {label}'s published location list (closed, renamed or moved?)", evidence, store_list=True)]
        return _by_street(store, label, rows, evidence, fetcher, menu)
    return None
