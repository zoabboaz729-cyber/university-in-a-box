"""Librarian routes — Phase 3: add-a-source + Shelf views on a Topic page.

POST /topics/{id}/sources: one LLM triage call, persist the Source row,
redirect back to the topic page. Provider/parse failures re-render the
topic page inline with a clear error — nothing half-written persists.
GET /topics/{id}/shelf: keep-only Shelf view.
"""
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.ai.provider import ProviderError, get_provider
from app.roles import librarian
from app.roles.course_manage import get_topic
from app.roles.review_store import list_reviews_for_topic
from app.roles.source_store import add_source, list_sources
from app.roles.tutor_store import find_open_session, list_sessions_for_topic

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _topic_or_404(request: Request, topic_id: int):
    topic = get_topic(topic_id)
    if topic is None:
        return None, templates.TemplateResponse(
            request, "error.html",
            {"message": "Topic not found. It may have been deleted."},
            status_code=404,
        )
    return topic, None


def _render_topic(request: Request, topic: dict, error: str = "",
                  shelf_only: bool = False):
    sources = list_sources(topic["id"], keep_only=shelf_only)
    return templates.TemplateResponse(
        request, "topic.html",
        {"topic": topic, "sources": sources, "shelf_only": shelf_only,
         "error": error,
         "sessions": list_sessions_for_topic(topic["id"]),
         "open_session_id": find_open_session(topic["id"]),
         "reviews": list_reviews_for_topic(topic["id"]),
         "submission_draft": ""},
    )


@router.get("/topics/{topic_id}/shelf", response_class=HTMLResponse)
def shelf_view(request: Request, topic_id: int):
    topic, err = _topic_or_404(request, topic_id)
    if err is not None:
        return err
    return _render_topic(request, topic, shelf_only=True)


@router.post("/topics/{topic_id}/sources")
def add_source_route(
    request: Request, topic_id: int,
    label: str = Form(...), reference: str = Form(""),
):
    topic, err = _topic_or_404(request, topic_id)
    if err is not None:
        return err
    if not label.strip():
        return _render_topic(
            request, topic,
            error="Give the source a short label before adding it.")
    try:
        verdict = librarian.triage(
            topic["title"], topic["milestone_description"] or "",
            label.strip(), reference.strip(), get_provider())
    except ProviderError as exc:
        return _render_topic(
            request, topic,
            error="Could not judge that source: " + str(exc))
    except Exception as exc:
        return _render_topic(
            request, topic,
            error="The verdict came back in a bad shape (" + str(exc) + "). "
                  "Please try again.")
    add_source(topic_id, label.strip(), reference.strip(), verdict.verdict,
               "Good for " + verdict.good_for + ". " + verdict.reason)
    return RedirectResponse(f"/topics/{topic_id}", status_code=303)
