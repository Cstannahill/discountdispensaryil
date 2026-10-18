CREATE TABLE IF NOT EXISTS live_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS live_sources(
 id TEXT PRIMARY KEY, url TEXT, evidence_id TEXT, published_at TEXT,
 last_success_at TEXT, last_attempt_at TEXT, status TEXT, row_count INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS live_source_observations(
 id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, source_key TEXT NOT NULL,
 observed_at TEXT NOT NULL, evidence_id TEXT NOT NULL, raw_json TEXT NOT NULL,
 FOREIGN KEY(source_id) REFERENCES live_sources(id));
CREATE TABLE IF NOT EXISTS live_stores(
 id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 address TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL,
 latitude REAL, longitude REAL, serves_medical INTEGER,
 identity_status TEXT NOT NULL DEFAULT 'registry_candidate',
 operating_status TEXT NOT NULL DEFAULT 'unverified', source_present INTEGER NOT NULL DEFAULT 1,
 source_evidence TEXT NOT NULL, observed_at TEXT NOT NULL, raw_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS live_regions(
 id TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL,
 label TEXT NOT NULL, radius_miles INTEGER NOT NULL, precision TEXT, source_url TEXT,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS live_resolutions(
 id INTEGER PRIMARY KEY, store_id TEXT NOT NULL, status TEXT NOT NULL,
 message TEXT, evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(store_id) REFERENCES live_stores(id));
CREATE TABLE IF NOT EXISTS live_endpoints(
 id TEXT PRIMARY KEY, store_id TEXT NOT NULL, url TEXT NOT NULL, provider TEXT NOT NULL,
 provider_store_id TEXT, license_type TEXT NOT NULL CHECK(license_type IN ('recreational','medicinal')),
 status TEXT NOT NULL DEFAULT 'pending', last_attempt_at TEXT, last_success_at TEXT, last_error TEXT,
 snapshot_id TEXT, pending_fingerprint TEXT, pending_since TEXT, resolution_json TEXT NOT NULL,
 UNIQUE(store_id,url,license_type), FOREIGN KEY(store_id) REFERENCES live_stores(id));
CREATE TABLE IF NOT EXISTS live_snapshots(
 id TEXT PRIMARY KEY, endpoint_id TEXT NOT NULL, observed_at TEXT NOT NULL,
 status TEXT NOT NULL, fingerprint TEXT NOT NULL, source_count INTEGER NOT NULL,
 expected_count INTEGER, manifest_json TEXT NOT NULL, errors_json TEXT NOT NULL,
 FOREIGN KEY(endpoint_id) REFERENCES live_endpoints(id));
CREATE TABLE IF NOT EXISTS live_offers(
 id TEXT PRIMARY KEY, endpoint_id TEXT NOT NULL, source_id TEXT NOT NULL, variant_id TEXT NOT NULL,
 payload_json TEXT NOT NULL, status TEXT NOT NULL, last_diff_action TEXT NOT NULL,
 first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, snapshot_id TEXT NOT NULL,
 UNIQUE(endpoint_id,source_id,variant_id), FOREIGN KEY(endpoint_id) REFERENCES live_endpoints(id),
 FOREIGN KEY(snapshot_id) REFERENCES live_snapshots(id));
CREATE TABLE IF NOT EXISTS live_diffs(
 id INTEGER PRIMARY KEY, endpoint_id TEXT NOT NULL, offer_id TEXT NOT NULL,
 action TEXT NOT NULL, created_at TEXT NOT NULL, snapshot_id TEXT NOT NULL,
 old_json TEXT, new_json TEXT, details_json TEXT NOT NULL,
 FOREIGN KEY(endpoint_id) REFERENCES live_endpoints(id));
CREATE TABLE IF NOT EXISTS live_jobs(
 id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
 started_at TEXT, finished_at TEXT, payload_json TEXT NOT NULL, results_json TEXT NOT NULL, error TEXT);
CREATE TABLE IF NOT EXISTS live_suggestions(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, city TEXT, url TEXT,
 status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS live_offers_endpoint ON live_offers(endpoint_id,status);
CREATE INDEX IF NOT EXISTS live_diffs_endpoint ON live_diffs(endpoint_id,created_at);
CREATE INDEX IF NOT EXISTS live_observations_source ON live_source_observations(source_id,observed_at);
PRAGMA user_version=1;
