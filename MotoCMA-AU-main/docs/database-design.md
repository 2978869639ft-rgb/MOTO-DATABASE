# Database design

MotoCMA-AU's database should preserve market evidence first and support valuation
second. The collection workflow already protects this principle: source adapters
create temporary drafts, and only an explicit owner approval writes permanent data.

This document describes the target database direction and the recommended v1
schema boundary. It is intentionally conservative. The goal is to build a reliable
market database now without locking the project into a premature valuation model.

## Goals

- Preserve raw source evidence for every approved record.
- Track listing history as immutable observations instead of overwriting values.
- Separate source identity from motorcycle identity.
- Support duplicate detection and owner-controlled merge decisions.
- Leave room for model standardisation, comparable market analysis, and valuation.
- Keep SQLite viable for local use while avoiding choices that would block a later
  PostgreSQL migration.

## Non-goals for v1

- Automated scraping at scale.
- Seller identity resolution across platforms.
- Full motorcycle catalogue coverage.
- Automated sold-price inference.
- Automated valuation or fair-value recommendations.
- Multi-user permissions and remote hosting.

## Current foundation

The existing application already has the most important v1 shape:

- `ImportDraft` is temporary and process-local.
- `listings` stores a stable approved listing identity.
- `listing_observations` stores historical snapshots of an approved listing.
- `SQLiteListingRepository` is the only permanent write path.

The next database iteration should extend this shape rather than replace it.

## Data layers

### 1. Raw import provenance

This layer records what the owner approved from the collection workflow. It should
preserve the original submitted text, URL, collection method, parser warnings, and
approval decision.

Recommended table:

```sql
CREATE TABLE raw_imports (
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
```

Why this matters: a future parser or standardisation rule can be improved without
losing the original evidence that supported the approved record.

### 2. Source listings

This layer represents the external listing identity as observed on a marketplace.
For Facebook Marketplace, this is usually the canonical URL and source listing ID.
In the future, Gumtree, Bikesales, dealer websites, or manual entries can use the
same pattern.

Recommended table:

```sql
CREATE TABLE source_listings (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_listing_id TEXT,
    canonical_url TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        status IN ('unknown', 'active', 'removed', 'sold', 'expired')
    ),
    UNIQUE (source, source_listing_id),
    UNIQUE (source, canonical_url)
);
```

`listings` can reference `source_listings.id` once this table exists. Until then,
the current `source`, `source_listing_id`, and `canonical_url` columns in
`listings` are acceptable.

### 3. Approved listings

`listings` should remain the stable internal identity for a marketplace listing.
It should not store volatile fields like price, odometer, title, or description.
Those belong in observations.

Recommended v1 shape:

```sql
CREATE TABLE listings (
    id TEXT PRIMARY KEY,
    source_listing_ref TEXT REFERENCES source_listings(id),
    source TEXT NOT NULL,
    source_listing_id TEXT,
    canonical_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    owner_notes TEXT,
    archived_at TEXT
);
```

The existing table already covers the required core fields. `owner_notes` and
`archived_at` can wait until the UI needs them.

### 4. Listing observations

Observations are immutable snapshots of what was known at a point in time. Every
approved create or update should append a new observation.

Recommended v1 additions to the current table:

```sql
ALTER TABLE listing_observations ADD COLUMN raw_import_id TEXT REFERENCES raw_imports(id);
ALTER TABLE listing_observations ADD COLUMN condition_notes TEXT;
ALTER TABLE listing_observations ADD COLUMN registration_status TEXT;
ALTER TABLE listing_observations ADD COLUMN roadworthy_status TEXT;
ALTER TABLE listing_observations ADD COLUMN is_lams_approved INTEGER;
ALTER TABLE listing_observations ADD COLUMN is_modified INTEGER;
ALTER TABLE listing_observations ADD COLUMN listing_status TEXT DEFAULT 'unknown';
```

Suggested status values:

- `registration_status`: `unknown`, `registered`, `unregistered`
- `roadworthy_status`: `unknown`, `included`, `not_included`
- `listing_status`: `unknown`, `active`, `removed`, `sold`, `expired`

SQLite does not have a native boolean type, so booleans should be stored as
nullable integers: `1`, `0`, or `NULL` for unknown.

