from pathlib import Path

from motocma.domain import ImportDraft
from motocma.imports import InMemoryDraftStore
from motocma.listings import ListingSearch
from motocma.persistence import SQLiteListingRepository


def test_draft_does_not_modify_approved_database(tmp_path: Path) -> None:
    database_path = tmp_path / "motocma.sqlite3"
    repository = SQLiteListingRepository(database_path)
    repository.initialise()
    store = InMemoryDraftStore()

    draft = store.add(
        ImportDraft(
            source="facebook_marketplace",
            collection_method="pasted_text",
            raw_input="Yamaha MT-07 $9000",
            original_title="Yamaha MT-07",
        )
    )

    assert store.get(draft.id).original_title == "Yamaha MT-07"
    assert repository.list_latest() == []
    assert repository.raw_import_count() == 0


def test_approved_update_appends_observation(tmp_path: Path) -> None:
    repository = SQLiteListingRepository(tmp_path / "motocma.sqlite3")
    repository.initialise()
    first = ImportDraft(
        source="facebook_marketplace",
        collection_method="facebook_url",
        raw_input="https://facebook.com/marketplace/item/1",
        canonical_url="https://facebook.com/marketplace/item/1",
        source_listing_id="1",
        original_title="2022 Yamaha MT-07",
        asking_price_cents=950_000,
    )
    listing_id = repository.approve_create(first)

    second = ImportDraft(
        source="facebook_marketplace",
        collection_method="facebook_url",
        raw_input="https://facebook.com/marketplace/item/1",
        canonical_url="https://facebook.com/marketplace/item/1",
        source_listing_id="1",
        original_title="2022 Yamaha MT-07",
        asking_price_cents=900_000,
    )
    repository.approve_update(listing_id, second)

    assert len(repository.list_latest()) == 1
    assert repository.list_latest()[0].price_cents == 900_000
    assert repository.observation_count(listing_id) == 2
    assert repository.raw_import_count() == 2


def test_approved_create_records_raw_import_and_cma_fields(tmp_path: Path) -> None:
    repository = SQLiteListingRepository(tmp_path / "motocma.sqlite3")
    repository.initialise()
    draft = ImportDraft(
        source="facebook_marketplace",
        collection_method="pasted_text",
        raw_input="2020 Kawasaki Ninja 400 $6500",
        original_title="2020 Kawasaki Ninja 400",
        condition_notes="Minor scratches on fairing.",
        registration_status="registered",
        roadworthy_status="included",
        is_lams_approved=True,
        is_modified=False,
        listing_status="active",
    )

    listing_id = repository.approve_create(draft)

    observation = repository.latest_observation(listing_id)
    assert repository.raw_import_count() == 1
    assert observation["raw_import_id"] is not None
    assert observation["condition_notes"] == "Minor scratches on fairing."
    assert observation["registration_status"] == "registered"
    assert observation["roadworthy_status"] == "included"
    assert observation["is_lams_approved"] == 1
    assert observation["is_modified"] == 0
    assert observation["listing_status"] == "active"


def test_list_latest_filters_by_market_fields(tmp_path: Path) -> None:
    repository = SQLiteListingRepository(tmp_path / "motocma.sqlite3")
    repository.initialise()
    repository.approve_create(
        ImportDraft(
            source="facebook_marketplace",
            collection_method="pasted_text",
            raw_input="2022 Yamaha MT-07 $9500",
            original_title="2022 Yamaha MT-07",
            asking_price_cents=950_000,
            location="Sydney",
            odometer_km=12_000,
            year=2022,
            make="Yamaha",
            model="MT-07",
            listing_status="active",
        )
    )
    repository.approve_create(
        ImportDraft(
            source="facebook_marketplace",
            collection_method="pasted_text",
            raw_input="2018 BMW R 1200 GS $18000",
            original_title="2018 BMW R 1200 GS",
            asking_price_cents=1_800_000,
            location="Melbourne",
            odometer_km=45_000,
            year=2018,
            make="BMW",
            model="R 1200 GS",
            listing_status="sold",
        )
    )

    results = repository.list_latest(
        ListingSearch(
            make="yam",
            min_year=2020,
            max_price_cents=1_000_000,
            max_odometer_km=20_000,
            listing_status="active",
        )
    )

    assert len(results) == 1
    assert results[0].title == "2022 Yamaha MT-07"
