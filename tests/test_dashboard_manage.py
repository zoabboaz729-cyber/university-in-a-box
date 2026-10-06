"""Phase 2 tests part 2: management actions + restart survival."""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path
from app.main import api
from tests.test_dashboard import make_client, seed_course


def test_topic_page_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    response = client.get("/topics/999")
    assert response.status_code == 404
    assert "Topic not found" in response.text


def test_pause_archive_resume_persists(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("Pause Course")
    for status in ["paused", "archived", "active"]:
        response = client.post(f"/courses/{course_id}/status",
                               data={"status": status},
                               follow_redirects=False)
        assert response.status_code == 303
        page = client.get(f"/courses/{course_id}")
        assert status in page.text
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM courses WHERE id = ?",
                           (course_id,)).fetchone()
        assert row["status"] == "active"


def test_topic_done_moves_dashboard_resume_pointer(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, topic_ids = seed_course("Prog Course",
                                       topics=[("Step One", "not_started"),
                                               ("Step Two", "not_started")])
    # Phase 5: topic-done is gated on an Editor review being on record.
    from app.roles.editor import Review
    from app.roles.review_store import save_review
    save_review(topic_ids[0], "Milestone for Step One", "User work",
                Review(strengths="s", biggest_weakness="w", next_edit="e"), 1)
    response = client.post(f"/topics/{topic_ids[0]}/status",
                           data={"status": "done"}, follow_redirects=False)
    assert response.status_code == 303
    dashboard = client.get("/")
    assert "Step Two" in dashboard.text
    assert "1/2" in dashboard.text


def test_dashboard_survives_restart(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("Restart Course",
                               topics=[("R1", "not_started")])
    client.post(f"/courses/{course_id}/status", data={"status": "paused"})
    del client
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT title, status FROM courses WHERE id = ?",
                           (course_id,)).fetchone()
        assert row["title"] == "Restart Course"
        assert row["status"] == "paused"
        topics = conn.execute("SELECT title FROM topics WHERE course_id = ?",
                              (course_id,)).fetchall()
        assert [t["title"] for t in topics] == ["R1"]
    client2 = TestClient(api)
    response = client2.get("/")
    assert response.status_code == 200
    assert "Restart Course" in response.text
    assert f'href="/courses/{course_id}"' in response.text


def test_activity_log_written_and_days_shown(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("Active Course")
    client.post(f"/courses/{course_id}/status", data={"status": "paused"})
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT action FROM activity_log "
            "WHERE entity_type = 'course' AND entity_id = ?",
            (course_id,)).fetchall()
        assert any("paused" in r["action"] for r in rows)
    response = client.get("/")
    assert "day(s) ago" in response.text
