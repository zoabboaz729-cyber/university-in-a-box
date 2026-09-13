"""Librarian triage logic — Phase 3 (no routes/DB here).

Given a source description/URL and the Topic's context, one LLM call
returns a verdict (keep|skip|later) + what-it's-good-for + one-line
reason. Same error discipline as the Advisor: retry once on malformed
output, never return a half-parsed verdict that could corrupt data.
The model never fetches the URL — fit/credibility is judged from the
user's description plus the URL/domain (P2: narrow the pile, don't
just store links).
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.ai.provider import ProviderError

# Marker: malformed verdict JSON is a parse failure (retry the LLM
# once), but a ProviderError means the endpoint is down (don't retry —
# the provider already retried internally).
PARSE_ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError)

PROMPT_FILE = Path(__file__).with_name("prompts") / "librarian.md"

VERDICTS = ("keep", "skip", "later")


@dataclass
class SourceVerdict:
    verdict: str
    good_for: str
    reason: str


def _parse_verdict(raw: str) -> SourceVerdict:
    """Parse the LLM's JSON verdict. Raises ValueError on anything unexpected."""
    text = raw.strip()
    # Tolerate markdown fences if the model adds them despite instructions.
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    verdict = data["verdict"]
    good_for = data["good_for"]
    reason = data["reason"]
    if verdict not in VERDICTS:
        raise ValueError("verdict is not keep|skip|later: " + repr(verdict))
    if not isinstance(good_for, str) or not good_for.strip():
        raise ValueError("verdict has no good_for")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("verdict has no reason")
    return SourceVerdict(
        verdict=verdict, good_for=good_for.strip(), reason=reason.strip()
    )


def triage(topic_title: str, milestone: str, label: str, reference: str,
           provider) -> SourceVerdict:
    """Judge one candidate source via one LLM call (retried once on bad JSON).

    `provider` is any object with .generate(system_prompt, user_message).
    ProviderError is NOT caught here: it means the endpoint is down, and
    the provider already retried.
    """
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    user_message = "\n".join([
        "Topic the user is studying: " + topic_title,
        "Topic milestone: " + (milestone or ""),
        "Source label: " + label,
        "Source URL or reference: " + (reference or ""),
    ])
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_verdict(raw)
    except PARSE_ERRORS:
        # Bad JSON from the model — retry the LLM once with the same
        # prompt, then let the error surface clearly.
        raw = provider.generate(system_prompt, user_message)
        return _parse_verdict(raw)
