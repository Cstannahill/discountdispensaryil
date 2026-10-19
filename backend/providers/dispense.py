"""Observed Dispense public storefront SDK: GET venue/products, skip/limit/count."""
from backend.domain import inventory_fields
from decimal import Decimal
import hashlib
import json
import re
from urllib.parse import urlencode,urlsplit
from backend.site_discovery import Page,objects,license_context

API='https://api.dispenseapp.com/v1/venues/'
VERSION='dispense-public-2'


def observe(url,response):
    text=response.body.decode('utf-8',errors='replace')
    # Next's RSC string embeds escape quotes; no JavaScript is evaluated.
    decoded=text.replace('\\"','"')
    match=re.search(r'"venueId"\s*[:,]\s*"([a-z0-9]+)"',decoded)
    if not match:return None
    page=Page(text,response.url)
    store=next((o for o in objects(page.structured) if o.get('@type')=='Store'),{})
    address=store.get('address') or {}
    path=urlsplit(response.url).path
    # The observed proxied shop root is a complete menu, unlike a category.
    base=path.split('/categories/')[0].rstrip('/')
    context,basis=license_context(url)
    return dict(url=response.url.split(path)[0]+base,provider='dispense',provider_store_id=match[1],license_type=context,
                license_basis=basis,script_urls=[u for u in page.links if '/_next/static/chunks/' in u and urlsplit(u).path.endswith('.js')],
                resolution_evidence=dict(url=response.url,evidence_id=response.evidence_id,fetched_at=response.fetched_at,
                                         retailer_name=store.get('name'),retailer_address=address.get('streetAddress'),method='Observed Dispense RSC venueId and Store schema'))


def public_key(endpoint,fetcher,evidence):
    if endpoint.get('public_api_key'):return endpoint['public_api_key']
    cached=getattr(fetcher,'_dispense_sdk_key',None)
    if cached:
        evidence.extend(cached['evidence']);return cached['key']
    for url in dict.fromkeys(endpoint.get('script_urls',[])):
        # Only scripts actually linked by the observed storefront.
        response=fetcher.get(url)
        evidence.append(response.evidence_id)
        match=re.search(r'apiKey\s*:\s*"([a-z0-9-]+)"\s*,\s*apiUrl\s*:\s*"https://api\.dispenseapp\.com"',response.body.decode(errors='replace'))
        if match:
            fetcher._dispense_sdk_key=dict(key=match[1],evidence=evidence.copy())
            return match[1]
    raise ValueError('Observed storefront SDK public key could not be located')


def normalize(product,endpoint):
    from backend.adapters import _decimal
    if not product.get('id'):raise ValueError('Dispense product identity missing')
    if str(product.get('venue'))!=str(endpoint['provider_store_id']):raise ValueError('Dispense product belongs to another venue')
    category=product.get('productCategoryName') or 'unknown'
    mapped={'flower':'flower','concentrates':'concentrate','concentrate':'concentrate','vapes':'vapes','vape':'vapes'}.get(category.casefold(),'other')
    variants=product.get('variants') or [product]
    result=[]
    for variant in variants:
        data=dict(product,**variant)
        if not variant.get('id'):raise ValueError('Dispense variant identity missing')
        if data.get('priceType') not in (None,'REGULAR'):raise ValueError('Dispense price-tier schema requires a dedicated variant normalization contract')
        grams=_decimal(data.get('weightInGrams')) if data.get('weightUnit') in ('GRAMS','OUNCES') else None
        discounts=data.get('discounts') or []
        size=re.sub(r'\s+','',str(data.get('weightFormatted') or '')).casefold()
        # A sale scoped to this variant's own size is a plain shelf sale; any other size scope is not this item's price.
        conditional=any(d.get('productOfferType')!='SALE' or d.get('orderPickUpTypes') or d.get('customerGroups') or d.get('minimumSpend')
                        or (d.get('weights') and (not size or size not in {re.sub(r'\s+','',str(w)).casefold() for w in d['weights']})) for d in discounts)
        labs=data.get('labs') or {}
        quantity=_decimal(data.get('quantity'))
        result.append(dict(source_id=str(product['id']),variant_id=str(variant['id']) if product.get('variants') else 'base',
                           name=data.get('name') or '',brand=(data.get('brand') or {}).get('name'),category=mapped,source_category=category,
                           subcategory=data.get('subType'),strain_type=data.get('cannabisType'),
                           thc_pct=_decimal(labs.get('thc')) if labs.get('thcContentUnit')=='%' else None,
                           weight_grams=grams,weight_label=data.get('weightFormatted'),regular_price=_decimal(data.get('price')),
                           effective_price=_decimal(data.get('priceWithDiscounts') if data.get('priceWithDiscounts') is not None else data.get('price')),
                           conditional=bool(conditional),promo=('bogo' if any(str(d.get('productOfferType','')).upper()=='BOGO' for d in discounts) else None),available=quantity is not None and Decimal(quantity)>0 and data.get('enable') is True and not data.get('deleted'),
                           source_url=data.get('productUrl') or endpoint['url'],raw=dict(product=product,variant=variant)))
    return result


