"""Evidence-bearing public search, branch inspection, and menu platform detection."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


def canonical_menu_url(url):
    parts=urlsplit(url)
    # Plain document anchors do not change the HTTP resource. Preserve SPA routes.
    fragment=parts.fragment if parts.fragment.startswith(('/','!')) else ''
    return urlunsplit((parts.scheme,parts.netloc,parts.path,parts.query,fragment))


def catalog_entry_url(url):
    parts=urlsplit(canonical_menu_url(url))
    # Observed catalog pagination is traversal state, not a distinct menu.
    query=[(key,value) for key,value in parse_qsl(parts.query,keep_blank_values=True)
           if not (key=='page' and value.isdigit())]
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),parts.fragment))


def is_directory_url(url):
    host=(urlsplit(url).hostname or '').lower()
    return any(host==domain or host.endswith('.'+domain) for domain in
               ('jointcommerce.com','leafly.com','weedmaps.com','yelp.com','allbud.com','potguide.com','cannabrands.com','cannabisshop.com','lookyweed.com'))


_CATEGORY_WORDS=r'(?:flowers?|edibles?|extracts?|concentrates?|vap(?:e|es|orizers?)|carts?|cartridges?|pre-?rolls?|tinctures?|topicals?|gear|accessories|apparel|merch|deals?|specials?|sale|cbd|new|brands?|strains?|under-\d+)'
_FILTER_KEY=re.compile(r'refinement|filter|facet|facets|sort_by|orderby',re.I)


def menu_document_scope(url):
    parts=urlsplit(url)
    # Storefront filters arrive as bracketed or named query keys, or as a category segment under the menu root.
    if any(_FILTER_KEY.search(key) for key,_ in parse_qsl(parts.query)) or re.search(r'/(?:menu|shop|products|order)/'+_CATEGORY_WORDS+r'/?$',parts.path,re.I):
        return 'filtered'
    if re.search(r'/(?:product-group|collections?|categor(?:y|ies)|brands?|products?)/[^/]+',parts.path,re.I) or any(key.lower() in ('category','brand','collection','group_id','product_id','q','query','search','searchterm','keyword','strain','deal','promotion') for key,_ in parse_qsl(parts.query)):
        return 'filtered'
    if re.search(r'/(?:menu|shop|products)(?:/(?:medical|medicinal|recreational|adult-use))?/?$',parts.path,re.I):
        return 'catalog_entry'
    return 'unknown'


def retailer_links_from_directory(text,url):
    page=Page(text,url)
    return list(dict.fromkeys(canonical_menu_url(link) for link,label in page.anchors
                if re.search(r'\b(?:website|official site|visit (?:site|store|dispensary))\b',label,re.I)
                and urlsplit(link).scheme in ('http','https')
                and urlsplit(link).hostname != urlsplit(url).hostname
                and not is_directory_url(link)
                and not (urlsplit(link).hostname or '').endswith(('facebook.com','instagram.com','twitter.com','x.com','youtube.com'))))


class Page(HTMLParser):
    def __init__(self, text, url):
        super().__init__(convert_charrefs=True)
        self.url, self.links, self.text, self.structured, self.options, self.next_links = url, [], [], [], [], []
        self.script, self.buffer, self.hidden = False, [], 0
        self.anchors=[];self.anchor=None;self.anchor_text=[]
        self.identity_text=[];self.navigation_depth=0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('nav','footer'):self.navigation_depth+=1
        if tag=='a' and a.get('href'):
            self.anchor=urljoin(self.url,a['href']);self.anchor_text=[]
        if tag == 'a' and 'next' in a.get('rel','').split() and a.get('href'):
            self.next_links.append(urljoin(self.url,a['href']))
        if tag in ('script','style'):
            self.hidden += 1
        if tag == 'script' and a.get('type','').lower() == 'application/ld+json':
            self.script, self.buffer = True, []
        for key in ('href','src','data-src'):
            if a.get(key):
                self.links.append(canonical_menu_url(urljoin(self.url, a[key])))
        if tag == 'option' and a.get('value') and a.get('data-address'):
            self.options.append((urljoin(self.url,a['value']),a['data-address']))

    def handle_endtag(self, tag):
        if tag in ('nav','footer'):self.navigation_depth=max(0,self.navigation_depth-1)
        if tag=='a' and self.anchor:
            self.anchors.append((self.anchor,' '.join(self.anchor_text)))
            self.anchor=None;self.anchor_text=[]
        if tag == 'script' and self.script:
            try:
                self.structured.append(json.loads(''.join(self.buffer)))
            except (ValueError,TypeError):
                pass
            self.script = False
        if tag in ('script','style'):
            self.hidden = max(0,self.hidden-1)

    def handle_data(self, data):
        if self.anchor:self.anchor_text.append(data)
        if self.script:
            self.buffer.append(data)
        elif not self.hidden:
            self.text.append(data)
            if not self.navigation_depth:self.identity_text.append(data)


def objects(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value,list):
        for child in value:
            yield from objects(child)


def words(text):
    return re.findall(r'[a-z0-9]+',re.sub(r"[’']",'',html.unescape(text or '').casefold()))


def business_words(name):
    stop={'dispensary','dispensaries','cannabis','marijuana','the','il','illinois','inc','llc','medical','recreational'}
    return set(words(name))-stop


def license_context(url, text=''):
    # The user's explicit policy: omitted license is recreational. Never invent
    # a medical channel from a registry flag or a discount description.
    if re.search(r'(?:/|[-_])(?:medical|medicinal|med)(?:/|[-_?]|$)',url,re.I):
        return 'medicinal','explicit'
    return 'recreational','explicit' if re.search(r'adult-use|recreational',url,re.I) else 'default'


def provider_links(url, text):
    page=Page(text,url)
    found=[]
    for link in dict.fromkeys(page.links):
        parts=urlsplit(link)
        if 'iheartjane.com' in (parts.hostname or ''):
            match=re.search(r'/(?:embed/)?stores/(\d+)',parts.path)
            if match:
                found.append(dict(url=link,provider='jane',provider_store_id=match[1]))
        if parts.hostname in ('dutchie.com','www.dutchie.com'):
            # Embed scripts exist for several API versions (v2 <id>.js, v3 <id>/carousels/...); the id is never the version.
            match=re.search(r'/api/v\d+/embedded-menu/([^/.]+)',parts.path)
            if match:
                # This is platform identity evidence only. Never ingest a
                # carousel as the full catalog. Fetch verifies the target.
                found.append(dict(url='https://dutchie.com/embedded-menu/'+match[1],provider='dutchie',provider_store_id=match[1],embed_script_url=link))
            elif re.search(r'/(?:embedded-menu|stores|kiosks)/[^/]+',parts.path):
                # Product detail, kiosk, store-slug and experience URLs all describe one menu; keep only its root.
                segments=[segment for segment in parts.path.split('/') if segment]
                slug=segments[1] if segments[1]!='experiences' or len(segments)<3 else segments[2]
                found.append(dict(url='https://dutchie.com/embedded-menu/'+slug,provider='dutchie',provider_store_id=slug))
        if parts.hostname and parts.hostname.endswith('.dispenseapp.com') and parts.hostname not in ('api.dispenseapp.com','cdn.dispenseapp.com','images.dispenseapp.com'):
            found.append(dict(url=link,provider='dispense',provider_store_id=parts.hostname.split('.')[0]))
    dutchie=[x for x in found if x['provider']=='dutchie']
    scripts=[x for x in dutchie if x.get('embed_script_url')]
    direct=[x for x in dutchie if not x.get('embed_script_url')]
    if len(scripts)==1 and len(direct)==1:
        direct[0]['provider_store_id']=scripts[0]['provider_store_id']
        direct[0]['embed_script_url']=scripts[0]['embed_script_url']
        found=[x for x in found if x is not scripts[0]]
    return list({(x['provider'],x['provider_store_id']):x for x in found}.values())


_DUTCHIE_KEYED=re.compile(r"""["']?([a-z][a-z0-9_-]*)["']?\s*:\s*['"]([0-9a-f]{24})['"]""",re.I)


def dutchie_page_endpoints(store, text):
    """Dutchie stores a page selects in script rather than in an embed URL: one `dispensaryId` across a headless
    storefront's records, or a location->id map whose key names the store's city. The Dutchie reader still checks
    the menu's own address against the registry store."""
    if 'dutchie' not in text:return []
    plain=text.replace('\\','')
    ids=set(re.findall(r'"dispensaryId"\s*:\s*"([0-9a-f]{24})"',plain))
    if not ids:
        city=set(re.findall(r'[a-z0-9]+',(store.get('city') or '').lower()))-_STREET_NOISE
        ids={value for key,value in _DUTCHIE_KEYED.findall(plain) if city and city<=set(re.findall(r'[a-z0-9]+',key.lower().replace('_',' ')))}
    if len(ids)!=1:return []
    found=ids.pop()
    return [dict(url='https://dutchie.com/embedded-menu/'+found,provider='dutchie',provider_store_id=found)]


