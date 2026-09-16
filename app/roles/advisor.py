"""Advisor interview logic — Phase 1a (no routes/DB here).

The five-step interview (destination → baseline → sequencing → cut_list →
milestones) uses FIXED questions asked strictly one at a time. This is
deliberate: fixed questions guarantee all five steps are covered (P1) and keep
behavior deterministic without depending on the LLM to pace itself. The LLM is
used exactly once — to turn the five answers into a curriculum draft.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.ai.provider import ProviderError

# Marker: malformed draft JSON is a parse failure (retry the LLM once),
# but a ProviderError means the endpoint itself is down (don't retry —
# the provider already retried internally). Without this, one outage
# would cost 4 HTTP calls instead of 2.
PARSE_ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError)

PROMPT_FILE = Path(__file__).with_name("prompts") / "advisor.md"

# Fixed order. Each step is asked exactly once, one question at a time.
STEPS = ["destination", "baseline", "sequencing", "cut_list", "milestones"]

STEP_QUESTIONS = {
    "destination": (
        "What does 'done' look like for you? Describe where you want to end up "
        "— what you'll be able to do that you can't do now."
    ),
    "baseline": (
        "Where are you starting from? What do you already know about this, "
        "and what have you already tried?"
    ),
    "sequencing": (
        "How much time can you realistically give this per week, and for how "
        "many weeks? Any deadlines or order constraints I should know about?"
    ),
    "cut_list": (
        "What should we deliberately skip or leave out? (Sub-topics, rabbit "
        "holes, or things you've decided don't matter for your goal.)"
    ),
    "milestones": (
        "How will you prove to yourself it's working? Name one or two concrete "
        "things you'd like to produce along the way (e.g. a write-up, a small "
        "project, solving a set of problems)."
    ),
}


@dataclass
class DraftTopic:
    title: str
    milestone_description: str
    time_box: str = ""


@dataclass
class CurriculumDraft:
    course_title: str
    topics: list = field(default_factory=list)


def next_step(answered_steps: set) -> str | None:
    """Return the next unanswered step, or None when all five are answered."""
    for step in STEPS:
        if step not in answered_steps:
            return step
    return None


def question_for(step: str) -> str:
    return STEP_QUESTIONS[step]


def _parse_draft(raw: str) -> CurriculumDraft:
    """Parse the LLM's JSON draft. Raises ValueError on anything unexpected."""
    text = raw.strip()
    # Tolerate markdown fences if the model adds them despite instructions.
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    title = data["course_title"]
    raw_topics = data["topics"]
    if not isinstance(title, str) or not title.strip():
        raise ValueError("draft has no course_title")
    if not isinstance(raw_topics, list) or not raw_topics:
        raise ValueError("draft has no topics list")
    topics = []
    for item in raw_topics:
        topic_title = item["title"]
        milestone = item["milestone_description"]
        if not topic_title or not milestone:
            raise ValueError("draft topic missing title or milestone_description")
        topics.append(
            DraftTopic(
                title=str(topic_title).strip(),
                milestone_description=str(milestone).strip(),
                time_box=str(item.get("time_box", "") or "").strip(),
            )
        )
    # Task 4 hardening: an implausible topic count is a model failure —
    # reject it so build_draft's retry path reruns the LLM once. Bounds are
    # deliberately wide (3–15): the PROMPT decides the count (derived from
    # the stated time budget, typically 4–8); this check only catches
    # degenerate output like a 1-topic or 40-topic filler dump.
    if not 3 <= len(topics) <= 15:
        raise ValueError("draft topic count outside 3-15: " + str(len(topics)))
    return CurriculumDraft(course_title=title.strip(), topics=topics)


def build_draft(topic: str, answers: dict, provider) -> CurriculumDraft:
    """Turn the five interview answers into a curriculum draft via one LLM call.

    `provider` is any object with .generate(system_prompt, user_message).
    Retries the LLM call once on malformed output, then raises a clear error —
    never returns a half-parsed draft that could corrupt persisted data.
    """
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    lines = ["Topic the user wants to learn: " + topic]
    for step in STEPS:
        lines.append(step.upper() + ": " + answers.get(step, ""))
    user_message = "\n".join(lines)
    raw = provider.generate(system_prompt, user_message)
    try:
        return _parse_draft(raw)
    except PARSE_ERRORS:
        # Bad JSON from the model — retry the LLM once with the same prompt,
        # then let the error surface clearly. ProviderError is NOT caught here:
        # it means the endpoint is down, and the provider already retried.
        raw = provider.generate(system_prompt, user_message)
        return _parse_draft(raw)
