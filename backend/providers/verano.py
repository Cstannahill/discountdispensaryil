"""Verano (Zen Leaf) storefronts: Sweed stores whose site downloads each branch's whole catalog as one document.

The branch page's Flight data lists every Sweed store (id, address, coordinates, sale types, menu url). The site's own
script reads `data.<site>/menu-config/<slug>` (the branch's Sweed id) and `data.<site>/catalog/<id>/<sale type>`, and
filters that one catalog in the browser. The catalog advertises no total, so two agreeing reads converge (grade B).
"""
from decimal import Decimal
import hashlib
import json
import re
from urllib.parse import urlsplit

from backend.domain import GRAMS_PER_OUNCE, category_of, inventory_fields
from backend.flight import records,resolve
from backend.site_discovery import objects

VERSION='verano-catalog-1'
HOSTS={'zenleafdispensaries.com':'https://data.zenleafdispensaries.com'}


def _host(url):
    host=(urlsplit(url).hostname or '').lower()
    return host[4:] if host.startswith('www.') else host


def slug(url):
    match=re.match(r'/locations/([a-z0-9-]+)(?:/|$)',urlsplit(url).path)
    return match[1] if match else None


def store_list(text):
    """The site's Sweed store list from the page's Flight data, or [] when the page carries none."""
    try:models=records(text)
    except ValueError:return []
    for model in models.values():
        for value in objects(model):
            if 'sweedStores' in value:
                stores=resolve(value['sweedStores'],models)
                if isinstance(stores,list) and all(isinstance(x,dict) for x in stores):return stores
    return []


def observe(url,response):
    if _host(response.url or url) not in HOSTS:return None
    text=response.body.decode('utf-8',errors='replace') if isinstance(response.body,bytes) else response.body
    branch=slug(response.url or url)
    if not branch:return None
    # The store list names every branch; this page's own slug picks one.
    matches=[x for x in store_list(text) if slug(x.get('url') or '')==branch and x.get('id') is not None]
    if len(matches)!=1:return None
    store=matches[0];path=urlsplit(response.url or url).path
    sale_types=[str(x).lower() for x in store.get('saleTypes') or []]
    if re.search(r'/medical(?:-menu)?(?:/|$)',path):license_type='medicinal'
    elif re.search(r'/recreational(?:/|$)',path) or 'recreational' in sale_types:license_type='recreational'
    elif sale_types==['medical']:license_type='medicinal'
    else:return None
    coords=(store.get('location') or {}).get('coords') or {}
    evidence=dict(url=response.url,evidence_id=response.evidence_id,fetched_at=response.fetched_at,method='Verano page Sweed store list (id, address, sale types)',
                  retailer_name=store.get('name'),retailer_address=(store.get('contacts') or {}).get('address'),sale_types=store.get('saleTypes'))
    if isinstance(coords.get('lat'),(int,float)) and isinstance(coords.get('lng'),(int,float)):evidence['platform_location']=dict(lat=coords['lat'],lng=coords['lng'])
    return dict(url=store['url'],provider='verano',provider_store_id=str(store['id']),license_type=license_type,resolution_evidence=evidence)