def street_in_text(address,text):
    from .locators import _tokens
    street=re.split(r'\b(?:unit|suite|ste)\b|#',address or '',flags=re.I)[0]
    tokens=_tokens(street)
    return bool(tokens and tokens[0].isdigit() and (' '+' '.join(tokens)+' ') in (' '+' '.join(_tokens(text))+' '))


_STATES={'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware',
         'DC':'District of Columbia','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa',
         'KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota',
         'MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey',
         'NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon',
         'PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah',
         'VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'}


def same_state(first, second):
    """A page may say "Illinois" where the registry says "IL"; only a different state is a contradiction."""
    def code(value):
        text=re.sub(r'[^a-z ]','',str(value or '').casefold()).strip()
        return next((abbreviation for abbreviation,name in _STATES.items() if text in (abbreviation.casefold(),name.casefold())),text)
    return code(first)==code(second)


_STATE_CODES=frozenset(code.lower() for code in _STATES)
_SLUG_NOISE=frozenset(('rec','med','recreational','medical','adult','use','menu','shop','order','online','dispensary','dispensaries','cannabis',
                       'locations','location','stores','store','experiences','products','embedded','illinois'))
_STREET_NOISE=frozenset(('st','street','ave','avenue','rd','road','dr','drive','blvd','boulevard','ln','lane','ct','court','pkwy','parkway','hwy','highway',
                         'n','s','e','w','north','south','east','west','suite','ste','unit'))
