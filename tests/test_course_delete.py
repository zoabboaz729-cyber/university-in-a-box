"""Tests for course deletion: cascading DB cleanup, routes, and state adaptation."""
import sqlite3

from app.db import get_connection, get_db_path
from app.roles.activity import log
from app.roles.course_manage import delete_course
from app.roles.editor import Review
from app.roles.review_store import save_review
from app.roles.roommate_store import latest_prompt, save_prompt
from app.roles.source_store import add_source
from app.roles.tutor_store import add_turn, start_session
from tests.test_dashboard import make_client, seed_course


def _populate_full_course(title="Complex Course"):
    """Create a course with data in every dependent table."""
    course_id, topic_ids = seed_course(
        title, topics=[("Topic A", "not_started"), ("Topic B", "not_started")]
    )
    topic_a = topic_ids[0]

    # Advisor interview
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO advisor_interviews (course_id, question, answer, step) "
            "VALUES (?, 'Where do you want to end up?', 'Expert level', 'destination')",
            (course_id,),
        )

    # Librarian source
    source_id = add_source(topic_a, "Book", "https://example.com/book", "keep", "Essential")

    # Tutor session + turn
    session_id = start_session(topic_a)
    add_turn(session_id, "What is X?")

    # Editor review
    save_review(
        topic_a,
        "Milestone A",
        "Submission draft text",
        Review(strengths="Good intro", biggest_weakness="Needs depth", next_edit="Expand section 2"),
    )

    # Roommate prompt
    prompt_id = save_prompt(course_id, "Biology", "Compare to cell membranes")

    # Activity log
    log(course_id, "course", course_id, "test_action")

    return course_id, topic_ids, source_id, session_id, prompt_id


def test_delete_course_cascades_all_tables(tmp_path, monkeypatch):
    make_client(tmp_path, monkeypatch)
    course_id, topic_ids, source_id, session_id, prompt_id = _populate_full_course()

    # Pre-condition: assert all rows exist
    with sqlite3.connect(get_db_path()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM courses WHERE id = ?", (course_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM topics WHERE course_id = ?", (course_id,)).fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM sources WHERE topic_id = ?", (topic_ids[0],)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tutor_sessions WHERE topic_id = ?", (topic_ids[0],)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tutor_turns WHERE session_id = ?", (session_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM editor_reviews WHERE topic_id = ?", (topic_ids[0],)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM advisor_interviews WHERE course_id = ?", (course_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM roommate_prompts WHERE course_id = ?", (course_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM activity_log WHERE course_id = ?", (course_id,)).fetchone()[0] > 0

    # Act
    ok = delete_course(course_id)
    assert ok is True

    # Post-condition: assert everything is purged
    with sqlite3.connect(get_db_path()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM courses WHERE id = ?", (course_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM topics WHERE course_id = ?", (course_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sources WHERE topic_id IN (?, ?)", tuple(topic_ids)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tutor_sessions WHERE topic_id IN (?, ?)", tuple(topic_ids)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tutor_turns WHERE session_id = ?", (session_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM editor_reviews WHERE topic_id IN (?, ?)", tuple(topic_ids)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM advisor_interviews WHERE course_id = ?", (course_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM roommate_prompts WHERE course_id = ?", (course_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM activity_log WHERE course_id = ?", (course_id,)).fetchone()[0] == 0


def test_delete_nonexistent_course_returns_false(tmp_path, monkeypatch):
    make_client(tmp_path, monkeypatch)
    assert delete_course(99999) is False


def test_delete_course_route_and_404_pages(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, topic_ids, _, _, _ = _populate_full_course("To Be Deleted")
    topic_id = topic_ids[0]

    # Verify initial access
    assert client.get(f"/courses/{course_id}").status_code == 200
    assert client.get(f"/topics/{topic_id}").status_code == 200

    # Delete via POST route
    response = client.post(f"/courses/{course_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    # Subsequent access gives 404 with friendly message
    resp_course = client.get(f"/courses/{course_id}")
    assert resp_course.status_code == 404
    assert "Course not found" in resp_course.text

    resp_topic = client.get(f"/topics/{topic_id}")
    assert resp_topic.status_code == 404
    assert "Topic not found" in resp_topic.text

    # Dashboard loads cleanly without the deleted course
    resp_dash = client.get("/")
    assert resp_dash.status_code == 200
    assert "To Be Deleted" not in resp_dash.text


def test_delete_course_roommate_fallback(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    c1, _, _, _, _ = _populate_full_course("Course 1")
    c2, _, _, _, _ = _populate_full_course("Course 2")

    save_prompt(c1, "Field1", "Prompt for Course 1")
    save_prompt(c2, "Field2", "Prompt for Course 2")

    # Latest prompt is Course 2
    latest = latest_prompt()
    assert latest is not None
    assert latest["course_id"] == c2

    # Delete Course 2
    delete_course(c2)

    # Latest prompt falls back cleanly to Course 1
    fallback = latest_prompt()
    assert fallback is not None
    assert fallback["course_id"] == c1

    # Delete Course 1
    delete_course(c1)

    # Now latest prompt is None
    assert latest_prompt() is None


def test_delete_ui_rendered_on_pages(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, _, _, _, _ = _populate_full_course("UI Check Course")

    # 1. Dashboard contains 3-dots menus and the modal dialog
    dash_resp = client.get("/")
    assert dash_resp.status_code == 200
    assert f"dash-menu-{course_id}" in dash_resp.text
    assert f"sb-menu-{course_id}" in dash_resp.text
    assert "delete-course-modal" in dash_resp.text
    assert "Delete Course Permanently" in dash_resp.text

    # 2. Course details page contains Delete Course button and modal
    course_resp = client.get(f"/courses/{course_id}")
    assert course_resp.status_code == 200
    assert "Delete course" in course_resp.text
    assert "openDeleteModal" in course_resp.text
    assert "delete-course-modal" in course_resp.text

