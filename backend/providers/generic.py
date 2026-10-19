"""Generic structured/semantic HTML extraction with explicit completeness proof."""
from decimal import Decimal
import copy
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit
from backend.site_discovery import Page, objects, inspect_page, license_context
from backend.domain import GRAMS_PER_OUNCE, inventory_fields
from backend.documents import read_document
from backend.completeness import MIN_CONVERGED_ITEMS, churn_convergence, counts_reconcile, visible_total

# Registry store ids an operator accepted despite a street-number difference between the registry and the menu. Each
# reason records both addresses so the exception can be revisited when the registry is corrected.
ACCEPTED_STREET_MISMATCHES = {
    'a9b8267a1dc370dc2b19cd77': 'Mint Cannabis Villa Park: registry 310 E North Ave, Dutchie menu 330 E North Ave; operator accepted 2026-10-19',
    '8ce3f490d5c2e8700b3ed175': 'Dutchess Cannabis Oak Park: registry 1132 Lake St, Dutchie menu 1142 Lake St; operator accepted 2026-10-19',
}

VERSION='structured-html-3'


def normalize(product, endpoint):
    from backend.adapters import _decimal
    offers=product.get('offers') or []
    if isinstance(offers,dict):offers=[offers]
    if not offers:offers=[{}]
    identity=product.get('sku') or product.get('productID') or product.get('@id') or product.get('url')
    offer_urls={urljoin(endpoint['url'],offer['url']) for offer in offers if offer.get('url')}
    if not identity and len(offer_urls)==1:identity=next(iter(offer_urls))
    if not identity:
        raise ValueError('Structured product has no stable source identity')
    weight=product.get('weight') or {}
    grams=None
    if isinstance(weight,dict):
        unit=str(weight.get('unitCode') or weight.get('unitText') or '').casefold()
        value=_decimal(weight.get('value'))
        if value and unit in ('grm','g','gram','grams','oz','ounce','ounces'):
            grams=_decimal(Decimal(value)*(GRAMS_PER_OUNCE if unit in ('oz','ounce','ounces') else 1))
    category=str(product.get('category') or 'unknown')
    mapped={'flower':'flower','concentrate':'concentrate','concentrates':'concentrate','vape':'vapes','vapes':'vapes'}.get(category.casefold(),'other')
    result=[]
    for offer in offers:
        variant=offer.get('sku') or offer.get('@id') or offer.get('url') or ('base' if len(offers)==1 else None)
        if variant is None:raise ValueError('Multiple structured offers lack stable variant identities')
        brand=product.get('brand') or ''
        if isinstance(brand,dict):brand=brand.get('name')
        price=_decimal(offer.get('price')) if offer.get('priceCurrency')=='USD' else None
        specifications=offer.get('priceSpecification') or []
        if isinstance(specifications,dict):specifications=[specifications]
        elif not isinstance(specifications,list):specifications=[]
        regulars={_decimal(spec.get('price')) for spec in specifications if isinstance(spec,dict)
                  and spec.get('priceType') in ('https://schema.org/StrikethroughPrice','http://schema.org/StrikethroughPrice','StrikethroughPrice')
                  and spec.get('priceCurrency',offer.get('priceCurrency'))=='USD'}
        regulars.discard(None)
        regular=next(iter(regulars)) if len(regulars)==1 else price
        if price is None or regular is None or Decimal(regular)<Decimal(price):regular=price
        result.append(dict(source_id=str(identity),variant_id=str(variant),name=product.get('name') or '',brand=brand,
                           category=mapped,source_category=category,weight_grams=grams,weight_label=str(weight) if grams else '',
                           regular_price=regular,effective_price=price,available=(offer['availability'] in ('https://schema.org/InStock','http://schema.org/InStock','InStock')) if offer.get('availability') else None,
                           conditional=bool(offer.get('eligibleCustomerType') or offer.get('eligibleQuantity') or offer.get('eligibleTransactionVolume')),
                           source_url=urljoin(endpoint['url'],product.get('url') or offer.get('url') or endpoint['url']),raw=dict(product=product,offer=offer)))
    return result


