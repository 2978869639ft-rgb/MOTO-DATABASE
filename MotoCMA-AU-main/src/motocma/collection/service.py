from __future__ import annotations

from motocma.collection.base import SourceAdapter
from motocma.domain import ImportDraft


class UnsupportedImportError(ValueError):
    pass


class CollectionService:
    def __init__(self, url_adapter: SourceAdapter, text_adapter: SourceAdapter) -> None:
        self._url_adapter = url_adapter
        self._text_adapter = text_adapter

    def collect(self, method: str, value: str) -> ImportDraft:
        if method == "facebook_url" and self._url_adapter.can_handle(value):
            return self._url_adapter.collect(value)
        if method == "pasted_text" and self._text_adapter.can_handle(value):
            return self._text_adapter.collect(value)
        raise UnsupportedImportError("Enter a supported Facebook URL or non-empty listing text.")
