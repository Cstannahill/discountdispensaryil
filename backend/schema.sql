-- TerpScout: Dispensary Menu Diff & $/g Deal Aggregator Schema
CREATE TABLE IF NOT EXISTS dispensaries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    license_type TEXT NOT NULL CHECK (license_type IN ('recreational', 'medicinal')),
    license_number TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    phone TEXT,
    hours TEXT,
    menu_url TEXT NOT NULL,
    platform_adapter TEXT NOT NULL DEFAULT 'dutchie_graphql',
    last_synced_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    sku_id TEXT NOT NULL,
    dispensary_id TEXT NOT NULL,
    license_type TEXT NOT NULL CHECK (license_type IN ('recreational', 'medicinal')),
    category TEXT NOT NULL CHECK (category IN ('concentrate', 'flower', 'vapes')),
    subcategory TEXT NOT NULL,
    name TEXT NOT NULL,
    brand TEXT NOT NULL,
    strain_type TEXT NOT NULL,
    thc_pct REAL NOT NULL,
    weight_grams REAL NOT NULL CHECK (weight_grams > 0),
     weight_label TEXT NOT NULL,
    regular_price REAL NOT NULL,
    effective_price REAL NOT NULL,
    price_per_gram REAL GENERATED ALWAYS AS (ROUND(effective_price / weight_grams, 2)) STORED,
    promo_badge TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
    last_diff_action TEXT NOT NULL DEFAULT 'verified' CHECK (last_diff_action IN ('added', 'updated', 'removed', 'verified')),
    previous_price REAL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dispensary_id, license_type, sku_id),
    FOREIGN KEY (dispensary_id) REFERENCES dispensaries(id)
);

CREATE TABLE IF NOT EXISTS sync_audit_log (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    schedule_slot TEXT NOT NULL,
    dispensaries_polled INTEGER NOT NULL,
    added_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    removed_count INTEGER NOT NULL DEFAULT 0,
    diff_details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_deals 
ON products(license_type, category, status, price_per_gram ASC);
