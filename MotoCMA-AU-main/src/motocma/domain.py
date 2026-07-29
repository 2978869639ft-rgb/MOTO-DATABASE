from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Self
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ImportDraft:
    source: str
    collection_method: str
    raw_input: str
    source_url: str | None = None
    canonical_url: str | None = None
    source_listing_id: str | None = None
    original_title: str | None = None
    asking_price_cents: int | None = None
    location: str | None = None
    odometer_km: int | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    description: str | None = None
    seller_name: str | None = None
    seller_profile_url: str | None = None
    condition_notes: str | None = None
    registration_status: str | None = None
    roadworthy_status: str | None = None
    is_lams_approved: bool | None = None
    is_modified: bool | None = None
    listing_status: str | None = None
    image_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    collected_at: datetime = field(default_factory=utc_now)
    id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def from_form(cls, existing: Self, values: dict[str, str]) -> Self:
        def optional(name: str) -> str | None:
            value = values.get(name, "").strip()
            return value or None

        image_urls_value = values.get("image_urls")
        image_urls = (
            [line.strip() for line in image_urls_value.splitlines() if line.strip()]
            if image_urls_value is not None
            else existing.image_urls
        )
        return cls(
            id=existing.id,
            source=existing.source,
            collection_method=existing.collection_method,
            raw_input=existing.raw_input,
            collected_at=existing.collected_at,
            source_url=optional("source_url"),
            canonical_url=existing.canonical_url,
            source_listing_id=optional("source_listing_id"),
            original_title=optional("original_title"),
            asking_price_cents=parse_money_to_cents(optional("asking_price")),
            location=optional("location"),
            odometer_km=parse_int(optional("odometer_km")),
            year=parse_int(optional("year")),
            make=optional("make"),
            model=optional("model"),
            description=optional("description"),
            seller_name=optional("seller_name"),
            seller_profile_url=optional("seller_profile_url"),
            condition_notes=optional("condition_notes"),
            registration_status=optional("registration_status"),
            roadworthy_status=optional("roadworthy_status"),
            is_lams_approved=parse_optional_bool(optional("is_lams_approved")),
            is_modified=parse_optional_bool(optional("is_modified")),
            listing_status=optional("listing_status"),
            image_urls=image_urls,
            warnings=existing.warnings,
        )


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    listing_id: str
    score: int
    reasons: tuple[str, ...]
    title: str | None
    price_cents: int | None
    location: str | None


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else None


def parse_money_to_cents(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.upper().replace("AUD", "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(Decimal(cleaned) * 100)
    except (InvalidOperation, ValueError):
        return None


def parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalised = value.strip().casefold()
    if normalised in {"1", "true", "yes", "y"}:
        return True
    if normalised in {"0", "false", "no", "n"}:
        return False
    return None


def format_money(cents: int | None) -> str:
    return "" if cents is None else f"{Decimal(cents) / 100:.2f}"


REGISTRATION_STATUSES = {"unknown", "registered", "unregistered"}
ROADWORTHY_STATUSES = {"unknown", "included", "not_included"}
LISTING_STATUSES = {"unknown", "active", "removed", "sold", "expired"}


def validate_for_approval(draft: ImportDraft) -> list[str]:
    errors: list[str] = []
    if not draft.original_title:
        errors.append("Original title is required before saving.")
    if draft.asking_price_cents is not None and draft.asking_price_cents < 0:
        errors.append("Asking price cannot be negative.")
    current_year = utc_now().year
    if draft.year is not None and not 1885 <= draft.year <= current_year + 1:
        errors.append(f"Year must be between 1885 and {current_year + 1}.")
    if draft.odometer_km is not None and draft.odometer_km < 0:
        errors.append("Odometer cannot be negative.")
    if draft.registration_status and draft.registration_status not in REGISTRATION_STATUSES:
        errors.append("Registration status is not recognised.")
    if draft.roadworthy_status and draft.roadworthy_status not in ROADWORTHY_STATUSES:
        errors.append("Roadworthy status is not recognised.")
    if draft.listing_status and draft.listing_status not in LISTING_STATUSES:
        errors.append("Listing status is not recognised.")
    return errors
