"""Phase 4 tests part 1: tutor parsing + store roundtrip."""
import pytest

from app.roles import tutor
from app.roles.tutor_store import (
    add_turn,
    end_session,
    find_open_session,
    get_session,
    last_gap_for_course,
    list_sessions_for_topic,
    save_answer,
    start_session,
)


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


Q1 = '{"question": "What is the core idea here?"}'
GAP = '{"gap_note": "Mixes up X and Y. Rework the milestone example."}'


def _seed_topic():
    from tests.test_dashboard import seed_course
    _, topic_ids = seed_course("Tutor Course",
                               topics=[("Tutor Topic", "not_started")])
    return topic_ids[0]


def test_next_question_parses_single_question():
    q = tutor.next_question("T", "M", "", [], FakeProvider([Q1]))
    assert q.question == "What is the core idea here?"


def test_next_question_retries_once_on_bad_json():
    q = tutor.next_question("T", "M", "", [], FakeProvider(["nope", Q1]))
    assert q.question.endswith("?")


def test_next_question_rejects_two_questions():
    bad = '{"question": "Is this X? Or is it Y?"}'
    with pytest.raises(ValueError):
        tutor.next_question("T", "M", "", [], FakeProvider([bad, bad]))


def test_next_question_rejects_lecture_without_question():
    bad = '{"question": "Here is a long explanation with no question at all"}'
    with pytest.raises(ValueError):
        tutor.next_question("T", "M", "", [], FakeProvider([bad, bad]))


def test_gap_note_parses():
    gap = tutor.make_gap_note("T", "M", [], FakeProvider([GAP]))
    assert "X and Y" in gap.text


def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    topic_id = _seed_topic()
    sid = start_session(topic_id, user_id=1)
    assert find_open_session(topic_id, user_id=1) == sid
    tid = add_turn(sid, "What is the core idea here?", user_id=1)
    save_answer(tid, "Something about X", user_id=1)
    end_session(sid, "Mixes up X and Y. Rework it.", user_id=1)
    assert find_open_session(topic_id, user_id=1) is None
    sess = get_session(sid, user_id=1)
    assert sess["turns"][0]["user_answer"] == "Something about X"
    assert sess["gap_note"].startswith("Mixes up")
    assert list_sessions_for_topic(topic_id, user_id=1)[0]["turn_count"] == 1
    with pytest.raises(ValueError):
        save_answer(tid, "   ", user_id=1)
    with pytest.raises(ValueError):
        end_session(sid, "  ", user_id=1)
    with pytest.raises(ValueError):
        start_session(9999, user_id=1)


def test_last_gap_for_course(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()
    from tests.test_dashboard import seed_course
    course_id, topic_ids = seed_course("Gap Course",
                                       topics=[("GT", "not_started")])
    assert last_gap_for_course(course_id) is None
    sid = start_session(topic_ids[0], user_id=1)
    add_turn(sid, "Q?", user_id=1)
    end_session(sid, "The gap text.", user_id=1)
    assert last_gap_for_course(course_id) == "The gap text."
