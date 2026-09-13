"""Phase 2 tests: dashboard lists active courses, survives restart."""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.main import api


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    return TestClient(api)


def seed_course(title="Spanish", status="active", topics=()):
    """Insert a course + topics directly. Returns (course_id, [topic_ids])."""
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "INSERT INTO courses (title, status) VALUES (?, ?)", (title, status)
        )
        course_id = cur.lastrowid
        topic_ids = []
        for i, (t_title, t_status) in enumerate(topics):
            tcur = conn.execute(
                "INSERT INTO topics (course_id, order_index, title, "
                "milestone_description, time_box, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (course_id, i, t_title, "Milestone for " + t_title, "1 week",
                 t_status),
            )
            topic_ids.append(tcur.lastrowid)
        conn.commit()
    return course_id, topic_ids


def test_dashboard_empty_state(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "University in a Box" in response.text
    assert "No courses yet" in response.text
    assert "Dashboard" in response.text


def test_dashboard_shows_start_new_course_entry_point(tmp_path, monkeypatch):
    """Regression: the link to /advisor/new was once missing from every
    template, so the only way to start an interview was typing the URL by
    hand. The dashboard button and the base-nav link must both stay."""
    client = make_client(tmp_path, monkeypatch)

    # Empty dashboard and a dashboard with courses must both carry it.
    for _ in range(2):
        response = client.get("/")
        assert response.status_code == 200
        assert 'href="/advisor/new"' in response.text
        seed_course("Second seeding pass course")

    # And the nav link must appear on every page, like the other nav links.
    course_id, topic_ids = seed_course("Entry Point Course",
                                       topics=[("EP1", "not_started")])
    for url in ["/", "/advisor/new", f"/courses/{course_id}",
                f"/topics/{topic_ids[0]}"]:
        response = client.get(url)
        assert response.status_code == 200
        assert 'href="/advisor/new"' in response.text, \
            f"no /advisor/new link on {url}"


def test_dashboard_lists_active_newest_first(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    old_id, _ = seed_course("Older Course", topics=[("T1", "done"),
                                                    ("T2", "not_started")])
    new_id, _ = seed_course("Newer Course", topics=[("N1", "not_started")])
    draft_id, _ = seed_course("Draft Course", status="draft",
                              topics=[("D1", "not_started")])

    response = client.get("/")
    assert response.status_code == 200
    assert f'href="/courses/{new_id}"' in response.text
    assert f'href="/courses/{old_id}"' in response.text
    assert response.text.index("Newer Course") < response.text.index("Older Course")
    assert "active" in response.text
    assert "1/2" in response.text
    assert "T2" in response.text
    assert "Draft Course" not in response.text
    assert f"/courses/{draft_id}" not in response.text


def test_dashboard_nav_link_on_every_page(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, topic_ids = seed_course("Nav Course",
                                       topics=[("Nav T", "not_started")])
    for url in ["/", "/advisor/new", f"/courses/{course_id}",
                f"/topics/{topic_ids[0]}"]:
        response = client.get(url)
        assert response.status_code == 200
        assert "Dashboard" in response.text, f"no Dashboard link on {url}"
        assert 'href="/"' in response.text


def test_topic_page_renders_placeholders(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    course_id, topic_ids = seed_course("T Course",
                                       topics=[("Deep Topic", "not_started")])
    response = client.get(f"/topics/{topic_ids[0]}")
    assert response.status_code == 200
    assert "Deep Topic" in response.text
    assert "Milestone for Deep Topic" in response.text
    assert "No sources yet" in response.text
    assert "No tutor sessions yet" in response.text
    assert "No reviews yet" in response.text
    assert f"/courses/{course_id}" in response.text
