"""Retailer connector entry points, not a fixed dispensary directory.

Branches and menu URLs are discovered from current retailer responses. The
official registry defines candidates; an unknown retailer remains a visible gap.
"""
import html
import json
import re
import time
from urllib.parse import urljoin, urlsplit

from .providers.sweed import query_cache

# Public chain locator entry points verified during implementation. These contain
# no store IDs, product records, per-branch menu URLs, or invented inventory.
CONNECTORS = [
    (r'snap\s*canna', 'https://snapcanna.com/'),
    (r'^stash\b', 'https://www.stashdispensaries.com/'),
    (r'tree\s*haus', 'https://shop.treehausil.com/'),
    (r'aroma\s*hill', 'https://shop.aromahillcannabis.com/'),
    (r'ivy\s*hall', 'https://ivyhalldispensary.com/locations/'),
    (r'beyond\s*/?\s*hello', 'https://beyond-hello.com/illinois-dispensaries/'),
    (r'bloom\s*wellness|^rise\b', 'https://risecannabis.com/dispensaries/illinois/'),
    (r'nuera|nu\s*era', 'https://nueracannabis.com/'),
    (r'^noxx\b', 'https://noxx.com/'),
    (r'^cloud\s*9\b', 'https://www.cloud9dispensaries.shop/'),
    (r'^cookies\b', 'https://cookies.co/stores/'),
    (r'high\s*haven', 'https://highhavencannabis.com/'),
    (r'^trinity\b', 'https://www.trinitydispensaries.com/'),
    (r'^verilife\b', 'https://www.verilife.com/'),
    (r'^curaleaf\b', 'https://curaleaf.com/'),
    (r'^revolution\b', 'https://www.revcanna.com/'),
    (r'^pekin\s*(?:local|s local)', 'https://pekindispensary.com/'),
]


def _tokens(value):
    value = html.unescape(value or '').casefold()
    substitutions = {'north':'n','south':'s','west':'w','east':'e','street':'st','avenue':'ave',
                     'road':'rd','drive':'dr','parkway':'pkwy','boulevard':'blvd','route':'rt'}
    tokens = re.findall(r'[a-z0-9]+', value)
    return [substitutions.get(token, token) for token in tokens]


def addresses_match(registry, retailer):
    a, b = _tokens(registry), _tokens(retailer)
    for label in ('suite', 'ste', 'unit'):
        if label in a:
            a = a[:a.index(label)]
        if label in b:
            b = b[:b.index(label)]
    return bool(a and b and a[0].isdigit() and a[0] == b[0] and
                (a == b[:len(a)] or b == a[:len(b)]))


def _get(fetcher, url):
    # Cache only locator pages for five minutes. Never cache adapter menu reads:
    # their independent full traversals must perform independent requests.
    cache = getattr(fetcher, '_terpscout_locator_cache', {})
    cached = cache.get(url)
    if cached and time.monotonic()-cached[0] < 300:
        return cached[1]
    from .documents import read_document
    response = read_document(url,fetcher)
    cache[url] = (time.monotonic(), response)
    fetcher._terpscout_locator_cache = cache
    return response


