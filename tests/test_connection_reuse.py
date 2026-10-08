"""Perf step 2 (connection reuse): the dashboard per-course loop must open
ONE database connection, not one-per-helper-per-course.

Guards the BEHAVIOR of the change (not the numbers):

a. list_dashboard_courses returns identical data whether the four
   per-course helpers run on a shared connection or each open their own
   (conn=None) — no value may drift when we stop reconnecting.
b. The number of sqlite3.connect calls for one list_dashboard_courses call
   is the same for 3 courses as for 9 (it must not grow with course count).
c. The dashboard connection is closed after the call — including when one
   of the helpers raises mid-loop.

No SQL, indexes, or write paths are touched; this only proves reads stay
identical while connections collapse.
"""
import sqlite3

import pytest

from app.db import init_db
from app.roles import dashboard
from app.roles.activity import log
from app.roles.dashboard import list_dashboard_courses
from app.roles.editor import Review
from app.roles.review_store import save_review
from app.roles.tutor_store import add_turn, end_session, start_session
from tests.test_dashboard import seed_course


def _seed_rich(tmp_path, monkeypatch):
    """A small but non-trivial DB: two active courses (one with a done and a
    not-done topic, plus real activity / gap / review rows) and one draft
    (which the dashboard must keep excluding)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()

    c1, t1 = seed_course("Course One",
                         topics=[("T1", "done"), ("T2", "not_started")])
    c2, _ = seed_course("Course Two", topics=[("C2T", "not_started")])
    seed_course("Draft Course", status="draft", topics=[("D1", "not_started")])

    # Real user activity on course one (feeds days_since + streak).
    log(c1, "topic", t1[0], "answered:1")
    # A gap note on course one's first topic.
    sid = start_session(t1[0], user_id=1)
    add_turn(sid, "What is the core idea?", user_id=1)
    end_session(sid, "Mixes up X and Y.", user_id=1)
    # An editor review on course one's first topic.
    save_review(t1[0], "m", "some text",
                Review(strengths="s", biggest_weakness="the weak bit",
                       next_edit="the edit"), user_id=1)
    return [c1, c2]


def test_shared_conn_matches_conn_none(tmp_path, monkeypatch):
    """(a) The dashboard result is byte-for-byte identical whether the four
    helpers share the dashboard connection or each open their own."""
    _seed_rich(tmp_path, monkeypatch)

    # Shared-connection path (the new default inside list_dashboard_courses).
    shared = list_dashboard_courses(1)

    # Force the conn=None path: wrap each helper so it ignores the conn the
    # dashboard passes and opens a private one, exactly as before.
    real_activity = dashboard.last_activity_for_course
    real_streak = dashboard.current_streak
    real_gap = dashboard.last_gap_for_course
    real_review = dashboard.last_review_note_for_course
    monkeypatch.setattr(
        dashboard, "last_activity_for_course",
        lambda course_id, conn=None: real_activity(course_id))
    monkeypatch.setattr(
        dashboard, "current_streak",
        lambda course_id, conn=None: real_streak(course_id))
    monkeypatch.setattr(
        dashboard, "last_gap_for_course",
        lambda course_id, conn=None: real_gap(course_id))
    monkeypatch.setattr(
        dashboard, "last_review_note_for_course",
        lambda course_id, conn=None: real_review(course_id))

    own = list_dashboard_courses(1)

    assert shared == own
    # Sanity: the seed populated the fields the helpers compute, so the
    # comparison above is meaningful rather than comparing empties.
    one = next(c for c in shared if c["title"] == "Course One")
    assert one["last_gap_note"] is not None
    assert one["last_review_note"] is not None
    assert one["done_topics"] == 1
    assert all(c["title"] != "Draft Course" for c in shared)


def test_connection_count_does_not_grow_with_courses(tmp_path, monkeypatch):
    """(b) One list_dashboard_courses call opens the same number of
    connections for 3 courses as for 9 — it must not scale with courses."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()

    real_connect = sqlite3.connect
    calls = {"n": 0}

    def counting_connect(*args, **kwargs):
        calls["n"] += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", counting_connect)

    for i in range(3):
        seed_course(f"C{i}")
    calls["n"] = 0
    list_dashboard_courses(1)
    count_3 = calls["n"]

    for i in range(3, 9):
        seed_course(f"C{i}")
    calls["n"] = 0
    list_dashboard_courses(1)
    count_9 = calls["n"]

    # The whole point: the count is flat, not 1 + 4*courses.
    assert count_3 == count_9
    # And it is a single connection for the entire call.
    assert count_3 == 1


class _TrackingConn:
    """Wraps a real connection and records whether close() was called."""

    def __init__(self, conn):
        self._conn = conn
        self.closed = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        self.closed = True
        return self._conn.close()


def _track_get_connection(monkeypatch, created):
    """Patch dashboard.get_connection to hand back a tracked wrapper so a
    test can assert the dashboard closed the connection it opened."""
    real_get_connection = dashboard.get_connection

    def tracking_get_connection():
        conn = real_get_connection()
        tracker = _TrackingConn(conn)
        created.append(tracker)
        return tracker

    monkeypatch.setattr(dashboard, "get_connection", tracking_get_connection)


def test_connection_closed_after_call(tmp_path, monkeypatch):
    """(c) The dashboard connection is closed once the call returns."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    seed_course("Only Course", topics=[("T", "not_started")])

    created = []
    _track_get_connection(monkeypatch, created)

    list_dashboard_courses(1)

    assert len(created) == 1
    assert created[0].closed is True


def test_connection_closed_when_helper_raises(tmp_path, monkeypatch):
    """(c) Even when a per-course helper raises mid-loop, the connection is
    still closed and the error propagates."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    seed_course("Boom Course", topics=[("T", "not_started")])

    created = []
    _track_get_connection(monkeypatch, created)

    def boom(course_id, conn=None):
        raise RuntimeError("helper blew up")

    monkeypatch.setattr(dashboard, "current_streak", boom)

    with pytest.raises(RuntimeError, match="helper blew up"):
        list_dashboard_courses(1)

    assert len(created) == 1
    assert created[0].closed is True

