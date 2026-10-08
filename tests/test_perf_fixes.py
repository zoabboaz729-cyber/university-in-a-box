"""Step-1 perf fixes (D-031): per-request sidebar memo + dashboard indexes.

Companion to the owner's 2026-10-07 perf plan step 1: these tests guard the
BEHAVIOR of the two changes (not the numbers): the memo must compute
sidebar_groups() once per request, refresh on the next request, and fall
back safely with no request on the context; init_db() must be idempotent
and leave the four new indexes present.
"""
import sqlite3
from types import SimpleNamespace

from app.db import get_db_path, init_db
from app.main import _sidebar_groups
from app.roles import group_store
from tests.test_dashboard import make_client, seed_course

PERF_INDEXES = (
    "idx_topics_course_order",
    "idx_tutor_sessions_topic",
    "idx_editor_reviews_topic",
    "idx_roommate_prompts_course",
)


def test_sidebar_groups_computed_once_per_request(monkeypatch):
    """Both base.html call sites share one store call per render."""
    calls = []

    def fake_sidebar_groups(user_id):
        calls.append(user_id)
        return [{"group": None, "courses": []}]

    monkeypatch.setattr(group_store, "sidebar_groups", fake_sidebar_groups)
    request = SimpleNamespace(
        state=SimpleNamespace(user={"id": 1, "email": "a@b.c"})
    )
    ctx = {"request": request}
    first = _sidebar_groups(ctx)
    second = _sidebar_groups(ctx)
    assert calls == [1]  # second call site hit the request.state memo
    assert first is second


def test_new_request_recomputes_shows_group_created_between_requests(
    tmp_path, monkeypatch
):
    """A group created after render #1 must appear on render #2 — the memo
    lives on request.state, so it can never leak across requests."""
    client = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("Solo Course", topics=[("T", "not_started")])
    r1 = client.get("/")
    assert r1.status_code == 200
    assert "Semester New" not in r1.text

    gid = group_store.create_group(1, "Semester New")
    group_store.set_course_group(course_id, gid, 1)
    r2 = client.get("/")
    assert r2.status_code == 200
    assert "Semester New" in r2.text


def test_sidebar_groups_falls_back_without_request(monkeypatch):
    """No request on the context (or no signed-in user) -> empty list, and
    the store is never touched."""
    def boom(user_id):
        raise AssertionError("store must not be called without a user")

    monkeypatch.setattr(group_store, "sidebar_groups", boom)
    assert _sidebar_groups({}) == []  # no request key at all
    # Request present but nobody signed in.
    request = SimpleNamespace(state=SimpleNamespace(user=None))
    assert _sidebar_groups({"request": request}) == []


def test_init_db_twice_leaves_perf_indexes(tmp_path, monkeypatch):
    """_migrate runs on every boot; running it twice must not error and must
    leave all four dashboard indexes present."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    init_db()
    conn = sqlite3.connect(get_db_path())
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
    finally:
        conn.close()
    for idx in PERF_INDEXES:
        assert idx in names, f"{idx} missing after two init_db() runs"
