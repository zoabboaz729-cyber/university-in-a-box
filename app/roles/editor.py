"""Editor review logic — Phase 5 (no routes/DB here).

One LLM task: given the submitted text and the Topic's milestone,
return structured feedback — strengths, exactly one biggest weakness,
one concrete next edit (P4: only real user output is reviewed; the
build-plan constraint forbids a bare list of positives with nothing
actionable, so parse validation enforces all three fields).

Same error discipline as Advisor/Librarian/Tutor: retry once on
malformed output, never return a half-parsed value. ProviderError
propagates (the provider already retried internally).
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.ai.provider import ProviderError  # noqa: F401 (re-exported for callers)

PARSE_ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError)

PROMPT_FILE = Path(__file__).with_name("prompts") / "editor.md"

MAX_SUBMISSION_CHARS = 8000
MAX_STRENGTHS_CHARS = 450
MAX_WEAKNESS_CHARS = 300
MAX_EDIT_CHARS = 300


@dataclass
class Review:
    strengths: str
    biggest_weakness: str
    next_edit: str


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines()
                 if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _parse_review(raw: str) -> Review:
    data = json.loads(_strip_fences(raw))
    fields = (
        ("strengths", data["strengths"], MAX_STRENGTHS_CHARS),
        ("biggest_weakness", data["biggest_weakness"], MAX_WEAKNESS_CHARS),
        ("next_edit", data["next_edit"], MAX_EDIT_CHARS),
    )
    parsed = {}
    for name, value, cap in fields:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("editor " + name + " is empty")
        if len(value.strip()) > cap:
            raise ValueError("editor " + name + " too long")
        parsed[name] = value.strip()
    return Review(strengths=parsed["strengths"],
                  biggest_weakness=parsed["biggest_weakness"],
                  next_edit=parsed["next_edit"])


def review_submission(topic_title: str, milestone: str, submitted_text: str,
                      provider) -> Review:
    """Review real user work against the milestone (retried once on bad JSON).

    `provider` is any object with .generate(system_prompt, user_message).
    ProviderError is NOT caught here: it means the endpoint is down, and
    the provider already retried.
    """
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        "Topic the user is studying: " + topic_title,
        "Topic milestone (the bar this work is judged against): "
        + (milestone or ""),
        "The user submitted this work for review:",
        "---",
        submitted_text,
        "---",
        "Review it now.",
    ])
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_review(raw)
    except PARSE_ERRORS:
        # Bad JSON from the model — retry the LLM once with the same
        # prompt, then let the error surface clearly.
        raw = provider.generate(system_prompt, user_message)
        return _parse_review(raw)