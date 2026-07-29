from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import SplitResult, parse_qsl, urlencode, urljoin, urlsplit

import httpx

from motocma.collection.parsing import enrich_from_text
from motocma.domain import ImportDraft, parse_money_to_cents

LISTING_ID_PATTERN = re.compile(r"/marketplace/item/(\d+)")
ALLOWED_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch"}
TRACKING_QUERY_KEYS = {"ref", "referral_code", "referral_story_type", "mibextid"}


class UnsafeSourceUrlError(ValueError):
    pass


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = dict(attrs)
        key = values.get("property") or values.get("name")
        content = values.get("content")
        if key and content:
            self.values[key.lower()] = content.strip()


def is_allowed_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.lower() in ALLOWED_HOSTS
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443)
    )


def canonicalise_url(value: str) -> str:
    if not is_allowed_url(value):
        raise UnsafeSourceUrlError(
            "Only HTTPS Facebook Marketplace or Facebook share URLs are accepted."
        )
    parsed = urlsplit(value.strip())
    host = parsed.hostname
    if host is None:
        raise UnsafeSourceUrlError("The Facebook URL has no hostname.")
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    path = parsed.path.rstrip("/") or "/"
    return SplitResult("https", host.lower(), path, urlencode(query), "").geturl()


class FacebookMarketplaceAdapter:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def can_handle(self, value: str) -> bool:
        return is_allowed_url(value.strip())

    def collect(self, value: str) -> ImportDraft:
        canonical_url = canonicalise_url(value)
        draft = ImportDraft(
            source="facebook_marketplace",
            collection_method="facebook_url",
            raw_input=value,
            source_url=value.strip(),
            canonical_url=canonical_url,
        )
        listing_match = LISTING_ID_PATTERN.search(urlsplit(canonical_url).path)
        if listing_match:
            draft.source_listing_id = listing_match.group(1)

        try:
            html, final_url = self._fetch(canonical_url)
        except (httpx.HTTPError, UnsafeSourceUrlError) as error:
            draft.warnings.append(
                "Facebook could not be read automatically. Review the URL and paste "
                f"listing text to complete missing fields. ({type(error).__name__})"
            )
            return draft

        draft.canonical_url = canonicalise_url(final_url)
        final_match = LISTING_ID_PATTERN.search(urlsplit(final_url).path)
        if final_match:
            draft.source_listing_id = final_match.group(1)

        parser = MetaParser()
        parser.feed(html)
        title = parser.values.get("og:title")
        description = parser.values.get("og:description")
        if title:
            draft.original_title = title[:300]
        if description:
            draft.description = description
        image = parser.values.get("og:image")
        if image and image.startswith("https://"):
            draft.image_urls.append(image)
        price = parser.values.get("product:price:amount")
        if price:
            draft.asking_price_cents = parse_money_to_cents(price)
        enrich_from_text(draft, "\n".join(part for part in (title, description) if part))
        if not title and not description:
            draft.warnings.append(
                "Facebook returned no public listing details. Complete the fields manually."
            )
        return draft

    def _fetch(self, initial_url: str) -> tuple[str, str]:
        owns_client = self._client is None
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(8.0),
            headers={"User-Agent": "MotoCMA-AU/0.1 personal-market-research"},
        )
        url = initial_url
        try:
            for _ in range(5):
                response = client.get(url, follow_redirects=False)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                    url = urljoin(url, location)
                    if not is_allowed_url(url):
                        raise UnsafeSourceUrlError("Facebook redirected to an unapproved host.")
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    raise httpx.HTTPError("Facebook response was not HTML.")
                if len(response.content) > 2_000_000:
                    raise httpx.HTTPError("Facebook response exceeded the size limit.")
                return response.text, str(response.url)
            raise httpx.TooManyRedirects("Facebook exceeded the redirect limit.")
        finally:
            if owns_client:
                client.close()
