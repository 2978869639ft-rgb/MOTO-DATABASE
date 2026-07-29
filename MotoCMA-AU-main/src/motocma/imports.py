from __future__ import annotations

from threading import RLock

from motocma.domain import ImportDraft


class DraftNotFoundError(KeyError):
    pass


class InMemoryDraftStore:
    """Temporary process-local storage; never writes unapproved data to disk."""

    def __init__(self) -> None:
        self._drafts: dict[str, ImportDraft] = {}
        self._lock = RLock()

    def add(self, draft: ImportDraft) -> ImportDraft:
        with self._lock:
            self._drafts[draft.id] = draft
        return draft

    def get(self, draft_id: str) -> ImportDraft:
        with self._lock:
            try:
                return self._drafts[draft_id]
            except KeyError as error:
                raise DraftNotFoundError(draft_id) from error

    def replace(self, draft: ImportDraft) -> ImportDraft:
        with self._lock:
            if draft.id not in self._drafts:
                raise DraftNotFoundError(draft.id)
            self._drafts[draft.id] = draft
        return draft

    def discard(self, draft_id: str) -> None:
        with self._lock:
            self._drafts.pop(draft_id, None)
