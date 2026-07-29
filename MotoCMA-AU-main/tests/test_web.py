from pathlib import Path

from fastapi.testclient import TestClient

from motocma.collection import CollectionService, FacebookMarketplaceAdapter, PastedTextAdapter
from motocma.domain import ImportDraft
from motocma.web import create_app


def make_client(tmp_path: Path) -> TestClient:
    collector = CollectionService(FacebookMarketplaceAdapter(), PastedTextAdapter())
    return TestClient(create_app(tmp_path / "test.sqlite3", collector))


def test_text_import_requires_explicit_save(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/imports",
        data={
            "method": "pasted_text",
            "value": "2022 Yamaha MT-07\n$9,500\n12,000 km\nLocation: Sydney",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    review_url = response.headers["location"]

    home_before = client.get("/")
    assert "No approved listings yet" in home_before.text

    review = client.get(review_url)
    assert "Review every field" in review.text
    assert "2022 Yamaha MT-07" in review.text

    draft_id = review_url.split("/")[2]
    saved = client.post(
        f"/imports/{draft_id}/save",
        data={
            "resolution": "create",
            "original_title": "2022 Yamaha MT-07",
            "asking_price": "9500",
            "odometer_km": "12000",
            "year": "2022",
            "location": "Sydney",
            "make": "Yamaha",
            "model": "MT-07",
            "condition_notes": "Stock bike with service history.",
            "registration_status": "registered",
            "roadworthy_status": "included",
            "is_lams_approved": "yes",
            "is_modified": "no",
            "listing_status": "active",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303

    listing_id = client.app.state.repository.list_latest()[0].id
    observation = client.app.state.repository.latest_observation(listing_id)
    assert observation["condition_notes"] == "Stock bike with service history."
    assert observation["registration_status"] == "registered"
    assert observation["roadworthy_status"] == "included"
    assert observation["is_lams_approved"] == 1
    assert observation["is_modified"] == 0
    assert observation["listing_status"] == "active"

    home_after = client.get("/")
    assert "2022 Yamaha MT-07" in home_after.text
    assert "$9500.00" in home_after.text


def test_cancel_discards_draft_without_saving(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/imports",
        data={"method": "pasted_text", "value": "Honda CB500F $7000"},
        follow_redirects=False,
    )
    draft_id = response.headers["location"].split("/")[2]

    cancelled = client.post(
        f"/imports/{draft_id}/save",
        data={"resolution": "cancel"},
        follow_redirects=False,
    )

    assert cancelled.status_code == 303
    assert "No approved listings yet" in client.get("/").text


def test_duplicate_requires_owner_resolution_and_update_appends_history(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)
    first = client.post(
        "/imports",
        data={"method": "pasted_text", "value": "2021 Honda CB500F\n$7,250\n8,100 km"},
        follow_redirects=False,
    )
    first_id = first.headers["location"].split("/")[2]
    client.post(
        f"/imports/{first_id}/save",
        data={
            "resolution": "create",
            "original_title": "2021 Honda CB500F",
            "asking_price": "7250",
            "odometer_km": "8100",
            "year": "2021",
            "make": "Honda",
            "model": "CB500F",
        },
    )

    second = client.post(
        "/imports",
        data={"method": "pasted_text", "value": "2021 Honda CB500F\n$6,950\n8,300 km"},
        follow_redirects=False,
    )
    second_id = second.headers["location"].split("/")[2]
    review = client.get(second.headers["location"])
    assert "Possible duplicate" in review.text
    listing_id = client.app.state.repository.list_latest()[0].id

    updated = client.post(
        f"/imports/{second_id}/save",
        data={
            "resolution": "update",
            "target_listing_id": listing_id,
            "original_title": "2021 Honda CB500F",
            "asking_price": "6950",
            "odometer_km": "8300",
            "year": "2021",
            "make": "Honda",
            "model": "CB500F",
        },
        follow_redirects=False,
    )

    assert updated.status_code == 303
    assert client.app.state.repository.observation_count(listing_id) == 2
    assert len(client.app.state.repository.list_latest()) == 1


def test_homepage_filters_approved_listings(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    repository = client.app.state.repository
    repository.approve_create(
        ImportDraft(
            source="facebook_marketplace",
            collection_method="pasted_text",
            raw_input="2022 Yamaha MT-07\n$9,500\n12,000 km",
            original_title="2022 Yamaha MT-07",
            asking_price_cents=950_000,
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
            raw_input="2018 BMW R 1200 GS\n$18,000\n45,000 km",
            original_title="2018 BMW R 1200 GS",
            asking_price_cents=1_800_000,
            odometer_km=45_000,
            year=2018,
            make="BMW",
            model="R 1200 GS",
            listing_status="active",
        )
    )

    response = client.get(
        "/",
        params={
            "make": "Yamaha",
            "min_year": "2020",
            "max_price": "10000",
            "max_odometer_km": "20000",
        },
    )

    assert response.status_code == 200
    assert "2022 Yamaha MT-07" in response.text
    assert "2018 BMW R 1200 GS" not in response.text
    assert "Clear filters" in response.text
