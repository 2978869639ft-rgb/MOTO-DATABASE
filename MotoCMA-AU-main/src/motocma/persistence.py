from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from motocma.domain import ImportDraft, utc_now
from motocma.listings import ListingSearch, ListingSummary

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class ListingNotFoundError(KeyError):
    pass


class SQLiteListingRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = migration.stem
                if version in applied:
                    continue
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, utc_now().isoformat()),
                )

    def list_latest(self, search: ListingSearch | None = None) -> list[ListingSummary]:
        filters = search or ListingSearch()
        where_clauses: list[str] = []
        parameters: list[object] = []

        def add_text_filter(column: str, value: str | None) -> None:
            if value:
                where_clauses.append(f"LOWER({column}) LIKE ?")
                parameters.append(f"%{value.casefold()}%")

        add_text_filter("o.make", filters.make)
        add_text_filter("o.model", filters.model)
        add_text_filter("o.location", filters.location)
        if filters.listing_status and filters.listing_status != "unknown":
            where_clauses.append("o.listing_status = ?")
            parameters.append(filters.listing_status)
        if filters.min_year is not None:
            where_clauses.append("o.year >= ?")
            parameters.append(filters.min_year)
        if filters.max_year is not None:
            where_clauses.append("o.year <= ?")
            parameters.append(filters.max_year)
        if filters.min_price_cents is not None:
            where_clauses.append("o.asking_price_cents >= ?")
            parameters.append(filters.min_price_cents)
        if filters.max_price_cents is not None:
            where_clauses.append("o.asking_price_cents <= ?")
            parameters.append(filters.max_price_cents)
        if filters.max_odometer_km is not None:
            where_clauses.append("o.odometer_km <= ?")
            parameters.append(filters.max_odometer_km)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
        SELECT l.id, l.source, l.source_listing_id, l.canonical_url,
               o.original_title, o.asking_price_cents, o.location,
               o.odometer_km, o.year, o.make, o.model, o.listing_status
        FROM listings AS l
        JOIN listing_observations AS o ON o.id = (
            SELECT newest.id
            FROM listing_observations AS newest
            WHERE newest.listing_id = l.id
            ORDER BY newest.observed_at DESC, newest.approved_at DESC
            LIMIT 1
        )
        {where_sql}
        ORDER BY l.updated_at DESC
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            ListingSummary(
                id=row["id"],
                source=row["source"],
                source_listing_id=row["source_listing_id"],
                canonical_url=row["canonical_url"],
                title=row["original_title"],
                price_cents=row["asking_price_cents"],
                location=row["location"],
                odometer_km=row["odometer_km"],
                year=row["year"],
                make=row["make"],
                model=row["model"],
                listing_status=row["listing_status"],
            )
            for row in rows
        ]

    def approve_create(self, draft: ImportDraft) -> str:
        listing_id = str(uuid4())
        now = utc_now().isoformat()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO listings (
                    id, source, source_listing_id, canonical_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    listing_id,
                    draft.source,
                    draft.source_listing_id,
                    draft.canonical_url,
                    now,
                    now,
                ),
            )
            raw_import_id = self._insert_raw_import(
                connection, listing_id, draft, now, "create_listing"
            )
            self._insert_observation(connection, listing_id, draft, now, raw_import_id)
        return listing_id

    def approve_update(self, listing_id: str, draft: ImportDraft) -> str:
        now = utc_now().isoformat()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM listings WHERE id = ?", (listing_id,)
            ).fetchone()
            if existing is None:
                raise ListingNotFoundError(listing_id)
            connection.execute(
                """
                UPDATE listings
                SET source_listing_id = COALESCE(?, source_listing_id),
                    canonical_url = COALESCE(?, canonical_url),
                    updated_at = ?
                WHERE id = ?
                """,
                (draft.source_listing_id, draft.canonical_url, now, listing_id),
            )
            raw_import_id = self._insert_raw_import(
                connection, listing_id, draft, now, "update_listing"
            )
            self._insert_observation(connection, listing_id, draft, now, raw_import_id)
        return listing_id

    def raw_import_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM raw_imports").fetchone()
        return int(row["count"])

    def latest_observation(self, listing_id: str) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM listing_observations
                WHERE listing_id = ?
                ORDER BY observed_at DESC, approved_at DESC
                LIMIT 1
                """,
                (listing_id,),
            ).fetchone()
        if row is None:
            raise ListingNotFoundError(listing_id)
        return row

    def observation_count(self, listing_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM listing_observations WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()
        return int(row["count"])

    def _insert_raw_import(
        self,
        connection: sqlite3.Connection,
        listing_id: str,
        draft: ImportDraft,
        approved_at: str,
        approval_action: str,
    ) -> str:
        raw_import_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO raw_imports (
                id, source, collection_method, raw_input, source_url, canonical_url,
                source_listing_id, parser_warnings_json, collected_at, approved_at,
                approval_action, approved_listing_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_import_id,
                draft.source,
                draft.collection_method,
                draft.raw_input,
                draft.source_url,
                draft.canonical_url,
                draft.source_listing_id,
                json.dumps(draft.warnings),
                draft.collected_at.isoformat(),
                approved_at,
                approval_action,
                listing_id,
            ),
        )
        return raw_import_id

    def _insert_observation(
        self,
        connection: sqlite3.Connection,
        listing_id: str,
        draft: ImportDraft,
        approved_at: str,
        raw_import_id: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO listing_observations (
                id, listing_id, raw_import_id, observed_at, approved_at, collection_method,
                raw_input, source_url, original_title, asking_price_cents,
                location, odometer_km, year, make, model, description,
                seller_name, seller_profile_url, image_urls_json, condition_notes,
                registration_status, roadworthy_status, is_lams_approved, is_modified,
                listing_status
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                str(uuid4()),
                listing_id,
                raw_import_id,
                draft.collected_at.isoformat(),
                approved_at,
                draft.collection_method,
                draft.raw_input,
                draft.source_url,
                draft.original_title,
                draft.asking_price_cents,
                draft.location,
                draft.odometer_km,
                draft.year,
                draft.make,
                draft.model,
                draft.description,
                draft.seller_name,
                draft.seller_profile_url,
                json.dumps(draft.image_urls),
                draft.condition_notes,
                draft.registration_status or "unknown",
                draft.roadworthy_status or "unknown",
                _optional_bool_to_int(draft.is_lams_approved),
                _optional_bool_to_int(draft.is_modified),
                draft.listing_status or "unknown",
            ),
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def _optional_bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)
