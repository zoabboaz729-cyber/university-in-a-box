"""Phase 4 tests part 2: HTTP routes + restart survival."""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.main import api
from tests.test_dashboard import seed_course
from tests.test_tutor import FakeProvider, GAP, Q1


def make_client(tmp_path, monkeypatch, replies):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    provider = FakeProvider(replies)
    monkeypatch.setattr("app.routes.tutor.get_provider", lambda: provider)
    return TestClient(api), provider


def _topic():
    _, topic_ids = seed_course("Route Tutor",
                               topics=[("RT", "not_started")])
    return topic_ids[0]


def test_full_session_start_answer_end(tmp_path, monkeypatch):
    q2 = '{"question": "Why does that follow?"}'
    client, _ = make_client(tmp_path, monkeypatch, [Q1, q2, GAP])
    topic_id = _topic()
    resp = client.post(f"/topics/{topic_id}/tutor/start",
                       follow_redirects=False)
    assert resp.status_code == 303
    session_url = resp.headers["location"]
    page = client.get(session_url)
    assert "What is the core idea here?" in page.text
    # Exactly one answer box on an open session.
    assert page.text.count("<textarea") == 1
    from app.roles.tutor_store import get_session
    sid = int(session_url.rsplit("/", 1)[-1])
    turn_id = get_session(sid, user_id=1)["turns"][0]["id"]
    resp2 = client.post(f"/tutor/{sid}/answer",
                        data={"turn_id": str(turn_id), "answer": "My answer"},
                        follow_redirects=False)
    assert resp2.status_code == 303
    page2 = client.get(session_url)
    assert "My answer" in page2.text
    assert "Why does that follow?" in page2.text
    resp3 = client.post(f"/tutor/{sid}/end", follow_redirects=False)
    assert resp3.status_code == 303
    topic_page = client.get(f"/topics/{topic_id}")
    assert "Mixes up X and Y" in topic_page.text
    dash = client.get("/")
    assert "Mixes up X and Y" in dash.text


def test_empty_answer_rerenders_no_write(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [Q1, Q1])
    topic_id = _topic()
    url = client.post(f"/topics/{topic_id}/tutor/start",
                      follow_redirects=False).headers["location"]
    from app.roles.tutor_store import get_session
    sid = int(url.rsplit("/", 1)[-1])
    turn_id = get_session(sid, user_id=1)["turns"][0]["id"]
    resp = client.post(f"/tutor/{sid}/answer",
                       data={"turn_id": str(turn_id), "answer": "   "})
    assert resp.status_code == 200
    assert "Please write an answer" in resp.text
    assert len(get_session(sid, user_id=1)["turns"]) == 1


def test_double_start_resumes_open_session(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch, [Q1])
    topic_id = _topic()
    first = client.post(f"/topics/{topic_id}/tutor/start",
                        follow_redirects=False).headers["location"]
    second = client.post(f"/topics/{topic_id}/tutor/start",
                         follow_redirects=False).headers["location"]
    assert first == second
    assert provider.calls == 1


def test_provider_error_on_start_writes_nothing(tmp_path, monkeypatch):
    from app.ai.provider import ProviderError

    class Boom:
        def generate(self, s, u):
            raise ProviderError("down")

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    monkeypatch.setattr("app.routes.tutor.get_provider", lambda: Boom())
    client = TestClient(api)
    topic_id = _topic()
    resp = client.post(f"/topics/{topic_id}/tutor/start")
    assert resp.status_code == 200
    assert "Could not start the session" in resp.text
    with sqlite3.connect(get_db_path()) as conn:
        assert conn.execute("SELECT * FROM tutor_sessions").fetchall() == []


def test_sessions_survive_restart(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [Q1])
    topic_id = _topic()
    url = client.post(f"/topics/{topic_id}/tutor/start",
                      follow_redirects=False).headers["location"]
    sid = int(url.rsplit("/", 1)[-1])
    del client
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT question FROM tutor_turns WHERE session_id = ?",
            (sid,)).fetchall()
        assert [r["question"] for r in rows] == ["What is the core idea here?"]
    client2 = TestClient(api)
    page = client2.get(url)
    assert "What is the core idea here?" in page.text
def test_tutor_answer_refreshes_days_since_on_dashboard(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    client, _ = make_client(tmp_path, monkeypatch, [Q1, Q1])
    course_id, topic_ids = seed_course("Tutor Clock",
                                       topics=[("TC", "not_started")])
    old = (datetime.now(timezone.utc) - timedelta(days=10)
           ).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("UPDATE courses SET created_at = ? WHERE id = ?",
                     (old, course_id))
    # Backdated course: the dashboard shows it as untouched.
    dash = client.get("/")
    assert "10 day(s) ago" in dash.text
    # One answered tutor turn must refresh the course's activity clock
    # (D-015 — previously tutor_session rows were invisible to it).
    url = client.post(f"/topics/{topic_ids[0]}/tutor/start",
                      follow_redirects=False).headers["location"]
    sid = int(url.rsplit("/", 1)[-1])
    from app.roles.tutor_store import get_session
    turn_id = get_session(sid, user_id=1)["turns"][0]["id"]
    client.post(f"/tutor/{sid}/answer",
                data={"turn_id": str(turn_id), "answer": "An answer"},
                follow_redirects=False)
    dash = client.get("/")
    assert "0 day(s) ago" in dash.text


def test_tutor_retry_generates_when_no_pending(tmp_path, monkeypatch):
    """The retry route re-attempts next question generation after a failure."""
    client, provider = make_client(tmp_path, monkeypatch, [Q1, Q1])
    topic_id = _topic()
    url = client.post(f"/topics/{topic_id}/tutor/start",
                      follow_redirects=False).headers["location"]
    sid = int(url.rsplit("/", 1)[-1])

    # 404 for nonexistent session
    assert client.post("/tutor/99999/retry").status_code == 404

    # With a pending question already present, retry just redirects without adding turns
    resp = client.post(f"/tutor/{sid}/retry", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/tutor/{sid}"

    # Now answer the turn
    from app.roles.tutor_store import get_session
    turn_id = get_session(sid, user_id=1)["turns"][0]["id"]
    client.post(f"/tutor/{sid}/answer",
                data={"turn_id": str(turn_id), "answer": "Answer 1"},
                follow_redirects=False)

    # Now we have 2 turns. Pretend turn 2 was deleted/not generated (simulate failure)
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("DELETE FROM tutor_turns WHERE session_id = ? AND user_answer IS NULL", (sid,))

    # Session has no pending turn now
    page = client.get(f"/tutor/{sid}").text
    assert "Try again" in page

    # Retry now calls the provider and creates the next turn
    provider.replies.append(Q1)
    retry_resp = client.post(f"/tutor/{sid}/retry", follow_redirects=False)
    assert retry_resp.status_code == 303
    assert retry_resp.headers["location"] == f"/tutor/{sid}"

    # Verify new turn was created
    session_after = get_session(sid, user_id=1)
    assert len(session_after["turns"]) == 2
    assert session_after["turns"][1]["question"] == "What is the core idea here?"
