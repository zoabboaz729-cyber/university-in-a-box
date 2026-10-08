"""Legacy NULL-owner backfill in db._migrate() — the owner-adoption rules.

A pre-Phase-12 database has courses / course_groups with a NULLABLE user_id
and no user_id anywhere else; the Phase-12 ADD COLUMN loop cannot backfill
those two tables (the column already exists). The backfill adopts such rows
ONLY when users holds exactly one row — it must never guess an owner.

Covered here (per the owner's request):
  * one user + NULL-owner rows  -> everything ends up owned by that user;
  * two users                   -> nothing changes, a warning is logged;
  * a second run                -> a no-op;
  * a course already owned by user 2 -> never reassigned;
  * zero users                  -> nothing changes, a warning is logged.
"""
import logging
import sqlite3

from app.db import get_db_path, init_db


def _legacy_tables() -> None:
    """Create courses/course_groups in the PRE-Phase-12 shape (user_id
    exists but is NULLable, no DEFAULT) — exactly what the owner's real
    database has. init_db()'s schema.sql uses CREATE IF NOT EXISTS, so these
    definitions survive and the NOT NULL DEFAULT 1 never applies."""
    with sqlite3.connect(get_db_path()) as conn:
        conn.executescript(
            "CREATE TABLE courses ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER REFERENCES users(id), "
            "title TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'active', "
            "created_at TEXT NOT NULL DEFAULT (datetime('now')));"
            "CREATE TABLE course_groups ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER REFERENCES users(id), "
            "name TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT (datetime('now')));"
        )


def _add_user(email: str) -> int:
    with sqlite3.connect(get_db_path()) as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, name) "
            "VALUES (?, 'hash', 'Someone')",
            (email,),
        )
        return cur.lastrowid


def _add_legacy_rows() -> None:
    """Two NULL-owner courses + one NULL-owner group, plus the child rows the
    real DB has (topics/sessions/... already carry user_id = 1 via their
    NOT NULL DEFAULT)."""
    with sqlite3.connect(get_db_path()) as conn:
        conn.executescript(
            "INSERT INTO courses (user_id, title) VALUES (NULL, 'Legacy A');"
            "INSERT INTO courses (user_id, title) VALUES (NULL, 'Legacy B');"
            "INSERT INTO course_groups (user_id, name) VALUES (NULL, 'Semester');"
            "INSERT INTO topics (course_id, user_id, order_index, title) "
            "VALUES (1, 1, 0, 'Topic of A');"
        )


def _owner_rows(table: str) -> list:
    with sqlite3.connect(get_db_path()) as conn:
        return [
            (row[0], row[1])
            for row in conn.execute(
                f"SELECT id, user_id FROM {table} ORDER BY id"
            )
        ]


def test_one_user_owns_every_null_owner_row(tmp_path, monkeypatch):
    """Exactly one user: all NULL-owner rows are adopted by it."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _legacy_tables()
    init_db()  # creates the remaining tables (users still empty -> no-op)
    uid = _add_user("me@local")
    _add_legacy_rows()
    assert _owner_rows("courses") == [(1, None), (2, None)]

    init_db()  # the backfill run

    assert _owner_rows("courses") == [(1, uid), (2, uid)]
    assert _owner_rows("course_groups") == [(1, uid)]


def test_two_users_changes_nothing_and_warns(tmp_path, monkeypatch, caplog):
    """Two users = ambiguous owner: rows stay NULL and a warning is logged."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _legacy_tables()
    init_db()
    _add_user("me@local")
    _add_user("other@local")
    _add_legacy_rows()

    with caplog.at_level(logging.WARNING, logger="uib"):
        init_db()

    assert _owner_rows("courses") == [(1, None), (2, None)]
    assert _owner_rows("course_groups") == [(1, None)]
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "expected a warning when the owner cannot be determined"
    message = warnings[-1].getMessage()
    assert "owner backfill SKIPPED" in message
    assert "courses" in message
    assert "2" in message  # the user count that made us refuse to guess


def test_second_run_is_a_noop(tmp_path, monkeypatch, caplog):
    """After a successful backfill, re-running init_db() changes nothing."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _legacy_tables()
    init_db()
    uid = _add_user("me@local")
    _add_legacy_rows()
    init_db()
    first = (_owner_rows("courses"), _owner_rows("course_groups"))
    assert first == ([(1, uid), (2, uid)], [(1, uid)]), first

    with caplog.at_level(logging.WARNING, logger="uib"):
        init_db()  # third run — must be a pure no-op

    assert (_owner_rows("courses"), _owner_rows("course_groups")) == first
    assert not [
        r for r in caplog.records if "owner backfill" in r.getMessage()
    ], "a fully-owned database must not warn on re-run"


def test_course_owned_by_user2_is_never_reassigned(tmp_path, monkeypatch):
    """The backfill only fills NULL — an explicit owner is sacred."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _legacy_tables()
    init_db()
    uid = _add_user("me@local")
    _add_legacy_rows()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "INSERT INTO courses (user_id, title) VALUES (2, 'Owned by 2')"
        )
        conn.execute(
            "INSERT INTO course_groups (user_id, name) VALUES (2, 'Other')"
        )

    init_db()

    courses = dict(_owner_rows("courses"))
    groups = dict(_owner_rows("course_groups"))
    assert courses[3] == 2, "user 2's course was reassigned"
    assert groups[2] == 2, "user 2's group was reassigned"
    # ...while the NULL rows still got adopted by the single real user.
    assert courses[1] == uid and courses[2] == uid
    assert groups[1] == uid


def test_zero_users_changes_nothing_and_warns(tmp_path, monkeypatch, caplog):
    """No users at all: there is nobody to adopt the rows."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _legacy_tables()
    init_db()
    _add_legacy_rows()

    with caplog.at_level(logging.WARNING, logger="uib"):
        init_db()

    assert _owner_rows("courses") == [(1, None), (2, None)]
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "expected a warning when there is no user to adopt rows"
    assert "owner backfill SKIPPED" in warnings[-1].getMessage()
    assert "0" in warnings[-1].getMessage()

