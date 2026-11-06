"""Pure normalization and time/distance rules shared by storage and the API."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import html
import json
import math
import re

# Cannabis retail sizes an ounce at 28 g (1/8 oz is sold as 3.5 g), not the avoirdupois 28.3495 g.
GRAMS_PER_OUNCE = Decimal("28")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def age_hours(value, now):
    return (instant(now) - instant(value)).total_seconds() / 3600 if value else float("inf")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def inventory_fields(item):
    """Inventory equality ignores only unmodeled source metadata, retained as raw evidence."""
    return {key:value for key,value in item.items() if key!='raw'}


def distance_miles(lat1, lon1, lat2, lon2):
    a, b, c, d = map(math.radians, [lat1, lon1, lat2, lon2])
    x = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 3958.8 * 2 * math.asin(math.sqrt(min(1, max(0, x))))


def decimal_value(value, positive=False):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or (positive and result == 0):
            return None
        return result
    except (InvalidOperation, ValueError):
        return None


def price_text(value):
    number = decimal_value(value)
    if number is None:
        return None
    return format(number, ".2f") if number.as_tuple().exponent >= -2 else str(number)


# Flower is ranked by grade: shake/trim and smalls/popcorn are cheaper per gram by design, and infused flower is a
# different product, so none of them compete with whole flower for "best deal" unless asked for.
FLOWER_GRADES = ("whole", "smalls", "shake", "infused")
_GRADE_PATTERNS = (("infused", re.compile(r"\b(?:infused|moon ?rocks?|caviar|kaviar)\b", re.I)),
                   ("shake", re.compile(r"\b(?:shake|trim|(?:pre[ _-]?)?ground|milled)\b", re.I)),
                   ("smalls", re.compile(r"\b(?:popcorn|smalls|mini ?buds?|budlets|littles|lil ?buds|mixed buds|small buds)\b", re.I)))


def flower_grade(item):
    """Grade of a flower offer from its source subcategory, else its name; None for other categories."""
    if str(item.get("category") or "").lower() != "flower":
        return None
    for text in (item.get("subcategory"), item.get("name")):
        for grade, pattern in _GRADE_PATTERNS:
            if text and pattern.search(str(text)):
                return grade
    return "whole"


# No flower, concentrate or vape is sold under 0.1 g; Dutchie lists mg doses and mistyped 0.5 g packs as ".05g", so such a
# mass is a source label error and the offer is excluded rather than priced at hundreds of dollars per gram.
# A mass written in the product name as [300mg], [4g] or (2.5 g) is the package the retailer says it sells; a priced option
# label that disagrees with every such mass (Jane "half gram" on a [4g] extract) would make a wrong $/g, so it is excluded.
_NAME_MASS = re.compile(r"[\[(]\s*(\d*\.?\d+)\s*(mg|g|grams?)\s*[\])]|\|\s*(\d*\.?\d+)\s*(mg|g|grams?)\s*(?:\||$)", re.I)


def name_masses(name):
    return {Decimal(n or n2) / (1000 if (u or u2).lower() == "mg" else 1) for n, u, n2, u2 in _NAME_MASS.findall(str(name or ""))}


# One category map for every provider: menus label the same product class many ways ("Vapes &amp; Carts", "Cartridge", "Extract").
CATEGORIES = {"flower": "flower", "concentrate": "concentrate", "concentrates": "concentrate", "extract": "concentrate", "extracts": "concentrate",
              "vape": "vapes", "vapes": "vapes", "vaporizer": "vapes", "vaporizers": "vapes", "cartridge": "vapes", "cartridges": "vapes",
              "vape cartridge": "vapes", "vape cartridges": "vapes", "disposable": "vapes", "disposables": "vapes", "vapes & carts": "vapes", "carts": "vapes",
              "edible": "edibles", "edibles": "edibles"}
# Edibles are priced per 10 mg THC (one Illinois serving) from the package's total THC dose; grams do not describe them.
SERVING_MG = Decimal("10")
MIN_PRICE_PER_SERVING = Decimal("0.30")
_MG = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*mg(?:\b|(?=thc|cbd|cbn|cbg|cbc))", re.I)
_CANNABINOIDS = r"(thc|thcv|cbd|cbn|cbg|cbc|cba|cbda|cbga|thca)"
_COUNT = re.compile(r"(?<![\d.])(\d{1,3})\s*-?\s*(?:pk|packs?|ct|count|pcs?|pieces?)\b", re.I)
_PER_PIECE = re.compile(r"^\s*(?:each\b|ea\b|/\s*(?:pc|piece|serving|unit|gummy)|per\s+(?:pc|piece|serving|gummy|unit))", re.I)


def edible_pack_count(name):
    counts = {int(n) for n in _COUNT.findall(str(name or "")) if int(n) > 0}
    return counts.pop() if len(counts) == 1 else None


def _raw_dose(raw, variant_id):
    """Total THC mg of the package from structured provider fields, or None. Provider amounts are per unit times unitsInPackage."""
    if not isinstance(raw, dict):
        return None
    variant = raw.get("variant")
    if isinstance(variant, dict) and isinstance(variant.get("unitSize"), dict) and str(variant["unitSize"].get("unitAbbr")).upper() == "MG":
        amount = decimal_value(variant["unitSize"].get("value"), positive=True)
        units = decimal_value(variant.get("unitsInPackage"), positive=True) or Decimal(1)
        if amount is not None:
            return amount * units
    product = raw.get("product")
    if not isinstance(product, dict):
        return None
    variants = [v for v in product.get("variants") or [] if isinstance(v, dict)]
    chosen = [v for v in variants if str(v.get("id")) == str(variant_id)] or (variants if len(variants) == 1 else [])
    for v in chosen[:1]:
        thc = ((v.get("labTests") or {}).get("thc") or {})
        values = thc.get("value") or []
        if str(thc.get("unitAbbr")).upper() == "MG" and values and decimal_value(values[0], positive=True) is not None:
            return decimal_value(values[0])
    labs = product.get("labs")
    if isinstance(labs, dict) and str(labs.get("thcContentUnit")).lower() == "mg":
        return decimal_value(labs.get("thc"), positive=True)
    return None


def _name_dose(name):
    """THC mg from a product name: a THC-labeled figure, else the one unlabeled figure; ambiguous labels give None.
    Small doses written beside a piece count ("10pk 5mg") are per piece and are multiplied out."""
    text = str(name or "")
    # "10 x 10mg" states pieces times dose outright.
    multiplied = {Decimal(n) * Decimal(m) for n, m in re.findall(r"(?<![\d.])(\d{1,3})\s*[x×]\s*(\d+(?:\.\d+)?)\s*mg\b", text, re.I)}
    if len(multiplied) == 1:
        return multiplied.pop(), edible_pack_count(text), "per_piece_times_count"
    thc, plain, per_piece = [], [], False
    for m in _MG.finditer(text):
        value = Decimal(m.group(1))
        after, before = text[m.end():m.end() + 14], text[max(0, m.start() - 8):m.start()]
        # A label after the figure ("100mg THC") or just before it ("THC 100mg"); the tail of a ratio ("1:1 THC:CBC 100mg") labels nothing.
        label = re.match(r"^\s*[:\-]?\s*" + _CANNABINOIDS, after, re.I) or re.search(r"(?<![:/])\b" + _CANNABINOIDS + r"\s*[:\-]?\s*$", before, re.I)
        kind = label.group(1).lower() if label else None
        if kind in ("thc", "thcv", "thca"):
            thc.append(value)
        elif kind is None:
            plain.append(value)
        if _PER_PIECE.match(after):
            per_piece = True
    pool, count = thc or plain, edible_pack_count(text)
    if not pool:
        return None, None, None
    if not thc and len(set(plain)) > 1:
        # "4 pack-12.5mg ... 50mg": the larger figure is the package total when it is the smaller one times the piece count.
        low, high = min(plain), max(plain)
        if len(set(plain)) == 2 and count and low * count == high:
            return high, count, "package"
        return None, None, None
    mg = pool[0]
    if count and count > 1 and (per_piece or mg <= SERVING_MG):
        return mg * count, count, "per_piece_times_count"
    return mg, count, "package"


def edible_dose(item):
    """(total THC mg, piece count, basis) of an edible offer, or (None, count, None) when the menu does not state a usable dose."""
    count = edible_pack_count(item.get("name"))
    dose = _raw_dose(item.get("raw"), item.get("variant_id"))
    basis = "provider_field"
    if dose is None:
        dose, name_count, basis = _name_dose(item.get("name"))
        count = name_count or count
    if dose is None:
        # The menu's own size label ("100 mg", "50.0 milligrams") when the name carries no dose.
        label = re.sub(r"milligrams?", "mg", str(item.get("weight_label") or ""), flags=re.I)
        dose, label_count, basis = _name_dose(label)
        count = count or label_count
        if dose is not None:
            basis = "size_label"
    if dose is None:
        # Menus list mg doses as grams (".1g" for 100 mg): a small weight stands for mg unless the product names another cannabinoid.
        weight = decimal_value(item.get("weight_grams"), positive=True)
        text = f"{item.get('name')} {item.get('weight_label')}"
        if weight is not None and weight <= Decimal("0.3") and not re.search(r"\b(?:cbd|cbn|cbg|cbc)\b", text, re.I):
            dose, basis = weight * 1000, "weight_as_mg"
    if dose is None:
        return None, count, None
    return (dose, count, basis) if Decimal("1") <= dose <= Decimal("2000") else (None, count, None)


def unit_value(offer):
    """The ranking price: dollars per gram, or dollars per 10 mg THC for edibles. None when the offer lacks its amount."""
    price = decimal_value(offer.get("effective_price"))
    if str(offer.get("category")) == "edibles":
        dose = decimal_value(offer.get("dose_mg"), positive=True)
        return None if price is None or dose is None else price / dose * SERVING_MG
    weight = decimal_value(offer.get("weight_grams"), positive=True)
    return None if price is None or weight is None else price / weight
# Forms sold under a concentrate label that do not compete per gram with concentrates: infused pre-rolls/multipacks, capsules, syringes.
_NOT_CONCENTRATE = re.compile(r"\b(?:kaviar|pre[ _-]?rolls?|cones?|\d+ ?pk|\d+ ?pack|multi-?packs?|show dogs|dogwalkers|capsules?|syringes?)\b", re.I)


def category_of(label):
    return CATEGORIES.get(html.unescape(str(label or "")).strip().lower().replace("_", " "))


def _normalize_edible(item, effective):
    dose, count, basis = edible_dose(item)
    conditional = item.get("conditional") is not False
    available = item.get("available") is True
    reasons = []
    if not str(item.get("name") or "").strip():
        reasons.append("missing_product_name")
    if dose is None:
        reasons.append("unknown_or_invalid_dose")
    if effective is None:
        reasons.append("unknown_or_invalid_price")
    elif dose is not None and effective / dose * SERVING_MG < MIN_PRICE_PER_SERVING:
        reasons.append("implausible_price_per_dose")  # a dose or price typo: no retailer sells THC for under this
    if conditional:
        reasons.append("conditional_or_unverified_price")
    if not available:
        reasons.append("unavailable_or_unknown_stock")
    result = {key: item.get(key, "") for key in ("name", "brand", "subcategory", "strain_type", "thc_pct", "weight_label", "source_url")}
    result.update(source_id=str(item["source_id"]), variant_id=str(item.get("variant_id") or "base"),
                  category="edibles", source_category=item.get("source_category") or "edibles",
                  weight_grams=None, dose_mg=format(dose.normalize(), "f") if dose is not None else None, pack_count=count, dose_basis=basis,
                  regular_price=price_text(item.get("regular_price")), effective_price=price_text(effective),
                  conditional=conditional, promo=item.get("promo"), available=available, eligible=not reasons, exclusion_reasons=reasons,
                  price_per_gram=None,
                  price_per_10mg=format((effective/dose*SERVING_MG).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")
                  if effective is not None and dose is not None else None,
                  raw=item.get("raw", {}))
    return result


def normalize_offer(item):
    if not str(item.get("source_id") or "").strip():
        raise ValueError("missing_product_identity")
    weight = decimal_value(item.get("weight_grams"), positive=True)
    effective = decimal_value(item.get("effective_price"))
    category = str(item.get("category") or "unknown").lower()
    category = category_of(category) or (category_of(item.get("source_category")) if category in ("other", "unknown") else None) or category
    if category == "concentrate" and any(_NOT_CONCENTRATE.search(str(item.get(k) or "")) for k in ("name", "subcategory")): category = "other"
    if category == "edibles":
        return _normalize_edible(item, effective)
    conditional = item.get("conditional") is not False
    available = item.get("available") is True
    reasons = []
    if not str(item.get("name") or "").strip():
        reasons.append("missing_product_name")
    if category not in ("flower", "concentrate", "vapes"):
        reasons.append("unsupported_category")
    if weight is None:
        reasons.append("unknown_or_invalid_package_mass")
    if weight is not None and (named := name_masses(item.get("name"))) and all(abs(weight - m) > m / 100 for m in named):
        reasons.append("conflicting_package_mass")
    if weight is not None and weight < Decimal("0.1") and category in ("flower", "concentrate", "vapes"):
        reasons.append("implausible_package_mass")
    if effective is None:
        reasons.append("unknown_or_invalid_price")
    if conditional:
        reasons.append("conditional_or_unverified_price")
    if not available:
        reasons.append("unavailable_or_unknown_stock")
    result = {key: item.get(key, "") for key in
              ("name", "brand", "subcategory", "strain_type", "thc_pct", "weight_label", "source_url")}
    result.update(source_id=str(item["source_id"]), variant_id=str(item.get("variant_id") or "base"),
                  category=category, source_category=item.get("source_category") or category,
                  weight_grams=str(weight.normalize()) if weight is not None else None,
                  regular_price=price_text(item.get("regular_price")), effective_price=price_text(effective),
                  conditional=conditional, promo=item.get("promo"), available=available, eligible=not reasons, exclusion_reasons=reasons,
                  price_per_gram=format((effective/weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")
                  if effective is not None and weight is not None else None,
                  raw=item.get("raw", {}))
    return result
