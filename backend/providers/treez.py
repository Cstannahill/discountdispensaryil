"""Observed Treez Ecommerce Flight catalogs, traversed through retailer links."""
from decimal import Decimal
import hashlib
import json
import re
from urllib.parse import urljoin

from backend.flight import records,resolve
from backend.domain import inventory_fields as comparable_item
from backend.site_discovery import objects,Page

VERSION='treez-flight-3'


def page_context(text):
    models=records(text)
    candidates=[value for model in models.values() for value in objects(model)
                if 'selectedStore' in value and 'initialSearchResponse' in value and 'initialPage' in value]
    if len(candidates)!=1:raise ValueError('Treez catalog has missing or ambiguous selected-store context')
    props=candidates[0];store=resolve(props['selectedStore'],models)
    if not isinstance(store,dict) or not store.get('object_id'):raise ValueError('Treez selected store identity missing')
    data=resolve(props['initialSearchResponse'],models)
    if not isinstance(data,dict) or not isinstance(data.get('hits'),dict):raise ValueError('Treez search response missing')
    queries=[]
    for model in models.values():
        for value in objects(model):
            key=value.get('queryKey')
            if isinstance(key,list) and len(key)>=5 and key[0]=='products-search' and key[1]==store.get('short_name'):
                body=resolve(key[-1],models)
                if isinstance(body,dict) and body not in queries:queries.append(body)
    if len(queries)!=1:raise ValueError('Treez observed pagination query missing or ambiguous')
    query=queries[0];page=props['initialPage'];size=query.get('size')
    if isinstance(page,bool) or not isinstance(page,int) or page<0 or isinstance(size,bool) or not isinstance(size,int) or size<1 or query.get('from')!=page*size:
        raise ValueError('Treez page/query offset mismatch')
    if (props.get('initialSearchFilter') not in (None,'','$undefined') or props.get('initialQueryFiltersByFacets') or query.get('collapse',{}).get('field')!='catalogParentId'):
        raise ValueError('Treez source is a filtered or unrecognized catalog query')
    customer=resolve(props.get('selectedCustomerType'),models)
    license_type='medicinal' if str(customer).upper() in ('MEDICAL','MEDICINAL') else 'recreational'
    return dict(store=store,data=data,page=page,size=size,query=query,license_type=license_type,products=resolve(props.get('products'),models) or [])


def observe(url,response):
    try:context=page_context(response.body.decode('utf-8',errors='replace'))
    except (ValueError,TypeError,KeyError):return None
    store=context['store']
    return dict(url=response.url,provider='treez',provider_store_id=store['object_id'],license_type=context['license_type'],requires_browser_context=True,
                resolution_evidence=dict(url=response.url,evidence_id=response.evidence_id,fetched_at=response.fetched_at,
                                         retailer_address=', '.join(str(store.get(key) or '') for key in ('address1','metro_area','state','zip')),
                                         method='Treez selected-store Flight model and catalog search context'))


