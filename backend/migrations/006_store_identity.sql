-- Additive: a store's current identity as evidence shows it (rebrands, closures). The registry row is never edited.
CREATE TABLE IF NOT EXISTS live_store_identity (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES live_stores(id),
    kind TEXT NOT NULL,
    name TEXT,
    source_url TEXT,
    quote TEXT,
    evidence_id TEXT,
    source TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(store_id,kind,name,source_url)
);
CREATE INDEX IF NOT EXISTS live_store_identity_store ON live_store_identity(store_id,kind);
