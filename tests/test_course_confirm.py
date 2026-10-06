"""Phase 1c tests: confirm-curriculum persists the Course + Topics and flips it active.

Covers: the /confirm POST reads the edited review-box fields and writes an
active Course with ordered Topics (title, milestone, time box), keeps the
interview transcript, and redirects to the course page; double-confirm is
idempotent; confirm is blocked mid-interview; blank title/milestone re-renders
the review page with an inline error and writes nothing (and blank-milestone
rows are dropped, keeping the valid rest); a fresh connection (restart-style)
still sees the Course and its Topics. LLM mocked — no key needed.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.main import api
from app.roles import advisor
from app.roles import course_store
from app.roles.interview_store import start_interview

ANSWERS = {
    "destination": "reach conversational level",
    "baseline": "know a few words",
    "sequencing": "30 min a day for 8 weeks",
    "cut_list": "skip classical literature",
    "milestones": "hold a 5-minute conversation",
}

GOOD_DRAFT = (
    '{"course_title": "Test Course", "topics": ['
    '{"title": "T1", "milestone_description": "Write a one-page summary.", "time_box": "1 week"}, '
    '{"title": "T2", "milestone_description": "Solve five practice problems.", "time_box": "2 weeks"}, '
    '{"title": "T3", "milestone_description": "Explain the concept aloud.", "time_box": "3 weeks"}]}'
)


class FakeProvider:
    def generate(self, system_prompt, user_message):
        return GOOD_DRAFT


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    import app.routes.advisor_review  # noqa: F401 (register review routes)
    return TestClient(api)


def start_and_answer(client):
    """Start an interview and answer all five steps (lands on the review page)."""
    client.post("/advisor/new", data={"topic": "Spanish"})
    for step in advisor.STEPS:
        response = client.post(
            "/advisor/1",
            data={"step": step, "answer": ANSWERS[step]},
        )
        assert response.status_code == 200


def confirm_data(edits=None):
    """Form data for POST /advisor/1/confirm, edited values by default."""
    data = {
        "course_title": "Conversational Spanish",
        "title-0": "Pronunciation basics",
        "milestone-0": "Record yourself reading a short paragraph aloud.",
        "timebox-0": "1 week",
        "title-1": "Everyday vocabulary",
        "milestone-1": "Hold a 5-minute conversation about your day.",
        "timebox-1": "2 weeks",
        "title-2": "Idioms in context",
        "milestone-2": "Write a story using five idioms you learned.",
        "timebox-2": "3 weeks",
    }
    if edits:
        data.update(edits)
    return data


def course_row(conn, course_id=1):
    # Match app.db: rows come back as sqlite3.Row, so ["status"] etc. work.
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT id, title, status, destination, baseline, cut_list "
        "FROM courses WHERE id = ?",
        (course_id,),
    ).fetchone()


def topic_rows(conn, course_id=1):
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT title, milestone_description, time_box, order_index "
        "FROM topics WHERE course_id = ? ORDER BY order_index",
        (course_id,),
    ).fetchall()


def test_confirm_persists_edited_course_and_redirects(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    start_and_answer(client)
    assert "Review your curriculum" in client.get("/advisor/1/review").text

    # The user edits every review box, then confirms.
    data = confirm_data({
        "course_title": "Edited Course Title",
        "title-0": "Edited topic one",
        "milestone-0": "Edited milestone one",
        "timebox-0": "10 days",
    })
    response = client.post("/advisor/1/confirm", data=data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/courses/1"

    # The course page (redirect target) shows the EDITED values, in order.
    page = client.get("/courses/1")
    assert page.status_code == 200
    assert "Edited Course Title" in page.text
    assert "Edited topic one" in page.text
    assert "Edited milestone one" in page.text
    assert "10 days" in page.text

    # DB is the source of truth: flipped to active, answers copied onto the
    # course row, topics ordered, transcript untouched (5 rows still linked).
    with sqlite3.connect(get_db_path()) as conn:
        course = course_row(conn)
        assert course["status"] == "active"
        assert course["title"] == "Edited Course Title"
        assert course["destination"] == ANSWERS["destination"]
        assert course["baseline"] == ANSWERS["baseline"]
        assert course["cut_list"] == ANSWERS["cut_list"]
        topics = topic_rows(conn)
        assert [t["order_index"] for t in topics] == [0, 1, 2]
        assert topics[0]["title"] == "Edited topic one"
        assert topics[0]["time_box"] == "10 days"
        transcript = conn.execute(
            "SELECT COUNT(*) FROM advisor_interviews WHERE course_id = 1"
        ).fetchone()[0]
        assert transcript == len(advisor.STEPS)


def test_confirm_mid_interview_is_blocked(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    client.post("/advisor/new", data={"topic": "Spanish"})
    client.post(
        "/advisor/1",
        data={"step": "destination", "answer": ANSWERS["destination"]},
    )
    response = client.post(
        "/advisor/1/confirm", data=confirm_data(), follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/advisor/1"
    with sqlite3.connect(get_db_path()) as conn:
        assert course_row(conn)["status"] == "draft"
        assert len(topic_rows(conn)) == 0


def test_confirm_twice_does_not_duplicate_topics(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    start_and_answer(client)
    data = confirm_data()
    client.post("/advisor/1/confirm", data=data, follow_redirects=False)
    client.post("/advisor/1/confirm", data=data, follow_redirects=False)
    with sqlite3.connect(get_db_path()) as conn:
        assert len(topic_rows(conn)) == 3


def test_confirm_with_blank_title_rerenders_review_and_writes_nothing(
    monkeypatch, tmp_path
):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    start_and_answer(client)
    data = confirm_data({"course_title": "   "})
    response = client.post("/advisor/1/confirm", data=data)
    assert response.status_code == 200
    assert "needs a title and at least one topic with a milestone" in response.text
    # The user's typed topic values are still in the boxes (no data lost).
    assert "Pronunciation basics" in response.text
    with sqlite3.connect(get_db_path()) as conn:
        assert course_row(conn)["status"] == "draft"
        assert len(topic_rows(conn)) == 0


def test_confirm_drops_blank_milestone_rows_keeps_valid_rest(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    start_and_answer(client)
    # Milestone-1 blanked out -> that row is dropped, the others still persist.
    data = confirm_data({"milestone-1": "   "})
    response = client.post("/advisor/1/confirm", data=data, follow_redirects=False)
    assert response.status_code == 303
    with sqlite3.connect(get_db_path()) as conn:
        rows = topic_rows(conn)
        assert [r["title"] for r in rows] == ["Pronunciation basics", "Idioms in context"]
        assert [r["order_index"] for r in rows] == [0, 1]


def test_confirm_all_blank_rows_rerenders_all_boxes_and_writes_nothing(
    monkeypatch, tmp_path
):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    start_and_answer(client)
    # Every milestone blanked: no dead end — the review page comes back with
    # all three boxes still editable and the inline error shown.
    data = confirm_data({
        "milestone-0": "   ", "milestone-1": "   ", "milestone-2": "   ",
    })
    response = client.post("/advisor/1/confirm", data=data)
    assert response.status_code == 200
    assert "needs a title and at least one topic with a milestone" in response.text
    assert 'name="title-0"' in response.text
    assert 'name="title-1"' in response.text
    assert 'name="title-2"' in response.text
    with sqlite3.connect(get_db_path()) as conn:
        assert course_row(conn)["status"] == "draft"
        assert len(topic_rows(conn)) == 0


def test_course_and_topics_survive_restart(monkeypatch, tmp_path):
    # "Session 1": interview + confirm, then throw the client away.
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    start_and_answer(client)
    client.post("/advisor/1/confirm", data=confirm_data(), follow_redirects=False)
    del client

    # "Session 2": a brand-new connection reads the SAME DB file (this is the
    # Phase 1 Definition of Done: close the app, reopen, Course still there).
    with sqlite3.connect(get_db_path()) as conn:
        assert course_row(conn)["status"] == "active"
        assert [t["title"] for t in topic_rows(conn)] == [
            "Pronunciation basics", "Everyday vocabulary", "Idioms in context",
        ]


def test_course_page_404_for_missing_course(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    response = client.get("/courses/999")
    assert response.status_code == 404
    assert "Course not found" in response.text


def test_confirm_curriculum_validates_input(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    course_id = start_interview("Spanish", 1)
    topic = {"title": "T", "milestone_description": "M", "time_box": "1 week"}
    with pytest.raises(ValueError):
        course_store.confirm_curriculum(course_id, "   ", [topic], {}, 1)
    with pytest.raises(ValueError):
        course_store.confirm_curriculum(course_id, "Title", [], {}, 1)