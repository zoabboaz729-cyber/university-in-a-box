"""Desired route behavior when the server-paid AI quota is exhausted.

The real provider factory and key resolver are exercised; HTTPX is routed
through MockTransport so no request can leave the test process.
"""
from html.parser import HTMLParser
import sqlite3

import httpx

from app.ai import provider
from app.ai.quota import QuotaExceeded
from app.auth.dependencies import get_current_user
from app.auth.store import create_user, get_user_by_id
from app.db import get_db_path
from app.main import api
from tests.test_advisor_flow import ANSWERS
from tests.test_editor import _seed_topic as seed_editor_topic
from tests.test_editor_routes import _review_rows
from tests.test_librarian_routes import make_client
from tests.test_tutor import Q1, _seed_topic as seed_tutor_topic


FREE_QUOTA_LIMIT = 10


def wire_provider_network(monkeypatch, content=Q1):
    """Keep real provider requests local and return one valid model response."""
    requests = []
    transport = httpx.MockTransport(
        lambda request: _mock_provider_response(requests, request, content)
    )
    real_async_client = httpx.AsyncClient

    def client_with_mock_transport(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_with_mock_transport)
    return requests


def _mock_provider_response(requests, request, content):
    requests.append(request)
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


class ErrorMessageParser(HTMLParser):
    """Collect visible text and links only from callout-error message areas."""

    def __init__(self):
        super().__init__()
        self.message_depth = 0
        self.messages = []
        self.active_messages = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div":
            is_error_message = any(
                name == "class" and "callout-error" in (value or "").split()
                for name, value in attrs
            )
            if self.message_depth:
                self.message_depth += 1
            elif is_error_message:
                self.message_depth = 1
            if self.message_depth and is_error_message:
                message = {
                    "depth": self.message_depth,
                    "text": [],
                }
                self.messages.append(message)
                self.active_messages.append(message)
    def handle_endtag(self, tag):
        if tag == "div" and self.message_depth:
            self.message_depth -= 1
            while (
                self.active_messages
                and self.active_messages[-1]["depth"] > self.message_depth
            ):
                self.active_messages.pop()

    def handle_data(self, data):
        if self.message_depth:
            for message in self.active_messages:
                message["text"].append(data)


def spy_quota_resolution(monkeypatch):
    calls = {"users": [], "raised": []}
    real_resolver = provider.resolve_ai_key_for_user

    def resolve_with_spy(user):
        calls["users"].append(dict(user) if user is not None else None)
        try:
            return real_resolver(user)
        except QuotaExceeded as exc:
            calls["raised"].append(exc)
            raise

    monkeypatch.setattr(provider, "resolve_ai_key_for_user", resolve_with_spy)
    return calls


def quota_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai_compatible")
    monkeypatch.setenv("AI_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.setenv("AI_API_KEY", "test-server-key")
    monkeypatch.setenv("MAX_FREE_QUOTA", str(FREE_QUOTA_LIMIT))
    client = make_client(tmp_path, monkeypatch)
    create_user("quota-test@local", "", "Quota Test User")
    # conftest's auth override only supplies id/email/name. Routes pass this
    # full DB row to get_provider(user=user), so the provider sees the quota
    # and BYOK fields; the spy below verifies their actual values at resolution.
    api.dependency_overrides[get_current_user] = lambda: get_user_by_id(1)
    requests = wire_provider_network(monkeypatch)
    quota_calls = spy_quota_resolution(monkeypatch)
    return client, requests, quota_calls


def set_quota_used(used):
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "UPDATE users SET ai_quota_used = ?, encrypted_ai_key = NULL "
            "WHERE id = 1",
            (used,),
        )


def assert_quota_response(response):
    assert response.status_code != 500
    parser = ErrorMessageParser()
    parser.feed(response.text)
    quota_messages = [
        message
        for message in parser.messages
        if "quota is exhausted" in "".join(message["text"]).casefold()
    ]
    assert quota_messages
    return quota_messages


def assert_quota_was_exceeded(quota_calls):
    assert quota_calls["users"]
    assert all(
        user["ai_quota_used"] >= FREE_QUOTA_LIMIT
        and user["encrypted_ai_key"] is None
        for user in quota_calls["users"]
    )
    assert quota_calls["raised"]


def seed_open_tutor_session(answer=None):
    topic_id = seed_tutor_topic()
    from app.roles.tutor_store import add_turn, save_answer, start_session

    session_id = start_session(topic_id, user_id=1)
    turn_id = add_turn(session_id, "What is the core idea here?", user_id=1)
    if answer is not None:
        save_answer(turn_id, answer, user_id=1)
    return topic_id, session_id, turn_id


def test_tutor_start_quota_error_leaves_no_session(tmp_path, monkeypatch):
    client, requests, quota_calls = quota_client(tmp_path, monkeypatch)
    topic_id = seed_tutor_topic()
    set_quota_used(FREE_QUOTA_LIMIT)

    response = client.post(
        f"/topics/{topic_id}/tutor/start",
        follow_redirects=False,
    )

    assert_quota_response(response)
    assert_quota_was_exceeded(quota_calls)
    assert len(requests) == 0
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT id FROM tutor_sessions WHERE topic_id = ?",
            (topic_id,),
        ).fetchall()
    assert rows == []