def normalize(source,parent,endpoint):
    from backend.adapters import _decimal
    identity=source.get('id');parent_id=parent.get('catalogParentId')
    if not identity or not parent_id:raise ValueError('Treez product/variant identity missing')
    product=source.get('productData') or {};pricing=product.get('pricing') or {}
    category=str(source.get('category') or parent.get('category') or 'unknown').upper()
    mapped={'FLOWER':'flower','EXTRACT':'concentrate','CONCENTRATE':'concentrate','CARTRIDGE':'vapes','VAPE':'vapes'}.get(category,'other')
    size=str(product.get('size') or '')
    weight=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(g|grams?|oz|ounces?)\s*',size,re.I)
    grams=_decimal(Decimal(weight[1])*(Decimal('28.349523125') if weight[2].lower().startswith(('oz','ounce')) else 1)) if weight else None
    regular=_decimal(pricing.get('priceSell'));sale=_decimal(pricing.get('discountedPrice'))
    applied=pricing.get('appliedDiscountIds') or []
    discounts={str(discount.get('discountId')):discount for discount in product.get('discounts',[]) if isinstance(discount,dict)}
    conditional=any(str(key) not in discounts or discounts[str(key)].get('discountConditions') or discounts[str(key)].get('discountAffinity') not in ('Product','PRODUCT','Pre-Cart','PRE-CART') or discounts[str(key)].get('discountMethod') in ('BUNDLE','BOGO') for key in applied)
    if sale is not None and regular is not None and Decimal(sale)<Decimal(regular) and not applied:conditional=True
    inventory=product.get('inventory') or []
    types={'ALL','BOTH','MEDICAL','MEDICINAL'} if endpoint['license_type']=='medicinal' else {'ALL','BOTH','ADULT','RECREATIONAL'}
    quantities=[_decimal(row.get('availableUnits')) for row in inventory if str(row.get('customerType')).upper() in types]
    available=any(quantity is not None and Decimal(quantity)>0 for quantity in quantities) if quantities else None
    if source.get('isActive') is False or source.get('status') not in (None,'ACTIVE') or source.get('isAboveThreshold') is False:available=False
    return dict(source_id=str(parent_id),variant_id=str(identity),name=source.get('menuTitle') or source.get('name') or parent.get('menuTitle') or '',
                brand=source.get('brand') or parent.get('brand'),category=mapped,source_category=category,subcategory=source.get('subtype'),
                weight_grams=grams,weight_label=size,regular_price=regular,effective_price=sale if sale is not None else regular,
                conditional=bool(conditional),available=available,
                source_url=urljoin(endpoint['url'],'/product/'+source['slug']) if source.get('slug') else endpoint['url'],
                raw=dict(product=source,parent_id=parent_id))


def variants(context,endpoint,expanded=None):
    data=context['data'];store=context['store']
    if str(store['object_id'])!=str(endpoint['provider_store_id']) or context['license_type']!=endpoint['license_type']:
        raise ValueError('Treez selected store/license changed')
    if data.get('timed_out') or data.get('errors') or (data.get('_shards') or {}).get('failed',0):raise ValueError('Treez search is incomplete')
    total=data['hits'].get('total') or {}
    if total.get('relation')!='eq' or isinstance(total.get('value'),bool) or not isinstance(total.get('value'),int) or total['value']<0:raise ValueError('Treez exact raw inventory total is missing')
    items=[];parents=set()
    for hit in data['hits'].get('hits',[]):
        if hit.get('_index')!='product_'+str(store['object_id']):raise ValueError('Treez hit belongs to another store index')
        parent=hit['_source'];parent_id=parent.get('catalogParentId')
        if parent_id in parents:raise ValueError('Treez repeated grouped product')
        parents.add(parent_id)
        inner=(hit.get('inner_hits') or {}).get('siblings',{}).get('hits',{})
        siblings=inner.get('hits')
        expected=inner.get('total') or {}
        if expanded and parent_id in expanded:
            complete=expanded[parent_id]
            if expected.get('value')!=len(complete):raise ValueError('Treez expanded group count changed')
            if not {str(child['_source']['id']) for child in siblings}<={str(item['variant_id']) for item in complete}:raise ValueError('Treez group variants changed during detail expansion')
            items.extend(complete);continue
        if not isinstance(siblings,list) or expected.get('relation')!='eq' or expected.get('value')!=len(siblings):raise ValueError('Treez grouped variants were truncated or omitted')
        if not any(str(child.get('_source',{}).get('id'))==str(parent.get('id')) for child in siblings):raise ValueError('Treez group representative is absent from its variants')
        for child in siblings:
            if child.get('_index')!='product_'+str(store['object_id']):raise ValueError('Treez sibling belongs to another store index')
            source=dict(parent,**child['_source'])
            items.append(normalize(source,parent,endpoint))
    return items,total['value'],parents


