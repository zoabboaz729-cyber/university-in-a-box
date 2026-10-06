"""Librarian verification logic — Phase 3, extended Stage 3 Task 7
(no routes/DB here).

verify() is the mandatory step added by Stage 3 Task 7: it is given the
source's ACTUAL TEXT (fetched page, PDF text, or YouTube transcript) and
judges fit, credibility, and access from what was really read. This
reverses the original "the model never fetches the URL" rule — the
reversal is recorded in memory-bank/decisions.md as D-024. Nothing is ever stored
as verified without having been read; an unreadable source is the user's
explicit call (keep it visibly unverified, retry, or discard).

Same error discipline as the Advisor: retry once on
malformed output, never return a half-parsed judgment that could corrupt
data.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.ai.provider import call_provider_async

# Marker: malformed verdict JSON is a parse failure (retry the LLM
# once), but a ProviderError means the endpoint is down (don't retry —
# the provider already retried internally).
PARSE_ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError)

VERIFY_PROMPT_FILE = Path(__file__).with_name("prompts") / "librarian_verify.md"

# The stored-row verdict vocabulary lives in app/roles/source_store.py
# (VERDICTS); 'later' is legacy (pre-verify rows), and the live verify()
# flow only ever writes keep/skip via mark_verified().
ACCESS_VALUES = ("free", "paid", "unknown")


@dataclass
class SourceVerification:
    """The Librarian's judgment AFTER reading the source's real text."""

    accepted: bool
    fit: str
    credibility: str
    access: str  # "free" | "paid" | "unknown" — always the model's call
    reason: str


def _parse_verification(raw: str) -> SourceVerification:
    """Parse verification JSON. Raises ValueError on anything unexpected."""
    text = raw.strip()
    # Tolerate markdown fences if the model adds them despite instructions.
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    accepted = data["accepted"]
    # Small free models often answer "true"/"false" as strings; accepting
    # both costs nothing and avoids burning the retry on a type slip.
    if isinstance(accepted, str) and accepted.strip().lower() in ("true", "false"):
        accepted = accepted.strip().lower() == "true"
    if not isinstance(accepted, bool):
        raise ValueError("accepted is not a boolean: " + repr(accepted))
    fit = data["fit"]
    credibility = data["credibility"]
    access = data["access"]
    reason = data["reason"]
    if access not in ACCESS_VALUES:
        raise ValueError("access is not free|paid|unknown: " + repr(access))
    if not isinstance(fit, str) or not fit.strip():
        raise ValueError("judgment has no fit")
    if not isinstance(credibility, str) or not credibility.strip():
        raise ValueError("judgment has no credibility")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("judgment has no reason")
    return SourceVerification(
        accepted=accepted, fit=fit.strip(), credibility=credibility.strip(),
        access=access, reason=reason.strip())


def judgement_text(verification: SourceVerification) -> str:
    """The single stored/displayed line for one verification judgment.

    Carries the model's own one-line reason FIRST (that is the part a
    rejection page must show) followed by the three judgment fields.
    Access is always labelled as the model's judgment — never presented
    as fact (docs/01-VISION.md: the Librarian advises, the user decides).
    """
    return ("Read: " + verification.reason
            + " Fit: " + verification.fit
            + " Credibility: " + verification.credibility
            + " Access: " + verification.access + " (the model's judgment).")


def topic_descriptor(topic: dict) -> str:
    """Context the source must serve, for a TOPIC-level source."""
    return ("Topic the user is studying: " + topic["title"]
            + "\nTopic milestone: " + (topic.get("milestone_description") or ""))


def course_descriptor(course: dict) -> str:
    """Context the source must serve, for a COURSE-level source."""
    titles = ", ".join(t["title"] for t in (course.get("topics") or []))
    return ("Course the user is building: " + course["title"]
            + "\nTopics in this course: " + (titles or "(none yet)"))


def verify(scope_descriptor: str, label: str, reference: str, source_text: str,
           provider) -> SourceVerification:
    """Judge ONE source from the text that was actually read.

    One LLM call, retried once on malformed output.
    This function never fetches anything: routes own the fetch (via
    app.fetching), roles own the judgment (docs/02-ARCHITECTURE.md).

    ProviderError is NOT caught here: it means the endpoint is down, and
    the provider already retried.
    """
    system_prompt = VERIFY_PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        scope_descriptor,
        "Source label: " + label,
        "Source URL or reference: " + (reference or ""),
        "--- SOURCE TEXT (truncated) ---",
        source_text,
    ])
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_verification(raw)
    except PARSE_ERRORS:
        # Bad JSON from the model — retry the LLM once with the same
        # prompt, then let the error surface clearly.
        raw = provider.generate(system_prompt, user_message)
        return _parse_verification(raw)


async def verify_async(scope_descriptor: str, label: str, reference: str,
                      source_text: str, provider) -> SourceVerification:
    """Async variant used by librarian routes so outbound fetch and AI calls are non-blocking."""
    system_prompt = VERIFY_PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        scope_descriptor,
        "Source label: " + label,
        "Source URL or reference: " + (reference or ""),
        "--- SOURCE TEXT (truncated) ---",
        source_text,
    ])
    raw = await call_provider_async(provider, system_prompt, user_message)
    try:
        return _parse_verification(raw)
    except PARSE_ERRORS:
        raw = await call_provider_async(provider, system_prompt, user_message)
        return _parse_verification(raw)
