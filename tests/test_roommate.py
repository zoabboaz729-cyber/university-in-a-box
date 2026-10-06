"""Phase 6 tests part 1: roommate role parsing + cadence + store."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.db import get_db_path
from app.roles import roommate
from app.roles.roommate_store import (
    due_courses,
    last_prompt_at,
    dash_visit_at,
    latest_prompt,
    list_all_prompts,
    prompt_newer_than,
    recent_fields,
    save_prompt,
    save_reaction,
    record_dash_visit,
)


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


GOOD = json.dumps({
    "field": "architecture",
    "prompt": "Consider how an architect would separate the load-bearing "
              "structure of your topic from its decorative parts.",
})


def _days_ago(days: int) -> str:
    stamp = datetime.now(timezone.utc) - timedelta(days=days)
    return stamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _seed(title="Roommate Course", status="active"):
    from tests.test_dashboard import seed_course
    return seed_course(title, status=status, topics=[("R1", "not_started")])


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db import init_db
    init_db()


# --- role parsing ------------------------------------------------------


def test_build_prompt_parses_field_and_prompt():
    conn = roommate.build_prompt("Spanish", "Speak fluently", "Tenses",
                                 [], FakeProvider([GOOD]))
    assert conn.field == "architecture"
    assert conn.prompt.startswith("Consider how an architect")


def test_build_prompt_retries_once_on_bad_json():
    provider = FakeProvider(["nope", GOOD])
    conn = roommate.build_prompt("X", "", "Y", [], provider)
    assert conn.field == "architecture"
    assert provider.calls == 2


def test_build_prompt_tolerates_markdown_fences():
    fenced = "```json\n" + GOOD + "\n```"
    conn = roommate.build_prompt("X", "", "Y", [], FakeProvider([fenced]))
    assert conn.field == "architecture"


def test_build_prompt_rejects_empty_field():
    bad = json.dumps({"field": "  ", "prompt": "p"})
    with pytest.raises(ValueError):
        roommate.build_prompt("X", "", "Y", [], FakeProvider([bad, bad]))


def test_build_prompt_rejects_missing_key():
    bad = '{"field": "architecture"}'
    with pytest.raises((ValueError, KeyError)):
        roommate.build_prompt("X", "", "Y", [], FakeProvider([bad, bad]))


def test_build_prompt_rejects_overlong_prompt():
    bad = json.dumps({"field": "f", "prompt": "x" * 501})
    with pytest.raises(ValueError):
        roommate.build_prompt("X", "", "Y", [], FakeProvider([bad, bad]))


def test_build_prompt_rejects_repeat_field():
    bad = json.dumps({"field": "architecture", "prompt": "p"})
    with pytest.raises(ValueError):
        roommate.build_prompt("X", "", "Y", ["architecture"],
                              FakeProvider([bad, bad]))
# --- cadence -----------------------------------------------------------


def test_cadence_defaults_to_three(monkeypatch):
    monkeypatch.delenv("ROOMMATE_CADENCE_DAYS", raising=False)
    assert roommate.cadence_days() == 3


def test_cadence_reads_env_and_clamps(monkeypatch):
    monkeypatch.setenv("ROOMMATE_CADENCE_DAYS", "30")
    assert roommate.cadence_days() == 30
    monkeypatch.setenv("ROOMMATE_CADENCE_DAYS", "0")
    assert roommate.cadence_days() == 1
    monkeypatch.setenv("ROOMMATE_CADENCE_DAYS", "abc")
    assert roommate.cadence_days() == 3


# --- store -------------------------------------------------------------


def test_store_roundtrip_newest_first(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    assert list_all_prompts(1) == []
    first = save_prompt(course_id, "architecture", "First prompt.", 1)
    second = save_prompt(course_id, "jazz", "Second prompt.", 1)
    assert first < second
    rows = list_all_prompts(1)
    assert [r["id"] for r in rows] == [second, first]
    assert rows[0]["course_title"] == "Roommate Course"
    assert rows[0]["field"] == "jazz"


def test_save_prompt_rejects_empty(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    with pytest.raises(ValueError):
        save_prompt(course_id, "  ", "text", 1)
    with pytest.raises(ValueError):
        save_prompt(course_id, "field", "   ", 1)
    with pytest.raises(ValueError):
        save_prompt(9999, "field", "text", 1)


def test_last_prompt_at(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    assert last_prompt_at(course_id) is None
    save_prompt(course_id, "architecture", "One.", 1)
    assert last_prompt_at(course_id) is not None


def test_due_courses_math(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    # Never prompted → due.
    assert [c["id"] for c in due_courses(3, 1)] == [course_id]
    save_prompt(course_id, "architecture", "First.", 1)
    # Fresh prompt, inside the 3-day cadence → not due.
    assert due_courses(3, 1) == []
    # Backdate the prompt → due again.
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("UPDATE roommate_prompts SET created_at = ?",
                     (_days_ago(10),))
    assert [c["id"] for c in due_courses(3, 1)] == [course_id]
    # ...but still inside a 30-day cadence.
    assert due_courses(30, 1) == []


def test_due_courses_excludes_non_active(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    for status in ("paused", "archived", "done", "draft"):
        _seed("S" + status, status=status)
    assert due_courses(3, 1) == []


def test_recent_fields_newest_first(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    save_prompt(course_id, "architecture", "One.", 1)
    save_prompt(course_id, "jazz", "Two.", 1)
    assert recent_fields(course_id, 8) == ["jazz", "architecture"]
    assert recent_fields(course_id, 1) == ["jazz"]


def test_latest_prompt_ignores_non_active(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    archived_id, _ = _seed("Old Course", status="archived")
    save_prompt(archived_id, "architecture", "Archived prompt.", 1)
    assert latest_prompt(1) is None
    active_id, _ = _seed("Active Course", status="active")
    save_prompt(active_id, "jazz", "Active prompt.", 1)
    row = latest_prompt(1)
    assert row["field"] == "jazz"
    assert row["course_id"] == active_id


def test_reaction_updates_clears_and_guards(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    prompt_id = save_prompt(course_id, "architecture", "Prompt.", 1)
    assert save_reaction(prompt_id, "Saw this at work today.", 1) is True
    assert list_all_prompts(1)[0]["user_reaction"] == "Saw this at work today."
    assert save_reaction(prompt_id, "", 1) is True  # clearing is allowed
    assert list_all_prompts(1)[0]["user_reaction"] == ""
    assert save_reaction(9999, "x", 1) is False  # missing prompt
    with pytest.raises(ValueError):
        save_reaction(prompt_id, "x" * 2001, 1)


def test_prompts_survive_restart(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    prompt_id = save_prompt(course_id, "architecture", "Prompt text.", 1)
    save_reaction(prompt_id, "My reaction.", 1)
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT field, prompt_text, user_reaction FROM roommate_prompts "
            "WHERE id = ?", (prompt_id,)).fetchone()
        assert row["field"] == "architecture"
        assert row["prompt_text"] == "Prompt text."
        assert row["user_reaction"] == "My reaction."
# --- generate_due_prompts orchestration --------------------------------


def test_generate_due_prompts_writes_one_per_due_course(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    _seed("Course One")
    _seed("Course Two")
    created = roommate.generate_due_prompts(FakeProvider([GOOD]), 1)
    assert len(created) == 2
    assert len(list_all_prompts(1)) == 2
    # Second run: both prompts are fresh → nothing new.
    assert roommate.generate_due_prompts(FakeProvider([GOOD]), 1) == []


def test_generate_due_prompts_keeps_going_after_bad_parse(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    _seed("Course A")
    _seed("Course B")
    # Course A burns both its draw + retry on garbage; Course B succeeds.
    created = roommate.generate_due_prompts(FakeProvider(["nope", "nope", GOOD]), 1)
    assert len(created) == 1
    assert len(list_all_prompts(1)) == 1
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT action FROM activity_log WHERE entity_type = 'roommate'"
        ).fetchall()
    assert any("generate_failed" in row[0] for row in rows)


def test_generate_due_prompts_isolates_provider_errors(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    _seed()

    class Boom:
        def generate(self, s, u):
            raise roommate.ProviderError("down")

    assert roommate.generate_due_prompts(Boom(), 1) == []
    assert list_all_prompts(1) == []
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT action FROM activity_log WHERE entity_type = 'roommate'"
        ).fetchall()
    assert any("generate_failed" in row[0] for row in rows)
    # The course stays due, so a later success finally fills it.
    created = roommate.generate_due_prompts(FakeProvider([GOOD]), 1)
    assert len(created) == 1

# --- durable "new since your last visit" indicator -----------------------


def test_last_visit_records_and_reads(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    assert dash_visit_at(1) is None
    record_dash_visit(1)
    visit = dash_visit_at(1)
    assert visit is not None
    # A fresh init still remembers the visit in the same DB.
    assert dash_visit_at(1) == visit


def test_visit_clears_indicator_on_next_load(tmp_path, monkeypatch):
    """record_dash_visit() moves the baseline forward so the badge clears on the
    next dashboard load (the durable-but-self-clearing behavior)."""
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    before = _days_ago(0)
    save_prompt(course_id, "architecture", "Prompt.", 1, created_at=before)
    # No visit yet → everything is "new".
    assert prompt_newer_than(None, 1) is not None
    record_dash_visit(1)  # simulate a dashboard render
    after = dash_visit_at(1)
    # Nothing newer than the visit we just recorded.
    assert prompt_newer_than(after, 1) is None
    # A newer prompt appears after the visit → the badge would show.
    newer = _days_ago(0)
    save_prompt(course_id, "jazz", "New prompt.", 1, created_at=newer)
    assert prompt_newer_than(after, 1) is not None


def test_prompt_newer_than_filters_old_prompts(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    course_id, _ = _seed()
    old = _days_ago(5)
    save_prompt(course_id, "architecture", "Old.", 1, created_at=old)
    recent = _days_ago(0)
    save_prompt(course_id, "jazz", "Recent.", 1, created_at=recent)
    # Baseline between the two → only the recent one counts.
    baseline = _days_ago(3)
    matches = prompt_newer_than(baseline, 1)
    assert matches is not None
    assert matches["field"] == "jazz"

    assert len(list_all_prompts(1)) == 2