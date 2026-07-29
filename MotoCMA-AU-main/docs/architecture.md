# Architecture

## Decision: modular monolith

MotoCMA-AU uses one deployable Python application with explicit module boundaries.
This keeps a personal project easy to run and debug while allowing collection,
standardisation, valuation, and analytics to evolve independently.

Microservices are intentionally avoided. They would add deployment, authentication,
networking, and consistency concerns without providing a current benefit.

## Collection flow

```text
owner input
  -> source adapter
  -> temporary ImportDraft
  -> parsing and warnings
  -> editable review
  -> duplicate candidates
  -> explicit owner decision
  -> transactional Listing + Observation write
```

Adapters have no database dependency. Extraction failure produces warnings and a
partially populated draft rather than aborting the workflow.

## Record model

`Listing` represents a stable marketplace identity. `ListingObservation` records
what was observed at a particular time. Updating an existing listing appends an
observation instead of erasing historical values.

Raw submitted input and approved field values are stored together with collection
metadata. Future standardisation can therefore be corrected without losing source
evidence.

## Security boundary

The Facebook adapter accepts HTTPS URLs only and limits requests and redirects to
Facebook-owned hostnames. This reduces server-side request forgery risk. It does not
attempt to bypass authentication or access controls.

The application is intended to bind to localhost. Authentication must be added
before exposing it to another machine or the public internet.

## Deferred decisions

- Downloading and retaining source images
- Screenshot OCR
- Batch review
- Motorcycle catalogue and model standardisation
- PostgreSQL migration
- User authentication and remote hosting

