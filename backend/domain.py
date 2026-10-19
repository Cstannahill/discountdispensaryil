"""Pure normalization and time/distance rules shared by storage and the API."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
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
_GRADE_PATTERNS = (("infused", re.compile(r"\b(?:infused|moon ?rocks?|caviar)\b", re.I)),
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


def normalize_offer(item):
    if not str(item.get("source_id") or "").strip():
        raise ValueError("missing_product_identity")
    weight = decimal_value(item.get("weight_grams"), positive=True)
    effective = decimal_value(item.get("effective_price"))
    category = str(item.get("category") or "unknown").lower()
    category = {"concentrates": "concentrate", "extracts": "concentrate", "vape": "vapes"}.get(category, category)
    conditional = item.get("conditional") is not False
    available = item.get("available") is True
    reasons = []
    if not str(item.get("name") or "").strip():
        reasons.append("missing_product_name")
    if category not in ("flower", "concentrate", "vapes"):
        reasons.append("unsupported_category")
    if weight is None:
        reasons.append("unknown_or_invalid_package_mass")
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
                  conditional=conditional, available=available, eligible=not reasons, exclusion_reasons=reasons,
                  price_per_gram=format((effective/weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")
                  if effective is not None and weight is not None else None,
                  raw=item.get("raw", {}))
    return result
