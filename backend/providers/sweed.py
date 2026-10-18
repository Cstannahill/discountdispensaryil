"""Sweed public SSR catalog, observed on prime and production storefronts.

Uses the retailer's ordinary paginated /menu links. No API keys, login, age
verification state, or carousel records are used to obtain catalog products.
"""
from backend.domain import inventory_fields
from decimal import Decimal
import html
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, urljoin

VERSION = 'sweed-ssr-2'


def query_cache(text):
    match = re.search(r'"__sw_qc"\s*:\s*', text)
    if not match:
        raise ValueError('Sweed SSR query cache missing')
    return json.JSONDecoder().raw_decode(text[match.end():])[0]['queries']


def context(queries):
    config = next(q['state']['data'] for q in queries if q['queryKey'][0] == '/Store/GetStoreConfig')
    info = next(q['state']['data']['storeInfo'] for q in queries if q['queryKey'][0] == '/Store/GetStoreInfoV2')
    if str(config['id']) != str(info['id']) or info.get('isMock'):
        raise ValueError('Sweed tenant identity mismatch or mocked source')
    return config, info


def observe(url, response):
    text = response.body.decode('utf-8-sig') if isinstance(response.body, bytes) else response.body
    queries = query_cache(text)
    config, info = context(queries)
    selected = None
    for query in queries:
        params = query['queryKey'][1] if len(query['queryKey']) > 1 and isinstance(query['queryKey'][1], dict) else {}
        if params.get('saleType'):
            selected = params['saleType'].lower()
            break
    sale_types = info.get('saleTypes') or []
    if not selected and len(sale_types) == 1:
        selected = sale_types[0].lower()
    canonical_license = 'medicinal' if selected == 'medical' else selected or 'recreational'
    base = info['url'].rstrip('/')
    product_list = any(q['queryKey'][0] == '/Products/GetProductList' and
                       not q['queryKey'][1].get('filters') and not q['queryKey'][1].get('searchTerm')
                       for q in queries)
    if product_list:
        parts = urlsplit(response.url)
        menu_url = urlunsplit((parts.scheme,parts.netloc,parts.path,'',''))
    else:
        links = [urljoin(response.url, html.unescape(link)) for link in re.findall(r'href=["\']([^"\']+)["\']',text,re.I)]
        prefix = urlsplit(base).path.rstrip('/')
        candidates = [link for link in links if urlsplit(link).hostname == urlsplit(response.url).hostname and
                      urlsplit(link).path.startswith(prefix + '/') and urlsplit(link).path.rstrip('/').endswith('/menu') and
                      not urlsplit(link).query and (not selected or not re.search(r'/(?:medical|recreational)(?:/|$)',urlsplit(link).path) or '/'+selected+'/' in urlsplit(link).path)]
        if not candidates:
            raise ValueError('No observed full-catalog link in Sweed landing page')
        menu_url = min(candidates,key=len)
    return {'url': menu_url, 'provider': 'sweed', 'provider_store_id': str(info['id']), 'license_type': canonical_license or 'unknown', 'resolution_evidence': {'url': response.url, 'evidence_id': response.evidence_id, 'fetched_at': response.fetched_at, 'method': 'Sweed SSR tenant config, store info, sale-type query context', 'retailer_name': info.get('name'), 'retailer_address': info.get('contacts', {}).get('address'), 'retailer_location': info.get('location'), 'sale_types': sale_types}}


def normalize_product(product, endpoint):
    from backend.adapters import _decimal
    if product.get('id') is None or not product.get('name') or not isinstance(product.get('variants'), list) or not product['variants']:
        raise ValueError('Sweed product identity/name/variants missing')
    category = (product.get('category') or {}).get('name') or 'Unknown'
    mapped = {'flower':'flower', 'concentrates':'concentrates', 'concentrate':'concentrates', 'vape':'vapes', 'vapes':'vapes'}.get(category.lower(), 'other')
    items = []
    for variant in product['variants']:
        if variant.get('id') is None:
            raise ValueError('Sweed variant identity missing')
        # All source variants remain present. Context is validated per page and
        # mixed license variants are structural failures, never silently dropped.
        source_license = 'Medical' if endpoint['license_type'] == 'medicinal' else 'Recreational'
        if variant.get('saleType') not in ('Both', source_license):
            raise ValueError('Sweed variant license context mismatch')
        size = variant.get('unitSize') or {}
        weight = None
        amount = _decimal(size.get('value'))
        units = str(size.get('unitAbbr', '')).upper()
        units_per_package = _decimal(variant.get('unitsInPackage'))
        if amount and units_per_package and units in ('G', 'OZ'):
            weight = _decimal(Decimal(amount) * Decimal(units_per_package) * (Decimal('28.349523125') if units == 'OZ' else 1))
        lab = (variant.get('labTests') or {}).get('thc') or {}
        values = lab.get('value') or []
        promos = variant.get('promos') or []
        # Some Sweed records label a multi-buy promo isConditional=false. Keep
        # those conditions visible and conservatively exclude their sale price.
        conditional = any(p.get('isConditional') is not False or p.get('isBogo') is True or p.get('minCartAmount') or p.get('matchedUserSegmentIds') or p.get('isActiveBySchedule') is False or re.search(r'\bbuy\b|\bget (?:two|three|\d)|save more|stackable|\b\d+\s+for\b', ' '.join(str(p.get(k) or '') for k in ('name','shortName','description')), re.I) for p in promos)
        regular, promo = _decimal(variant.get('price')), _decimal(variant.get('promoPrice'))
        qty = _decimal(variant.get('availableQty'))
        reason = (variant.get('orderingAvailability') or {}).get('reason')
        items.append({'source_id': str(product['id']), 'variant_id': str(variant['id']), 'name': product['name'], 'brand': (product.get('brand') or {}).get('name'), 'category': mapped, 'source_category': category, 'subcategory': (product.get('subcategory') or {}).get('name'), 'strain_type': ((product.get('strain') or {}).get('prevalence') or {}).get('name'), 'thc_pct': _decimal(values[0]) if len(values) == 1 and lab.get('unitAbbr') == '%' else None, 'weight_grams': weight, 'weight_label': variant.get('name'), 'regular_price': regular, 'effective_price': promo if promo is not None else regular, 'conditional': bool(conditional and promo is not None), 'available': qty is not None and Decimal(qty) > 0 and reason == 'Available', 'source_url': endpoint['url'], 'raw': {'product': product, 'variant': variant}})
    return items