def expand_detail(response,context,request,endpoint):
    models=records(response.body.decode('utf-8',errors='replace'));parent=request['parent'];parent_id=parent['catalogParentId']
    products=[value for model in models.values() for value in objects(model) if value.get('catalogParentId')==parent_id and value.get('siblings')]
    if len(products)!=1:raise ValueError('Treez detail has missing or ambiguous variant group')
    siblings=products[0]['siblings'];ids=[str(item.get('id')) for item in siblings]
    if len(siblings)!=request['expected'] or len(set(ids))!=len(ids) or not request['known_ids']<=set(ids):raise ValueError('Treez product detail did not expand the advertised variants')
    from backend.locators import addresses_match
    labels=context.get('store_labels') or []
    if not any((match:=re.search(r'\b\d+\s+.*',label,re.S)) and addresses_match(request['address'],match[0]) for label in labels):
        raise ValueError('Treez product detail selected branch is not corroborated')
    items=[]
    for item in siblings:
        if item.get('catalogParentId')!=parent_id:raise ValueError('Treez detail variant belongs to another parent')
        choices=item.get('variants') or []
        if len(choices)!=1 or str(choices[0].get('id'))!=str(item.get('id')):raise ValueError('Treez detail price variant schema changed')
        price=choices[0];size=item.get('size') or []
        if len(size)!=1:raise ValueError('Treez detail package size is ambiguous')
        pricing=item.get('pricing') or {}
        source=dict(parent,id=item['id'],name=item.get('name'),menuTitle=item.get('name'),slug=item.get('path_slug') or item.get('slug'),
                    brand=item.get('brand_name') or parent.get('brand'),isActive=item.get('enabled'),isAboveThreshold=item.get('in_stock'),
                    productData=dict(size=size[0],pricing=dict(priceSell=Decimal(str(price['price']))/100,
                                                            discountedPrice=Decimal(str(price.get('salePrice',price['price'])))/100,
                                                            appliedDiscountIds=pricing.get('applied_discount_ids') or []),
                                     discounts=parent.get('productData',{}).get('discounts') or [],inventory=[dict(customerType='ALL',availableUnits=item.get('qty'))]))
        normalized=normalize(source,parent,endpoint)
        normalized['raw']=dict(product=item,parent_id=parent_id,source_kind='treez_product_detail')
        items.append(normalized)
    return items