def normalize(product,endpoint):
    from backend.adapters import _decimal
    if product.get('id') is None or not product.get('name') or not isinstance(product.get('variants'),list) or not product['variants']:
        raise ValueError('Verano product identity/name/variants missing')
    category=(product.get('category') or {}).get('name') or 'Unknown'
    mapped=category_of(category) or 'other'
    items=[]
    for variant in product['variants']:
        if variant.get('id') is None:raise ValueError('Verano variant identity missing')
        size=variant.get('unitSize') or {};amount=_decimal(size.get('value'));units=str(size.get('unitAbbr','')).upper()
        count=_decimal(variant.get('unitsInPackage'));weight=None
        # Milligrams are THC dose, never package mass.
        if amount and count and units in ('G','OZ'):weight=_decimal(Decimal(amount)*Decimal(count)*(GRAMS_PER_OUNCE if units=='OZ' else 1))
        regular=_decimal(variant.get('price'))
        # The catalog carries a promo price without the promotion's terms (bundles and minimums share the field), so
        # only the shelf price is comparable; the promo price stays in raw.
        items.append(dict(source_id=str(product['id']),variant_id=str(variant['id']),name=product['name'],brand=(product.get('brand') or {}).get('name'),
                          category=mapped,source_category=category,subcategory=(product.get('subcategory') or {}).get('name'),
                          strain_type=((product.get('strain') or {}).get('prevalence') or {}).get('name'),thc_pct=None,
                          weight_grams=weight,weight_label=variant.get('name'),regular_price=regular,effective_price=regular,conditional=False,
                          available=(variant.get('orderingAvailability') or {}).get('reason')=='Available',source_url=endpoint['url'],
                          raw=dict(product={k:v for k,v in product.items() if k!='variants'},variant=variant,promo_price_terms_unknown=variant.get('promoPrice') is not None)))
    return items


def fetch(endpoint,fetcher):
    result=dict(provider='verano',adapter_version=VERSION,items=[],complete=False,expected_count=None,source_product_count=None,pages=[],errors=[],evidence=[],
                authoritative_zero=False,limits=dict(verification_passes=2,concurrency=1),
                count_semantics='whole-branch catalog document without an advertised total; expected_count counts expanded unique variants')
    try:
        base=HOSTS.get(_host(endpoint['url']));branch=slug(endpoint['url'])
        if not base or not branch:raise ValueError('Verano endpoint is not a branch page on a known site')
        if endpoint.get('license_type') not in ('recreational','medicinal'):raise ValueError('unverified Verano license context')
        sale='medical' if endpoint['license_type']=='medicinal' else 'recreational'
        # Recheck the branch through the site's own config: the slug must still name this Sweed store and sale type.
        response=fetcher.get(f'{base}/menu-config/{branch}');result['evidence'].append(response.evidence_id)
        if response.status_code!=200:raise ValueError(f'Verano menu config HTTP {response.status_code}')
        config=json.loads(response.body)
        if str(config.get('sweedId'))!=str(endpoint['provider_store_id']):raise ValueError('Verano branch config names a different store')
        if config.get('hasMedicalMenu' if sale=='medical' else 'hasRecreationalMenu') is not True:raise ValueError('Verano branch has no menu for this license')
        passes=[]
        for index in range(2):
            response=fetcher.get(f"{base}/catalog/{endpoint['provider_store_id']}/{sale}");result['evidence'].append(response.evidence_id)
            if response.status_code!=200:raise ValueError(f'Verano catalog HTTP {response.status_code}')
            products=json.loads(response.body).get('products')
            if not isinstance(products,list):raise ValueError('Verano catalog product list missing')
            items,keys=[],set()
            for product in products:
                for item in normalize(product,endpoint):
                    key=(item['source_id'],item['variant_id'])
                    if key in keys:raise ValueError('Verano duplicate variant identity')
                    keys.add(key);items.append(item)
            fingerprint=hashlib.sha256(json.dumps(sorted(json.dumps(inventory_fields(i),sort_keys=True) for i in items)).encode()).hexdigest()
            result['pages'].append(dict(pass_=index+1,products=len(products),variants=len(items),fingerprint=fingerprint,evidence_id=response.evidence_id))
            passes.append(items)
            if index==0:result.update(items=items,expected_count=len(items),source_product_count=len(products))
        from backend.completeness import churn_convergence
        convergence=churn_convergence(passes[0],passes[1],kind='churn_tolerant')
        if not convergence:raise ValueError('Verano catalog changed between reads (or is too small to converge)')
        result['convergence']=convergence
    except Exception as exc:
        result['errors'].append(dict(code='incomplete_verano_menu',message=str(exc),evidence_id=getattr(exc,'evidence_id',None)))
    return result