### 5. Motorcycle standardisation

This should be introduced carefully. Marketplace titles are messy, and the system
should allow uncertain matches instead of pretending every listing is cleanly
classified.

Recommended tables:

```sql
CREATE TABLE motorcycle_makes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE motorcycle_models (
    id TEXT PRIMARY KEY,
    make_id TEXT NOT NULL REFERENCES motorcycle_makes(id),
    name TEXT NOT NULL,
    model_family TEXT,
    category TEXT,
    UNIQUE (make_id, name)
);

CREATE TABLE motorcycle_variants (
    id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL REFERENCES motorcycle_models(id),
    name TEXT NOT NULL,
    engine_cc INTEGER,
    learner_approved INTEGER,
    abs_available INTEGER,
    UNIQUE (model_id, name)
);

CREATE TABLE listing_motorcycle_matches (
    id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL REFERENCES listings(id),
    make_id TEXT REFERENCES motorcycle_makes(id),
    model_id TEXT REFERENCES motorcycle_models(id),
    variant_id TEXT REFERENCES motorcycle_variants(id),
    confidence REAL NOT NULL DEFAULT 0,
    match_method TEXT NOT NULL CHECK (
        match_method IN ('manual', 'rule', 'parser', 'imported')
    ),
    owner_confirmed_at TEXT,
    created_at TEXT NOT NULL
);
```

For v1, the existing free-text `make` and `model` fields in
`listing_observations` are enough. The standardisation tables should be added when
search, filtering, or comparable grouping needs stronger identity.

### 6. Duplicate decisions

Duplicate detection is currently computed on demand and not persisted. That is
fine for v1. Persisting decisions becomes useful when the owner repeatedly sees
the same candidates or when imports are reviewed in batches.

Future table:

```sql
CREATE TABLE duplicate_decisions (
    id TEXT PRIMARY KEY,
    draft_fingerprint TEXT NOT NULL,
    candidate_listing_id TEXT NOT NULL REFERENCES listings(id),
    decision TEXT NOT NULL CHECK (
        decision IN ('same_listing', 'separate_listing', 'ignored')
    ),
    reasons_json TEXT NOT NULL DEFAULT '[]',
    decided_at TEXT NOT NULL
);
```

## Recommended v1 implementation order

1. Add `docs/database-design.md` as the shared design reference.
2. Add a simple migration mechanism instead of embedding all schema in one string.
3. Introduce `raw_imports` and connect observations to approved imports.
4. Add observation fields that materially help motorcycle CMA:
   `condition_notes`, `registration_status`, `roadworthy_status`,
   `is_lams_approved`, `is_modified`, and `listing_status`.
5. Update the review form so the owner can approve those fields.
6. Add read APIs for filtering approved listings by make, model, year, price,
   odometer, location, and status.
7. Add motorcycle standardisation tables only after enough real listings show the
   naming patterns that need normalisation.

## Implemented v1 query surface

The current SQLite repository exposes `list_latest(search)` for querying the
latest approved observation for each listing. The supported filters are:

- make
- model
- location
- listing status
- minimum and maximum year
- minimum and maximum asking price
- maximum odometer

The owner-facing homepage uses the same query surface, so database filtering is
shared by the UI and future application services.

## Migration strategy

Use numbered SQL migrations stored in a repository folder such as:

```text
src/motocma/migrations/
  0001_initial.sql
  0002_raw_imports.sql
  0003_observation_cma_fields.sql
```

Track applied migrations with:

```sql
CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

This keeps local SQLite databases upgradeable while preserving a clear path to
PostgreSQL later.

## Data quality rules

- Never delete raw approved evidence.
- Never overwrite historical observation values.
- Prefer nullable fields over fake certainty.
- Store parser warnings and confidence separately from owner-confirmed values.
- Use owner confirmation as the strongest source of truth.
- Keep source-specific fields at the source layer and motorcycle facts at the
  motorcycle identity layer.

## Open questions

- Should removed or sold listings be manually marked first, or inferred later from
  repeated failed observations?
- Should asking price and sold price be represented as separate price event types?
- How much seller data should be retained, given privacy and personal-use limits?
- Should images be stored only as URLs in v1, or downloaded into local storage?
- Should location be normalised to suburb/state/postcode before valuation begins?
