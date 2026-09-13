"""Editor routes — Phase 5: structured review of user-submitted work.

POST /topics/{id}/editor/submit: one LLM review call, persist the
editor_reviews row, redirect back to the topic page. Same failure
discipline as Librarian/Tutor: provider/parse errors re-render the
topic page inline with the submission preserved in the textarea —
nothing half-written persists.
"""
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.ai.provider import ProviderError, get_provider
from app.roles import editor
from app.roles.course_manage import get_topic
from app.roles.review_store import list_reviews_for_topic, save_review
from app.roles.source_store import list_sources
from app.roles.tutor_store import find_open_session, list_sessions_for_topic

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

MAX_SUBMISSION_CHARS = editor.MAX_SUBMISSION_CHARS


def _render_topic(request: Request, topic: dict, error: str = "",
                  submission_draft: str = ""):
    """Full topic-page context (same shape as every other re-render)."""
    context = {
        "topic": topic,
        "sources": list_sources(topic["id"]),
        "shelf_only": False,
        "error": error,
        "sessions": list_sessions_for_topic(topic["id"]),
        "open_session_id": find_open_session(topic["id"]),
        "reviews": list_reviews_for_topic(topic["id"]),
        "submission_draft": submission_draft,
    }
    return templates.TemplateResponse(request, "topic.html", context)


@router.post("/topics/{topic_id}/editor/submit")
def editor_submit(request: Request, topic_id: int,
                  submission: str = Form(...)):
    topic = get_topic(topic_id)
    if topic is None:
        return templates.TemplateResponse(
            request, "error.html",
            {"message": "Topic not found. It may have been deleted."},
            status_code=404,
        )
    text = submission.strip()
    if not text:
        return _render_topic(
            request, topic,
            error="Write or paste what you produced before submitting "
                  "for review.")
    if len(text) > MAX_SUBMISSION_CHARS:
        return _render_topic(
            request, topic,
            error="Keep the submission under 8000 characters — trim it "
                  "and submit again.",
            submission_draft=text)
    try:
        review = editor.review_submission(
            topic["title"], topic["milestone_description"] or "",
            text, get_provider())
    except ProviderError as exc:
        return _render_topic(
            request, topic,
            error="Could not review that submission: " + str(exc),
            submission_draft=text)
    except Exception as exc:
        return _render_topic(
            request, topic,
            error="The review came back in a bad shape (" + str(exc)
                  + "). Please try again.",
            submission_draft=text)
    save_review(topic_id, topic["milestone_description"] or "", text, review)
    return RedirectResponse(f"/topics/{topic_id}", status_code=303)