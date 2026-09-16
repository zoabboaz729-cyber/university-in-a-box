"""Phase 3 tests: source store + verify() (read-then-judge) parsing."""
import pytest

from app.roles import librarian
from app.roles.source_store import (
    add_source,
    delete_source,
    get_source,
    list_course_sources,
    list_sources,
    mark_verified,
)


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.last_message = ""

    def generate(self, system_prompt, user_message):
        self.calls += 1
        self.last_message = user_message
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


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


# --- Stage 3 Task 7: verify() reads the source, then judges ----------------

VERIFY_GOOD = ('{"accepted": true, "fit": "matches the milestone directly", '
               '"credibility": "a real, sourced explainer", '
               '"access": "free", '
               '"reason": "Read it — worked examples match the milestone."}')

VERIFY_REJECT = ('{"accepted": false, "fit": "covers a different topic", '
                 '"credibility": "thin marketing page", '
                 '"access": "unknown", '
                 '"reason": "Read it — it is a sales page, not study material."}')


def test_verify_parses_judgment_from_real_text():
    verification = librarian.verify(
        "Topic the user is studying: T", "Book", "https://example.com/b",
        "Actual page text.", FakeProvider([VERIFY_GOOD]))
    assert verification.accepted is True
    assert verification.fit == "matches the milestone directly"
    assert verification.credibility == "a real, sourced explainer"
    assert verification.access == "free"


def test_verify_parses_rejection():
    verification = librarian.verify(
        "Topic the user is studying: T", "Ad", "https://example.com/ad",
        "Buy now!", FakeProvider([VERIFY_REJECT]))
    assert verification.accepted is False
    assert verification.access == "unknown"


def test_verify_sends_the_fetched_text_to_the_model():
    """The judgment must be made from the text that was actually read."""
    provider = FakeProvider([VERIFY_GOOD])
    librarian.verify("Scope line", "Label", "ref",
                     "UNIQUE_SOURCE_SENTENCE", provider)
    assert "UNIQUE_SOURCE_SENTENCE" in provider.last_message
    assert "Scope line" in provider.last_message


def test_verify_retries_once_on_bad_json_then_parses():
    verification = librarian.verify("S", "L", "R", "text",
                                    FakeProvider(["not json", VERIFY_GOOD]))
    assert verification.accepted is True


def test_verify_retries_once_then_raises_clearly():
    with pytest.raises(ValueError):
        librarian.verify("S", "L", "R", "text",
                         FakeProvider(["nope", "still nope"]))


def test_verify_rejects_bad_access_value():
    bad = ('{"accepted": true, "fit": "f", "credibility": "c", '
           '"access": "cheap", "reason": "r"}')
    with pytest.raises(ValueError):
        librarian.verify("S", "L", "R", "text", FakeProvider([bad, bad]))


def test_verify_rejects_non_boolean_accepted():
    bad = ('{"accepted": "yes please", "fit": "f", "credibility": "c", '
           '"access": "free", "reason": "r"}')
    with pytest.raises(ValueError):
        librarian.verify("S", "L", "R", "text", FakeProvider([bad, bad]))


def test_verify_accepts_string_booleans_from_small_models():
    """Free-tier models often answer "false" as a string; that is a type
    slip, not a reason to burn the retry."""
    loose = ('{"accepted": "false", "fit": "f", "credibility": "c", '
             '"access": "paid", "reason": "r"}')
    verification = librarian.verify("S", "L", "R", "text",
                                    FakeProvider([loose]))
    assert verification.accepted is False


def test_verify_tolerates_markdown_fences():
    fenced = "```json\n" + VERIFY_GOOD + "\n```"
    verification = librarian.verify("S", "L", "R", "text",
                                    FakeProvider([fenced]))
    assert verification.accepted is True


def test_judgement_text_labels_access_as_the_models_judgment():
    """Access is never presented as fact (docs/01-VISION.md)."""
    verification = librarian.verify("S", "L", "R", "text",
                                    FakeProvider([VERIFY_GOOD]))
    text = librarian.judgement_text(verification)
    assert "Fit: matches the milestone directly" in text
    assert "Access: free (the model's judgment)." in text


def test_descriptors_carry_the_scope_context():
    topic_line = librarian.topic_descriptor(
        {"title": "Bayes", "milestone_description": "Derive it"})
    assert "Bayes" in topic_line and "Derive it" in topic_line
    course_line = librarian.course_descriptor(
        {"title": "Stats", "topics": [{"title": "A"}, {"title": "B"}]})
    assert "Stats" in course_line and "A, B" in course_line
    empty_line = librarian.course_descriptor({"title": "Stats", "topics": []})
    assert "(none yet)" in empty_line


def test_verify_prompt_demands_judging_from_the_actual_text():
    """The prompt carries the reversal of the old no-fetch rule."""
    prompt = (librarian.VERIFY_PROMPT_FILE.read_text(encoding="utf-8")).lower()
    assert "actual" in prompt
    assert "never" in prompt