def fetch(endpoint, fetcher):
    result = {'items':[], 'complete':False, 'expected_count':None, 'pages':[], 'errors':[], 'evidence':[], 'authoritative_zero':False, 'provider':'sweed', 'adapter_version':VERSION, 'source_product_count':None, 'limits':{'max_pages':int(endpoint.get('max_pages',1000)), 'verification_passes':2, 'concurrency':1}}
    passes, pass_items, convergence = [], [], None
    try:
        if endpoint.get('license_type') not in ('medicinal','recreational'):
            raise ValueError('unverified Sweed license context')
        for pass_index in range(2):
            expected, source_ids, fingerprints, items, record_count = None, set(), {}, [], 0
            for page in range(1, result['limits']['max_pages']+1):
                parts = urlsplit(endpoint['url'])
                query = dict(parse_qsl(parts.query))
                query['page'] = str(page)
                url = urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),''))
                response = fetcher.get(url)
                result['evidence'].append(response.evidence_id)
                if response.status_code != 200:
                    raise ValueError(f'Sweed menu HTTP {response.status_code} at page {page}')
                text = response.body.decode('utf-8-sig') if isinstance(response.body,bytes) else response.body
                queries = query_cache(text)
                config, info = context(queries)
                if str(info['id']) != str(endpoint['provider_store_id']):
                    raise ValueError('Sweed provider tenant changed')
                observed = observe(url,response)
                if observed['license_type'] != endpoint['license_type']:
                    raise ValueError('Sweed selected license changed')
                query = next(q for q in queries if q['queryKey'][0] == '/Products/GetProductList')
                data, params = query['state']['data'], query['queryKey'][1]
                if params.get('filters') or params.get('searchTerm'):
                    raise ValueError('Sweed returned a filtered catalog')
                total, page_size, products = data['total'], data['pageSize'], data['list']
                if not isinstance(total,int) or isinstance(total,bool) or total < 0 or not isinstance(page_size,int) or page_size <= 0:
                    raise ValueError('invalid Sweed advertised counts')
                if data['page'] != page or params['page'] != page or params['pageSize'] != page_size:
                    raise ValueError('Sweed ignored requested page')
                if expected is None:
                    expected = total
                result['pages'].append({'pass':pass_index+1,'page':page,'page_size':page_size,'count':len(products),'advertised_total':total,'evidence_id':response.evidence_id})
                if total != expected:
                    raise ValueError(f'Sweed advertised total changed at page {page}: started with {expected}, received {total}; independent full traversal required')
                expected_page=min(page_size,max(0,total-(page-1)*page_size))
                if len(products)!=expected_page:
                    raise ValueError(f'Sweed missing products at page {page}: expected {expected_page}, received {len(products)}; advertised total {total}')
                for product in products:
                    source_id = str(product['id'])
                    source_ids.add(source_id)
                    record_count += 1
                    for item in normalize_product(product,endpoint):
                        key = (item['source_id'],item['variant_id'])
                        if key in fingerprints:
                            raise ValueError('Sweed duplicate variant identity')
                        fingerprints[key] = hashlib.sha256(json.dumps(inventory_fields(item),sort_keys=True,separators=(',',':')).encode()).hexdigest()
                        items.append(item)
                if pass_index==0:
                    result['items']=items.copy()
                    result['source_product_count']=len(source_ids)
                    result['expected_count']=len(items)
                if record_count == expected:
                    break
            else:
                raise ValueError('Sweed configured page limit reached')
            passes.append((expected,fingerprints))
            pass_items.append(items)
            if pass_index == 0:
                result['items'],result['source_product_count'],result['expected_count'] = items,len(source_ids),len(items)
                result['advertised_record_count'] = expected
            elif passes[0] != passes[1]:
                # Both passes reconciled to their own advertised totals; only live inventory differs (grade B).
                from backend.completeness import churn_convergence
                convergence = churn_convergence(pass_items[0],pass_items[1],kind='churn_tolerant',source_total=passes[1][0])
                if not convergence:
                    raise ValueError('Sweed menu changed across independent complete traversals')
        if convergence:
            result.update(complete=False,convergence=convergence)
            return result
        result.update(complete=True,authoritative_zero=result['expected_count']==0,count_semantics='advertised total counts listing records, including repeated parent products with different variants; source_product_count counts unique parent IDs; expected_count counts expanded unique variants')
    except Exception as exc:
        result['errors'].append({'code':'incomplete_menu','message':str(exc) or type(exc).__name__ + ': required source query missing'})
    return result
