"""Phase 5 tests part 2: HTTP routes + done-gating + restart survival."""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.main import api
from tests.test_dashboard import seed_course
from tests.test_editor import GOOD, FakeProvider


def make_client(tmp_path, monkeypatch, replies=(GOOD,)):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    provider = FakeProvider(list(replies))
    monkeypatch.setattr("app.routes.editor.get_provider", lambda: provider)
    return TestClient(api), provider


def _topic():
    _, topic_ids = seed_course("Route Editor",
                               topics=[("RT", "not_started")])
    return topic_ids[0]


def _review_rows(topic_id):
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM editor_reviews WHERE topic_id = ?",
            (topic_id,)).fetchall()


def test_submit_saves_review_and_shows_it(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    topic_id = _topic()
    resp = client.post(f"/topics/{topic_id}/editor/submit",
                       data={"submission": "My draft answer."},
                       follow_redirects=False)
    assert resp.status_code == 303
    page = client.get(f"/topics/{topic_id}")
    assert "The argument is direct" in page.text
    assert "contradicts the claim" in page.text
    assert "Replace the X example" in page.text
    rows = _review_rows(topic_id)
    assert len(rows) == 1
    assert rows[0]["submitted_text"] == "My draft answer."


def test_empty_submission_rerenders_no_write(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch)
    topic_id = _topic()
    resp = client.post(f"/topics/{topic_id}/editor/submit",
                       data={"submission": "   "})
    assert resp.status_code == 200
    assert "Write or paste what you produced" in resp.text
    assert provider.calls == 0
    assert _review_rows(topic_id) == []


def test_provider_error_preserves_submission_writes_nothing(
        tmp_path, monkeypatch):
    from app.ai.provider import ProviderError

    class Boom:
        def generate(self, s, u):
            raise ProviderError("down")

    client, _ = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.editor.get_provider", lambda: Boom())
    topic_id = _topic()
    resp = client.post(f"/topics/{topic_id}/editor/submit",
                       data={"submission": "My kept draft."})
    assert resp.status_code == 200
    assert "Could not review that submission" in resp.text
    assert "My kept draft." in resp.text  # submission preserved in the form
    assert _review_rows(topic_id) == []


def test_bad_parse_after_retry_renders_error_no_write(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch,
                            replies=["garbage", "garbage"])
    topic_id = _topic()
    resp = client.post(f"/topics/{topic_id}/editor/submit",
                       data={"submission": "My draft."})
    assert resp.status_code == 200
    assert "came back in a bad shape" in resp.text
    assert "My draft." in resp.text
    assert _review_rows(topic_id) == []


def test_done_blocked_without_review(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    topic_id = _topic()
    resp = client.post(f"/topics/{topic_id}/status",
                       data={"status": "done"}, follow_redirects=False)
    assert resp.status_code == 200
    assert "needs at least one Editor review" in resp.text
    with sqlite3.connect(get_db_path()) as conn:
        status = conn.execute("SELECT status FROM topics WHERE id = ?",
                              (topic_id,)).fetchone()[0]
    assert status == "not_started"


def test_done_allowed_after_review_and_reopen_ungated(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    topic_id = _topic()
    client.post(f"/topics/{topic_id}/editor/submit",
                data={"submission": "My draft answer."})
    resp = client.post(f"/topics/{topic_id}/status",
                       data={"status": "done"}, follow_redirects=False)
    assert resp.status_code == 303
    with sqlite3.connect(get_db_path()) as conn:
        status = conn.execute("SELECT status FROM topics WHERE id = ?",
                              (topic_id,)).fetchone()[0]
    assert status == "done"
    # Reopen needs no review.
    resp2 = client.post(f"/topics/{topic_id}/status",
                        data={"status": "in_progress"},
                        follow_redirects=False)
    assert resp2.status_code == 303
    with sqlite3.connect(get_db_path()) as conn:
        status = conn.execute("SELECT status FROM topics WHERE id = ?",
                              (topic_id,)).fetchone()[0]
    assert status == "in_progress"


def test_review_and_gate_state_survive_restart(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    topic_id = _topic()
    client.post(f"/topics/{topic_id}/editor/submit",
                data={"submission": "My draft answer."})
    del client
    with sqlite3.connect(get_db_path()) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM editor_reviews WHERE topic_id = ?",
            (topic_id,)).fetchone()[0]
        assert count == 1
    client2 = TestClient(api)
    page = client2.get(f"/topics/{topic_id}")
    assert "The argument is direct" in page.text
    resp = client2.post(f"/topics/{topic_id}/status",
                        data={"status": "done"}, follow_redirects=False)
    assert resp.status_code == 303  # gate satisfied even after restart


def test_dashboard_shows_last_review_note(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    topic_id = _topic()
    dash = client.get("/")
    assert "last review:" not in dash.text
    client.post(f"/topics/{topic_id}/editor/submit",
                data={"submission": "My draft answer."})
    dash = client.get("/")
    assert "last review:" in dash.text
    assert "contradicts the claim" in dash.text