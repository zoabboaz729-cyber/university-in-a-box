"""Outbound fetching infrastructure (Stage 3 Task 6).

Shared infrastructure in the same sense as app/ai/: role routes call
into this package, and no network I/O is constructed inline in routes
or templates. Deterministic code only — no LLM calls here.

fetch_source_text() is the single entry point the Librarian's
verification flow uses (Task 7). It picks the right reader for the URL
type — HTML page, PDF, or YouTube transcript — and ALWAYS returns a
structured result: an unreadable source is a normal, visible outcome
(Task 7 outcome 3), never an exception.
"""
import asyncio
import threading
from dataclasses import dataclass

from app.fetching import extract, http, youtube
from app.fetching.http import FetchError


@dataclass
class FetchedSource:
    """What one fetch attempt produced — already truncated, LLM-ready."""

    ok: bool
    kind: str    # "page" | "pdf" | "transcript"; "" when unavailable
    text: str    # truncated to MAX_FETCH_CHARS; "" when unavailable
    reason: str  # user-facing reason for unavailability; "" when ok


def _looks_like_pdf(url: str, content_type: str) -> bool:
    """PDF by content type, or by a .pdf path (sites lie about both)."""
    if "application/pdf" in (content_type or "").lower():
        return True
    return url.lower().split("?")[0].split("#")[0].endswith(".pdf")


async def fetch_source_text_async(url: str) -> FetchedSource:
    """Async source-text fetcher for phase 13 non-blocking operations."""
    url = (url or "").strip()
    if not url:
        return FetchedSource(ok=False, kind="", text="",
                             reason="this source has no URL to read")
    if youtube.youtube_video_id(url):
        transcript = await youtube.fetch_transcript_async(url)
        if not transcript.ok:
            return FetchedSource(ok=False, kind="", text="",
                                 reason=transcript.reason)
        return FetchedSource(ok=True, kind="transcript",
                             text=extract.truncate(transcript.text), reason="")
    try:
        page = await http.fetch_url_async(url)
    except FetchError as exc:
        return FetchedSource(ok=False, kind="", text="", reason=str(exc))
    if _looks_like_pdf(url, page.content_type):
        try:
            text = extract.pdf_to_text(page.body)
        except Exception as exc:
            return FetchedSource(
                ok=False, kind="", text="",
                reason="could not read that PDF: " + str(exc))
        kind = "pdf"
    else:
        text = extract.html_to_text(page.body.decode("utf-8", "replace"))
        kind = "page"
    text = extract.truncate(text)
    if not text.strip():
        return FetchedSource(ok=False, kind="", text="",
                             reason="no readable text was found at that URL")
    return FetchedSource(ok=True, kind=kind, text=text, reason="")


def fetch_source_text(url: str) -> FetchedSource:
    """Sync compatibility wrapper for legacy callers and tests.

    Keep a simple, direct behavior for non-async callers while route handlers
    use the async version to keep request flow responsive.
    """
    url = (url or "").strip()
    if not url:
        return FetchedSource(ok=False, kind="", text="",
                             reason="this source has no URL to read")
    if youtube.youtube_video_id(url):
        transcript = youtube.fetch_transcript(url)
        if not transcript.ok:
            return FetchedSource(ok=False, kind="", text="",
                                 reason=transcript.reason)
        return FetchedSource(ok=True, kind="transcript",
                             text=extract.truncate(transcript.text), reason="")
    try:
        page = http.fetch_url(url)
    except FetchError as exc:
        return FetchedSource(ok=False, kind="", text="", reason=str(exc))
    if _looks_like_pdf(url, page.content_type):
        try:
            text = extract.pdf_to_text(page.body)
        except Exception as exc:
            return FetchedSource(ok=False, kind="", text="",
                                 reason="could not read that PDF: " + str(exc))
        kind = "pdf"
    else:
        text = extract.html_to_text(page.body.decode("utf-8", "replace"))
        kind = "page"
    text = extract.truncate(text)
    if not text.strip():
        return FetchedSource(ok=False, kind="", text="",
                             reason="no readable text was found at that URL")
    return FetchedSource(ok=True, kind=kind, text=text, reason="")
