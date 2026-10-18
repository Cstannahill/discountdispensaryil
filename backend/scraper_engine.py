"""
TerpScout Menu Ingestion, Normalization & Diff Engine
Polls Recreational and Medicinal dispensary menus 2-4x/day, normalizes weights to grams,
computes $/g across Concentrate, Flower, and Vapes, and reconciles ADD / UPDATE / REMOVE diffs.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import math
import re
from typing import List, Dict, Optional, Tuple

EARTH_RADIUS_MILES = 3958.8
ALLOWED_RADII_MILES = (1, 5, 25, 50, 100)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in miles between two coordinates."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return round(EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(a)), 2)


def parse_weight_to_grams(raw_weight: str) -> float:
    """Normalize standard cannabis package weights ('3.5g', '1/8 oz', '500mg', '14g') into grams."""
    s = raw_weight.strip().lower()
    fraction_map = {
        "1/8 oz": 3.5, "eighth": 3.5,
        "1/4 oz": 7.0, "quarter": 7.0,
        "1/2 oz": 14.0, "half oz": 14.0,
        "1 oz": 28.0, "ounce": 28.0,
    }
    for k, v in fraction_map.items():
        if k in s:
            return v
    mg_match = re.search(r"(\d+(?:\.\d+)?)\s*mg", s)
    if mg_match:
        return round(float(mg_match.group(1)) / 1000.0, 3)
    g_match = re.search(r"(\d+(?:\.\d+)?)\s*g", s)
    if g_match:
        return float(g_match.group(1))
    oz_match = re.search(r"(\d+(?:\.\d+)?)\s*oz", s)
    if oz_match:
        return round(float(oz_match.group(1)) * 28.0, 2)
    raise ValueError(f"Unrecognized weight format: {raw_weight}")


@dataclass
class MenuProductSnapshot:
    sku_id: str
    dispensary_id: str
    license_type: str  # 'recreational' | 'medicinal'
    category: str      # 'concentrate' | 'flower' | 'vapes'
    subcategory: str
    name: str
    brand: str
    strain_type: str
    thc_pct: float
    weight_grams: float
    weight_label: str
    regular_price: float
    effective_price: float
    promo_badge: str = ""

    @property
    def price_per_gram(self) -> float:
        return round(self.effective_price / self.weight_grams, 2)


def reconcile_menu_snapshot(
    previous_catalog: Dict[str, dict],
    incoming_snapshot: List[MenuProductSnapshot],
    dispensary_id: str,
    license_type: str,
) -> Tuple[Dict[str, dict], List[dict]]:
    """
    Compare incoming menu scrape against stored catalog for (dispensary_id, license_type).
    Returns updated catalog dictionary and list of diff audit records (ADDED, UPDATED, REMOVED).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    diffs: List[dict] = []
    incoming_keys = set()

    for item in incoming_snapshot:
        key = f"{dispensary_id}::{license_type}::{item.sku_id}"
        incoming_keys.add(key)
        existing = previous_catalog.get(key)

        if existing is None or existing.get("status") == "removed":
            record = asdict(item)
            record["price_per_gram"] = item.price_per_gram
            record["status"] = "active"
            record["last_diff_action"] = "added"
            record["previous_price"] = None
            record["updated_at"] = now_iso
            previous_catalog[key] = record
            diffs.append({
                "action": "ADDED",
                "sku_id": item.sku_id,
                "dispensary_id": dispensary_id,
                "license_type": license_type,
                "category": item.category,
                "name": item.name,
                "weight_label": item.weight_label,
                "new_price": item.effective_price,
                "new_ppg": item.price_per_gram,
                "timestamp": now_iso,
            })
        else:
            old_price = existing["effective_price"]
            old_thc = existing["thc_pct"]
            if abs(old_price - item.effective_price) > 0.009 or abs(old_thc - item.thc_pct) > 0.05:
                old_ppg = existing["price_per_gram"]
                existing["previous_price"] = old_price
                existing["effective_price"] = item.effective_price
                existing["regular_price"] = item.regular_price
                existing["thc_pct"] = item.thc_pct
                existing["promo_badge"] = item.promo_badge
                existing["price_per_gram"] = item.price_per_gram
                existing["last_diff_action"] = "updated"
                existing["updated_at"] = now_iso
                diffs.append({
                    "action": "UPDATED",
                    "sku_id": item.sku_id,
                    "dispensary_id": dispensary_id,
                    "license_type": license_type,
                    "category": item.category,
                    "name": item.name,
                    "weight_label": item.weight_label,
                    "old_price": old_price,
                    "new_price": item.effective_price,
                    "old_ppg": old_ppg,
                    "new_ppg": item.price_per_gram,
                    "timestamp": now_iso,
                })
            else:
                existing["last_diff_action"] = "verified"

    # Detect REMOVED products no longer on the dispensary's live menu
    prefix = f"{dispensary_id}::{license_type}::"
    for key, existing in list(previous_catalog.items()):
        if key.startswith(prefix) and existing.get("status") == "active" and key not in incoming_keys:
            existing["status"] = "removed"
            existing["last_diff_action"] = "removed"
            existing["updated_at"] = now_iso
            diffs.append({
                "action": "REMOVED",
                "sku_id": existing["sku_id"],
                "dispensary_id": dispensary_id,
                "license_type": license_type,
                "category": existing["category"],
                "name": existing["name"],
                "weight_label": existing["weight_label"],
                "old_price": existing["effective_price"],
                "old_ppg": existing["price_per_gram"],
                "timestamp": now_iso,
            })

    return previous_catalog, diffs
