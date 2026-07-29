from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from motocma.collection import CollectionService, FacebookMarketplaceAdapter, PastedTextAdapter
from motocma.collection.service import UnsupportedImportError
from motocma.domain import (
    DuplicateCandidate,
    ImportDraft,
    format_money,
    parse_int,
    parse_money_to_cents,
    validate_for_approval,
)
from motocma.imports import DraftNotFoundError, InMemoryDraftStore
from motocma.listings import ListingSearch, find_duplicate_candidates
from motocma.persistence import ListingNotFoundError, SQLiteListingRepository

PACKAGE_DIR = Path(__file__).parent


def create_app(
    database_path: Path | None = None,
    collection_service: CollectionService | None = None,
) -> FastAPI:
    app = FastAPI(title="MotoCMA-AU", version="0.1.0")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.globals["format_money"] = format_money
    drafts = InMemoryDraftStore()
    repository = SQLiteListingRepository(
        database_path or Path(os.environ.get("MOTOCMA_DATABASE", "data/motocma.sqlite3"))
    )
    repository.initialise()
    collector = collection_service or CollectionService(
        FacebookMarketplaceAdapter(), PastedTextAdapter()
    )

    app.state.drafts = drafts
    app.state.repository = repository
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, message: str | None = None) -> HTMLResponse:
        search = _search_from_query(request)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "listings": repository.list_latest(search),
                "search": search,
                "message": message,
                "error": None,
            },
        )

    @app.post("/imports")
    async def create_import(request: Request) -> Response:
        form = await request.form()
        method = str(form.get("method", ""))
        value = str(form.get("value", ""))
        try:
            draft = drafts.add(collector.collect(method, value))
        except UnsupportedImportError as error:
            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={
                    "listings": repository.list_latest(),
                    "search": ListingSearch(),
                    "message": None,
                    "error": str(error),
                },
                status_code=422,
            )
        return RedirectResponse(f"/imports/{draft.id}/review", status_code=303)

    @app.get("/imports/{draft_id}/review", response_class=HTMLResponse)
    async def review_import(request: Request, draft_id: str) -> HTMLResponse:
        try:
            draft = drafts.get(draft_id)
        except DraftNotFoundError:
            return _missing_draft_response(templates, request)
        candidates = find_duplicate_candidates(draft, repository.list_latest())
        return _review_response(templates, request, draft, candidates)

    @app.post("/imports/{draft_id}/review", response_class=HTMLResponse)
    async def recheck_import(request: Request, draft_id: str) -> HTMLResponse:
        try:
            draft = _update_draft(drafts, draft_id, await request.form())
        except DraftNotFoundError:
            return _missing_draft_response(templates, request)
        candidates = find_duplicate_candidates(draft, repository.list_latest())
        return _review_response(templates, request, draft, candidates)

    @app.post("/imports/{draft_id}/save")
    async def save_import(request: Request, draft_id: str) -> Response:
        form = await request.form()
        resolution = str(form.get("resolution", ""))
        if resolution == "cancel":
            drafts.discard(draft_id)
            return RedirectResponse(
                "/?message=Import+cancelled.+No+listing+was+saved.",
                status_code=303,
            )
        try:
            draft = _update_draft(drafts, draft_id, form)
        except DraftNotFoundError:
            return _missing_draft_response(templates, request)

        candidates = find_duplicate_candidates(draft, repository.list_latest())
        validation_errors = validate_for_approval(draft)
        if validation_errors:
            return _review_response(
                templates,
                request,
                draft,
                candidates,
                error=" ".join(validation_errors),
                status_code=422,
            )
        if resolution == "update":
            target_id = str(form.get("target_listing_id", ""))
            candidate_ids = {candidate.listing_id for candidate in candidates}
            if not target_id or target_id not in candidate_ids:
                return _review_response(
                    templates,
                    request,
                    draft,
                    candidates,
                    error="Select one duplicate candidate before adding an observation.",
                    status_code=422,
                )
            try:
                repository.approve_update(target_id, draft)
            except ListingNotFoundError:
                return _review_response(
                    templates,
                    request,
                    draft,
                    candidates,
                    error="The selected listing no longer exists. Recheck duplicates.",
                    status_code=409,
                )
            message = "Approved: a new historical observation was added."
        elif resolution == "create":
            repository.approve_create(draft)
            message = "Approved: the listing was saved."
        else:
            return _review_response(
                templates,
                request,
                draft,
                candidates,
                error="Choose how this draft should be saved.",
                status_code=422,
            )

        drafts.discard(draft_id)
        return RedirectResponse(f"/?message={message.replace(' ', '+')}", status_code=303)

    return app


def _update_draft(drafts: InMemoryDraftStore, draft_id: str, form: Any) -> ImportDraft:
    existing = drafts.get(draft_id)
    values = {key: str(value) for key, value in form.items()}
    return drafts.replace(ImportDraft.from_form(existing, values))


def _review_response(
    templates: Jinja2Templates,
    request: Request,
    draft: ImportDraft,
    candidates: list[DuplicateCandidate],
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={"draft": draft, "candidates": candidates, "error": error},
        status_code=status_code,
    )


def _missing_draft_response(templates: Jinja2Templates, request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "listings": [],
            "search": ListingSearch(),
            "message": None,
            "error": "This temporary draft no longer exists. Start a new import.",
        },
        status_code=404,
    )


def _search_from_query(request: Request) -> ListingSearch:
    query = request.query_params
    return ListingSearch(
        make=_optional_query_value(query.get("make")),
        model=_optional_query_value(query.get("model")),
        location=_optional_query_value(query.get("location")),
        listing_status=_optional_query_value(query.get("listing_status")),
        min_year=parse_int(_optional_query_value(query.get("min_year"))),
        max_year=parse_int(_optional_query_value(query.get("max_year"))),
        min_price_cents=parse_money_to_cents(_optional_query_value(query.get("min_price"))),
        max_price_cents=parse_money_to_cents(_optional_query_value(query.get("max_price"))),
        max_odometer_km=parse_int(_optional_query_value(query.get("max_odometer_km"))),
    )


def _optional_query_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


app = create_app()


def run() -> None:
    uvicorn.run("motocma.web:app", host="127.0.0.1", port=8000, reload=False)
