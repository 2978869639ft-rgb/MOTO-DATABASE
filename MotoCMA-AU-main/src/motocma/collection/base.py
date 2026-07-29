from __future__ import annotations

from typing import Protocol

from motocma.domain import ImportDraft


class SourceAdapter(Protocol):
    def can_handle(self, value: str) -> bool: ...

    def collect(self, value: str) -> ImportDraft: ...
