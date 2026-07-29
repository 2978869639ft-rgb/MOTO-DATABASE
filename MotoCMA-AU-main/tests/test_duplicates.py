from motocma.domain import ImportDraft
from motocma.listings import ListingSummary, find_duplicate_candidates


def test_exact_source_id_is_a_strong_duplicate() -> None:
    draft = ImportDraft(
        source="facebook_marketplace",
        collection_method="facebook_url",
        raw_input="url",
        source_listing_id="123",
        original_title="2020 Kawasaki Ninja 400",
    )
    existing = ListingSummary(
        id="listing-1",
        source="facebook_marketplace",
        source_listing_id="123",
        canonical_url=None,
        title="Kawasaki Ninja 400 MY20",
        price_cents=650_000,
        location="Sydney",
        odometer_km=10_000,
        year=2020,
        make="Kawasaki",
        model="Ninja 400",
        listing_status="active",
    )

    candidates = find_duplicate_candidates(draft, [existing])

    assert candidates[0].listing_id == "listing-1"
    assert "same source listing ID" in candidates[0].reasons


def test_unrelated_listing_is_not_a_duplicate() -> None:
    draft = ImportDraft(
        source="facebook_marketplace",
        collection_method="pasted_text",
        raw_input="text",
        original_title="Honda Grom",
        asking_price_cents=4_000_00,
        location="Brisbane",
    )
    existing = ListingSummary(
        id="listing-1",
        source="facebook_marketplace",
        source_listing_id="999",
        canonical_url=None,
        title="BMW R 1250 GS Adventure",
        price_cents=25_000_00,
        location="Perth",
        odometer_km=5_000,
        year=2022,
        make="BMW",
        model="R 1250 GS",
        listing_status="active",
    )

    assert find_duplicate_candidates(draft, [existing]) == []
