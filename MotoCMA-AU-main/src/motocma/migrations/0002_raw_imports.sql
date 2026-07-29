CREATE TABLE IF NOT EXISTS raw_imports (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    collection_method TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    source_url TEXT,
    canonical_url TEXT,
    source_listing_id TEXT,
    parser_warnings_json TEXT NOT NULL DEFAULT '[]',
    collected_at TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    approval_action TEXT NOT NULL CHECK (
        approval_action IN ('create_listing', 'update_listing')
    ),
    approved_listing_id TEXT NOT NULL REFERENCES listings(id)
);

ALTER TABLE listing_observations
    ADD COLUMN raw_import_id TEXT REFERENCES raw_imports(id);

CREATE INDEX IF NOT EXISTS idx_raw_imports_approved_listing
    ON raw_imports(approved_listing_id);
