from __future__ import annotations

import re

from motocma.domain import ImportDraft, parse_int, parse_money_to_cents

PRICE_PATTERN = re.compile(r"(?:AUD\s*)?\$\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")
ODOMETER_PATTERN = re.compile(r"\b([\d,.]+)\s*(?:km|kms|kilometres|kilometers)\b", re.IGNORECASE)
LOCATION_PATTERN = re.compile(r"(?:location|located\s+in)\s*[:\-]?\s*([^\n|]+)", re.IGNORECASE)


def enrich_from_text(draft: ImportDraft, text: str) -> ImportDraft:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and draft.original_title is None:
        draft.original_title = lines[0][:300]

    price = PRICE_PATTERN.search(text)
    if price and draft.asking_price_cents is None:
        draft.asking_price_cents = parse_money_to_cents(price.group(1))

    year = YEAR_PATTERN.search(text)
    if year and draft.year is None:
        draft.year = int(year.group(1))

    odometer = ODOMETER_PATTERN.search(text)
    if odometer and draft.odometer_km is None:
        draft.odometer_km = parse_int(odometer.group(1))

    location = LOCATION_PATTERN.search(text)
    if location and draft.location is None:
        draft.location = location.group(1).strip()[:200]

    if text.strip() and draft.description is None:
        draft.description = text.strip()
    return draft
