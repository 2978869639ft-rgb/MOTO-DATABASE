from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from motocma.domain import DuplicateCandidate, ImportDraft


@dataclass(frozen=True, slots=True)
class ListingSummary:
    id: str
    source: str
    source_listing_id: str | None
    canonical_url: str | None
    title: str | None
    price_cents: int | None
    location: str | None
    odometer_km: int | None
    year: int | None
    make: str | None
    model: str | None
    listing_status: str | None


@dataclass(frozen=True, slots=True)
class ListingSearch:
    make: str | None = None
    model: str | None = None
    location: str | None = None
    listing_status: str | None = None
    min_year: int | None = None
    max_year: int | None = None
    min_price_cents: int | None = None
    max_price_cents: int | None = None
    max_odometer_km: int | None = None

    def has_filters(self) -> bool:
        return any(
            value is not None
            for value in (
                self.make,
                self.model,
                self.location,
                self.listing_status,
                self.min_year,
                self.max_year,
                self.min_price_cents,
                self.max_price_cents,
                self.max_odometer_km,
            )
        )


def find_duplicate_candidates(
    draft: ImportDraft, listings: list[ListingSummary]
) -> list[DuplicateCandidate]:
    candidates: list[DuplicateCandidate] = []
    for listing in listings:
        score = 0
        reasons: list[str] = []
        if (
            draft.source_listing_id
            and listing.source_listing_id
            and draft.source == listing.source
            and draft.source_listing_id == listing.source_listing_id
        ):
            score += 100
            reasons.append("same source listing ID")
        if (
            draft.canonical_url
            and listing.canonical_url
            and draft.canonical_url == listing.canonical_url
        ):
            score += 95
            reasons.append("same canonical source URL")

        title_similarity = _similarity(draft.original_title, listing.title)
        if title_similarity >= 0.85:
            score += 30
            reasons.append(f"very similar title ({title_similarity:.0%})")
        elif title_similarity >= 0.65:
            score += 15
            reasons.append(f"similar title ({title_similarity:.0%})")

        if draft.asking_price_cents is not None and draft.asking_price_cents == listing.price_cents:
            score += 10
            reasons.append("same asking price")
        if (
            draft.location
            and listing.location
            and _normalise(draft.location) == _normalise(listing.location)
        ):
            score += 10
            reasons.append("same location")
        if (
            draft.odometer_km is not None
            and listing.odometer_km is not None
            and abs(draft.odometer_km - listing.odometer_km) <= 500
        ):
            score += 10
            reasons.append("similar odometer")
        if draft.model and listing.model and _normalise(draft.model) == _normalise(listing.model):
            score += 15
            reasons.append("same motorcycle model")
        if draft.make and listing.make and _normalise(draft.make) == _normalise(listing.make):
            score += 5
            reasons.append("same make")

        if score >= 40:
            candidates.append(
                DuplicateCandidate(
                    listing_id=listing.id,
                    score=score,
                    reasons=tuple(reasons),
                    title=listing.title,
                    price_cents=listing.price_cents,
                    location=listing.location,
                )
            )
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, _normalise(left), _normalise(right)).ratio()
