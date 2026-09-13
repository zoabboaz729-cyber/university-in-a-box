"""Roommate cross-domain prompt logic — Phase 6.

Two responsibilities, both small:
1. build_prompt — the role itself: one LLM call returns
   {"field", "prompt"} connecting what the user is studying to a
   genuinely different field (P5). Pure logic, no DB calls, same
   contract as editor.py / tutor.py.
2. generate_due_prompts — the dashboard-load due-check. It composes this
   role with its own store (per 02-ARCHITECTURE: a role writes its own
   persisted output) so the dashboard route stays a one-line call. One
   course's failure is logged and skipped; it never blocks the rest.

Same error discipline as every role: retry once on malformed output,
never return a half-parsed value. ProviderError propagates out of
build_prompt; generate_due_prompts catches it per course.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.ai.provider import ProviderError
from app.monitor import get_logger
from app.roles import roommate_store

PARSE_ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError)

PROMPT_FILE = Path(__file__).with_name("prompts") / "roommate.md"

# Hard caps: a connection that takes longer than a few seconds to read
# has stopped being a nudge (VISION: reading it takes seconds).
MAX_FIELD_CHARS = 40
MAX_PROMPT_CHARS = 500
# How many past fields are shown to the LLM (and checked against) so it
# keeps picking genuinely new directions.
RECENT_FIELDS_CONTEXT = 8

DEFAULT_CADENCE_DAYS = 3


@dataclass
class Connection:
    field: str
    prompt: str


def cadence_days() -> int:
    """Roommate cadence — 'a couple of times a week' = 3 days by default.

    Overridable via ROOMMATE_CADENCE_DAYS (never below 1). Phase 7's
    Settings page will expose the same knob.
    """
    raw = os.environ.get("ROOMMATE_CADENCE_DAYS", str(DEFAULT_CADENCE_DAYS))
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_CADENCE_DAYS
    return max(1, days)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines()
                 if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _parse_connection(raw: str, recent_fields: list) -> Connection:
    data = json.loads(_strip_fences(raw))
    field = data["field"]
    prompt = data["prompt"]
    if not isinstance(field, str) or not field.strip():
        raise ValueError("roommate field is empty")
    field = field.strip()
    if len(field) > MAX_FIELD_CHARS:
        raise ValueError("roommate field too long")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("roommate prompt is empty")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError("roommate prompt too long")
    if field in recent_fields:
        raise ValueError("roommate field already used")
    return Connection(field=field, prompt=prompt)


def build_prompt(course_title: str, destination: str,
                 current_topic_title: str, recent_fields: list,
                 provider) -> Connection:
    """One short cross-domain prompt via one LLM call (retried once)."""
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        "Course the user is studying: " + (course_title or ""),
        "Course destination: " + (destination or ""),
        "Topic the user is on right now: " + (current_topic_title or ""),
        "Fields already connected for this course:",
        ", ".join(recent_fields[-RECENT_FIELDS_CONTEXT:]) or "(none yet)",
        "Write exactly one new connection now.",
    ])
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_connection(raw, recent_fields)
    except PARSE_ERRORS:
        # Bad JSON / empty / duplicate field — retry the LLM once, then
        # let the error surface for generate_due_prompts to handle.
        raw = provider.generate(system_prompt, user_message)
        return _parse_connection(raw, recent_fields)


def generate_due_prompts(provider) -> list[int]:
    """Generate and persist one prompt per due active course.

    Called on every dashboard load (Phase 6 step 2 — a local single-user
    app needs no job scheduler). Each course is isolated: a provider or
    parse failure logs one 'generate_failed' activity row and the course
    waits for the next dashboard load — the page itself always renders.
    """
    created = []
    for course in roommate_store.due_courses(cadence_days()):
        try:
            connection = build_prompt(
                course["title"], course["destination"],
                course["current_topic_title"],
                roommate_store.recent_fields(course["id"], RECENT_FIELDS_CONTEXT),
                provider,
            )
        except ProviderError as exc:
            get_logger().warning(
                "Roommate: provider failure for course %s: %s",
                course["id"], exc)
            roommate_store.log_generate_failed(course["id"],
                                               "provider: " + str(exc))
            continue
        except PARSE_ERRORS as exc:
            get_logger().warning(
                "Roommate: parse failure for course %s: %s",
                course["id"], exc)
            roommate_store.log_generate_failed(course["id"],
                                               "parse: " + str(exc))
            continue
        try:
            created.append(
                roommate_store.save_prompt(course["id"], connection.field,
                                           connection.prompt))
        except ValueError as exc:
            # Only reachable if the course vanished mid-check.
            get_logger().warning(
                "Roommate: save failure for course %s: %s",
                course["id"], exc)
            roommate_store.log_generate_failed(course["id"], str(exc))
    return created