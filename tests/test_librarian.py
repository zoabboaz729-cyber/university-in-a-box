"""Phase 3 tests part 1: triage parsing + source store."""
import pytest

from app.roles import librarian
from app.roles.source_store import add_source, list_sources


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


GOOD = ('{"verdict": "keep", "good_for": "hands-on practice", '
        '"reason": "Worked examples match the milestone exactly."}')


def test_triage_parses_verdict():
    verdict = librarian.triage("T", "M", "L", "R", FakeProvider([GOOD]))
    assert verdict.verdict == "keep"
    assert verdict.good_for == "hands-on practice"
    assert "milestone" in verdict.reason


def test_triage_retries_once_on_bad_json_then_parses():
    verdict = librarian.triage("T", "M", "L", "R",
                               FakeProvider(["not json", GOOD]))
    assert verdict.verdict == "keep"


def test_triage_rejects_bad_verdict_value():
    bad = ('{"verdict": "maybe", "good_for": "x", "reason": "y"}')
    with pytest.raises(ValueError):
        librarian.triage("T", "M", "L", "R", FakeProvider([bad, bad]))


def test_add_and_list_sources_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    from tests.test_dashboard import seed_course
    _, topic_ids = seed_course("Lib Course",
                               topics=[("Lib Topic", "not_started")])
    topic_id = topic_ids[0]
    add_source(topic_id, "Strong Book", "https://example.com/book",
               "keep", "Good for background. Deep and credible.")
    add_source(topic_id, "Weak Link", "https://example.com/click",
               "skip", "Good for nothing now. Thin listicle.")
    rows = list_sources(topic_id)
    assert [r["label"] for r in rows] == ["Weak Link", "Strong Book"]
    shelf = list_sources(topic_id, keep_only=True)
    assert [r["label"] for r in shelf] == ["Strong Book"]
    with pytest.raises(ValueError):
        add_source(topic_id, "   ", "ref", "keep", "reason")
    with pytest.raises(ValueError):
        add_source(9999, "Label", "ref", "keep", "reason")
