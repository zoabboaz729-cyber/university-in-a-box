"""Course + topic routes — Phase 1c course page, Phase 2 + 5 management.

GET /courses/{id} is the post-confirm landing page. Phase 2 adds:
GET /topics/{id} (milestone + Shelf + Tutor sessions + Editor reviews),
POST /courses/{id}/status (pause/archive/resume),
POST /topics/{id}/status (Phase 5: marking done requires at least one
Editor review on record for that topic — enforced server-side here).
"""
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.roles.course_manage import get_topic, set_course_status, set_topic_status
from app.roles.course_store import get_course
from app.roles.review_store import has_editor_review, list_reviews_for_topic
from app.roles.source_store import list_sources
from app.roles.tutor_store import find_open_session, list_sessions_for_topic

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

GATE_MESSAGE = ("This topic needs at least one Editor review before it "
                "can be marked done.")


def _topic_context(topic_id: int) -> dict:
    """Shared topic.html context (Phase 5 adds reviews)."""
    return {
        "sources": list_sources(topic_id),
        "shelf_only": False,
        "sessions": list_sessions_for_topic(topic_id),
        "open_session_id": find_open_session(topic_id),
        "reviews": list_reviews_for_topic(topic_id),
        "submission_draft": "",
    }


def _not_found(request: Request, message: str):
    return templates.TemplateResponse(
        request, "error.html", {"message": message}, status_code=404
    )


@router.get("/courses/{course_id}", response_class=HTMLResponse)
def course_view(request: Request, course_id: int):
    course = get_course(course_id)
    if course is None:
        return _not_found(request, "Course not found. It may have been deleted.")
    return templates.TemplateResponse(
        request, "course.html", {"course": course}
    )


@router.post("/courses/{course_id}/status")
def course_status(course_id: int, status: str = Form(...)):
    try:
        ok = set_course_status(course_id, status)
    except ValueError:
        # Unknown status value: bounce back to the course page unchanged.
        return RedirectResponse(f"/courses/{course_id}", status_code=303)
    if not ok:
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(f"/courses/{course_id}", status_code=303)


@router.get("/topics/{topic_id}", response_class=HTMLResponse)
def topic_view(request: Request, topic_id: int):
    topic = get_topic(topic_id)
    if topic is None:
        return _not_found(request, "Topic not found. It may have been deleted.")
    return templates.TemplateResponse(
        request, "topic.html",
        {"topic": topic, "error": "", **_topic_context(topic_id)},
    )


@router.post("/topics/{topic_id}/status")
def topic_status(request: Request, topic_id: int, status: str = Form(...)):
    topic = get_topic(topic_id)
    if topic is None:
        return RedirectResponse("/", status_code=303)
    if status == "done" and not has_editor_review(topic_id):
        # Phase 5 gate: no review on record, no done — status unchanged.
        return templates.TemplateResponse(
            request, "topic.html",
            {"topic": topic, "error": GATE_MESSAGE,
             **_topic_context(topic_id)},
        )
    try:
        ok = set_topic_status(topic_id, status)
    except ValueError:
        return RedirectResponse(f"/topics/{topic_id}", status_code=303)
    if not ok:
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(f"/topics/{topic_id}", status_code=303)