def fetch(endpoint,fetcher):
    result=dict(provider='treez',adapter_version=VERSION,items=[],complete=False,expected_count=None,pages=[],errors=[],evidence=[],authoritative_zero=False,
                limits=dict(max_pages=int(endpoint.get('max_pages',1000)),verification_passes=3,max_page_rechecks=2,max_seconds=900),
                count_semantics='Exact uncollapsed search hit total counts variants; grouped product cardinality is approximate and cannot prove completeness')
    traversal=0;page_index=0;seen={};parents=set();previous=None;totals=set();expanded={};detail_request=None;best_partial=(0,[])
    page_state=dict(index=None,baseline=set(),observed=set(),target=0,recheck=0)
    def observe_page(response,context):
        nonlocal traversal,page_index,seen,parents,previous,totals,expanded,detail_request,best_partial
        result['evidence'].append(response.evidence_id)
        if response.status_code!=200:raise ValueError(f'Treez browser page HTTP {response.status_code}')
        if detail_request:
            expanded[detail_request['parent']['catalogParentId']]=expand_detail(response,context,detail_request,endpoint)
            detail_request=None
            return dict(back=True)
        current=page_context(response.body.decode('utf-8',errors='replace'))
        if current['page']!=page_index:raise ValueError('Treez browser returned a repeated or out-of-order page')
        if str(current['store']['object_id'])!=str(endpoint['provider_store_id']) or current['license_type']!=endpoint['license_type']:
            raise ValueError('Treez selected store/license changed')
        currencies={obj.get('priceCurrency') for obj in objects(Page(context['html'],response.url).structured) if obj.get('priceCurrency')}
        if currencies!={'USD'}:raise ValueError('Treez USD price context not corroborated')
        for hit in current['data']['hits'].get('hits',[]):
            inner=(hit.get('inner_hits') or {}).get('siblings',{}).get('hits',{});parent=hit['_source']
            if inner.get('total',{}).get('value',0)>len(inner.get('hits',[])) and parent.get('catalogParentId') not in expanded:
                declared=next((product.get('url') for product in current['products'] if product.get('catalogParentId')==parent.get('catalogParentId') and product.get('url')),None)
                if not declared:raise ValueError('Treez truncated group has no declared product-detail link')
                detail_request=dict(parent=parent,expected=inner['total']['value'],known_ids={str(child['_source']['id']) for child in inner['hits']},address=current['store'].get('address1',''))
                return dict(next_url=urljoin(response.url,declared),declared_product=True)
        items,total,page_parents=variants(current,endpoint,expanded)
        expanded={}
        if page_state['index']!=page_index:
            page_state.update(index=page_index,baseline=set(parents),observed=set(),target=len(page_parents),recheck=0)
        page_state['observed'].update(page_parents)
        parents.update(page_parents)
        duplicates=0
        for item in items:
            key=(item['source_id'],item['variant_id'])
            if key in seen:
                if comparable_item(seen[key])!=comparable_item(item):raise ValueError('Treez overlapping variant changed within traversal')
                duplicates+=1
                continue
            seen[key]=item
        # Keep valid partial observations from the latest traversal.
        result['items']=list(seen.values());totals.add(total)
        result['pages'].append(dict(traversal=traversal+1,page=page_index+1,page_recheck=page_state['recheck'],products=len(page_parents),variants=len(items),duplicate_variants=duplicates,observed_variants=len(seen),advertised_total=total,evidence_id=response.evidence_id))
        progress=getattr(fetcher,'progress_callback',None)
        if callable(progress):progress(dict(traversal=traversal+1,page=page_index+1,page_recheck=page_state['recheck'],observed_variants=len(seen),advertised_total=total))
        # Price ties can shift groups between adjacent offset pages. Re-read an
        # affected page a bounded number of times, keeping only matching unique
        # observations from this traversal. Counts and independent verification
        # still decide completeness; rechecks cannot invent missing products.
        new_parents=len(page_state['observed']-page_state['baseline'])
        if len(seen)<total and new_parents<page_state['target'] and page_state['recheck']<result['limits']['max_page_rechecks']:
            page_state['recheck']+=1
            return dict(reload=True)
        next_links=[link['url'] for link in context['links'] if str(link['label']).lower()=='go to next page']
        if next_links:
            if page_index+1>=result['limits']['max_pages']:raise ValueError('Treez traversal page limit reached')
            page_index+=1
            return dict(next_url=next_links[0])
        comparable={key:comparable_item(item) for key,item in seen.items()}
        fingerprint=hashlib.sha256(json.dumps(sorted(comparable.items()),sort_keys=True).encode()).hexdigest()
        count_complete=len(seen)==total and len(totals)==1
        if len(seen)>=len(best_partial[1]):best_partial=(traversal+1,list(seen.values()))
        result.setdefault('traversals',[]).append(dict(traversal=traversal+1,observed_variants=len(seen),advertised_totals=sorted(totals),count_complete=count_complete,fingerprint=fingerprint))
        if count_complete and previous==(total,fingerprint):
            result.update(complete=True,expected_count=len(seen),source_product_count=len(parents),authoritative_zero=total==0)
            return {}
        previous=(total,fingerprint) if count_complete else None
        traversal+=1
        if traversal>=result['limits']['verification_passes']:raise ValueError(f'Treez catalog did not reconcile across bounded independent traversals: observed {len(seen)} unique variants; advertised totals {sorted(totals)}')
        page_index=0;seen={};parents=set();totals=set()
        page_state['index']=None
        first=[link['url'] for link in context['links'] if str(link['label']).lower() in ('go to first page','go to page 1')]
        return dict(next_url=first[0]) if first else dict(reload=True)
    try:fetcher.render_catalog(endpoint['url'],observe_page,license_type=endpoint['license_type'])
    except Exception as exc:
        result['errors'].append(dict(code='incomplete_treez_menu',message=str(exc),evidence_id=getattr(exc,'evidence_id',None)))
        if len(best_partial[1])>len(result['items']):
            result['items']=best_partial[1];result['partial_items_traversal']=best_partial[0]
    return result
