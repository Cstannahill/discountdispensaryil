"""Observed public storefront adapters. Unsupported sources never return success."""
from __future__ import annotations
from backend.domain import GRAMS_PER_OUNCE, inventory_fields

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlencode, urljoin, urlparse

ADAPTER_VERSION = 'blaze-jsonapi-2'
BLAZE_API = 'https://ecom-api.blaze.me/api/v1/products/'


def provider_capabilities(provider):
    native=provider in ('blaze','sweed','dispense','treez','joint','jane','verano')
    structured=provider in ('generic','jane','dutchie','cresco')
    return dict(native_full_menu=native,structured_fallback=structured,
                support='native_full_menu' if native else 'conditional_structured_fallback' if structured else 'unsupported')


def _text(response):
    return response.body.decode('utf-8-sig') if isinstance(response.body, bytes) else response.body


def _next_data(text):
    match = re.search(r'<script\b[^>]*\bid=[\"\']__NEXT_DATA__[\"\'][^>]*>(.*?)</script>', text, re.S)
    return json.loads(match[1])['props']['pageProps'] if match else {}


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = Decimal(str(value))
        return format(value.normalize(), 'f') if value.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _money(value):
    if not isinstance(value, dict) or value.get('currency', '').lower() != 'usd':
        return None
    amount = _decimal(value.get('amount'))
    return _decimal(Decimal(amount) / 100) if amount is not None else None


def _related(item, name, included):
    relationship = item.get('relationships', {}).get(name, {}).get('data') or {}
    if relationship.get('attributes') is not None:
        return relationship['attributes']
    return next((x['attributes'] for x in included if str(x.get('id')) == str(relationship.get('id')) and x.get('type') == relationship.get('type')), {})


def normalize_blaze(item, included, endpoint):
    """Normalize the observed prepackaged-product schema; retain every source field."""
    a = item['attributes']
    source_id = str(item['id'])
    if not source_id or not a.get('name'):
        raise ValueError('missing product identity or name')
    if a.get('weight_prices'):
        raise ValueError('unvalidated weight_prices variant schema')
    unit_prices = a.get('unit_prices') or []
    singles = [x for x in unit_prices if x.get('quantity') == 1]
    if len(singles) != 1:
        raise ValueError('missing or ambiguous single-package price variant')
    single = singles[0]
    size = a.get('size') or {}
    weight = None
    amount = _decimal(size.get('amount'))
    # Milligrams on these menus describes THC dose, never package mass.
    units = str(size.get('units', '')).lower()
    if amount and units in ('grams', 'gram', 'g'):
        weight = amount
    elif amount and units in ('ounces', 'ounce', 'oz'):
        weight = _decimal(Decimal(amount) * GRAMS_PER_OUNCE)
    category = _related(item, 'category', included).get('name') or 'Unknown'
    mapped = {'flower': 'flower', 'concentrates': 'concentrates', 'concentrate': 'concentrates', 'vape': 'vapes', 'vapes': 'vapes'}.get(category.lower(), 'other')
    regular = _money(single.get('price'))
    effective = _money(single.get('discount_price')) or regular
    thc = a.get('thc') or {}
    return {
        'source_id': source_id, 'variant_id': 'single', 'name': a['name'],
        'brand': _related(item, 'brand', included).get('name'), 'category': mapped,
        'source_category': category, 'subcategory': None, 'strain_type': a.get('flower_type'),
        'thc_pct': _decimal(thc.get('amount')) if thc.get('units') == '%' else None,
        'weight_grams': weight, 'weight_label': size.get('display_text') or (f"{amount} {units}" if amount else None),
        'regular_price': regular, 'effective_price': effective, 'conditional': False,
        'available': a.get('in_stock') is True and a.get('is_active') is not False and not a.get('is_deleted'),
        'source_url': a.get('store_url') or endpoint['url'],
        'raw': {'product': item, 'included': [x for x in included if any(str(r.get('data', {}).get('id')) == str(x.get('id')) and r.get('data', {}).get('type') == x.get('type') for r in item.get('relationships', {}).values() if isinstance(r.get('data'), dict))]},
    }


