"""Librarian BYOK + quota: the provider must be built from the FULL user row.

The Librarian used to hand ``get_provider`` an id-only dict
(``{"id": user_id}``), so a user's own stored key (BYOK) was never seen and
the free-quota check never ran, while the counter still incremented. The
other roles (Tutor, Editor, Advisor) already pass the whole user row.

These tests cover the three cases from docs/05-VERIFICATION.md item 4:
a key-holding user gets a provider built with that key, a server-key user
over quota sees a friendly page (not a 500) and stores nothing, and the
ordinary path is unchanged.

No real network here: the fetch seam is stubbed and the provider seam is
either stubbed (FakeProvider) or the real one, which fails on the quota
check BEFORE any outbound request.
"""
import sqlite3

import pytest

from app.ai.quota import resolve_ai_key_for_user
from app.auth.dependencies import get_current_user
from app.auth.security import encrypt_api_key
from app.auth.store import create_user, get_user_by_id, update_user_ai_key
from app.db import get_db_path
from app.main import api
from tests.test_librarian_routes import (
    FakeFetcher,
    FakeProvider,
    make_client,
    make_topic,
    stored_rows,
    wire,
)

BYOK_KEY = "sk-user-byok-key"
SERVER_KEY = "server-test-key"


class RecordingProviderFactory:
    """Stands in for get_provider and records the user object it received.

    A provider built from the full user row is what makes BYOK work; this
    records exactly what the route handed over.
    """

    def __init__(self, provider=None):
        self.provider = provider or FakeProvider()
        self.users = []  # one entry per call that received a user

    def __call__(self, user=None):
        if user is not None:
            self.users.append(user)
        return self.provider


@pytest.fixture
def user_factory():
    """Create a REAL user row and make the Librarian route see THAT row.

    The dependency override is restored when the test ends, so the shared
    conftest test user is back in place for the next test.
    """
    previous = api.dependency_overrides.get(get_current_user)

    def _make(byok_key="", quota_used=0):
        user = create_user("owner@local", "hash", "Owner")
        user_id = user["id"]
        if byok_key:
            update_user_ai_key(user_id, encrypt_api_key(byok_key))
        with sqlite3.connect(get_db_path()) as conn:
            conn.execute("UPDATE users SET ai_quota_used = ? WHERE id = ?",
                         (quota_used, user_id))
            conn.commit()
        api.dependency_overrides[get_current_user] = (
            lambda: get_user_by_id(user_id))
        return user_id
    yield _make
    if previous is None:
        api.dependency_overrides.pop(get_current_user, None)
    else:
        api.dependency_overrides[get_current_user] = previous


def wire_fetcher(monkeypatch, fetcher=None):
    """Patch ONLY the fetch seam — the real provider stays in place.

    Used by the BYOK and quota tests: the key resolution and the quota
    check live in the real provider, so it must not be stubbed out.
    """
    monkeypatch.setattr("app.routes.librarian.fetch_source_text",
                        fetcher or FakeFetcher())


# --- (a) a user with a stored BYOK key gets a provider built with that key --

def test_stored_byok_key_reaches_the_provider(tmp_path, monkeypatch,
                                              user_factory):
    client = make_client(tmp_path, monkeypatch)
    user_id = user_factory(byok_key=BYOK_KEY)
    factory = RecordingProviderFactory()
    monkeypatch.setattr("app.routes.librarian.get_provider", factory)
    wire_fetcher(monkeypatch)
    topic_id = make_topic()

    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Keyed Book",
                                 "reference": "https://example.com/k"},
                           follow_redirects=False)

    assert response.status_code == 303
    # The route handed the WHOLE user row to get_provider — not {"id": ...}.
    assert len(factory.users) == 1
    handed = factory.users[0]
    assert handed["id"] == user_id
    assert handed["encrypted_ai_key"]
    # ...and that row resolves to the user's own key, not the server key.
    assert resolve_ai_key_for_user(handed) == (BYOK_KEY, "byok")
    # The normal flow still completed on top of it.
    rows = stored_rows(topic_id)
    assert len(rows) == 1 and rows[0]["verdict"] == "keep"


# --- (b) a server-key user over quota: friendly page, nothing stored -------

def test_over_quota_user_gets_the_friendly_page_and_stores_nothing(
        tmp_path, monkeypatch, user_factory):
    client = make_client(tmp_path, monkeypatch)
    # Server-key user who has already spent the free quota.
    user_factory(quota_used=1)
    monkeypatch.setenv("MAX_FREE_QUOTA", "1")
    monkeypatch.setenv("AI_API_KEY", SERVER_KEY)
    wire_fetcher(monkeypatch)
    topic_id = make_topic()

    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Over Quota",
                                 "reference": "https://example.com/q"})

    # A friendly page — not a 500 (an uncaught QuotaExceeded would raise
    # out of the test client instead of returning a response).
    assert response.status_code == 200
    assert "quota is exhausted" in response.text
    assert "Add your own API key in Settings" in response.text
    # Nothing was stored on this path.
    assert stored_rows(topic_id) == []


# --- (c) the ordinary path is unchanged -----------------------------------

def test_normal_user_path_is_unchanged(tmp_path, monkeypatch, user_factory):
    client = make_client(tmp_path, monkeypatch)
    user_factory()
    provider = FakeProvider()
    wire(monkeypatch, provider)
    topic_id = make_topic()

    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Ordinary Book",
                                 "reference": "https://example.com/o"},
                           follow_redirects=False)

    assert response.status_code == 303
    assert provider.calls == 1
    rows = stored_rows(topic_id)
    assert len(rows) == 1
    assert rows[0]["label"] == "Ordinary Book"
    assert rows[0]["verdict"] == "keep"
    assert rows[0]["verified_at"]