def fetch(endpoint,fetcher):
    result=dict(provider='dispense',adapter_version=VERSION,items=[],complete=False,expected_count=None,pages=[],errors=[],evidence=[],authoritative_zero=False,
                limits=dict(page_size=100,max_pages=int(endpoint.get('max_pages',1000)),verification_passes=2),source_filter=dict(quantityMin=1),
                count_semantics='Public current menu filter quantityMin=1; advertised count is product records, expected_count is expanded variants')
    try:
        key=public_key(endpoint,fetcher,result['evidence'])
        headers={'api-key':key,'accept':'application/json'}
        venue=fetcher.get(API+endpoint['provider_store_id'],headers=headers)
        result['evidence'].append(venue.evidence_id)
        context=venue.json()['data']
        if str(context['id'])!=str(endpoint['provider_store_id']) or context.get('testMode') or context.get('currencyCode')!='USD':
            raise ValueError('Dispense venue identity/currency/test context mismatch')
        if endpoint.get('license_type')=='medicinal' and context.get('medicalDispensary') is not True:
            raise ValueError('Explicit medical endpoint conflicts with Dispense venue context')
        passes=[];pass_items=[];convergence=None
        for traversal in range(2):
            items=[];seen=set();expected=None;records=0
            for page in range(result['limits']['max_pages']):
                url=API+endpoint['provider_store_id']+'/products?'+urlencode(dict(limit=100,skip=page*100,quantityMin=1))
                response=fetcher.get(url,headers=headers);result['evidence'].append(response.evidence_id)
                body=response.json();total=body['count'];products=body['data']
                if not isinstance(total,int) or isinstance(total,bool) or total<0:raise ValueError('Invalid Dispense advertised total')
                if expected is None:expected=total
                if expected!=total or len(products)!=min(100,max(0,total-page*100)):raise ValueError('Dispense total changed or page is missing records')
                for product in products:
                    records+=1
                    for item in normalize(product,endpoint):
                        identity=(item['source_id'],item['variant_id'])
                        if identity in seen:raise ValueError('Dispense repeated product/variant page')
                        seen.add(identity);items.append(item)
                if traversal==0:result['items']=items.copy()
                result['pages'].append(dict(traversal=traversal+1,page=page+1,skip=page*100,products=len(products),advertised_total=total,evidence_id=response.evidence_id))
                if records==total:break
            else:raise ValueError('Dispense page limit reached')
            fingerprint=hashlib.sha256(json.dumps(sorted((inventory_fields(item) for item in items),key=lambda i:(i['source_id'],i['variant_id'])),sort_keys=True).encode()).hexdigest()
            passes.append(fingerprint);pass_items.append(items)
            if traversal and passes[0]!=passes[1]:
                # Each pass reconciled to its advertised total; live price/stock churn is graded B, not discarded.
                from backend.completeness import churn_convergence
                convergence=churn_convergence(pass_items[0],pass_items[1],kind='churn_tolerant',source_total=expected)
                if not convergence:raise ValueError('Dispense catalog changed across independent full traversals')
        if convergence:result.update(complete=False,expected_count=len(result['items']),source_product_count=expected,convergence=convergence)
        else:result.update(complete=True,expected_count=len(result['items']),source_product_count=expected,authoritative_zero=expected==0)
    except Exception as exc:
        result['errors'].append(dict(code='incomplete_dispense_menu',message=str(exc)))
    return result