_SLUG_STATE=re.compile(r'^(?P<base>[a-z0-9-]+?)-(?P<state>[a-z]{2})(?:-(?:rec|med|recreational|medical|adult-use))?$')


def _slug_candidates(url):
    parts=urlsplit(url)
    paths=[parts.path]+[urlsplit(value).path for key,value in parse_qsl(parts.query) if key=='routeRoot']
    found=[]
    for path in paths:
        segments=[segment.lower() for segment in path.split('/') if segment]
        for index,segment in enumerate(segments):
            if segment in ('locations','location','stores','store') and index+1<len(segments):found.append(segments[index+1])
            elif _SLUG_STATE.match(segment) and _SLUG_STATE.match(segment)['state'] in _STATE_CODES:found.append(segment)
    return [slug for slug in dict.fromkeys(found) if not re.fullmatch(r'[0-9a-f]{12,}|\d+',slug) and slug not in _SLUG_NOISE]


def branch_slug_conflict(store, *urls):
    """True when a URL (or an embed's routeRoot) names a different locality or state than the requested store.
    Chain sites list every sibling branch on one page; a sibling must prove itself rather than inherit the
    requested store's identity. A URL with no location slug is never a conflict."""
    city=set(re.findall(r'[a-z0-9]+',(store.get('city') or '').lower()))-_STREET_NOISE
    street=set(re.findall(r'[a-z]+',(store.get('address') or '').lower()))-_STREET_NOISE
    state=(store.get('state') or 'IL').lower()
    for url in urls:
        for slug in _slug_candidates(url or ''):
            match=_SLUG_STATE.match(slug)
            if match and match['state'] in _STATE_CODES and match['state']!=state:return True
            tokens=set(re.findall(r'[a-z0-9]+',slug))-_SLUG_NOISE-_STREET_NOISE-{state}
            if tokens and city and not (tokens & (city|street)):return True
    return False


def branch_slug_confirms(store, url):
    """True when the URL names a location slug and it is the requested store's own (a branch-specific page,
    as opposed to a hub that lists every branch)."""
    return bool(_slug_candidates(url or '')) and not branch_slug_conflict(store,url)


