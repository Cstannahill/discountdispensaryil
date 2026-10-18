-- Additive: per-attempt outcomes keyed by pipeline version, and website leads kept apart from menu endpoints.
CREATE TABLE IF NOT EXISTS live_attempts (
    id INTEGER PRIMARY KEY,
    job_id TEXT,
    store_id TEXT NOT NULL REFERENCES live_stores(id),
    endpoint_id TEXT,
    pipeline_version TEXT NOT NULL,
    stage TEXT NOT NULL,
    tier TEXT NOT NULL,
    provider TEXT,
    license_type TEXT,
    status TEXT NOT NULL,
    code TEXT,
    grade TEXT,
    items INTEGER,
    seconds REAL,
    detail TEXT,
    evidence_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS live_attempts_store ON live_attempts(store_id,id);
CREATE INDEX IF NOT EXISTS live_attempts_version ON live_attempts(pipeline_version,stage);
CREATE TABLE IF NOT EXISTS live_leads (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES live_stores(id),
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(store_id,url)
);
