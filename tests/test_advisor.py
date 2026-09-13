"""Phase 1a tests: interview pacing + draft parsing, LLM mocked (no API key needed).

Covers: next_step walks the five steps in order and returns None when done;
every step has a non-empty fixed question; build_draft parses a well-formed
JSON draft; build_draft retries once on garbage then surfaces a clear error
instead of returning a half-parsed draft.
"""
import pytest

from app.ai.provider import ProviderError
from app.roles import advisor


class FakeProvider:
    """Stands in for the real LLM. Scripted responses, one per generate() call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        response = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response


GOOD_DRAFT = (
    '{"course_title": "Test Course", "topics": ['
    '{"title": "T1", "milestone_description": "Write a one-page summary.", '
    '"time_box": "1 week"}, '
    '{"title": "T2", "milestone_description": "Solve five practice problems.", '
    '"time_box": "1 week"}]}'
)

ANSWERS = {
    "destination": "d",
    "baseline": "b",
    "sequencing": "s",
    "cut_list": "c",
    "milestones": "m",
}


def test_next_step_walks_five_steps_in_order():
    assert advisor.next_step(set()) == "destination"
    answered = {"destination", "baseline"}
    assert advisor.next_step(answered) == "sequencing"
    answered = set(advisor.STEPS)
    assert advisor.next_step(answered) is None


def test_every_step_has_a_question():
    for step in advisor.STEPS:
        question = advisor.question_for(step)
        assert isinstance(question, str) and question.strip()


def test_build_draft_parses_good_json():
    draft = advisor.build_draft("X", ANSWERS, FakeProvider([GOOD_DRAFT]))
    assert draft.course_title == "Test Course"
    assert len(draft.topics) == 2
    assert draft.topics[0].milestone_description.startswith("Write")


def test_build_draft_retries_once_then_raises_clearly():
    provider = FakeProvider(["not json at all", "still not json"])
    with pytest.raises(Exception):
        advisor.build_draft("X", ANSWERS, provider)
    assert provider.calls == 2


def test_provider_error_propagates_without_parse():
    # The provider retries internally (once) then raises; build_draft must NOT
    # retry on ProviderError — a dead endpoint shouldn't cost 4 calls.
    # So generate() is called exactly once here.
    provider = FakeProvider([ProviderError("down"), ProviderError("down")])
    with pytest.raises(ProviderError):
        advisor.build_draft("X", ANSWERS, provider)
    assert provider.calls == 1