def inspect_page(store, response):
    from .locators import addresses_match
    text=response.body.decode('utf-8',errors='replace')
    page=Page(text,response.url)
    addresses=[];unscoped=[]
    for item in objects(page.structured):
        address=item.get('address')
        # Scope structured identity to this page, not a different default
        # branch or all locations mentioned in the site's navigation schema.
        target=item.get('url')
        if target:
            declared=urlsplit(urljoin(response.url,target));current=urlsplit(response.url)
            if declared.hostname!=current.hostname or declared.path.rstrip('/')!=current.path.rstrip('/'):
                continue
        if isinstance(address,dict) and address.get('streetAddress'):
            (addresses if target else unscoped).append(address)
    if not addresses and len({a.get('streetAddress') for a in unscoped})==1:
        addresses=unscoped
    matched=[a for a in addresses if addresses_match(store.get('address',''),a.get('streetAddress','')) and
             (not a.get('addressRegion') or same_state(a['addressRegion'],store.get('state','IL')))]
    visible=' '.join(page.identity_text)
    registry_words=business_words(store.get('name',''))-set(words(store.get('city','')))
    combined=set(words(visible+' '+response.url))
    name_match=bool(registry_words and registry_words & combined)
    city_match=set(words(store.get('city',''))) <= combined
    address_in_text=street_in_text(store.get('address',''),visible)
    cannabis_context=bool(combined & {'cannabis','marijuana','dispensary','dispensaries'})
    if addresses and not matched:
        identity='conflict'
    elif matched or (address_in_text and (name_match or (city_match and cannabis_context))):
        identity='matched'
    elif name_match and city_match:
        identity='name_locality'
    else:
        identity='candidate'
    return dict(identity_status=identity,addresses=addresses,matched_addresses=matched,
                endpoints=provider_links(response.url,text),links=list(dict.fromkeys(page.links)),
                navigation_links=[dict(url=canonical_menu_url(link),label=label) for link,label in page.anchors
                                  if re.search(r'\b(?:menu|shop|order(?: online)?|locations?|dispensaries)\b',label,re.I)],
                evidence=dict(url=response.url,evidence_id=response.evidence_id,fetched_at=response.fetched_at),
                name_match=name_match,city_match=city_match)


def provider_address_matches(store,endpoint):
    """None means absent evidence, not a contradiction. False is an actual mismatch."""
    from .locators import addresses_match
    details=endpoint.get('resolution_evidence') or {}
    place=details.get('platform_location') if isinstance(details,dict) else None
    if place and store.get('latitude') is not None and store.get('longitude') is not None:
        # The platform's own store coordinates: at the registry point proves the branch, far away refutes it.
        from .providers.jane import MAX_MILES,NEAR_MILES,_miles
        miles=_miles(float(store['latitude']),float(store['longitude']),place['lat'],place['lng'])
        if miles<=MAX_MILES:return True
        if miles>NEAR_MILES:return False
    address=details.get('retailer_address') if isinstance(details,dict) else None
    if not address or not store.get('address'):
        return None
    return addresses_match(store['address'],address)


def domain_is(host, domain):
    return host == domain or host.endswith('.'+domain)


def search_llm(fetcher):
    """The web-search client: an injected `fetcher.search_llm`, else the configured OpenRouter model for a real
    network fetcher only (test doubles never reach a paid API). None means search is not configured."""
    if hasattr(fetcher,'search_llm'):return fetcher.search_llm
    from .network import PublicFetcher
    if not isinstance(fetcher,PublicFetcher) or fetcher._transport_override is not None:return None
    from .verifier import load_env,llm_from_config,budgets
    config=load_env()
    llm=llm_from_config(config)
    if llm:llm.usd_per_day=budgets(config)['usd_per_day']
    fetcher.search_llm=llm
    return llm