def test_tutor_answer_quota_error_keeps_answer_and_open_session(
        tmp_path, monkeypatch):
    client, requests, quota_calls = quota_client(tmp_path, monkeypatch)
    _, session_id, turn_id = seed_open_tutor_session()
    set_quota_used(FREE_QUOTA_LIMIT)

    response = client.post(
        f"/tutor/{session_id}/answer",
        data={"turn_id": str(turn_id), "answer": "My saved answer."},
    )

    assert_quota_response(response)
    assert_quota_was_exceeded(quota_calls)
    assert len(requests) == 0
    from app.roles.tutor_store import get_session

    session = get_session(session_id, user_id=1)
    assert session["turns"][0]["user_answer"] == "My saved answer."
    assert session["ended_at"] is None


def test_tutor_end_quota_error_keeps_session_open(tmp_path, monkeypatch):
    client, requests, quota_calls = quota_client(tmp_path, monkeypatch)
    _, session_id, _ = seed_open_tutor_session()
    set_quota_used(FREE_QUOTA_LIMIT)

    response = client.post(f"/tutor/{session_id}/end")

    assert_quota_response(response)
    assert_quota_was_exceeded(quota_calls)
    assert len(requests) == 0
    from app.roles.tutor_store import get_session

    assert get_session(session_id, user_id=1)["ended_at"] is None


def test_tutor_retry_quota_error_leaves_session_unchanged(
        tmp_path, monkeypatch):
    client, requests, quota_calls = quota_client(tmp_path, monkeypatch)
    _, session_id, _ = seed_open_tutor_session(answer="Already answered.")
    set_quota_used(FREE_QUOTA_LIMIT)
    from app.roles.tutor_store import get_session

    before = get_session(session_id, user_id=1)

    response = client.post(f"/tutor/{session_id}/retry")

    assert_quota_response(response)
    assert_quota_was_exceeded(quota_calls)
    assert len(requests) == 0
    assert get_session(session_id, user_id=1) == before


def test_advisor_submit_answer_quota_error_keeps_interview(
        tmp_path, monkeypatch):
    client, requests, quota_calls = quota_client(tmp_path, monkeypatch)
    created = client.post(
        "/advisor/new",
        data={"topic": "Spanish"},
        follow_redirects=False,
    )
    interview_id = int(created.headers["location"].rsplit("/", 1)[-1])
    from app.roles import advisor

    for step in advisor.STEPS[:-1]:
        response = client.post(
            f"/advisor/{interview_id}",
            data={"step": step, "answer": ANSWERS[step]},
            follow_redirects=False,
        )
        assert response.status_code != 500
    set_quota_used(FREE_QUOTA_LIMIT)

    response = client.post(
        f"/advisor/{interview_id}",
        data={
            "step": advisor.STEPS[-1],
            "answer": ANSWERS[advisor.STEPS[-1]],
        },
    )

    assert_quota_response(response)
    assert_quota_was_exceeded(quota_calls)
    assert len(requests) == 0
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT step, answer FROM advisor_interviews "
            "WHERE course_id = ? ORDER BY id",
            (interview_id,),
        ).fetchall()
        course = conn.execute(
            "SELECT status FROM courses WHERE id = ?",
            (interview_id,),
        ).fetchone()
    assert len(rows) == len(advisor.STEPS)
    assert dict(rows)[advisor.STEPS[-1]] == ANSWERS[advisor.STEPS[-1]]
    assert course[0] == "draft"


def test_editor_submit_quota_error_stores_nothing_and_preserves_text(
        tmp_path, monkeypatch):
    client, requests, quota_calls = quota_client(tmp_path, monkeypatch)
    topic_id = seed_editor_topic()
    submission = "My draft must stay in the form."
    set_quota_used(FREE_QUOTA_LIMIT)

    response = client.post(
        f"/topics/{topic_id}/editor/submit",
        data={"submission": submission},
    )

    assert_quota_response(response)
    assert_quota_was_exceeded(quota_calls)
    assert len(requests) == 0
    assert _review_rows(topic_id) == []
    assert submission in response.text


def test_tutor_start_under_quota_still_creates_session(
        tmp_path, monkeypatch):
    client, requests, quota_calls = quota_client(tmp_path, monkeypatch)
    topic_id = seed_tutor_topic()

    response = client.post(
        f"/topics/{topic_id}/tutor/start",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert quota_calls["users"]
    assert all(
        user["ai_quota_used"] < FREE_QUOTA_LIMIT
        and user["encrypted_ai_key"] is None
        for user in quota_calls["users"]
    )
    assert not quota_calls["raised"]
    assert len(requests) == 1
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(
            "SELECT id FROM tutor_sessions WHERE topic_id = ?",
            (topic_id,),
        ).fetchone()
    assert row is not None
