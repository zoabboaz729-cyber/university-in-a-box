"""Tutor routes — Phase 4: Socratic sessions on a Topic page.

POST /topics/{id}/tutor/start, GET /tutor/{id},
POST /tutor/{id}/answer, POST /tutor/{id}/end.
Failure discipline (same as Librarian): provider/parse errors
re-render inline; start writes nothing half-done, answer/end keep
saved work with the session still open.
"""
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.ai.provider import ProviderError, get_provider
from app.roles import tutor
from app.roles.course_manage import get_topic
from app.roles.review_store import list_reviews_for_topic
from app.roles.source_store import list_sources
from app.roles.tutor_store import (
    add_turn,
    delete_session,
    end_session,
    find_open_session,
    get_session,
    list_sessions_for_topic,
    save_answer,
    start_session,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

SHELF_CHAR_CAP = 800


def _shelf_lines(topic_id: int) -> str:
    """Keep-only shelf as short 'label — reason' lines for the prompt."""
    lines = []
    for src in list_sources(topic_id, keep_only=True):
        lines.append(src["label"] + " — " + (src["reason"] or ""))
    return ("\n".join(lines))[:SHELF_CHAR_CAP]


def _render_session(request: Request, session: dict, error: str = ""):
    turns = session["turns"]
    pending = None
    if session["ended_at"] is None:
        for turn in reversed(turns):
            if not turn["user_answer"]:
                pending = turn
                break
    return templates.TemplateResponse(
        request, "tutor_session.html",
        {"session": session, "pending": pending, "error": error},
    )


def _topic_error(request: Request, topic: dict, topic_id: int, msg: str):
    sessions = list_sessions_for_topic(topic_id)
    return templates.TemplateResponse(
        request, "topic.html",
        {"topic": topic, "sources": list_sources(topic_id),
         "shelf_only": False, "error": msg,
         "sessions": sessions,
         "open_session_id": None,
         "reviews": list_reviews_for_topic(topic_id),
         "submission_draft": ""},
    )

@router.post("/topics/{topic_id}/tutor/start")
def tutor_start(topic_id: int, request: Request):
    topic = get_topic(topic_id)
    if topic is None:
        return templates.TemplateResponse(
            request, "error.html",
            {"message": "Topic not found. It may have been deleted."},
            status_code=404,
        )
    existing = find_open_session(topic_id)
    if existing is not None:
        return RedirectResponse(f"/tutor/{existing}", status_code=303)
    session_id = start_session(topic_id)
    try:
        first = tutor.next_question(
            topic["title"], topic["milestone_description"] or "",
            _shelf_lines(topic_id), [], get_provider())
    except ProviderError as exc:
        delete_session(session_id)
        return _topic_error(request, topic, topic_id,
                            "Could not start the session: " + str(exc))
    except Exception as exc:
        delete_session(session_id)
        return _topic_error(
            request, topic, topic_id,
            "The first question came back in a bad shape ("
            + str(exc) + "). Please try again.")
    add_turn(session_id, first.question)
    return RedirectResponse(f"/tutor/{session_id}", status_code=303)


@router.get("/tutor/{session_id}", response_class=HTMLResponse)
def tutor_view(request: Request, session_id: int):
    session = get_session(session_id)
    if session is None:
        return templates.TemplateResponse(
            request, "error.html",
            {"message": "Tutor session not found."}, status_code=404,
        )
    return _render_session(request, session)


@router.post("/tutor/{session_id}/answer")
def tutor_answer(request: Request, session_id: int,
                 turn_id: int = Form(...), answer: str = Form(...)):
    session = get_session(session_id)
    if session is None:
        return templates.TemplateResponse(
            request, "error.html",
            {"message": "Tutor session not found."}, status_code=404,
        )
    if session["ended_at"] is not None:
        return RedirectResponse(f"/tutor/{session_id}", status_code=303)
    if not answer.strip():
        return _render_session(
            request, session,
            error="Please write an answer before continuing.")
    try:
        save_answer(turn_id, answer)
    except ValueError:
        session = get_session(session_id)
        return _render_session(
            request, session, error="That answer could not be saved.")
    session = get_session(session_id)
    topic = get_topic(session["topic_id"])
    try:
        nxt = tutor.next_question(
            topic["title"], topic["milestone_description"] or "",
            _shelf_lines(session["topic_id"]),
            session["turns"], get_provider())
    except ProviderError as exc:
        return _render_session(
            request, session,
            error="Your answer is saved. Could not ask the next question: "
                  + str(exc) + " — reload to try again.")
    except Exception as exc:
        return _render_session(
            request, session,
            error="Your answer is saved. The next question came back in a "
                  "bad shape (" + str(exc) + ") — reload to try again.")
    add_turn(session_id, nxt.question)
    return RedirectResponse(f"/tutor/{session_id}", status_code=303)


@router.post("/tutor/{session_id}/end")
def tutor_end(request: Request, session_id: int):
    session = get_session(session_id)
    if session is None:
        return templates.TemplateResponse(
            request, "error.html",
            {"message": "Tutor session not found."}, status_code=404,
        )
    if session["ended_at"] is not None:
        return RedirectResponse(
            f"/topics/{session['topic_id']}", status_code=303)
    topic = get_topic(session["topic_id"])
    try:
        gap = tutor.make_gap_note(
            topic["title"], topic["milestone_description"] or "",
            session["turns"], get_provider())
    except ProviderError as exc:
        return _render_session(
            request, session,
            error="Could not write the gap note: " + str(exc)
                  + " — the session stays open, try ending again.")
    except Exception as exc:
        return _render_session(
            request, session,
            error="The gap note came back in a bad shape (" + str(exc)
                  + ") — the session stays open, try ending again.")
    end_session(session_id, gap.text)
    return RedirectResponse(f"/topics/{session['topic_id']}", status_code=303)

