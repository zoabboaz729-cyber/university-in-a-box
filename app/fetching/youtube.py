"""YouTube transcript fetching — structured failure, NEVER raises.

The transcript is the only way the Librarian can "read" a video, so an
unfetchable transcript must surface as an explicit unavailable result
(Stage 3 Task 7 outcome 3): never a crash, never a silent accept.
"""
import asyncio
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

_YOUTUBE_HOSTS = ("www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be")


@dataclass
class TranscriptResult:
    ok: bool
    text: str
    reason: str  # human-readable; shown to the user when ok is False


def youtube_video_id(url: str) -> str | None:
    """Video id from a YouTube watch/short URL, else None."""
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return None
    path = parts.path or ""
    if host == "youtu.be":
        return path.lstrip("/").split("/")[0] or None
    if path == "/watch":
        return parse_qs(parts.query).get("v", [""])[0] or None
    if path.startswith("/shorts/"):
        return path[len("/shorts/"):].split("/")[0] or None
    return None


async def fetch_transcript_async(url: str) -> TranscriptResult:
    """Async fetch a transcript while keeping failure handling explicit."""
    video_id = youtube_video_id(url)
    if not video_id:
        return TranscriptResult(
            ok=False, text="", reason="not a YouTube watch/short URL")
    try:
        transcript_list = await asyncio.to_thread(YouTubeTranscriptApi().list, video_id)
        transcript = next(iter(transcript_list))
        fetched = await asyncio.to_thread(transcript.fetch)
        text = " ".join(snippet.text for snippet in fetched)
    except Exception as exc:
        return TranscriptResult(
            ok=False, text="", reason=f"transcript unavailable: {exc}")
    if not text.strip():
        return TranscriptResult(
            ok=False, text="", reason="transcript was empty")
    return TranscriptResult(ok=True, text=text, reason="")


def fetch_transcript(url: str) -> TranscriptResult:
    """Compatibility wrapper for sync callers; phase 13 routes use async I/O."""
    return asyncio.run(fetch_transcript_async(url))