def _detect_endpoint(url, response):
    text = _text(response)
    evidence = {'url': response.url, 'evidence_id': response.evidence_id, 'fetched_at': response.fetched_at}
    props = _next_data(text)
    if 'initialSearchResponse' in text and 'selectedStore' in text:
        from backend.providers.treez import observe
        observed=observe(url,response)
        if observed:return observed
    if 'api.dispenseapp.com' in text:
        from backend.providers.dispense import observe
        endpoint=observe(url,response)
        if endpoint:return endpoint
    if 'jointEcommerce' in text or '/wp-content/plugins/joint-ecommerce/' in text:
        from backend.providers.joint import observe as observe_joint
        endpoint = observe_joint(url, response)
        if endpoint:return endpoint
    if 'sweedStores' in text:
        from backend.providers.verano import observe as observe_verano
        endpoint=observe_verano(url,response)
        if endpoint:return endpoint
    if '"__sw_qc"' in text:
        from backend.providers.sweed import observe
        return observe(url, response)
    site = props.get('site') or {}
    if site.get('id') and site.get('env', {}).get('REACT_APP_TYMBER_ECOMMERCE_HOST') == 'https://ecom-api.blaze.me/':
        settings = site.get('settings') or {}
        license_type = 'medicinal' if settings.get('allow_medical_customers') and not settings.get('allow_recreational_customers') else 'recreational'
        return {'url': site.get('site', {}).get('url') or url, 'provider': 'blaze', 'provider_store_id': str(site['id']), 'license_type': license_type, 'resolution_evidence': dict(evidence, method='Blaze storefront __NEXT_DATA__ tenant and customer context')}
    hosted = re.search(r'iheartjane\.com/(?:embed/)?stores/(\d+)', response.url or url)
    if hosted:
        return {'url': response.url or url, 'provider': 'jane', 'provider_store_id': hosted[1], 'license_type': 'unknown', 'resolution_evidence': dict(evidence, method='Jane hosted store menu URL')}
    if 'dmerch.iheartjane.com' in text:
        # Retailer-hosted Jane storefronts render the store's own search records into the page. One store id across
        # every record (agreeing with a /store/<id> path) names the Jane store; the reader proves the branch by location.
        ids = set(re.findall(r'"store_?[iI]d"\s*:\s*(\d+)', text.replace('\\', '')))
        path = re.search(r'/stores?/(\d+)(?:/|$)', urlparse(response.url or url).path)
        if len(ids) == 1 and (not path or path[1] in ids):
            places = list(set(re.findall(r'"_geoloc"\s*:\s*\{\s*"lat"\s*:\s*(-?[\d.]+)\s*,\s*"lng"\s*:\s*(-?[\d.]+)', text.replace('\\', ''))))
            located = dict(platform_location=dict(lat=float(places[0][0]), lng=float(places[0][1]))) if len(places) == 1 else {}
            # The records' own store_types are the platform's license context (a medical-only twin shares the branch).
            types = set(re.findall(r'"store_types"\s*:\s*\[([^\]]*)\]', text.replace('\\', '')))
            license_type = 'medicinal' if types == {'"medical"'} else 'recreational' if types and all('"recreational"' in t for t in types) else 'unknown'
            return {'url': response.url or url, 'provider': 'jane', 'provider_store_id': ids.pop(), 'license_type': license_type, 'resolution_evidence': dict(evidence, method='Jane storefront records name one store', **located)}
    match = re.search(r'[\"\']storeId[\"\']\s*:\s*(\d+)', text)
    if match and 'iheartjane.com' in text:
        return {'url': url, 'provider': 'jane', 'provider_store_id': match[1], 'license_type': 'recreational' if 'adult-use' in url else 'unknown', 'resolution_evidence': dict(evidence, method='Jane partner hosted storeId; traversal unsupported')}
    provider = 'sweed' if 'sweedpos.com' in text else 'cresco' if 'cloud9dispensaries.shop' in url else 'unsupported'
    return {'url': url, 'provider': provider, 'provider_store_id': None, 'license_type': 'unknown', 'resolution_evidence': dict(evidence, method='Unresolved provider contract')}


def _observed_endpoint(url, response):
    from .site_discovery import license_context
    endpoint = _detect_endpoint(url, response)
    license_type,basis=license_context(endpoint['url'],_text(response))
    if endpoint.get('license_type') not in ('recreational','medicinal'):
        endpoint['license_type']=license_type
        endpoint['license_basis']=basis
    else:
        endpoint['license_basis']='provider_context'
    return endpoint


