# MotoCMA-AU

MotoCMA-AU is a personal motorcycle market intelligence platform for researching,
comparing, and valuing used motorcycles in Australia.

The project is **not a Facebook scraper**. Version 1 supports a deliberate,
human-reviewed collection workflow: paste a Marketplace URL or listing text, review
and correct every extracted field, check possible duplicates, and explicitly approve
the permanent database write.

## Current scope

- Facebook Marketplace and Facebook share URL intake
- Copy-and-paste listing text intake
- Best-effort extraction that tolerates missing fields
- Editable review page with field-level warnings
- Duplicate candidate detection with reasons
- Explicit create, update, or cancel decisions
- Immutable observations so price and listing history are preserved
- Source URL, collection method, and collection timestamp provenance

Screenshot OCR and batch import are deliberately postponed.

## Quick start

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
motocma
```

Open <http://127.0.0.1:8000>. Approved records are saved to
`data/motocma.sqlite3`. The `data/` directory is ignored by Git.

Run the quality checks:

```bash
ruff check .
mypy
pytest
```

## Data ownership guarantee

Source adapters and extractors return temporary `ImportDraft` objects. Drafts live
only in process memory and disappear when the application restarts. They cannot
write to the approved-listing database.

The application writes permanent data only through `ApproveImport`, invoked after
the owner submits the review form. A database transaction then creates a listing or
adds a new observation to an explicitly selected existing listing.

## Architecture

MotoCMA-AU is a modular monolith:

- `collection`: source-specific adapters and extraction
- `imports`: temporary draft workflow
- `listings`: approved records, observations, and duplicate matching
- `persistence`: SQLite implementation
- `web`: owner-facing review interface

See [`docs/architecture.md`](docs/architecture.md) for boundaries and trade-offs.

