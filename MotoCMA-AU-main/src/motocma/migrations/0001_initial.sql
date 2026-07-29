CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_listing_id TEXT,
    canonical_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_source_identity
    ON listings(source, source_listing_id);
CREATE INDEX IF NOT EXISTS idx_listings_canonical_url
    ON listings(canonical_url);

CREATE TABLE IF NOT EXISTS listing_observations (
    id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    collection_method TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    source_url TEXT,
    original_title TEXT,
    asking_price_cents INTEGER,
    currency TEXT NOT NULL DEFAULT 'AUD',
    location TEXT,
    odometer_km INTEGER,
    year INTEGER,
    make TEXT,
    model TEXT,
    description TEXT,
    seller_name TEXT,
    seller_profile_url TEXT,
    image_urls_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_observations_listing_time
    ON listing_observations(listing_id, observed_at DESC);