def has_menu_contract(endpoint):
    """A platform asset is a discovery hint, not a store/catalog contract."""
    if endpoint.get('provider')=='unsupported':return False
    details=endpoint.get('resolution_evidence') or {}
    if isinstance(details,dict) and details.get('method')=='Unresolved provider contract':return False
    return not provider_capabilities(endpoint.get('provider'))['native_full_menu'] or bool(endpoint.get('provider_store_id'))


def resolve_menu(store, fetcher):
    """Bounded search/branch crawl. Platform and generic paths share evidence."""
    from .platforms import detect as detect_platforms
    from .locators import discover_menu_candidates
    from .site_discovery import dutchie_page_endpoints, inspect_page, license_context, provider_address_matches, catalog_entry_url, is_directory_url, retailer_links_from_directory, menu_document_scope, search_websites, branch_slug_conflict, branch_slug_confirms
    from .providers.generic import extract
    from .providers.jane import hosted_store as jane_hosted_store
    from .documents import read_document
    import copy
    fetcher=copy.copy(fetcher)
    fetcher.browser_options=dict(getattr(fetcher,'browser_options',{}),target_store={key:store.get(key) for key in ('id','name','address','city','state','latitude','longitude')})
    fetcher._branch_render_cache={}
    initial=list(dict.fromkeys(store[k] for k in ('menu_url','website','source_url','url') if isinstance(store.get(k),str) and store[k]))
    seeds=[dict(url=url,status='candidate',evidence=[]) for url in initial] if initial else discover_menu_candidates(store,fetcher)
    pending=[(c['url'],0,c,c.get('status')=='matched') for c in seeds if c.get('url') and c['status'] in ('candidate','matched')]
    # Verifier-cited branch pages go first: they name one location, where chain roots and search results name many.
    pending=[(url,0,dict(url=url,status='candidate',reason='Store verifier lead',evidence=[]),False) for url in store.get('lead_urls') or []
             if isinstance(url,str) and url.startswith(('https://','http://'))]+pending
    results=[];failures=[];visited=set();max_pages=int(store.get('max_discovery_pages',24))
    for c in seeds:
        if c['status'] not in ('candidate','matched'):
            failures.append(dict(url=c.get('url'),provider='generic',provider_store_id=None,license_type='recreational',
                                 status=c['status'],reason=c.get('reason'),resolution_evidence=c.get('evidence',[])))
    searched=False
    while len(visited)<max_pages:
        # A configured brand root is a lead, not proof that the branch is still
        # operated by that brand. Reserve crawl capacity for independent search
        # when the old chain never yields a matching menu (including rebrands).
        if not results and not searched and (not pending or len(visited)>=max(1,max_pages-8)):
            searched=True
            leads=search_websites(store,fetcher)+search_websites(store,fetcher,by_address=True)
            seeds.extend(leads)
            pending=[(lead['url'],0,lead,False) for lead in leads if lead.get('url') and catalog_entry_url(lead['url']) not in visited]+pending
            attempts=getattr(fetcher,'_last_search_attempts',[])
            if not leads and attempts:
                failures.append(dict(url=None,provider='generic',license_type='recreational',status='unresolved',reason='Fallback website search found no corroborated branch lead',resolution_evidence=attempts))
        if not pending:break
        url,depth,seed,inherited=pending.pop(0)
        hosted=jane_hosted_store(store,url)
        if hosted:
            # The menu URL itself names the Jane store; the Jane reader proves the branch at the platform's coordinates.
            url=urlparse(url)._replace(query='',fragment='').geturl()
            if url in visited:continue
            visited.add(url)
            license_type,basis=license_context(url)
            results.append(dict(url=url,provider='jane',provider_store_id=hosted[0],license_type=license_type,license_basis=basis,identity_confidence=hosted[1],
                                resolution_evidence=dict(url=url,method='Rise-hosted Jane store id in the menu URL'),locator_evidence=seed.get('evidence',[]),platforms=['jane']))
            continue
        url=catalog_entry_url(url)
        if url in visited:continue
        visited.add(url)
        if menu_document_scope(url)=='filtered':continue
        # Everything this page yields (endpoints, embeds, failures) carries the platforms seen on it, for the census.
        marks,page_platforms=(len(results),len(failures)),[]
        try:
            response=fetcher._branch_render_cache.get(url) or read_document(url,fetcher)
            if response.status_code!=200:raise ValueError(f'HTTP {response.status_code}')
            if is_directory_url(response.url):
                # Listings help discover a retailer website; they are not a
                # substitute for its authoritative menu, even with an address.
                for official in retailer_links_from_directory(_text(response),response.url):
                    pending.insert(0,(official,0,dict(seed,reason='Website link observed on directory listing'),False))
                failures.append(dict(url=url,provider='generic',provider_store_id=None,license_type='recreational',status='unresolved',
                                     reason='Third-party directory is a discovery lead, not a retailer menu',resolution_evidence=dict(url=response.url,evidence_id=response.evidence_id)))
                continue
            page_platforms=detect_platforms(_text(response))
            identity=inspect_page(store,response)
            # Explicit supplied URLs are useful for diagnostic probes. Registry
            # discovery accepts address OR business+locality evidence.
            verified=(inherited or identity['identity_status'] in ('matched','name_locality') or bool(initial and not store.get('address'))) and identity['identity_status']!='conflict'
            if identity['identity_status']=='conflict':
                failures.append(dict(url=url,provider='generic',provider_store_id=None,license_type='recreational',status='identity_conflict',reason='Branch page names a different street address/locality',resolution_evidence=identity))
            observed=_observed_endpoint(url,response)
            if (identity['identity_status'] in ('candidate','conflict') or provider_address_matches(store,observed) is False) and hasattr(fetcher,'render') and fetcher.browser_options.get('enabled',True) and url not in fetcher._branch_render_cache and len(fetcher._branch_render_cache)<2:
                # A wrong default branch is a reason to select the requested
                # location first, rather than immediately reject the retailer.
                fetcher._branch_render_cache[url]=None
                try:
                    rendered=fetcher.render(url)
                    fetcher._branch_render_cache[url]=rendered
                    if rendered.status_code==200:
                        response=rendered
                        identity=inspect_page(store,response)
                        verified=(identity['identity_status'] in ('matched','name_locality') or inherited) and identity['identity_status']!='conflict'
                        observed=_observed_endpoint(url,response)
                        page_platforms=sorted(set(page_platforms)|set(detect_platforms(_text(response))))
                except Exception as exc:
                    failures.append(dict(url=url,provider='generic',license_type='recreational',status='failed',reason='Branch-selection browser attempt failed: '+str(exc),resolution_evidence=dict(evidence_id=getattr(exc,'evidence_id',None))))
            details=observed.get('resolution_evidence') or {}
            address_match=provider_address_matches(store,observed)
            if address_match is True:
                verified=True
                identity['identity_status']='matched'
            elif address_match is False:
                verified=False
                failures.append(dict(url=url,provider=observed['provider'],provider_store_id=observed.get('provider_store_id'),license_type=observed['license_type'],
                                     status='identity_conflict',reason='Detected menu belongs to a different street address: '+str(details.get('retailer_address')),resolution_evidence=details))
            if has_menu_contract(observed) and verified:
                observed.update(identity_confidence=identity['identity_status'],locator_evidence=seed.get('evidence',[]))
                results.append(observed)
                if observed['provider']=='sweed' and isinstance(details,dict) and len(details.get('sale_types',[]))>1:
                    for mode in ('recreational','medical'):
                        other=re.sub(r'/(?:medical|recreational)(?=/|$)','/'+mode,observed['url'])
                        if other!=observed['url'] and other not in visited:pending.insert(0,(other,depth+1,seed,verified))
                continue
            if observed['provider']!='unsupported' and not has_menu_contract(observed):
                failures.append(dict(url=url,provider=observed['provider'],provider_store_id=None,license_type=observed['license_type'],status='unresolved',
                                     reason='Provider reference detected, but store/tenant or full-catalog contract is unresolved; continuing discovery',resolution_evidence=details))
            # Script-selected Dutchie stores (location maps, headless storefronts) join the page's embed links.
            known={e.get('provider_store_id') for e in identity['endpoints']}
            for endpoint in identity['endpoints']+[x for x in dutchie_page_endpoints(store,_text(response)) if x['provider_store_id'] not in known]:
                if verified and branch_slug_conflict(store,endpoint['url'],endpoint.get('embed_script_url')):
                    failures.append(dict(url=endpoint['url'],provider=endpoint['provider'],provider_store_id=endpoint.get('provider_store_id'),license_type='recreational',status='identity_conflict',
                                         reason='Embed on this page names a different branch locality; not the requested store',resolution_evidence=dict(embed=endpoint.get('embed_script_url'))))
                    continue
                if verified:
                    license_type,basis=license_context(endpoint['url'])
                    endpoint.update(license_type=license_type,license_basis=basis,identity_confidence=identity['identity_status'],
                                    resolution_evidence={k:v for k,v in identity.items() if k!='endpoints'},locator_evidence=seed.get('evidence',[]))
                    results.append(endpoint)
            _,products,_=extract(_text(response),response.url)
            sibling=branch_slug_conflict(store,url) and identity['identity_status']!='matched'
            if verified and not sibling and (products or re.search(r'/(?:menu|shop|products)(?:/|$)',urlparse(url).path)):
                license_type,basis=license_context(url)
                results.append(dict(url=url,provider='generic',provider_store_id=None,license_type=license_type,license_basis=basis,
                                    resolution_evidence=identity,identity_confidence=identity['identity_status'],requires_browser_context=fetcher._branch_render_cache.get(url) is response))
            if depth<2:
                city=[word for word in re.findall(r'[a-z0-9]+',store.get('city','').lower()) if word not in ('east','west','north','south')]
                semantic={link['url'] for link in identity.get('navigation_links',[])}
                links=[link for link in identity['links'] if urlparse(link).scheme in ('http','https') and
                       not re.search(r'\.(?:css|js|jpg|jpeg|webp|png|svg|woff2?)(?:\?|$)',link,re.I) and
                       (urlparse(link).hostname==urlparse(response.url).hostname) and
                       (link in semantic or re.search(r'/(?:menu|shop|stores?|locations?|dispensaries|products)(?:/|[-_]|$)',urlparse(link).path,re.I))]
                links.sort(key=lambda link:(not any(w in urlparse(link).path.lower() for w in city),not bool(re.search('menu|shop',link)),len(link)))
                for link in list(dict.fromkeys(links))[:10]:
                    # A location selector with multiple branches does not pass
                    # its identity to another branch; an observed menu does.
                    child_verified=verified and bool(re.search(r'/(?:menu|shop)(?:/|$)',urlparse(link).path)) and not branch_slug_conflict(store,link)
                    pending.append((link,depth+1,seed,child_verified))
            if not verified:
                failures.append(dict(url=url,provider='generic',provider_store_id=None,license_type='recreational',status='unresolved',
                                     reason='Candidate website found; branch name/locality or street address still needs matching',resolution_evidence=identity))
        except Exception as exc:
            failures.append(dict(url=url,provider='generic',provider_store_id=None,license_type='recreational',status='failed',reason=str(exc),
                                 resolution_evidence=dict(url=url,evidence_id=getattr(exc,'evidence_id',None))))
        finally:
            for found in results[marks[0]:]+failures[marks[1]:]:found.setdefault('platforms',page_platforms)
    # Prefer actual platform menus over sibling generic landing/carousel pages.
    platforms=[x for x in results if x['provider']!='generic']
    catalog_entries=[x for x in results if x['provider']=='generic' and menu_document_scope(x['url'])=='catalog_entry']
    official_urls={candidate['url'] for candidate in seeds if candidate.get('source_role')=='retailer'}
    official_failures=[failure for failure in failures if failure.get('url') in official_urls]
    # A hub that lists every branch is not this branch's menu when a page carrying the branch's own slug was found.
    own=[x for x in catalog_entries+[x for x in results if x['provider']=='generic'] if branch_slug_confirms(store,x['url'])]
    if own and not platforms:catalog_entries=own
    chosen=platforms or catalog_entries or results or [dict(failure,discovery_attempts=failures) for failure in official_failures] or failures
    # A native store id is the menu; its category and landing pages are one endpoint, not several.
    return list({(x['provider'],x.get('provider_store_id'),None if x.get('provider_store_id') and x['provider']=='jane' else x.get('url'),x['license_type']):x for x in chosen}.values())


