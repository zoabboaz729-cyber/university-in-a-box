"""Roommate cross-domain prompt logic — Phase 6 (+ Phase 11 intra-group).

Two responsibilities, both small:
1. build_prompt — the role itself: one LLM call returns
   {"field", "prompt"} connecting what the user is studying to a
   genuinely different field (P5). Pure logic, no DB calls, same
   contract as editor.py / tutor.py.
2. generate_due_prompts — the dashboard-load due-check. It composes this
   role with its own store (per 02-ARCHITECTURE: a role writes its own
   persisted output) so the dashboard route stays a one-line call. One
   course's failure is logged and skipped; it never blocks the rest.

Phase 11 (P5 — range, now also BETWEEN concurrent courses): a due active
course that shares a group with another ACTIVE course gets an intra-group
bridge prompt connecting its current topic to the peer's current topic
(build_intra_group_prompt, persisted with connection_type='intra_group'
and secondary_course_id). Frequency is bounded by the ordinary cadence —
each course still gets exactly one prompt per due-check. When both sides
of a pair are due at once, each course gets its own bridge (two
complementary perspectives, not a doubled workload).

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
INTRA_PROMPT_FILE = Path(__file__).with_name("prompts") / "roommate_intra.md"

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


def build_intra_group_prompt(course_a_title: str, course_a_destination: str,
                             course_a_topic: str, course_b_title: str,
                             course_b_destination: str, course_b_topic: str,
                             recent_labels: list, provider) -> Connection:
    """One short cross-course bridge prompt via one LLM call (retried once).

    Phase 11 (P5): instead of reaching OUT to an unrelated field, the
    Roommate bridges two courses the user is actively taking together in
    the same group — the "field" is the connection LABEL between them,
    and the prompt moves ideas from Course A's current topic to Course
    B's current topic (and back). Same structural contract as
    build_prompt so the journal behaves identically.
    """
    system_prompt = INTRA_PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        "Course A the user is studying: " + (course_a_title or ""),
        "Course A destination: " + (course_a_destination or ""),
        "Topic in Course A right now: " + (course_a_topic or ""),
        "Course B the user is also studying (same semester/group): "
        + (course_b_title or ""),
        "Course B destination: " + (course_b_destination or ""),
        "Topic in Course B right now: " + (course_b_topic or ""),
        "Bridges already written for this course:",
        ", ".join(recent_labels[-RECENT_FIELDS_CONTEXT:]) or "(none yet)",
        "Write exactly one new bridge now.",
    ])
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_connection(raw, recent_labels)
    except PARSE_ERRORS:
        raw = provider.generate(system_prompt, user_message)
        return _parse_connection(raw, recent_labels)


def generate_due_prompts(provider) -> list[int]:
    """Generate and persist one prompt per due active course.

    Called on every dashboard load (Phase 6 step 2 — a local single-user
    app needs no job scheduler). Each course is isolated: a provider or
    parse failure logs one 'generate_failed' activity row and the course
    waits for the next dashboard load — the page itself always renders.

    Phase 11 (P5): a due active course that shares a group with another
    ACTIVE course gets an intra-group cross-course bridge prompt (the
    course's one prompt per cadence, like every other prompt — no extra
    spamming); without a group peer the classic unrelated-field prompt
    is built. Both are saved through the same store and journal.
    """
    created = []
    for course in roommate_store.due_courses(cadence_days()):
        peer = roommate_store.peer_course(course["id"])
        try:
            if peer is not None:
                connection = build_intra_group_prompt(
                    course["title"], course["destination"],
                    course["current_topic_title"],
                    peer["title"], peer["destination"],
                    peer["current_topic_title"],
                    roommate_store.recent_fields(
                        course["id"], RECENT_FIELDS_CONTEXT),
                    provider,
                )
                save_kwargs = {
                    "secondary_course_id": peer["id"],
                    "connection_type": "intra_group",
                }
            else:
                connection = build_prompt(
                    course["title"], course["destination"],
                    course["current_topic_title"],
                    roommate_store.recent_fields(
                        course["id"], RECENT_FIELDS_CONTEXT),
                    provider,
                )
                save_kwargs = {}
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
                roommate_store.save_prompt(
                    course["id"], connection.field, connection.prompt,
                    **save_kwargs))
        except ValueError as exc:
            # Only reachable if a course vanished mid-check (e.g. the peer
            # was deleted between the peer query and the save).
            get_logger().warning(
                "Roommate: save failure for course %s: %s",
                course["id"], exc)
            roommate_store.log_generate_failed(course["id"], str(exc))
    return created