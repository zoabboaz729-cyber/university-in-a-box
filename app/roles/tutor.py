"""Tutor Socratic logic — Phase 4 (no routes/DB here).

Two LLM tasks behind one prompt file (per architecture: one prompt
file per role): ASK returns the next single question, GAP returns the
short gap note at session end. Both use the Topic milestone + Shelf
as context plus the full transcript so far (P3: adapt to what was
actually said, never lecture).

Same error discipline as Advisor/Librarian: retry once on malformed
output, never return a half-parsed value. ProviderError propagates
(the provider already retried internally).
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.ai.provider import ProviderError  # noqa: F401 (re-exported for callers)

PARSE_ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError)

PROMPT_FILE = Path(__file__).with_name("prompts") / "tutor.md"

MAX_QUESTION_CHARS = 400


@dataclass
class NextQuestion:
    question: str


@dataclass
class GapNote:
    text: str


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines()
                 if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _parse_question(raw: str) -> NextQuestion:
    data = json.loads(_strip_fences(raw))
    question = data["question"]
    if not isinstance(question, str) or not question.strip():
        raise ValueError("tutor question is empty")
    question = question.strip()
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError("tutor question too long")
    if question.count("?") != 1:
        raise ValueError("tutor must ask exactly one question")
    return NextQuestion(question=question)


def _parse_gap(raw: str) -> GapNote:
    data = json.loads(_strip_fences(raw))
    text = data["gap_note"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("tutor gap note is empty")
    return GapNote(text=text.strip())


def format_transcript(turns: list) -> str:
    """Numbered Q/A transcript for the prompt. Turns are dicts with
    'question' and 'user_answer' (answer may be None for the pending Q)."""
    lines = []
    for i, turn in enumerate(turns, start=1):
        lines.append("Q%d: %s" % (i, turn["question"]))
        answer = turn.get("user_answer")
        if answer:
            lines.append("A%d: %s" % (i, answer))
    return "\n".join(lines)


def _context_block(topic_title: str, milestone: str, shelf_lines: str) -> str:
    return "\n".join([
        "Topic the user is studying: " + (topic_title or ""),
        "Topic milestone: " + (milestone or ""),
        "Trusted shelf (keep-only sources):",
        shelf_lines or "(empty shelf)",
    ])


def next_question(topic_title: str, milestone: str, shelf_lines: str,
                  turns: list, provider) -> NextQuestion:
    """Ask exactly one follow-up question via one LLM call (retried
    once on bad JSON). `provider` has .generate(system, user)."""
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        "TASK: ASK",
        _context_block(topic_title, milestone, shelf_lines),
        "Transcript so far:",
        format_transcript(turns) or "(no turns yet — ask the opening question)",
        "Ask exactly one follow-up question now.",
    ])
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_question(raw)
    except PARSE_ERRORS:
        raw = provider.generate(system_prompt, user_message)
        return _parse_question(raw)


def make_gap_note(topic_title: str, milestone: str, turns: list,
                  provider) -> GapNote:
    """Summarize the session into a 1-3 sentence gap note (retried
    once on bad JSON). Never returns a generic/empty note."""
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        "TASK: GAP",
        _context_block(topic_title, milestone, ""),
        "Full transcript:",
        format_transcript(turns) or "(no answers given)",
        "Write the gap note now.",
    ])
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_gap(raw)
    except PARSE_ERRORS:
        raw = provider.generate(system_prompt, user_message)
        return _parse_gap(raw)
