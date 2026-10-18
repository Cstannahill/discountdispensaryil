"""Network-first menu extraction: find product collections in JSON responses a rendered page already
loaded, and map them to normalized items. No site-specific code: detection is structural (arrays of
objects with a name and a price) and mapping is by key-name families, validated against stored evidence."""
from decimal import Decimal, InvalidOperation
import gzip
import json
from pathlib import Path
import re

MIN_ARRAY = 3
MAX_BODY_BYTES = 20 * 1024 * 1024
NAME_KEYS = ('name', 'Name', 'title', 'product_name', 'productName', 'display_name', 'displayName')
ID_KEYS = ('product_id', 'productId', 'id', '_id', 'objectID', 'object_id', 'sku', 'uuid', 'slug', 'url_slug')
BRAND_KEYS = ('brand', 'brand_name', 'brandName', 'vendor', 'manufacturer')
KIND_KEYS = ('kind', 'product_type', 'productType', 'type', 'category', 'category_name', 'categoryName', 'root_type')
STRAIN_KEYS = ('strain_type', 'strainType', 'category', 'cannabis_type', 'cannabisType', 'species')
STRAINS = {'indica', 'sativa', 'hybrid'}
# Parallel arrays: Options[i] is the package label priced by Prices[i] (recreational / medical, regular / special).
ARRAY_PRICES = {'recreational': ('recPrices', 'Prices'), 'medicinal': ('medicalPrices', 'Prices')}
ARRAY_SPECIALS = {'recreational': ('recSpecialPrices',), 'medicinal': ('medicalSpecialPrices',)}
ARRAY_PRICE_KEYS = ('Prices', 'recPrices', 'medicalPrices')
TOTAL_KEYS = ('totalCount', 'nb_hits', 'nbHits', 'total', 'total_count', 'totalCount', 'total_results', 'count', 'numberOfItems')
PRICE_KEY = re.compile(r'^(?:(?:sale|discounted|special|regular|retail|unit|list)_?)?price$|^price_(?:each|[a-z_]+)$|^(?:sale|retail)Price$', re.I)
# Weight-keyed price families: price_<w>, discounted_price_<w>, special_price_<w>.
WEIGHTS = {'each': None, 'half_gram': '0.5', 'gram': '1', 'two_gram': '2', 'two_grams': '2', 'eighth_ounce': '3.5', 'eighth': '3.5',
           'quarter_ounce': '7', 'quarter': '7', 'half_ounce': '14', 'ounce': '28', 'full_ounce': '28'}
FAMILY = re.compile(r'^(price|discounted_price|special_price)_(' + '|'.join(sorted(WEIGHTS, key=len, reverse=True)) + r')$')
CATEGORY = {'flower': 'flower', 'vape': 'vapes', 'vaporizers': 'vapes', 'vaporizer': 'vapes', 'vapes': 'vapes', 'cartridge': 'vapes', 'cartridges': 'vapes', 'extract': 'concentrate',
            'extracts': 'concentrate', 'concentrate': 'concentrate', 'concentrates': 'concentrate'}
