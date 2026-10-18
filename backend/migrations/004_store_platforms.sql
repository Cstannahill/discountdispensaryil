-- Additive: menu platforms observed on each store's own pages (census input; never an endpoint or identity proof).
CREATE TABLE IF NOT EXISTS live_store_platforms (
    store_id TEXT NOT NULL REFERENCES live_stores(id),
    platform TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'resolver',
    evidence_id TEXT,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (store_id, platform, url)
);
