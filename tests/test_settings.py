"""Phase 7 completion — Settings page tests.

Covers: the masked key display uses the SAME variable the provider reads
(AI_API_KEY — regression: it used to read a bogus OPENROUTER_API_KEY and
always showed "(not set)"), "(not set)" when no key exists, cadence
validation + update, the per-course pause default toggle (which is read
by course_store.confirm_curriculum for new Courses), persistence of both
settings to the .env file (the write path is pointed at a temp file so a
test run never rewrites the real .env), and the Settings nav link added
to the shared nav.
"""
import os
import sqlite3

from fastapi.testclient import TestClient

from app.ai.config import AIConfig
from app.db import get_db_path, init_db
from app.main import api
from app.routes import settings as settings_module


def _fake_load_config():
    """A key source that reads os.environ only — never the real repo .env."""
    return AIConfig(
        provider="openai_compatible",
        base_url="http://example.test/v1",
        model="fake",
        api_key=os.environ.get("AI_API_KEY", ""),
    )


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    monkeypatch.setattr(settings_module, "load_config", _fake_load_config)
    monkeypatch.setattr(settings_module, "ENV_FILE", tmp_path / ".env")
    return TestClient(api)


def _seed_draft_course(title="Draft Row"):
    """A draft course row, mirroring an in-progress Advisor interview."""
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "INSERT INTO courses (title, status) VALUES (?, 'draft')",
            (title,),
        )
        return cur.lastrowid


def _confirm(course_id: int, title="Real Title"):
    from app.roles.course_store import confirm_curriculum
    confirm_curriculum(
        course_id, title,
        [{"title": "T1", "milestone_description": "M1", "time_box": "1 week"}],
        {"destination": "d", "baseline": "b", "cut_list": "c"},
    )


def _course_status(course_id: int) -> str:
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM courses WHERE id = ?",
                           (course_id,)).fetchone()
    return row["status"]


def test_settings_shows_not_set_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "(not set)" in resp.text
    assert "Roommate Cadence" in resp.text


def test_settings_masks_the_real_key(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "sk-live-9999")
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/settings")
    body = resp.text
    assert "(not set)" not in body
    assert "9999" in body          # last 4 chars visible
    assert "sk-live" not in body   # the actual key must never appear


def test_settings_nav_link_on_every_page(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    for url in ["/", "/advisor/new"]:
        resp = client.get(url)
        assert resp.status_code == 200
        assert 'href="/settings"' in resp.text, f"no Settings link on {url}"


def test_cadence_below_one_rejected(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/settings", data={"cadence_days": "0"})
    assert resp.status_code == 400
    assert "at least 1 day" in resp.text
    # The error render also carries the backup note (06-MONITORING §A).
    assert "Backup" in resp.text


def test_settings_shows_backup_note(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/settings").text
    assert "Backup" in page
    assert "university.db" in page
    assert "No backup found" in page  # fresh temp DB dir: nothing to find

    (tmp_path / "university.db.backup-20260913-000000").write_text(
        "fake-backup", encoding="utf-8"
    )
    page = client.get("/settings").text
    assert "university.db.backup-20260913-000000" in page
    assert "No backup found" not in page


def test_last_backup_info_picks_newest_and_age(tmp_path):
    from app.roles.roommate_store import last_backup_info
    assert last_backup_info(tmp_path)["exists"] is False
    a = tmp_path / "university.db.backup-20200101-000000"
    b = tmp_path / "university.db.backup-20210101-000000"
    a.write_text("old", encoding="utf-8")
    b.write_text("new", encoding="utf-8")
    info = last_backup_info(tmp_path)
    assert info["exists"] is True
    assert info["name"] == b.name
    assert isinstance(info["age_days"], int) and info["age_days"] >= 0


def test_cadence_update_persists_to_env_file(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/settings",
        data={"cadence_days": "7", "new_courses_start_paused": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert os.environ["ROOMMATE_CADENCE_DAYS"] == "7"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ROOMMATE_CADENCE_DAYS=7" in env_text
    # The unchecked checkbox still records its (off) value, like the cadence.
    assert "NEW_COURSES_START_PAUSED=false" in env_text


def test_new_courses_start_active_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("NEW_COURSES_START_PAUSED", raising=False)
    client = make_client(tmp_path, monkeypatch)
    course_id = _seed_draft_course()
    _confirm(course_id)
    assert _course_status(course_id) == "active"


def test_new_courses_start_paused_when_set(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/settings",
        data={"cadence_days": "3", "new_courses_start_paused": "on"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert os.environ["NEW_COURSES_START_PAUSED"] == "true"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "NEW_COURSES_START_PAUSED=true" in env_text
    # A brand-new confirmed Course must come out paused.

    course_id = _seed_draft_course("Second Draft")
    _confirm(course_id)
    assert _course_status(course_id) == "paused"


def test_write_env_value_preserves_other_lines(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nAI_API_KEY=super-secret\nROOMMATE_CADENCE_DAYS=3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ENV_FILE", env_file)
    settings_module.write_env_value("ROOMMATE_CADENCE_DAYS", "5")
    text = env_file.read_text(encoding="utf-8")
    assert "ROOMMATE_CADENCE_DAYS=5" in text
    assert "AI_API_KEY=super-secret" in text  # secrets untouched
    assert "# comment" in text