from motocma.collection.parsing import enrich_from_text
from motocma.domain import ImportDraft


class PastedTextAdapter:
    def can_handle(self, value: str) -> bool:
        return bool(value.strip())

    def collect(self, value: str) -> ImportDraft:
        draft = ImportDraft(
            source="facebook_marketplace",
            collection_method="pasted_text",
            raw_input=value,
        )
        return enrich_from_text(draft, value)
