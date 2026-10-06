"""Route-3 (D-015) regression tests: activity model, query, migration.

These pin the structural fix: every activity row carries its owning
course_id and an is_user flag; last_activity_for_course counts any user
row (no entity-type whitelist); system rows never refresh the clock;
and the migration upgrades + backfills pre-D-015 databases.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.db import get_db_path, init_db
from app.roles import activity
from app.roles.roommate_store import save_prompt
from app.roles.tutor_store import start_session
from tests.test_dashboard import seed_course


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    return seed_course("Activity Course", topics=[("AT", "not_started")])


def _old_stamp(days=10) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)
            ).strftime("%Y-%m-%d %H:%M:%S")


def test_log_requires_course_and_writes_is_user(tmp_path, monkeypatch):
    course_id, _ = _init(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        activity.log(entity_type="course", entity_id=course_id, action="x")
    activity.log(course_id, "tutor_session", 999, "started")
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT course_id, entity_type, entity_id, action, is_user "
            "FROM activity_log").fetchone()
        assert row["course_id"] == course_id
        assert row["entity_type"] == "tutor_session"
        assert row["is_user"] == 1


def test_last_activity_counts_tutor_rows(tmp_path, monkeypatch):
    course_id, _ = _init(tmp_path, monkeypatch)
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("UPDATE courses SET created_at = ? WHERE id = ?",
                     (_old_stamp(), course_id))
    # No user rows yet → the fallback (old created_at) is returned.
    assert activity.days_since(
        activity.last_activity_for_course(course_id)) == 10
    # A tutor answer — the previously invisible Phase 4 case — counts now.
    activity.log(course_id, "tutor_session", 1, "answered:7")
    assert activity.days_since(
        activity.last_activity_for_course(course_id)) == 0


def test_system_rows_do_not_refresh_the_clock(tmp_path, monkeypatch):
    course_id, _ = _init(tmp_path, monkeypatch)
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("UPDATE courses SET created_at = ? WHERE id = ?",
                     (_old_stamp(), course_id))
    # Only system-generated rows exist: a prompt generated, a failed check.
    activity.log(course_id, "roommate", 1, "generated", is_user=False)
    activity.log(course_id, "roommate", course_id, "generate_failed: x",
                 is_user=False)
    assert activity.days_since(
        activity.last_activity_for_course(course_id)) == 10
    # A real user reaction placed after them DOES refresh the clock.
    activity.log(course_id, "roommate", 1, "reacted")
    assert activity.days_since(
        activity.last_activity_for_course(course_id)) == 0


def test_migrate_upgrades_old_activity_log_and_backfills(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Simulate a pre-D-015 DB: only activity_log exists, old shape.
    with sqlite3.connect(get_db_path()) as conn:
        conn.executescript(
            "CREATE TABLE activity_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "entity_type TEXT NOT NULL, entity_id INTEGER, "
            "action TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    init_db()  # creates the remaining tables AND ALTERs the two columns in

    course_id, topic_ids = seed_course("Mig Course",
                                       topics=[("M", "not_started")])
    sid = start_session(topic_ids[0], 1)
    prompt_id = save_prompt(course_id, "architecture", "Prompt text.", 1)
    # Legacy-shaped rows, exactly as earlier phases wrote them.
    with sqlite3.connect(get_db_path()) as conn:
        conn.executescript(
            f"INSERT INTO activity_log (entity_type, entity_id, action) VALUES "
            f"('topic', {topic_ids[0]}, 'status:done'), "
            f"('tutor_session', {sid}, 'answered:1'), "
            f"('roommate', {prompt_id}, 'generated')")
    init_db()  # rerun: idempotent backfill fills the NULL columns

    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT entity_type, entity_id, action, course_id, is_user "
            "FROM activity_log").fetchall()
    by_key = {(r["entity_type"], r["action"]): r for r in rows}
    topic_row = by_key[("topic", "status:done")]
    assert topic_row["course_id"] == course_id
    session_row = by_key[("tutor_session", "answered:1")]
    assert session_row["course_id"] == course_id
    assert session_row["is_user"] == 1
    # Both the new-style and the legacy 'generated' rows are system rows.
    for r in rows:
        if r["entity_type"] == "roommate" and r["action"] == "generated":
            assert r["course_id"] == course_id
            assert r["is_user"] == 0