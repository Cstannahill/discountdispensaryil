-- Additive: store verifier verdicts (leads for an operator; never registry or identity changes).
CREATE TABLE IF NOT EXISTS live_store_verifications (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES live_stores(id),
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    verdict TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    claims_json TEXT NOT NULL DEFAULT '[]',
    dropped_json TEXT NOT NULL DEFAULT '[]',
    transcript_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    model TEXT,
    steps INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    usd REAL NOT NULL DEFAULT 0,
    seconds REAL,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS live_store_verifications_store ON live_store_verifications(store_id,id);
