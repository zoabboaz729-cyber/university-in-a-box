"""Librarian routes — Phase 3; rewritten in Stage 3 Task 7 so every source
is actually READ before it is accepted (course-level and topic-level).

  POST /topics/{id}/sources              add a topic-level source (read + judged)
  POST /courses/{id}/sources             add a course-level source (read + judged)
  POST /topics/{id}/sources/{sid}/verify re-run read + judge on an existing row
  POST /courses/{id}/sources/{sid}/verify
  GET  /topics/{id}/shelf                keep-only Shelf view

Exactly one of three explicit outcomes per attempt — never a crash, never
a silent accept (see memory-bank/decisions.md, D-024):
  1 verified-accept  → row persisted (new) or updated (existing) with
                       verified_at set; the judgment is shown on the row
  2 verified-reject  → visible reasons; nothing is persisted (an existing
                       row is removed, and the message says so)
  3 unavailable      → the fetch/extract/transcript failed, so the app
                       asks: retry, discard, or keep it permanently badged
                       unverified (verified_at stays NULL)
The `decision` form field carries the outcome-3 choices: "" (try to read),
"keep_unverified", "discard". One fetch + one LLM call per attempt; the
text is truncated in app.fetching by code, never by a summarizing LLM call.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.ai.provider import ProviderError, get_provider
from app.ai.quota import QuotaExceeded
from app.auth.dependencies import get_current_user
from app.fetching import fetch_source_text, fetch_source_text_async

_ORIGINAL_FETCH_SOURCE_TEXT = fetch_source_text
_ORIGINAL_FETCH_SOURCE_TEXT_ASYNC = fetch_source_text_async
from app.roles import librarian
from app.roles.course_manage import get_topic
from app.roles.course_store import get_course
from app.roles.review_store import list_reviews_for_topic
from app.roles.source_store import (
    UNVERIFIED_VERDICT,
    add_source,
    delete_source,
    get_source,
    list_course_sources,
    list_sources,
    mark_verified,
)
from app.roles.tutor_store import find_open_session, list_sessions_for_topic

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _topic_or_404(request: Request, topic_id: int, user_id: int):
    topic = get_topic(topic_id, user_id)
    if topic is None:
        return None, templates.TemplateResponse(
            request, "error.html",
            {"message": "Topic not found. It may have been deleted."},
            status_code=404,
        )
    return topic, None


def _now() -> str:
    """UTC timestamp for verified_at (matches the codebase's text stamps)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _safe_next(raw: str) -> str:
    """Only ever redirect to a local path — never an off-site URL."""
    raw = (raw or "").strip()
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/"


def _render_error(request: Request, message: str, status_code: int = 200):
    """Any failure here is visible inline — never a silent no-op."""
    return templates.TemplateResponse(
        request, "librarian_error.html", {"message": message},
        status_code=status_code,
    )


def _render_scope(request: Request, scope: str, scope_id: int, user_id: int,
                  error: str = "", shelf_only: bool = False):
    """Render the surface that owns this source section (topic or course)."""
    if scope == "course":
        course = get_course(scope_id, user_id)
        if course is None:
            return _render_error(request, "Course not found. It may have been "
                                          "deleted.", status_code=404)
        return templates.TemplateResponse(
            request, "course.html",
            {"course": course,
             "sources": list_course_sources(scope_id, user_id),
             "error": error},
        )
    topic, err = _topic_or_404(request, scope_id, user_id)
    if err is not None:
        return err
    return templates.TemplateResponse(
        request, "topic.html",
        {"topic": topic,
         "sources": list_sources(scope_id, user_id, keep_only=shelf_only),
         "shelf_only": shelf_only, "error": error,
         "sessions": list_sessions_for_topic(scope_id, user_id),
         "open_session_id": find_open_session(scope_id, user_id),
         "reviews": list_reviews_for_topic(scope_id, user_id),
         "submission_draft": ""},
    )


def _descriptor(scope: str, scope_id: int, user_id: int) -> str | None:
    """What this source must serve — topic milestone or course syllabus."""
    if scope == "topic":
        topic = get_topic(scope_id, user_id)
        return None if topic is None else librarian.topic_descriptor(topic)
    course = get_course(scope_id, user_id)
    return None if course is None else librarian.course_descriptor(course)


def _insert(scope: str, scope_id: int, user_id: int, label: str,
            reference: str, verdict: str, reason: str,
            verified_at: str | None) -> int:
    """Insert one source in the scope the caller named (exactly one of the two)."""
    return add_source(
        topic_id=scope_id if scope == "topic" else None,
        course_id=scope_id if scope == "course" else None,
        user_id=user_id,
        label=label, reference=reference, verdict=verdict, reason=reason,
        verified_at=verified_at,
    )


@router.get("/topics/{topic_id}/shelf", response_class=HTMLResponse)
async def shelf_view(request: Request, topic_id: int,
                     user: dict = Depends(get_current_user)):
    return _render_scope(request, "topic", topic_id, user["id"],
                         shelf_only=True)


async def _fetch_source_text(url: str):
    """Read a source's text WITHOUT blocking the event loop.

    The configured fetcher (``fetch_source_text``) is a *blocking* call: a
    synchronous ``httpx`` client for pages/PDFs, and — for a YouTube URL —
    ``asyncio.run`` internally (see ``app.fetching.youtube.fetch_transcript``).
    Calling it directly inside this ``async def`` route would (a) freeze the
    event loop for the whole HTTP timeout and (b) crash on a YouTube URL,
    because ``asyncio.run`` cannot start a loop while one is already running
    (a 500 instead of a clean outcome-3 page). Running it in a worker thread
    via ``asyncio.to_thread`` keeps the loop responsive and lets that nested
    ``asyncio.run`` succeed.

    The name is resolved on the module (tests patch
    ``app.routes.librarian.fetch_source_text``). The ``except TypeError``
    seam, the coroutine check, and the async fallback below are unchanged.
    """
    try:
        result = await asyncio.to_thread(fetch_source_text, url)
    except TypeError:
        result = None
    if result is not None:
        if asyncio.iscoroutine(result):
            return await result
        return result
    if fetch_source_text_async is not None:
        return await fetch_source_text_async(url)
    return await _ORIGINAL_FETCH_SOURCE_TEXT_ASYNC(url)


def _provider_for_user(user: dict):
    """Build the provider for THIS user, so BYOK and the quota apply.

    Mirrors the other roles (tutor/editor/advisor): the FULL user row is
    handed to ``get_provider``, which then resolves the user's own stored
    key (BYOK) or the server key under the free quota
    (app/ai/quota.py). An id-only dict would silently skip both.

    The ``except TypeError`` fallback keeps older test patches that
    replace ``get_provider`` with a no-argument callable working.
    """
    try:
        return get_provider(user=user)
    except TypeError:
        return get_provider()


def _quota_error(request: Request, exc: QuotaExceeded):
    """The friendly quota page (docs/05-VERIFICATION.md, item 4).

    Nothing is stored on this path: the quota check happens before any
    row is written, and an existing row keeps its exact previous state.
    """
    return _render_error(request, str(exc) + " Nothing was stored.")


async def _handle(request: Request, scope: str, scope_id: int, user: dict,
                  source_id: int | None, label: str, reference: str,
                  decision: str, next_path: str):
    """One source attempt: read → judge → exactly one visible outcome.

    Shared by all four POST routes (topic/course × add/re-verify). Outcome
    3 is the only path that asks a question back, and it does so by
    rendering a page whose three choices post to this same handler.

    The provider is built lazily: a discard or a keep-as-unverified needs
    no AI config and must not fail because of one. It is built from the
    FULL user row, so the user's own key (BYOK) and the free quota apply
    exactly as they do for the Tutor, Editor and Advisor.
    """
    user_id = user["id"]
    next_path = _safe_next(next_path)
    if not label.strip():
        return _render_scope(request, scope, scope_id, user_id,
                             error="Give the source a short label before "
                                   "adding it.")
    existing = get_source(source_id, user_id) if source_id else None
    if source_id and existing is None:
        return _render_error(request, "That source no longer exists.")

    if decision == "discard":
        if existing is not None:
            delete_source(source_id, user_id)
        return RedirectResponse(next_path, status_code=303)

    fetched = await _fetch_source_text(reference)
    if not fetched.ok:
        if decision == "keep_unverified":
            if existing is None:
                _insert(scope, scope_id, user_id, label, reference,
                        UNVERIFIED_VERDICT,
                        "Saved without verification: " + fetched.reason, None)
            return RedirectResponse(next_path, status_code=303)
        return templates.TemplateResponse(
            request, "librarian_unavailable.html",
            {"message": fetched.reason, "scope": scope, "scope_id": scope_id,
             "source_id": source_id or "", "label": label,
             "reference": reference, "next": next_path})

    descriptor = _descriptor(scope, scope_id, user_id)
    if descriptor is None:
        return _render_error(request, "That page no longer exists.")
    try:
        verification = await librarian.verify_async(
            descriptor, label, reference, fetched.text, _provider_for_user(user))
    except QuotaExceeded as exc:
        # The free quota is spent and the user has no key of their own.
        # Show the friendly message — never a 500 (docs/05-VERIFICATION.md).
        return _quota_error(request, exc)
    except ProviderError as exc:
        return _render_error(request, "Could not judge that source: "
                                      + str(exc) + " Nothing was stored.")
    except (ValueError, KeyError, TypeError):
        return _render_error(
            request, "The Librarian's judgment could not be read (the model "
                     "did not return usable JSON). Nothing was stored. "
                     "Try again.")

    reason = librarian.judgement_text(verification)
    if verification.accepted:
        if existing is None:
            _insert(scope, scope_id, user_id, label, reference, "keep", reason,
                    _now())
        else:
            mark_verified(source_id, "keep", reason, _now(), user_id)
        return RedirectResponse(next_path, status_code=303)

    removed = (delete_source(source_id, user_id)
               if existing is not None else False)
    return templates.TemplateResponse(
        request, "librarian_verdict.html",
        {"message": reason, "removed": removed, "next": next_path})


async def _reverify(request: Request, scope: str, scope_id: int, source_id: int,
                   label: str, reference: str, decision: str, next_path: str,
                   user: dict):
    """Re-run read + judge on a row the user already has.

    This is how the pre-existing rows (verified_at NULL after migration)
    become verified: per-row, on demand — never a silent bulk re-fetch.
    """
    row = get_source(source_id, user["id"])
    if row is None:
        return _render_error(request, "That source no longer exists.")
    try:
        return await _handle(request, scope, scope_id, user, source_id,
                             (label or row["label"]).strip(),
                             (reference or row["url_or_reference"] or "").strip(),
                             decision, next_path)
    except QuotaExceeded as exc:
        # Safety net for this path: the quota page, never a 500. _handle
        # catches the same error for the call it makes itself.
        return _quota_error(request, exc)


@router.post("/topics/{topic_id}/sources")
async def add_topic_source(request: Request, topic_id: int, label: str = Form(...),
                          reference: str = Form(""), decision: str = Form(""),
                          next: str = Form(""),
                          user: dict = Depends(get_current_user)):
    return await _handle(request, "topic", topic_id, user, None,
                         label.strip(), reference.strip(), decision,
                         next or f"/topics/{topic_id}")


@router.post("/courses/{course_id}/sources")
async def add_course_source(request: Request, course_id: int, label: str = Form(...),
                           reference: str = Form(""), decision: str = Form(""),
                           next: str = Form(""),
                           user: dict = Depends(get_current_user)):
    return await _handle(request, "course", course_id, user, None,
                         label.strip(), reference.strip(), decision,
                         next or f"/courses/{course_id}")


@router.post("/topics/{topic_id}/sources/{source_id}/verify")
async def verify_topic_source(request: Request, topic_id: int, source_id: int,
                             label: str = Form(""), reference: str = Form(""),
                             decision: str = Form(""), next: str = Form(""),
                             user: dict = Depends(get_current_user)):
    return await _reverify(request, "topic", topic_id, source_id, label,
                          reference, decision, next or f"/topics/{topic_id}",
                          user)


@router.post("/courses/{course_id}/sources/{source_id}/verify")
async def verify_course_source(request: Request, course_id: int, source_id: int,
                              label: str = Form(""), reference: str = Form(""),
                              decision: str = Form(""), next: str = Form(""),
                              user: dict = Depends(get_current_user)):
    return await _reverify(request, "course", course_id, source_id, label,
                          reference, decision, next or f"/courses/{course_id}",
                          user)