CONDITIONAL_SPECIALS = ('applicable_cart_total_special_ids', 'applicable_bulk_special_ids', 'applicable_any_qualifier_special_ids')


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        for key in ('amount', 'value', 'price'):
            if key in value:
                return _number(value[key])
        return None
    try:
        number = Decimal(str(value).replace('$', '').replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


def _text(number):
    return format(number.normalize(), 'f')


def _first(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, '', [], {}):
            return value
    return None


def _label(value):
    if isinstance(value, dict):
        value = value.get('name') or value.get('title')
    return str(value).strip() if value not in (None, '') else None


def _attributes(product):
    nested = product.get('search_attributes')
    return {**{k: v for k, v in product.items() if k != 'search_attributes'}, **nested} if isinstance(nested, dict) else product


def _looks_like_product(product):
    if not isinstance(product, dict):
        return False
    attrs = _attributes(product)
    has_name = any(isinstance(attrs.get(k), str) and attrs.get(k).strip() for k in NAME_KEYS)
    has_price = any(PRICE_KEY.match(k) and _number(v) is not None for k, v in attrs.items()) or \
        any(isinstance(attrs.get(k), list) and attrs[k] and all(_number(x) is not None for x in attrs[k]) for k in ARRAY_PRICE_KEYS)
    return has_name and has_price


def _shape(path):
    return re.sub(r'\[\d+\]', '[]', path)


def _skeleton(item):
    """An id-only placeholder (some menus list every id but hydrate details a page at a time)."""
    attrs = _attributes(item) if isinstance(item, dict) else {}
    return isinstance(item, dict) and not any(isinstance(attrs.get(k), str) for k in NAME_KEYS) and         not any(PRICE_KEY.match(k) for k in attrs) and len(attrs) <= 8


def find_product_arrays(value, path='$', parent=None, min_size=MIN_ARRAY, only_shapes=None):
    """Yield (path, array, parent_object) for lists in which most elements look like products.
    Placeholders without details are ignored in the ratio and in the yielded array."""
    if isinstance(value, list):
        dicts = [x for x in value if isinstance(x, dict)]
        real = [x for x in dicts if not _skeleton(x)]
        shape_ok = only_shapes is None or _shape(path) in only_shapes
        if shape_ok and len(real) >= min_size and sum(_looks_like_product(x) for x in real) >= 0.6 * len(real):
            yield path, real, parent
            return
        for index, child in enumerate(value[:200]):
            yield from find_product_arrays(child, f'{path}[{index}]', parent, min_size, only_shapes)
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from find_product_arrays(child, f'{path}.{key}', value, min_size, only_shapes)


def _total(parent):
    if not isinstance(parent, dict):
        return None
    for key in TOTAL_KEYS:
        value = parent.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    for key in ('queryInfo', 'meta', 'pagination', 'pageInfo'):
        nested = parent.get(key)
        if isinstance(nested, dict) and _total(nested):
            return _total(nested)
    return None


def _available_weights(attrs):
    weights = attrs.get('available_weights')
    if not isinstance(weights, list):
        return None
    return {str(w).strip().lower().replace(' ', '_') for w in weights}


def _conditional(attrs):
    if any(attrs.get(key) for key in CONDITIONAL_SPECIALS):
        return True
    bundle = attrs.get('applicable_bundle_special_ids')
    return isinstance(bundle, dict) and any(bundle.values())


def _in_stock(attrs):
    for key in ('in_stock', 'inStock', 'available', 'is_available', 'isAvailable'):
        if isinstance(attrs.get(key), bool):
            return attrs[key]
    return None


def _item(product, attrs, source_id, variant, grams, label, regular, effective, available, source_url, kind):
    category = CATEGORY.get(str(kind or '').strip().lower().replace('_', '-'), 'other') if kind else 'other'
    strain = _first(attrs, STRAIN_KEYS)
    content = attrs.get('THCContent')
    thc = _number(content['range'][0]) if isinstance(content, dict) and isinstance(content.get('range'), list) and content['range'] and content.get('unit') == 'PERCENTAGE' else \
        _number(_first(attrs, ('percent_thc', 'thc_percentage', 'thc', 'thcPercent')))
    return dict(source_id=source_id, variant_id=variant, name=_label(_first(attrs, NAME_KEYS)) or '', brand=_label(_first(attrs, BRAND_KEYS)),
                category=category, source_category=str(kind) if kind else None,
                strain_type=str(strain).title() if str(strain).lower() in STRAINS else None,
                thc_pct=_text(thc) if thc is not None else None,
                weight_grams=grams, weight_label=label, regular_price=_text(regular), effective_price=_text(effective),
                available=available, conditional=_conditional(attrs), source_url=source_url,
                raw=dict(source='network_json', product_id=source_id, prices={k: attrs[k] for k in attrs if k.startswith(('price', 'discounted_price', 'special_price')) and attrs[k] not in ({}, None)}))


_OUNCES = {'1/8': '3.5', '1/4': '7', '1/2': '14', '1': '28'}


def _option_grams(label):
    """Package mass in grams from an option label such as 3.5g, 1/8oz, 1oz; None for doses (100mg) and counts."""
    text = str(label or '').strip().lower().replace(' ', '')
    grams = re.fullmatch(r'(\d*\.?\d+)(?:g|gram|grams)', text)
    if grams:
        return _text(Decimal(grams[1]))
    ounce = re.fullmatch(r'(\d+/\d+|\d*\.?\d+)(?:oz|ounce|ounces)', text)
    if ounce:
        value = ounce[1]
        if value in _OUNCES:
            return _OUNCES[value]
        try:
            fraction = Decimal(value) if '/' not in value else Decimal(value.split('/')[0]) / Decimal(value.split('/')[1])
        except (InvalidOperation, ZeroDivisionError):
            return None
        return _text(fraction * 28)
    return None


def _option_variants(product, attrs, source_id, kind, source_url, license_type):
    options = attrs.get('Options')
    if not isinstance(options, list) or not options:
        return None
    if (license_type == 'recreational' and attrs.get('medicalOnly') is True) or (license_type == 'medicinal' and attrs.get('recOnly') is True):
        return []
    prices = next((attrs[k] for k in ARRAY_PRICES[license_type] if isinstance(attrs.get(k), list) and attrs[k]), None)
    if not prices or len(prices) != len(options):
        return None
    specials = next((attrs[k] for k in ARRAY_SPECIALS[license_type] if isinstance(attrs.get(k), list) and len(attrs[k]) == len(options)), [None] * len(options))
    below = attrs.get('optionsBelowThreshold')
    items = []
    for label, price, special in zip(options, prices, specials):
        regular = _number(price)
        if regular is None:
            continue
        effective = _number(special)
        effective = effective if effective is not None and effective < regular else regular
        if attrs.get('Status') == 'Active' and isinstance(below, list):
            available = str(label) not in [str(x) for x in below]
        else:
            available = None
        grams = _option_grams(label)
        items.append(_item(product, attrs, source_id, str(label).replace(' ', '').replace('/', '_'), grams, str(label), regular, effective, available, source_url, kind))
    return items


def _products(array, source_url, license_type='recreational'):
    items = []
    for product in array:
        attrs = _attributes(product)
        source_id = _first({**product, **attrs}, ID_KEYS)
        if source_id is None or not _looks_like_product(product):
            continue
        source_id = str(source_id)
        kind = _label(_first(attrs, ('kind', 'product_type', 'productType', 'type', 'category_name', 'categoryName', 'root_type')) or
                      (attrs.get('category') if str(attrs.get('category', '')).lower() not in STRAINS else None))
        variants = _option_variants(product, attrs, source_id, kind, source_url, license_type)
        if variants is not None:
            items.extend(variants)
            continue
        families = {}
        for key, value in attrs.items():
            match = FAMILY.match(key)
            if match and _number(value) is not None or (match and isinstance(value, dict) and value):
                families.setdefault(match[2], {})[match[1]] = value
        families = {w: f for w, f in families.items() if _number(f.get('price')) is not None}
        if families:
            available = _available_weights(attrs)
            for weight, family in families.items():
                regular = _number(family['price'])
                special = family.get('special_price')
                effective = _number(family.get('discounted_price')) if family.get('discounted_price') is not None else None
                if effective is None and isinstance(special, dict):
                    effective = _number(special.get('discount_price'))
                effective = effective if effective is not None else regular
                if effective > regular:
                    effective = regular
                items.append(_item(product, attrs, source_id, weight, WEIGHTS[weight], weight.replace('_', ' '), regular, effective,
                                   # Jane lists weights, not per-unit items: an empty list or an "each" price says nothing about stock.
                                   (weight in available) if available and weight != 'each' else None, source_url, kind))
            continue
        price = _number(_first(attrs, ('price', 'sale_price', 'salePrice', 'retail_price', 'retailPrice', 'discounted_price')))
        if price is None:
            continue
        regular = _number(_first(attrs, ('regular_price', 'regularPrice', 'retail_price', 'compare_at_price', 'original_price'))) or price
        weight = _number(_first(attrs, ('weight_grams', 'net_weight_grams', 'weight', 'size')))
        unit = str(_first(attrs, ('unit', 'weight_unit', 'weightUnit', 'units')) or 'g').lower()
        grams = None
        if weight and weight > 0:
            grams = _text(weight * Decimal('28.349523125')) if unit in ('oz', 'ounce', 'ounces') else _text(weight) if unit in ('g', 'gram', 'grams', 'grm') else None
        items.append(_item(product, attrs, source_id, 'base', grams, f'{weight}{unit}' if grams else None, max(regular, price), price,
                           _in_stock(attrs), source_url, kind))
    return items


_BENIGN_FILTER_KEYS = frozenset((
    'dispensaryId', 'pricingType', 'strainTypes', 'subcategories', 'Status', 'types', 'useCache', 'isDefaultSort', 'sortBy',
    'sortDirection', 'bypassOnlineThresholds', 'ignoreQuantityThresholds', 'isKioskMenu', 'removeProductsBelowOptionThresholds',
    'platformType', 'preOrderType'))


def _filter_of(url):
    from urllib.parse import parse_qs, urlsplit
    raw = parse_qs(urlsplit(url).query).get('variables', [None])[0]
    try:
        flt = json.loads(raw)['productsFilter']
    except (TypeError, ValueError, KeyError):
        return None
    return flt if isinstance(flt, dict) else None


def _narrowing(flt):
    """Filter keys that narrow the result set. Only presentation and context keys are benign, so a flag this code
    has never seen (staffPicks, isOnSpecial, ...) counts as narrowing instead of silently passing as a whole menu."""
    return {key: value for key, value in flt.items() if key not in _BENIGN_FILTER_KEYS and value not in (None, False, [], '')}


def _unfiltered(url):
    """True when a GraphQL-style request carries no category, strain, id or special filters (the whole catalog)."""
    flt = _filter_of(url)
    if flt is None or _narrowing(flt):
        return False
    return not any(flt.get(key) for key in ('types', 'strainTypes', 'subcategories'))


def _single_type(url):
    flt = _filter_of(url)
    # A query that hydrates a chunk of ids still reports the category's own total, so productIds does not disqualify it here.
    if flt is None or _narrowing({k: v for k, v in flt.items() if k != 'productIds'}) or flt.get('strainTypes') or flt.get('subcategories'):
        return None
    types = flt.get('types')
    return types[0] if isinstance(types, list) and len(types) == 1 else None


def extract_products(captured, page_url, license_type='recreational'):
    """captured: [(url, parsed_json)]. Returns union of items (deduped by identity), the largest declared
    total, and a per-collection summary. Empty items means no product collection was recognised."""
    items, seen, collections = [], set(), []
    # A menu's last page can hold one or two products. Once a path has proved to be a product collection
    # elsewhere in the same capture set, small arrays at that same path count too.
    shapes = {_shape(path) for _, value in captured for path, _, _ in find_product_arrays(value)}
    for url, value in captured:
        for path, array, parent in find_product_arrays(value, min_size=1, only_shapes=shapes):
            found = _products(array, page_url, license_type)
            total = _total(parent)
            if found:
                collections.append(dict(url=url, path=path, count=len(found), total=total, filtered=not _unfiltered(url) and 'variables=' in url, category=_single_type(url)))
            for item in found:
                key = (item['source_id'], item['variant_id'])
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    # The menu total is the one declared by the largest collection. Featured rows and sponsored placements
    # declare their own, different hit counts and must not be mistaken for the catalog total.
    declared = [c for c in collections if c['total']]
    # A whole-catalog query's total outranks category totals; otherwise the largest declaring collection decides.
    whole = [c for c in declared if 'variables=' in c['url'] and not c['filtered']]
    largest = max(whole or declared, key=lambda c: (c['count'], c['total']), default=None)
    total = largest['total'] if largest else None
    # Single-category queries partition the menu: their totals add up to a catalog total even when no whole-menu query ran.
    per_type = {}
    for c in declared:
        if c['category']:
            per_type[c['category']] = max(per_type.get(c['category'], 0), c['total'])
    if per_type and (total is None or sum(per_type.values()) > total):
        total = sum(per_type.values())
    return dict(items=items, total=total, collections=collections)


def dispensary_identities(captured):
    """Street addresses the menu platform itself declares for the store (for example a dispensary record with
    location.ln1). Used to prove a hosted menu belongs to the requested branch, not just to the same brand."""
    found = []

    def walk(value, depth=0):
        if depth > 6:
            return
        if isinstance(value, dict):
            location = value.get('location')
            if isinstance(location, dict) and isinstance(location.get('ln1'), str) and location['ln1'].strip() and (value.get('cName') or value.get('name') or value.get('id')):
                found.append(dict(id=value.get('id'), name=value.get('name'), street=location['ln1'].strip(), city=location.get('city'), state=location.get('state')))
            for child in value.values():
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:50]:
                walk(child, depth + 1)

    for _, value in captured:
        walk(value)
    return list({(item['street'], item['city']): item for item in found}.values())


def load_captured(evidence_dir, render_evidence_id):
    """JSON responses the render captured, in capture order, read back from retained evidence."""
    root = Path(evidence_dir)
    try:
        diagnostics = json.loads((root / 'browser' / f'{render_evidence_id}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    result = []
    for entry in diagnostics.get('network_json') or []:
        if entry.get('status') != 200 or (entry.get('bytes') or 0) > MAX_BODY_BYTES:
            continue
        try:
            manifest = json.loads((root / 'manifests' / f"{entry['evidence_id']}.json").read_text(encoding='utf-8'))
            text = gzip.decompress((root / manifest['body_path']).read_bytes()).decode('utf-8', errors='replace')
            if entry.get('content_type') == 'application/x-ndjson':
                value = [json.loads(line) for line in text.splitlines() if line.strip()]
            else:
                value = json.loads(text)
        except (OSError, ValueError, KeyError):
            continue
        result.append((entry['url'], value))
    return result