def fetch_menu(endpoint, fetcher):
    if endpoint.get('provider')=='treez':
        from backend.providers.treez import fetch
        return fetch(endpoint,fetcher)
    if endpoint.get('provider') == 'dispense':
        from backend.providers.dispense import fetch
        return fetch(endpoint,fetcher)
    if endpoint.get('provider') == 'joint':
        from backend.providers.joint import fetch
        return fetch(endpoint,fetcher)
    if endpoint.get('provider') == 'jane' and endpoint.get('provider_store_id'):
        from backend.providers.jane import fetch
        return fetch(endpoint,fetcher)
    if endpoint.get('provider') in ('generic','jane','dutchie','cresco'):
        from backend.providers.generic import fetch
        return fetch(endpoint, fetcher)
    if endpoint.get('provider')=='verano':
        from backend.providers.verano import fetch
        return fetch(endpoint,fetcher)
    if endpoint.get('provider') == 'sweed':
        from backend.providers.sweed import fetch
        return fetch(endpoint, fetcher)
    result = {'items': [], 'complete': False, 'expected_count': None, 'pages': [], 'errors': [], 'evidence': [], 'authoritative_zero': False, 'provider': endpoint.get('provider'), 'adapter_version': ADAPTER_VERSION, 'source_product_count': None, 'limits': {'page_size': 100, 'max_pages': int(endpoint.get('max_pages', 1000)), 'verification_passes': 2, 'concurrency': 1}}
    if endpoint.get('provider') != 'blaze':
        result['errors'].append({'code': 'unsupported_provider', 'message': f"No validated complete-menu traversal for {endpoint.get('provider', 'unknown')}"})
        return result
    try:
        response = fetcher.get(endpoint['url'])
        if response.status_code != 200:
            raise ValueError(f'storefront HTTP {response.status_code}')
        context = _observed_endpoint(endpoint['url'], response)
        result['evidence'].append(response.evidence_id)
        if context['provider'] != 'blaze' or context['provider_store_id'] != str(endpoint.get('provider_store_id')):
            raise ValueError('provider store context changed')
        if context['license_type'] != endpoint.get('license_type') or context['license_type'] == 'unknown':
            raise ValueError('unverified or changed license context')
        headers = {'X-Store': str(endpoint['provider_store_id']), 'Accept': 'application/vnd.api+json'}
        passes = []
        for pass_number in range(2):
            offset, expected, fingerprints, items = 0, None, {}, []
            for page_number in range(result['limits']['max_pages']):
                url = BLAZE_API + '?' + urlencode({'limit': 100, 'offset': offset, 'delivery_type': 'pickup'})
                page = fetcher.get(url, headers=headers)
                result['evidence'].append(page.evidence_id)
                if page.status_code != 200:
                    raise ValueError(f'menu HTTP {page.status_code} at offset {offset}')
                body = page.json()
                meta, objects = body['meta'], body['data']
                total = meta['total_count']
                if isinstance(total, bool) or not isinstance(total, int) or total < 0 or not isinstance(objects, list):
                    raise ValueError('invalid advertised count or product collection')
                if meta['offset'] != offset or meta['limit'] != 100:
                    raise ValueError('provider ignored requested offset/limit')
                if expected is None:
                    expected = total
                if total != expected:
                    raise ValueError('advertised total changed during traversal')
                if len(objects) != min(100, expected - offset):
                    raise ValueError('missing page products or inconsistent total')
                result['pages'].append({'pass': pass_number + 1, 'offset': offset, 'limit': 100, 'count': len(objects), 'advertised_total': total, 'evidence_id': page.evidence_id})
                for obj in objects:
                    normalized = normalize_blaze(obj, body.get('included') or [], endpoint)
                    key = normalized['source_id']
                    if key in fingerprints:
                        raise ValueError('repeated product identity across page boundaries')
                    fingerprints[key] = hashlib.sha256(json.dumps(inventory_fields(normalized), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    items.append(normalized)
                offset += len(objects)
                if offset == expected:
                    break
            else:
                raise ValueError('configured page limit reached')
            passes.append((expected, fingerprints))
            if pass_number == 0:
                result['items'] = items
                result['expected_count'] = expected
                result['source_product_count'] = expected
            elif passes[0] != passes[1]:
                raise ValueError('menu changed between independent full traversals')
        result['complete'] = True
        result['authoritative_zero'] = result['expected_count'] == 0
        result['count_semantics'] = 'one observed single-package variant per provider product; multibuy tiers retained in raw product'
    except Exception as exc:
        result['errors'].append({'code': 'incomplete_menu', 'message': str(exc)})
    return result
