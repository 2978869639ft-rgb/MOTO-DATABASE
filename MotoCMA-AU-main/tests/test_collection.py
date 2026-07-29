from __future__ import annotations

import httpx
import pytest

from motocma.collection.facebook import (
    FacebookMarketplaceAdapter,
    UnsafeSourceUrlError,
    canonicalise_url,
)
from motocma.collection.text import PastedTextAdapter


def test_pasted_text_extracts_common_fields() -> None:
    draft = PastedTextAdapter().collect(
        "2022 Yamaha MT-07\n$9,500\n12,345 km\nLocation: Parramatta NSW"
    )

    assert draft.original_title == "2022 Yamaha MT-07"
    assert draft.asking_price_cents == 950_000
    assert draft.year == 2022
    assert draft.odometer_km == 12_345
    assert draft.location == "Parramatta NSW"
    assert draft.collection_method == "pasted_text"


def test_facebook_url_is_canonicalised_and_tracking_removed() -> None:
    result = canonicalise_url(
        "https://www.facebook.com/marketplace/item/12345/?ref=share&mibextid=abc"
    )
    assert result == "https://www.facebook.com/marketplace/item/12345"


@pytest.mark.parametrize(
    "url",
    [
        "http://www.facebook.com/marketplace/item/1",
        "https://example.com/marketplace/item/1",
        "https://facebook.com.evil.example/marketplace/item/1",
        "file:///etc/passwd",
    ],
)
def test_facebook_adapter_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeSourceUrlError):
        canonicalise_url(url)


def test_facebook_adapter_reads_public_metadata() -> None:
    html = """
    <html><head>
      <meta property="og:title" content="2021 Honda CB500F - $7,250">
      <meta property="og:description" content="8,100 km. Great condition.">
      <meta property="og:image" content="https://images.example/bike.jpg">
      <meta property="product:price:amount" content="7250">
    </head></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    draft = FacebookMarketplaceAdapter(client).collect(
        "https://www.facebook.com/marketplace/item/987654"
    )

    assert draft.source_listing_id == "987654"
    assert draft.original_title == "2021 Honda CB500F - $7,250"
    assert draft.asking_price_cents == 725_000
    assert draft.year == 2021
    assert draft.odometer_km == 8_100
    assert draft.image_urls == ["https://images.example/bike.jpg"]