def _known_menu_candidates(store, fetcher):
    name = re.sub(r"[’']", '', store.get('name', ''))
    root = next((url for pattern, url in CONNECTORS if re.search(pattern, name, re.I)), None)
    if not root:
        return [dict(status='unresolved', url=None, reason='No retailer locator connector configured for this brand', evidence=[])]
    try:
        cache=getattr(fetcher,'_branch_render_cache',{})
        response = cache.get(root) or _get(fetcher, root)
        text = response.body.decode('utf-8', errors='replace')
        evidence = dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at)
        if response.status_code != 200:
            raise ValueError(f'Locator HTTP {response.status_code}')
        if re.search(r'<title>[^<]*(?:just a moment|attention required)', text, re.I):
            return [dict(status='blocked', url=response.url, reason='Retailer returned an access challenge', evidence=[evidence])]
        # Sweed exposes a complete chain directory in the normal public SSR cache.
        try:
            queries = query_cache(text)
            directories = [q['state']['data']['shortStoreInfoList'] for q in queries
                           if q['queryKey'][0] == '/Store/GetStoreShortInfoList']
        except (ValueError, KeyError, TypeError):
            directories = []
        if directories:
            candidates = []
            city = ''.join(_tokens(store.get('city', '')))
            for branch in directories[0]:
                address = (branch.get('contacts') or {}).get('address') or ''
                if not branch.get('url'):
                    continue
                exact = addresses_match(store['address'], address)
                same_city = city and city in ''.join(_tokens(branch.get('name', '') + ' ' + address))
                if exact or same_city:
                    candidates.append(dict(url=branch['url'], status='matched' if exact else 'identity_conflict',
                                           reason='Exact normalized street address in public retailer directory' if exact else 'Retailer branch address conflicts with registry',
                                           retailer_address=address, evidence=[evidence]))
            if not any(candidate['status']=='matched' for candidate in candidates) and _render_locator(root,store,fetcher):
                return _known_menu_candidates(store,fetcher)
            return candidates or [dict(status='unresolved', url=response.url, reason='No matching branch in the live retailer directory', evidence=[evidence])]
        branches = _embedded_store_list(text)
        if branches:
            return _directory_candidates(store, branches, response.url, evidence)
        links = list(dict.fromkeys(urljoin(response.url, html.unescape(x)) for x in
                                   re.findall(r'(?:href|src)=["\']([^"\']+)["\']', text, re.I)))
        city_words=[w for w in _tokens(store.get('city','')) if w not in ('e','w','n','s')]
        city = ''.join(city_words)
        relevant = [link for link in links if city and city in ''.join(_tokens(urlsplit(link).netloc + urlsplit(link).path)) and
                    not re.search(r'\.(?:jpg|png|webp|css|js|svg)(?:\?|$)', link, re.I)]
        # Prefer observed menu/location links rather than unrelated city blog posts.
        relevant.sort(key=lambda link: (not bool(re.search(r'menu|shop|dispensar|location', link, re.I)), len(link)))
        if relevant:
            street = ''.join(_tokens(store['address'].split(' Unit ')[0]))
            address_on_page = street in ''.join(_tokens(re.sub(r'<[^>]+>', ' ', text)))
            from .site_discovery import menu_document_scope
            # City-named promotion links must not displace the actual Shop All
            # entry after a browser has selected and corroborated the branch.
            entries=[link for link in links if menu_document_scope(link)=='catalog_entry'] if address_on_page else []
            relevant=list(dict.fromkeys(entries+[link for link in relevant if menu_document_scope(link)!='filtered']))
            if not relevant:return [dict(status='candidate',url=response.url,reason='Inspect retailer catalog after location selection',evidence=[evidence])]
            return [dict(status='matched' if address_on_page and re.search(r'/menu/', link) else 'candidate', url=link,
                         reason='Observed retailer address and branch-specific menu link' if address_on_page else 'Observed retailer branch link; endpoint identity still requires corroboration',
                         evidence=[evidence]) for link in relevant[:12]]
        # Single-location sites can expose a menu link without the city in its URL.
        if ''.join(_tokens(store['address'])) in ''.join(_tokens(re.sub(r'<[^>]+>', ' ', text))):
            menus = [link for link in links if re.search(r'/menu(?:/|$)|adult-use-menu|medical-menu|/shop(?:/|$)', link)]
            if menus:
                return [dict(status='candidate', url=link, reason='Observed menu link on retailer page containing the registry street address', evidence=[evidence]) for link in menus[:12]]
        if _render_locator(root,store,fetcher):return _known_menu_candidates(store,fetcher)
        age_gate = 'age-gate' in response.url or 'please confirm you are at least' in text.lower()
        return [dict(status='blocked' if age_gate else 'unresolved', url=response.url,
                     reason='Retailer requires age/terms confirmation; menu not fetched' if age_gate else 'Retailer locator did not expose a corroborated branch/menu link', evidence=[evidence])]
    except Exception as exc:
        return [dict(status='failed', url=root, reason=str(exc), evidence=[dict(url=root, evidence_id=getattr(exc, 'evidence_id', None))])]


