-- Additive orchestration checkpoint; preserve catalog and prior job history.
CREATE TABLE IF NOT EXISTS live_store_work (
    job_id TEXT NOT NULL REFERENCES live_jobs(id),
    store_id TEXT NOT NULL REFERENCES live_stores(id),
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL,
    report_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (job_id,store_id)
);
CREATE INDEX IF NOT EXISTS live_store_work_latest ON live_store_work(store_id,updated_at DESC);
