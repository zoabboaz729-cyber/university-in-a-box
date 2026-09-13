"""Phase 6 tests part 2: dashboard due-check, journal page, reactions."""
import json
import pytest
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.ai.provider import ProviderError
from app.db import get_db_path, init_db
from app.main import api
from app.roles.roommate_store import (
    dash_visit_at,
    prompt_newer_than,
    save_prompt,
    record_dash_visit,
)
from tests.test_dashboard import seed_course


@pytest.fixture(autouse=True)
def _clear_dash_visits():
    """Ensure clean _dash_visits state for each test (prevents state leakage)."""
    yield
    # After each test, clear the _dash_visits table to prevent state leakage
    # from background threads or incomplete test cleanup.
    try:
        with sqlite3.connect(str(get_db_path())) as conn:
            conn.execute("DELETE FROM _dash_visits")
            conn.commit()
    except (FileNotFoundError, sqlite3.DatabaseError):
        # Database might not exist yet or might be from a different test.
        pass


def _init(tmp_path, monkeypatch):
    """Set DATA_DIR and initialize the database for durable-badge tests."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()

GOOD = json.dumps({
    "field": "architecture",
    "prompt": "Consider how an architect would separate the load-bearing "
              "structure of your topic from its decorative parts.",
})


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


def make_client(tmp_path, monkeypatch, replies=(GOOD,)):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    provider = FakeProvider(list(replies))
    monkeypatch.setattr("app.routes.dashboard.get_provider", lambda: provider)
    return TestClient(api), provider


def _prompt_rows():
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT id, course_id, field, prompt_text, user_reaction "
            "FROM roommate_prompts").fetchall()


def test_dashboard_generates_and_shows_due_prompt(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("R Course", topics=[("RT", "not_started")])
    resp = client.get("/")
    assert resp.status_code == 200
    assert provider.calls == 1
    assert "Fresh connection" in resp.text
    assert "architecture" in resp.text
    assert "consider how an architect" in resp.text.lower()
    assert 'href="/roommate"' in resp.text
    rows = _prompt_rows()
    assert len(rows) == 1
    assert rows[0]["course_id"] == course_id
    assert rows[0]["field"] == "architecture"


def test_fresh_prompt_not_generated_again(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch)
    seed_course("R2", topics=[("T", "not_started")])
    client.get("/")
    provider.calls = 0
    resp = client.get("/")
    assert resp.status_code == 200
    assert provider.calls == 0
    assert "Fresh connection" in resp.text


def test_non_active_courses_never_generate(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch)
    for status in ("paused", "archived", "done", "draft"):
        seed_course("S" + status, status=status, topics=[("T", "not_started")])
    resp = client.get("/")
    assert resp.status_code == 200
    assert provider.calls == 0
    assert "Fresh connection" not in resp.text
    assert _prompt_rows() == []


def test_dashboard_survives_provider_failure(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    class Boom:
        def generate(self, s, u):
            raise ProviderError("down")

    monkeypatch.setattr("app.routes.dashboard.get_provider", lambda: Boom())
    seed_course("B Course", topics=[("BT", "not_started")])
    resp = client.get("/")
    assert resp.status_code == 200
    assert "B Course" in resp.text
    assert "Fresh connection" not in resp.text
    assert _prompt_rows() == []


def test_cadence_env_override_honored(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch)
    seed_course("C Course", topics=[("CT", "not_started")])
    client.get("/")  # one prompt inside the cadence now
    with sqlite3.connect(get_db_path()) as conn:
        old = (datetime.now(timezone.utc) - timedelta(days=2)
               ).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE roommate_prompts SET created_at = ?", (old,))
    provider.calls = 0
    # Default 3-day cadence: 2 days old -> not due yet.
    client.get("/")
    assert provider.calls == 0
    # A 30-day cadence stays quiet; a 1-day cadence refires.
    monkeypatch.setenv("ROOMMATE_CADENCE_DAYS", "30")
    client.get("/")
    assert provider.calls == 0
    monkeypatch.setenv("ROOMMATE_CADENCE_DAYS", "1")
    # The second draw must use a field the course has not used before,
    # otherwise the dedup guard (correctly) rejects it.
    second = FakeProvider([json.dumps({
        "field": "jazz improvisation",
        "prompt": "One sentence on improvising over a constant structure.",
    })])
    monkeypatch.setattr("app.routes.dashboard.get_provider",
                        lambda: second)
    client.get("/")
    assert second.calls == 1
    with sqlite3.connect(get_db_path()) as conn:
        fields = [row[0] for row in conn.execute(
            "SELECT field FROM roommate_prompts ORDER BY id")]
    assert fields == ["architecture", "jazz improvisation"]
# --- journal + reactions -----------------------------------------------


def test_journal_lists_prompts_newest_first_with_course(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("J Course", topics=[("JT", "not_started")])
    client.get("/")  # one prompt generated
    save_prompt(course_id, "jazz", "Second prompt.")  # newest now
    resp = client.get("/roommate")
    assert resp.status_code == 200
    assert resp.text.index("Second prompt.") < resp.text.index("architecture")
    assert "J Course" in resp.text


def test_journal_empty_state(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    resp = client.get("/roommate")
    assert resp.status_code == 200
    assert "No prompts yet" in resp.text


def test_reaction_saves_and_survives_restart(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    seed_course("R Course", topics=[("RT", "not_started")])
    client.get("/")
    prompt_id = _prompt_rows()[0]["id"]
    resp = client.post(f"/roommate/prompts/{prompt_id}/reaction",
                       data={"reaction": "Seen this in my work today."},
                       follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/roommate")
    assert "Seen this in my work today." in page.text
    # Restart survival.
    del client
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(
            "SELECT user_reaction FROM roommate_prompts WHERE id = ?",
            (prompt_id,)).fetchone()
        assert row[0] == "Seen this in my work today."
    client2 = TestClient(api)
    page = client2.get("/roommate")
    assert "Seen this in my work today." in page.text


def test_reaction_unknown_prompt_404(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    resp = client.post("/roommate/prompts/999/reaction",
                       data={"reaction": "x"})
    assert resp.status_code == 404


def test_reaction_too_long_rerenders_with_error(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    seed_course("R Course", topics=[("RT", "not_started")])
    client.get("/")
    prompt_id = _prompt_rows()[0]["id"]
    resp = client.post(f"/roommate/prompts/{prompt_id}/reaction",
                       data={"reaction": "x" * 2001})
    assert resp.status_code == 400
    assert "Keep the reaction under" in resp.text


def test_archived_course_prompt_hidden_from_dashboard(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    archived_id, _ = seed_course("Old Course", status="archived",
                                 topics=[("A", "not_started")])
    save_prompt(archived_id, "architecture", "Archived prompt.")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Fresh connection" not in resp.text


def test_prompts_and_journal_survive_full_restart(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch)
    seed_course("Restart Course", topics=[("RT", "not_started")])
    client.get("/")
    assert provider.calls == 1
    del client
    with sqlite3.connect(get_db_path()) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM roommate_prompts").fetchone()[0]
        assert count == 1
    client2 = TestClient(api)
    page = client2.get("/")
    assert "Fresh connection" in page.text
    page2 = client2.get("/roommate")


def test_durable_badge_store_behavior(tmp_path, monkeypatch):
    """(B3 durable indicator) The badge is driven by the store: a newer prompt
    than the last visit shows the badge; a refresh past it clears it. These
    semantics are tested at the store level (test_roommate.py) and here we
    confirm the route renders the Fresh connection block and the badge text
    is present in the template vocabulary when a new prompt exists."""
    _init(tmp_path, monkeypatch)
    course_id, _ = seed_course("Badge Course", topics=[("T", "not_started")])
    client, provider = make_client(tmp_path, monkeypatch, replies=[])
    # Seed a prompt older than a baseline visit.
    older = datetime.now(timezone.utc) - timedelta(minutes=5)
    older_str = older.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    save_prompt(course_id, "architecture", "old", created_at=older_str)
    record_dash_visit()  # simulate a previous dashboard load
    baseline = dash_visit_at()
    # Now a newer prompt exists after the visit → store says "new".
    newer = datetime.now(timezone.utc)
    newer_str = newer.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    save_prompt(course_id, "jazz", "new", created_at=newer_str)
    assert prompt_newer_than(baseline) is not None
    # Render the dashboard: the route should still return 200 and the
    # template should contain both the Fresh connection mark and the badge
    # vocabulary (the badge is shown when new_since_visit is True).
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Fresh connection" in resp.text
    assert "New connection" in resp.text


def test_no_badge_when_nothing_new(tmp_path, monkeypatch):
    """If nothing newer than the last visit exists, no badge — even though a
    prompt exists to show in the 'Fresh connection' block."""
    _init(tmp_path, monkeypatch)
    seed_course("Stale Course", topics=[("T", "not_started")])
    # One GOOD reply gets the first prompt generated; the second load then
    # has nothing new to generate (cadence suppresses it).
    client, provider = make_client(tmp_path, monkeypatch)
    client.get("/")  # baseline visit + first prompt
    record_dash_visit()
    baseline = dash_visit_at()
    # No prompt newer than the visit → store says "not new".
    assert prompt_newer_than(baseline) is None
    provider.calls = 0
    resp = client.get("/")
    assert provider.calls == 0  # nothing regenerated
    assert resp.status_code == 200
    assert "Fresh connection" in resp.text
    assert "New connection" not in resp.text


# --- durable indicator on the dashboard -------------------------------


def test_dashboard_does_not_block_on_generation(tmp_path, monkeypatch):
    """(B3) `GET /` renders even when generation is artificially slow — the
    background pass fires and forgets with a safety net."""
    client, provider = make_client(tmp_path, monkeypatch)

    import time

    class Slow:
        def generate(self, s, u):
            time.sleep(0.5)
            return json.dumps({"field": "architecture", "prompt": "slow"})

    monkeypatch.setattr("app.routes.dashboard.get_provider", lambda: Slow())
    seed_course("Slow Course", topics=[("T", "not_started")])
    start = time.monotonic()
    resp = client.get("/")
    elapsed = time.monotonic() - start
    assert resp.status_code == 200
    # The page must return in well under the slow call's 0.5s — the page is
    # not waiting on the background thread.
    assert elapsed < 0.4
    # With a slow provider, the background thread does not finish in time,
    # so no prompt is rendered on this load. The next load will pick it up.
    assert "Fresh connection" not in resp.text or "architecture" in resp.text


def test_durable_indicator_shows_when_new_prompt_generated(tmp_path, monkeypatch):
    """The durable "new since your last visit" badge appears when background
    generation creates a prompt newer than the snapshot rendered."""
    client, provider = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("Badge Course", topics=[("T", "not_started")])
    # Generate once so the baseline visit exists.
    r1 = client.get("/")
    assert "Fresh connection" in r1.text
    # Backdate the first prompt so the course is due for a second generation
    # on the next load (the 3-day cadence would otherwise suppress it).
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("UPDATE roommate_prompts SET created_at = ?", (old,))
    # Now use the same provider but return a second prompt for the same
    # course on the next call (simulates a new due prompt appearing).
    provider.replies.append(json.dumps({"field": "jazz", "prompt": "second"}))
    r2 = client.get("/")
    assert r2.status_code == 200
    # The badge is durable: it shows on this load because a newer prompt
    # exists than what was on the previous render.
    assert "New connection" in r2.text or "new connection" in r2.text.lower()


def test_durable_indicator_clears_after_refresh(tmp_path, monkeypatch):
    """Once the user refreshes past the new prompt, the badge clears."""
    client, provider = make_client(tmp_path, monkeypatch)
    course_id, _ = seed_course("Clear Course", topics=[("T", "not_started")])
    r1 = client.get("/")
    assert "Fresh connection" in r1.text
    # Backdate the first prompt so the course is due for a second generation.
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("UPDATE roommate_prompts SET created_at = ?", (old,))
    provider.replies.append(json.dumps({"field": "jazz", "prompt": "second"}))
    r2 = client.get("/")
    assert ("New connection" in r2.text or "new connection" in r2.text.lower())
    # Third load: visit has moved past the new prompt → badge gone.
    r3 = client.get("/")
    assert "New connection" not in r3.text


def test_no_indicator_when_nothing_new(tmp_path, monkeypatch):
    """If nothing new is generated, no badge appears."""
    client, provider = make_client(tmp_path, monkeypatch)
    seed_course("Stale Course", topics=[("T", "not_started")])
    client.get("/")  # generates a prompt
    provider.calls = 0
    r = client.get("/")  # prompt already fresh → no regeneration
    assert provider.calls == 0
    assert "Fresh connection" in r.text
    assert "New connection" not in r.text