def _embedded_store_list(text):
    """The chain's own branch list when its page script assigns one (e.g. `var bhData = {"stores": [...]}`): a list of
    objects that each carry a street address, at least two of them with a menu link (coming-soon and delivery-only
    branches have none)."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\bvar\s+\w+\s*=\s*(?=[{\[])', text):
        try:
            value, _ = decoder.raw_decode(text, match.end())
        except ValueError:
            continue
        for candidate in [value] + (list(value.values()) if isinstance(value, dict) else []):
            if (isinstance(candidate, list) and all(isinstance(x, dict) and isinstance(x.get('address'), str) for x in candidate) and
                    sum(bool(_menu_links(x, '')) for x in candidate) >= 2):
                return candidate
    return []


def _menu_links(branch, base):
    links = [urljoin(base, html.unescape(value).strip()) for key, value in branch.items()
             if 'menu' in key.lower() and 'delivery' not in key.lower() and isinstance(value, str) and re.match(r'\s*(?:https?://|/)', value)]
    links = list(dict.fromkeys(links))
    # The retailer's own branch menu pages carry its license wording; platform embeds are used only when it has none.
    host = urlsplit(base).hostname
    own = [link for link in links if urlsplit(link).hostname == host]
    return own or links


def _directory_candidates(store, branches, base, evidence):
    out = []
    city = ''.join(_tokens(store.get('city', '')))
    for branch in branches:
        if branch.get('is_coming_soon'):
            continue
        address = branch['address']
        if addresses_match(store['address'], address):
            out += [dict(url=link, status='matched', reason='Exact normalized street address in the retailer\'s embedded store list',
                         retailer_address=address, evidence=[evidence]) for link in _menu_links(branch, base)]
        elif city and city in ''.join(_tokens(address)) and not out:
            out.append(dict(url=None, status='identity_conflict', reason='Retailer branch in the same city has a different street address',
                            retailer_address=address, evidence=[evidence]))
    if any(x['status'] == 'matched' for x in out):
        return [x for x in out if x['status'] == 'matched']
    # A complete branch list without this address is an answer, not a page to crawl for siblings.
    return out or [dict(status='unresolved', url=base, reason='Branch absent from the retailer\'s current embedded store list (closed, renamed or moved?)',
                        evidence=[evidence], store_list=True)]


def _render_locator(url,store,fetcher):
    options=getattr(fetcher,'browser_options',{})
    cache=getattr(fetcher,'_branch_render_cache',{})
    if not hasattr(fetcher,'render') or options.get('enabled') is False or url in cache or len(cache)>=2:return False
    fetcher.browser_options=dict(options,target_store={key:store.get(key) for key in ('id','name','address','city','state')})
    try:
        cache[url]=fetcher.render(url)
        fetcher._branch_render_cache=cache
        return cache[url].status_code==200
    except Exception:
        # Preserve the original locator result; resolver records later attempts.
        cache[url]=None;fetcher._branch_render_cache=cache
        return False


def discover_menu_candidates(store, fetcher):
    from .site_discovery import search_websites
    known=_known_menu_candidates(store,fetcher)
    known=[dict(candidate,source_role='retailer') if candidate.get('url') else candidate for candidate in known]
    options=getattr(fetcher,'browser_options',{})
    if options.get('age_confirmed') and hasattr(fetcher,'render'):
        for candidate in known:
            if candidate['status']=='blocked' and 'age' in candidate.get('reason','').lower() and candidate.get('url'):
                try:
                    rendered=fetcher.render(candidate['url'])
                    from .site_discovery import inspect_page
                    inspected=inspect_page(store,rendered)
                    links=[link for link in inspected['links'] if re.search(r'menu|shop|location|store',link,re.I) and not re.search(r'\.(?:js|css|png|jpg|svg)',link)]
                    if links:
                        return [dict(url=link,status='candidate',reason='Observed after ordinary consent-enabled browser flow',evidence=[inspected['evidence']]) for link in links[:12]]
                except Exception as exc:
                    candidate['reason']+='; browser attempt: '+str(exc)
    if any(x['status'] in ('matched','candidate') for x in known):
        return known
    searched=search_websites(store,fetcher)
    if searched:
        # Keep the known retailer and its actual failure visible. Search leads
        # must not silently replace an official site with an aggregator listing.
        return [x for x in known if x.get('url')] + searched
    if known and known[0].get('url'):
        if known[0]['status']=='unresolved' and not known[0].get('store_list'):
            return [dict(known[0],status='candidate',reason='Inspect public locator and its observed branch links')]
        return known
    return [dict(status='unresolved',url=None,
                 reason='Public website search found no corroborated candidate; inspect search attempts',
                 evidence=getattr(fetcher,'_last_search_attempts',[]))]