def search_websites(store, fetcher, *, by_address=False):
    from .verifier import search,record_spend,spend_since,day_ago
    brand_name=re.split(r'\s+-\s+',store.get('name',''))[0]
    brand_name=re.sub(r'\b'+re.escape(store.get('city',''))+r'\b','',brand_name,flags=re.I).strip()
    if by_address and not store.get('address'):return []
    street=re.split(r'\b(?:unit|suite|ste)\b|#',store.get('address',''),flags=re.I)[0].strip()
    query=('"'+street+'" "'+store.get('city','')+'" '+store.get('state','IL')+' dispensary menu') if by_address else ('"'+brand_name+'" '+store.get('city',''))
    cache=getattr(fetcher,'_website_search_cache',{})
    folder=getattr(fetcher,'evidence_dir',None)
    cache_path=Path(folder)/'search-cache'/(hashlib.sha256(query.encode()).hexdigest()+'.json') if folder else None
    if query not in cache and cache_path and cache_path.exists():
        try:
            saved=json.loads(cache_path.read_text(encoding='utf-8'))
            if saved.get('strategy_version')==5:
                cache[query]=(saved['time'],saved['results'],saved.get('attempts',[]))
        except (OSError,ValueError,KeyError):
            pass
    if query in cache and time.time()-cache[query][0] < (86400 if cache[query][1] else 300):
        fetcher._last_search_attempts=cache[query][2] if len(cache[query])>2 else []
        return cache[query][1]
    results,attempts=[],[]
    # One OpenRouter web-plugin (Exa) request per query; the registry state and cannabis context keep a name search on topic.
    text=query if by_address else query+' '+store.get('state','IL')+' dispensary cannabis menu'
    llm=search_llm(fetcher)
    if llm is None:
        fetcher._last_search_attempts=[dict(url=None,error='Web search not configured (set OPENROUTER_API_KEY in .env)')]
        return []
    cap=getattr(llm,'usd_per_day',None)
    run=getattr(fetcher,'run_spend',None)
    # Samples and triage runs (fetcher.sample_run) are small and bypass the daily cap; the per-run ceiling bounds them.
    store_run=getattr(fetcher,'store_spend',None)
    # Hitting a store's own cap stops that store only: it is annotated 'hit cap' and the run moves on.
    if store_run is not None and store_run['usd']>=store_run['ceiling']:
        fetcher._last_search_attempts=[dict(url=None,error='Per-store search cap reached (hit cap); web search skipped for this store')]
        return []
    if run is not None and run['usd']>=run['ceiling']:
        fetcher._last_search_attempts=[dict(url=None,error='Per-run search ceiling reached (--max-usd); web search skipped')]
        return []
    if cap is not None and not getattr(fetcher,'sample_run',False) and spend_since(folder,day_ago())>=cap:
        # Not cached: the search runs again once the 24h window has room.
        fetcher._last_search_attempts=[dict(url=None,error='Daily LLM spend cap reached (VERIFIER_MAX_USD_PER_DAY); web search skipped')]
        return []
    try:
        found,evidence=search(llm,text,fetcher)
        record_spend(folder,'discovery',getattr(llm,'model',None),found['usd'],found['tokens'],store.get('id'))
        if run is not None:run['usd']+=found['usd']
        if store_run is not None:store_run['usd']+=found['usd']
        attempts.append(dict(url=evidence['url'],evidence_id=evidence['evidence_id'],status=200,engine='openrouter-web-exa'))
        for item in found['results']:
            block_text=item['title']+' '+item['url']+' '+item['snippet'];block_words=set(words(block_text))
            required=business_words(brand_name)
            ordered=[w for w in words(brand_name) if w in required]
            compact=''.join(ordered[:2])
            compact_match=bool(compact and compact in ''.join(words(block_text)))
            city_match=set(words(store.get('city',''))) <= block_words
            context_match=bool(block_words & {'dispensary','dispensaries','cannabis','marijuana'})
            if by_address:
                if not (street_in_text(street,block_text) and city_match and context_match):continue
            else:
                if required and len(required & block_words)<min(2,len(required)) and not compact_match:continue
                if not (city_match or context_match) or (not required and not (city_match and context_match)):continue
            target=item['url']
            host=urlsplit(target).hostname or ''
            excluded=('openrouter.ai','bing.com','microsoft.com','facebook.com','instagram.com','youtube.com','leafly.com','yelp.com','weedmaps.com')
            if urlsplit(target).scheme not in ('http','https') or not host or any(domain_is(host,domain) for domain in excluded):
                continue
            results.append(dict(url=target,status='candidate',reason='Primary public search result; branch identity will be inspected',evidence=[dict(query=text,url=evidence['url'],evidence_id=evidence['evidence_id'],fetched_at=evidence['fetched_at'])]))
    except Exception as exc:
        attempts.append(dict(url=None,error=f'{type(exc).__name__}: {str(exc)[:200]}'))
    results=list({canonical_menu_url(x['url']):dict(x,url=canonical_menu_url(x['url'])) for x in results}.values())
    results.sort(key=lambda candidate:is_directory_url(candidate['url']))
    results=results[:8]
    cache[query]=(time.time(),results,attempts)
    if cache_path:
        cache_path.parent.mkdir(parents=True,exist_ok=True)
        cache_path.write_text(json.dumps(dict(time=cache[query][0],results=results,attempts=attempts,strategy_version=5)),encoding='utf-8')
    fetcher._website_search_cache=cache
    fetcher._last_search_attempts=attempts
    return results
