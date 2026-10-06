"""Phase 5 tests part 1: editor parsing + store roundtrip + gating helper."""
import json

import pytest

from app.roles import editor
from app.roles.editor import Review
from app.roles.review_store import (
    has_editor_review,
    last_review_note_for_course,
    list_reviews_for_topic,
    save_review,
)


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


GOOD = json.dumps({
    "strengths": "The argument is direct and cites the source.",
    "biggest_weakness": "The example contradicts the claim about X.",
    "next_edit": "Replace the X example with the Q2 case.",
})


def _seed_topic():
    from tests.test_dashboard import seed_course
    _, topic_ids = seed_course("Editor Course",
                               topics=[("ET", "not_started")])
    return topic_ids[0]


def test_review_submission_parses_three_fields():
    r = editor.review_submission("T", "M", "My work", FakeProvider([GOOD]))
    assert r.strengths.startswith("The argument")
    assert r.biggest_weakness == "The example contradicts the claim about X."
    assert r.next_edit.startswith("Replace the X")


def test_review_submission_retries_once_on_bad_json():
    provider = FakeProvider(["nope", GOOD])
    r = editor.review_submission("T", "M", "My work", provider)
    assert r.next_edit.endswith("Q2 case.")
    assert provider.calls == 2  # one bad reply, one retry


def test_review_submission_tolerates_markdown_fences():
    fenced = "```json\n" + GOOD + "\n```"
    r = editor.review_submission("T", "M", "My work", FakeProvider([fenced]))
    assert r.biggest_weakness.startswith("The example")


def test_review_rejects_empty_weakness():
    bad = json.dumps({"strengths": "s", "biggest_weakness": "  ",
                      "next_edit": "e"})
    with pytest.raises(ValueError):
        editor.review_submission("T", "M", "My work",
                                 FakeProvider([bad, bad]))


def test_review_rejects_missing_key():
    bad = '{"strengths": "s", "biggest_weakness": "w"}'
    # Same convention as Tutor/Librarian: a missing JSON key is a parse
    # failure (KeyError), retried once, then allowed to surface.
    with pytest.raises((ValueError, KeyError)):
        editor.review_submission("T", "M", "My work",
                                 FakeProvider([bad, bad]))


def test_review_rejects_overlong_field():
    bad = json.dumps({"strengths": "x" * 500, "biggest_weakness": "w",
                      "next_edit": "e"})
    with pytest.raises(ValueError):
        editor.review_submission("T", "M", "My work",
                                 FakeProvider([bad, bad]))


def test_store_roundtrip_and_gate_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    topic_id = _seed_topic()
    assert has_editor_review(topic_id, user_id=1) is False
    assert list_reviews_for_topic(topic_id, user_id=1) == []
    rid = save_review(topic_id, "Milestone for ET", "My submitted work",
                      Review(strengths="s", biggest_weakness="w",
                             next_edit="e"), user_id=1)
    assert has_editor_review(topic_id, user_id=1) is True
    rows = list_reviews_for_topic(topic_id, user_id=1)
    assert len(rows) == 1 and rows[0]["id"] == rid
    assert rows[0]["submitted_text"] == "My submitted work"
    assert rows[0]["milestone_ref"] == "Milestone for ET"
    assert rows[0]["biggest_weakness"] == "w"
    with pytest.raises(ValueError):
        save_review(9999, "m", "text",
                    Review(strengths="s", biggest_weakness="w",
                           next_edit="e"), user_id=1)
    with pytest.raises(ValueError):
        save_review(topic_id, "m", "   ",
                    Review(strengths="s", biggest_weakness="w",
                           next_edit="e"), user_id=1)
    with pytest.raises(ValueError):
        save_review(topic_id, "m", "text",
                    Review(strengths="s", biggest_weakness="", next_edit="e"),
                    user_id=1)


def test_reviews_survive_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    topic_id = _seed_topic()
    save_review(topic_id, "Milestone for ET", "Work text",
                Review(strengths="s", biggest_weakness="weak point",
                       next_edit="edit"), user_id=1)
    import sqlite3
    from app.db import get_db_path
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT strengths, biggest_weakness, next_edit, submitted_text "
            "FROM editor_reviews WHERE topic_id = ?", (topic_id,)
        ).fetchone()
        assert row["biggest_weakness"] == "weak point"
        assert row["submitted_text"] == "Work text"


def test_last_review_note_for_course(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    from tests.test_dashboard import seed_course
    course_id, topic_ids = seed_course(
        "Note Course", topics=[("NT", "not_started")])
    assert last_review_note_for_course(course_id) is None
    save_review(topic_ids[0], "m", "text",
                Review(strengths="s", biggest_weakness="the weak bit",
                       next_edit="the edit"), user_id=1)
    note = last_review_note_for_course(course_id)
    assert "the weak bit" in note and "the edit" in note
    # A second topic's newer review wins (newest across the course).
    _, t2 = seed_course("Note Course 2", topics=[("NT2", "not_started")])
    save_review(t2[0], "m", "text",
                Review(strengths="s", biggest_weakness="newer weakness",
                       next_edit="newer edit"), user_id=1)
    # Seeding created a NEW course, so query that course for its own note.
    assert "newer weakness" in last_review_note_for_course(course_id + 1)