def extract(text,url):
    page=Page(text,url)
    products=[]
    totals=[]
    for item in objects(page.structured):
        types=item.get('@type') or []
        if isinstance(types,str):types=[types]
        if 'Product' in types:products.append(item)
        if ('ItemList' in types and isinstance(item.get('numberOfItems'),int) and
                re.search(r'\ball products\b|\bfull (?:menu|catalog)\b|\bcomplete (?:menu|catalog)\b|\ball menu items\b',str(item.get('name') or ''),re.I) and
                not re.search(r'featured|carousel|recommended|related|specials|category',str(item.get('name') or ''),re.I)):
            totals.append(item['numberOfItems'])
    # Semantic microdata/data attributes are observations too. A page lacking
    # advertised catalog totals remains partial even when cards are extracted.
    for match in re.finditer(r'<(?:article|div|li)\b(?=[^>]*data-product-id=["\']([^"\']+))[^>]*>(.*?)</(?:article|div|li)>',text,re.S|re.I):
        tag=match[0]
        attrs=dict(re.findall(r'(data-[\w-]+)=["\']([^"\']*)',tag))
        if attrs.get('data-product-name'):
            products.append({'@type':'Product','sku':attrs['data-product-id'],'name':attrs['data-product-name'],
                             'category':attrs.get('data-category'),'offers':{'price':attrs.get('data-price'),'priceCurrency':attrs.get('data-currency')}})
    return page,products,totals


def network_collections(fetcher,response,endpoint):
    """Product collections found in JSON the rendered page itself loaded (None unless the response was a render)."""
    from backend.network_extract import dispensary_identities, extract_products, load_captured
    folder=getattr(fetcher,'evidence_dir',None)
    if not folder:return None
    captured=load_captured(folder,response.evidence_id)
    result=extract_products(captured,endpoint['url'],endpoint.get('license_type','recreational')) if captured else None
    if result:result['identities']=dispensary_identities(captured)
    return result if result and (result['items'] or result.get('identities')) else None