# --- Stage 3 Task 7: source store scope / verification state ---------------


def _seed(tmp_path, monkeypatch, title):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    from tests.test_dashboard import seed_course
    return seed_course(title, topics=[(title + " Topic", "not_started")])


def test_store_requires_exactly_one_scope(tmp_path, monkeypatch):
    course_id, topic_ids = _seed(tmp_path, monkeypatch, "Scope Course")
    topic_id = topic_ids[0]
    with pytest.raises(ValueError):
        add_source(None, "Neither", "ref", "keep", "reason")
    with pytest.raises(ValueError):
        add_source(topic_id, "Both", "ref", "keep", "reason", None, course_id)
    with pytest.raises(ValueError):
        add_source(None, "Bad course", "ref", "keep", "reason", None, 9999)


def test_unverified_verdict_is_accepted_and_kept(tmp_path, monkeypatch):
    _, topic_ids = _seed(tmp_path, monkeypatch, "Unver Course")
    topic_id = topic_ids[0]
    source_id = add_source(topic_id, "Unread", "https://example.com/x",
                           "unverified", "Saved without verification: nope.")
    row = get_source(source_id)
    assert row["verdict"] == "unverified"
    assert row["verified_at"] is None
    with pytest.raises(ValueError):
        add_source(topic_id, "Bogus", "ref", "probably", "reason")


def test_mark_verified_then_delete(tmp_path, monkeypatch):
    _, topic_ids = _seed(tmp_path, monkeypatch, "Mark Course")
    topic_id = topic_ids[0]
    source_id = add_source(topic_id, "Later Read", "ref", "unverified",
                           "Saved without verification: x.")
    assert mark_verified(source_id, "keep", "Fit: yes. Access: free.",
                         "2026-09-14 10:00:00") is True
    row = get_source(source_id)
    assert (row["verdict"], row["verified_at"]) == (
        "keep", "2026-09-14 10:00:00")
    # "unverified" is not a judgment: mark_verified must refuse to store it.
    with pytest.raises(ValueError):
        mark_verified(source_id, "unverified", "x", "y")
    assert delete_source(source_id) is True
    assert get_source(source_id) is None
    assert delete_source(source_id) is False


def test_course_level_listing_excludes_topic_level_rows(tmp_path, monkeypatch):
    course_id, topic_ids = _seed(tmp_path, monkeypatch, "List Course")
    add_source(None, "Course Wide", "ref", "keep", "reason", None, course_id)
    add_source(topic_ids[0], "Topic Only", "ref", "keep", "reason")
    course_rows = list_course_sources(course_id)
    assert [r["label"] for r in course_rows] == ["Course Wide"]
    assert course_rows[0]["course_id"] == course_id
    assert course_rows[0]["topic_id"] is None
    assert [r["label"] for r in list_sources(topic_ids[0])] == ["Topic Only"]


def test_unverified_verdict_is_accepted_and_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    from tests.test_dashboard import seed_course
    _, topic_ids = seed_course("Unver Course",
                               topics=[("Unver Topic", "not_started")])
    topic_id = topic_ids[0]
    source_id = add_source(topic_id, "Unread", "https://example.com/x",
                           "unverified", "Saved without verification: nope.",
                           None)
    row = get_source(source_id)
    assert row["verdict"] == "unverified"
    assert row["verified_at"] is None
    with pytest.raises(ValueError):
        add_source(topic_id, "Bogus", "ref", "probably", "reason")


def test_mark_verified_then_delete_source(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    from tests.test_dashboard import seed_course
    _, topic_ids = seed_course("Mark Course",
                               topics=[("Mark Topic", "not_started")])
    topic_id = topic_ids[0]
    source_id = add_source(topic_id, "Later Read", "ref", "unverified",
                           "Saved without verification: x.", None)
    assert mark_verified(source_id, "keep", "Fit: yes. Access: free.",
                         "2026-09-14 10:00:00") is True
    row = get_source(source_id)
    assert (row["verdict"], row["verified_at"]) == (
        "keep", "2026-09-14 10:00:00")
    with pytest.raises(ValueError):
        mark_verified(source_id, "unverified", "x", "y")
    assert delete_source(source_id) is True
    assert get_source(source_id) is None
    assert delete_source(source_id) is False


def test_old_rows_migrate_to_unverified(tmp_path, monkeypatch):
    """Pre-Task-7 rows have no verified_at; they must read as unverified
    rather than as verified (docs/05-VERIFICATION.md: never claim more
    than the data supports)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import get_db_path, init_db
    init_db()
    from tests.test_dashboard import seed_course
    _, topic_ids = seed_course("Old Course",
                               topics=[("Old Topic", "not_started")])
    topic_id = topic_ids[0]
    add_source(topic_id, "Legacy", "ref", "keep", "reason")
    row = get_source(list_sources(topic_id)[0]["id"])
    assert row["verified_at"] is None
    import sqlite3
    with sqlite3.connect(get_db_path()) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
    assert {"course_id", "verified_at"} <= columns
