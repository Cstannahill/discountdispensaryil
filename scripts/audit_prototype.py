"""Read-only audit of the original TerpScout prototype; no network or DB writes.

Run from the project root:
    .venv/Scripts/python.exe scripts/audit_prototype.py
Optional public registry snapshot:
    ... --registry docs/evidence/2026-10-17-illinois-dispensary-map.csv

This inspects the current prototype, not arbitrary JavaScript or future adapters.
"""
import argparse
from collections import Counter
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.scraper_engine import MenuProductSnapshot, reconcile_menu_snapshot


def source_records(html, constant, identity):
    body = html.split(f"const {constant} = [", 1)[1].split("\n    ];", 1)[0]
    records = []
    for block in re.findall(r"\{(.*?)\}", body, re.S):
        fields = dict(re.findall(r'(\w+):\s*"([^"]*)"', block))
        if identity in fields:
            records.append(fields)
    return records


def probe_reconciler():
    product = MenuProductSnapshot(
        "audit-sku", "audit-store", "recreational", "flower", "Flower",
        "Original", "Brand", "Hybrid", 20, 3.5, "3.5g", 40, 35,
    )
    catalog, changes = reconcile_menu_snapshot({}, [product], "audit-store", "recreational")
    assert len(catalog) == 1 and changes[0]["action"] == "ADDED"
    changed = replace(product, name="Corrected", weight_grams=7, weight_label="7g")
    catalog, changes = reconcile_menu_snapshot(catalog, [changed], "audit-store", "recreational")
    stored = next(iter(catalog.values()))
    result = {
        "empty_catalog_accepts_initial_product": True,
        "changed_weight": {
            "incoming_grams": changed.weight_grams,
            "stored_grams": stored["weight_grams"],
            "incoming_price_per_gram": changed.price_per_gram,
            "stored_price_per_gram": stored["price_per_gram"],
            "change_count": len(changes),
            "defect_reproduced": stored["weight_grams"] != changed.weight_grams,
        },
    }
    catalog, changes = reconcile_menu_snapshot(catalog, [], "audit-store", "recreational")
    result["unguarded_empty_snapshot"] = {
        "resulting_status": next(iter(catalog.values()))["status"],
        "actions": [change["action"] for change in changes],
        "requires_complete_snapshot_guard": True,
    }
    return result


def miles(lat, lon, origin_latitude=40.4592, origin_longitude=-90.6718):
    origin_lat, origin_lon = map(math.radians, (origin_latitude, origin_longitude))
    lat, lon = map(math.radians, (lat, lon))
    a = math.sin((lat-origin_lat)/2)**2 + math.cos(lat)*math.cos(origin_lat)*math.sin((lon-origin_lon)/2)**2
    return 3958.8 * 2 * math.asin(math.sqrt(min(1, a)))


def inspect_registry(path, origin_latitude=40.4592, origin_longitude=-90.6718, radius_miles=100):
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    rows = csv.reader(io.StringIO(raw.decode(encoding), newline=""))
    headers = next(rows)
    records = []
    for values in rows:
        if not values:
            continue
        if len(values) != len(headers):
            raise ValueError("Registry row width does not match headers")
        row = {}
        for key, value in zip(headers, values):
            if key in row and row[key] != value:
                raise ValueError(f"Conflicting duplicate column {key}")
            row[key] = value
        lat, lon = float(row["Latitude"]), float(row["Longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid registry coordinates")
        distance = miles(lat, lon, origin_latitude, origin_longitude)
        row["distance_miles"] = round(distance, 3)
        row["within_radius"] = distance <= radius_miles
        records.append(row)
    nearby = sorted(
        [row for row in records if row["within_radius"]],
        key=lambda row: row["distance_miles"],
    )
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "statewide_export_rows": len(records),
        "duplicate_column_names": [key for key, n in Counter(headers).items() if n > 1],
        "origin_latitude": origin_latitude,
        "origin_longitude": origin_longitude,
        "radius_miles": radius_miles,
        "rows_within_radius": len(nearby),
        "nearby_registry_rows": nearby,
        "boundary": "Registry candidates only; operating status, identity, coordinates and menu access require verification. Illinois only; neighboring states not included.",
    }


def audit(registry=None, origin_latitude=40.4592, origin_longitude=-90.6718, radius_miles=100):
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    stores = source_records(html, "INITIAL_DISPENSARIES", "id")
    products = source_records(html, "INITIAL_PRODUCTS", "skuId")
    counts = Counter(product["dispensaryId"] for product in products)
    db = ROOT / "terpscout.db"
    db_before = hashlib.sha256(db.read_bytes()).hexdigest()
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        db_counts = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("dispensaries", "products", "sync_audit_log")
        }
    result = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("index.html", "backend/main.py", "backend/scraper_engine.py", "backend/schema.sql")
        },
        "initial_store_menu_entries": len(stores),
        "initial_product_entries": len(products),
        "initial_product_statuses": dict(Counter(p["status"] for p in products)),
        "store_entries": [dict(store, sample_product_count=counts[store["id"]]) for store in stores],
        "frontend_http_call_markers": len(re.findall(r"\bfetch\s*\(|XMLHttpRequest|\baxios\b", html)),
        "frontend_browser_storage_markers": len(re.findall(r"localStorage|sessionStorage|indexedDB", html)),
        "database_rows": db_counts,
        "reconciler_probes": probe_reconciler(),
        "audit_left_database_bytes_unchanged": db_before == hashlib.sha256(db.read_bytes()).hexdigest(),
    }
    if registry:
        result["public_registry_snapshot"] = inspect_registry(registry, origin_latitude, origin_longitude, radius_miles)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--origin-latitude", type=float, default=40.4592)
    parser.add_argument("--origin-longitude", type=float, default=-90.6718)
    parser.add_argument("--radius-miles", type=float, default=100)
    args = parser.parse_args()
    if not (-90 <= args.origin_latitude <= 90 and -180 <= args.origin_longitude <= 180):
        parser.error("Origin coordinates are outside valid ranges")
    if not math.isfinite(args.radius_miles) or args.radius_miles <= 0:
        parser.error("Radius must be positive and finite")
    print(json.dumps(audit(args.registry, args.origin_latitude, args.origin_longitude, args.radius_miles), indent=2, ensure_ascii=True))