def fetch(endpoint,fetcher):
    fetcher=copy.copy(fetcher)
    fetcher.browser_options=dict(getattr(fetcher,'browser_options',{}),license_type=endpoint.get('license_type','recreational'),await_menu=True)
    result=dict(provider=endpoint.get('provider','generic'),adapter_version=VERSION,items=[],complete=False,
                expected_count=None,pages=[],errors=[],evidence=[],authoritative_zero=False,
                limits=dict(max_pages=int(endpoint.get('max_pages',1000)),verification_passes=2),
                count_semantics='Advertised ItemList total counts parent products; accepted expected_count counts expanded variants')
    passes=[];pass_items=[];modes=[];shown_totals=[]
    try:
        for traversal in range(2):
            url=endpoint['url'];visited=set();seen=set();parents=set();items=[];expected=None;shown=set()
            for number in range(result['limits']['max_pages']):
                if url in visited:raise ValueError('Generic pagination repeated a URL')
                visited.add(url)
                response=(fetcher.render(url,license_type=endpoint.get('license_type','recreational')) if endpoint.get('requires_browser_context') else read_document(url,fetcher,license_type=endpoint.get('license_type','recreational')))
                result['evidence'].append(response.evidence_id)
                if response.status_code!=200:raise ValueError(f'Generic menu HTTP {response.status_code}')
                text=response.body.decode('utf-8',errors='replace')
                page,products,totals=extract(text,response.url)
                if not products and number==0 and hasattr(fetcher,'render'):
                    response=fetcher.render(url,license_type=endpoint.get('license_type','recreational'))
                    if response.status_code>=400:
                        raise ValueError(f'Browser menu document returned HTTP {response.status_code}')
                    result['evidence'].append(response.evidence_id)
                    text=response.body.decode('utf-8',errors='replace')
                    page,products,totals=extract(text,response.url)
                network=[]
                found=network_collections(fetcher,response,endpoint)
                target=fetcher.browser_options.get('target_store')
                if found and target and target.get('address') and found.get('identities') and target.get('id') not in ACCEPTED_STREET_MISMATCHES:
                    from backend.locators import addresses_match
                    if not any(addresses_match(target['address'],identity['street']) for identity in found['identities']):
                        raise ValueError('Menu source belongs to a different street address: '+'; '.join(identity['street'] for identity in found['identities'][:3]))
                if found and not found['items']:found=None
                if found and len({i['source_id'] for i in found['items']})>=len(products):
                    # The page's own JSON is a better source than visible cards; keep the DOM only when it saw more.
                    network=found['items'];products=[]
                    if found['total'] and not totals:totals=[found['total']]
                    result['network_collections']=found['collections']
                if products or network:
                    counter=visible_total(text)
                    if counter:shown.add(counter)
                expected_host=(urlsplit(endpoint['url']).hostname or '').removeprefix('www.')
                actual_host=(urlsplit(response.url).hostname or '').removeprefix('www.')
                if actual_host!=expected_host:raise ValueError('Generic menu redirected to a different source hostname; rediscovery required')
                actual_license,license_basis=license_context(response.url)
                if license_basis=='explicit' and actual_license!=endpoint.get('license_type','recreational'):
                    raise ValueError('Generic menu changed explicit license context')
                target=fetcher.browser_options.get('target_store')
                if target and inspect_page(target,response)['identity_status']=='conflict':
                    raise ValueError('Generic menu changed branch address; selected store no longer matches')
                if totals:
                    if len(set(totals))!=1:raise ValueError('Ambiguous structured listing totals')
                    if expected is not None and expected!=totals[0]:raise ValueError('Structured total changed between pages')
                    expected=totals[0]
                if not products and not network:raise ValueError('No structured products extracted; JavaScript or an additional schema extractor may be required')
                for item in network:
                    key=(item['source_id'],item['variant_id'])
                    if key in seen:raise ValueError('Generic duplicate product/variant identity')
                    seen.add(key);parents.add(item['source_id']);items.append(item)
                for product in products:
                    for item in normalize(product,endpoint):
                        key=(item['source_id'],item['variant_id'])
                        if key in seen:raise ValueError('Generic duplicate product/variant identity')
                        seen.add(key);parents.add(item['source_id']);items.append(item)
                if traversal==0:result['items']=items.copy()
                result['pages'].append(dict(traversal=traversal+1,page=number+1,url=response.url,products=len(products)+len({i['source_id'] for i in network}),variants=len(items),advertised_total=expected,evidence_id=response.evidence_id))
                next_links=list(dict.fromkeys(page.next_links))
                if len(next_links)>1:raise ValueError('Ambiguous next-page links')
                if not next_links:break
                if urlsplit(next_links[0]).hostname!=urlsplit(endpoint['url']).hostname:raise ValueError('Generic pagination changed source hostname')
                url=next_links[0]
            else:raise ValueError('Generic page limit reached')
            if expected is None:
                # No structured total. A count the page itself displays can still corroborate a
                # traversal that matches it exactly (grade B); a lone carousel cannot, hence the floor.
                counter=max(shown) if shown else None
                if not (counter and len(items)>=MIN_CONVERGED_ITEMS and (counts_reconcile(counter,len(parents)) or counts_reconcile(counter,len(items)))):
                    raise ValueError('Products extracted, but source advertises no independently verifiable full-menu total')
                modes.append('visible_counter');shown_totals.append(counter)
            elif len(parents)!=expected:raise ValueError('Structured product total does not reconcile with traversed catalog')
            else:modes.append('structured_total')
            pass_items.append(items)
            fingerprint=hashlib.sha256(json.dumps([inventory_fields(item) for item in sorted(items,key=lambda i:(i['source_id'],i['variant_id']))],sort_keys=True).encode()).hexdigest()
            passes.append(fingerprint)
            if traversal and modes[0]!=modes[1]:raise ValueError('Generic menu total evidence changed across independent traversals')
            if traversal and passes[0]!=passes[1] and modes[0]!='visible_counter':raise ValueError('Generic menu changed across independent traversals')
        if modes[0]=='visible_counter':
            convergence=churn_convergence(pass_items[0],pass_items[1],kind='visible_counter',source_total=shown_totals[0])
            if not convergence:raise ValueError('Generic menu changed across independent traversals')
            result.update(complete=False,expected_count=len(result['items']),source_product_count=len({i['source_id'] for i in result['items']}),convergence=convergence)
        else:result.update(complete=True,expected_count=len(result['items']),source_product_count=expected)
    except Exception as exc:
        if getattr(exc,'evidence_id',None):
            result['evidence'].append(exc.evidence_id)
            result['pages'].append(dict(url=locals().get('url',endpoint['url']),error=str(exc),evidence_id=exc.evidence_id))
        result['errors'].append(dict(code='incomplete_generic_menu',message=str(exc)))
    return result
