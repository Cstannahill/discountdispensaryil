"""Cross-store product identity and price sanity, on offers already normalized (pure functions, no storage access)."""
from decimal import Decimal
import html
import re

# Words menus add around the same product: package form, provider labels, flower grade (grade is part of the key instead).
_FORM_WORDS = frozenset("""flower cartridge cartridges cart carts vape vapes pen pens disposable disposables aio distillate rechargeable
    popcorn smalls shake trim infused pre prepack prepacked pack packs the of and with by gram grams mg oz ounce eighth quarter half""".split())
_GENERIC = frozenset("sativa indica hybrid cbd thc blend mix assorted mixed any strain".split())
_MASS = re.compile(r"\d*\.?\d+\s*(?:mg|g|gm|grams?|oz|ounces?)\b|\b\d+/\d+\s*oz\b", re.I)
OUTLIER_RATIO = Decimal("0.4")  # a price under 40% of what other stores charge for the same product is treated as bad data
SUSPECT_STORE_MIN = 5  # comparable offers needed before a store's own pattern of outliers condemns all its offers
SUSPECT_STORE_SHARE = Decimal("0.5")


def _tokens(text):
    return re.findall(r"[a-z0-9]+", html.unescape(str(text or "")).lower())


def product_key(item):
    """Same brand, product and package at different stores share a key; None when the name cannot identify a product."""
    brand = _tokens(item.get("brand"))
    if not brand: return None
    drop = set(brand) | _FORM_WORDS
    name = _MASS.sub(" ", html.unescape(str(item.get("name") or "")))
    words = {t for t in _tokens(name) if t not in drop and len(t) > 1}
    if not words or words <= _GENERIC: return None
    return (str(item.get("category") or ""), str(item.get("weight_grams") or ""), str(item.get("flower_grade") or ""), " ".join(brand), " ".join(sorted(words)))


def _ppg(item):
    return Decimal(item["effective_price"]) / Decimal(item["weight_grams"])


def _median(values):
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid-1] + values[mid]) / 2


def _cheapest_by_store(offers):
    best = {}
    for offer in offers:
        value = _ppg(offer)
        if offer["store_id"] not in best or value < best[offer["store_id"]][0]: best[offer["store_id"]] = (value, offer)
    return best


def flag_outliers(offers):
    """Copies of offers with `price_outlier`: priced far under the same product at other stores, or from a store where that is the norm."""
    by_key = {}
    for offer in offers:
        key = product_key(offer)
        if key: by_key.setdefault(key, []).append(offer)
    flagged = set()
    comparable = {}
    for group in by_key.values():
        cheapest = _cheapest_by_store(group)
        for offer in group:
            others = [value for store, (value, _) in cheapest.items() if store != offer["store_id"]]
            if not others: continue
            comparable.setdefault(offer["store_id"], []).append(offer["id"])
            if _ppg(offer) < OUTLIER_RATIO * _median(others): flagged.add(offer["id"])
    suspect = {store for store, ids in comparable.items() if len(ids) >= SUSPECT_STORE_MIN and Decimal(sum(i in flagged for i in ids)) / len(ids) >= SUSPECT_STORE_SHARE}
    return [{**offer, "price_outlier": offer["id"] in flagged or offer["store_id"] in suspect} for offer in offers]


def group_offers(offers, min_stores=2):
    """One group per product that several stores carry: its cheapest offer and each store's cheapest offer, cheapest group first."""
    by_key = {}
    for offer in offers:
        key = product_key(offer)
        if key: by_key.setdefault(key, []).append(offer)
    groups = []
    for key, group in by_key.items():
        ranked = [offer for _, offer in sorted(_cheapest_by_store(group).values(), key=lambda pair: (pair[0], pair[1]["distance_miles"], pair[1]["id"]))]
        if len(ranked) < min_stores: continue
        low, high = _ppg(ranked[0]), _ppg(ranked[-1])
        best = ranked[0]
        groups.append(dict(id="|".join(key), name=best["name"], brand=best.get("brand"), category=best["category"], weight_grams=best["weight_grams"],
                           flower_grade=best.get("flower_grade"), store_count=len(ranked), best=best, offers=ranked,
                           savings_vs_highest_pct=float(round((high-low)/high*100, 1)) if high else 0.0))
    groups.sort(key=lambda g: (_ppg(g["best"]), g["id"]))
    return groups
