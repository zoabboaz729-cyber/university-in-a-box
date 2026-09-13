"""Phase 3 tests part 2: HTTP routes + restart survival."""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.main import api
from tests.test_dashboard import seed_course
from tests.test_librarian import GOOD


class FakeProvider:
    def generate(self, system_prompt, user_message):
        return GOOD


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    return TestClient(api)


def test_add_source_posts_verdict_and_shows_it(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.librarian.get_provider",
                        lambda: FakeProvider())
    _, topic_ids = seed_course("Route Course",
                               topics=[("Route Topic", "not_started")])
    topic_id = topic_ids[0]
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Great Book",
                                 "reference": "https://example.com/g"},
                           follow_redirects=False)
    assert response.status_code == 303
    page = client.get(f"/topics/{topic_id}")
    assert "Great Book" in page.text
    assert "keep" in page.text
    assert "hands-on practice" in page.text
    assert "Shelf view" in page.text


def test_shelf_view_filters_keep_only(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.librarian.get_provider",
                        lambda: FakeProvider())
    _, topic_ids = seed_course("Shelf Course",
                               topics=[("Shelf Topic", "not_started")])
    topic_id = topic_ids[0]
    from app.roles.source_store import add_source
    add_source(topic_id, "Keep Me", "ref", "keep",
               "Good for study. Solid.")
    add_source(topic_id, "Skip Me", "ref", "skip",
               "Good for nothing. Thin.")
    all_page = client.get(f"/topics/{topic_id}")
    assert "Keep Me" in all_page.text
    assert "Skip Me" in all_page.text
    shelf = client.get(f"/topics/{topic_id}/shelf")
    assert shelf.status_code == 200
    assert "Keep Me" in shelf.text
    assert "Skip Me" not in shelf.text
    assert "Shelf (keep only)" in shelf.text


def test_provider_error_renders_inline_and_writes_nothing(
        tmp_path, monkeypatch):
    from app.ai.provider import ProviderError

    class BoomProvider:
        def generate(self, system_prompt, user_message):
            raise ProviderError("down")

    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.librarian.get_provider",
                        lambda: BoomProvider())
    _, topic_ids = seed_course("Err Course",
                               topics=[("Err Topic", "not_started")])
    topic_id = topic_ids[0]
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "X", "reference": "Y"})
    assert response.status_code == 200
    assert "Could not judge that source" in response.text
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT * FROM sources WHERE topic_id = ?",
            (topic_id,)).fetchall()
        assert rows == []


def test_sources_survive_restart(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.librarian.get_provider",
                        lambda: FakeProvider())
    _, topic_ids = seed_course("Restart Lib",
                               topics=[("Restart Topic", "not_started")])
    topic_id = topic_ids[0]
    client.post(f"/topics/{topic_id}/sources",
                data={"label": "Persisted", "reference": "ref"})
    del client
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT label, verdict FROM sources WHERE topic_id = ?",
            (topic_id,)).fetchall()
        assert [(r["label"], r["verdict"]) for r in rows] == [
            ("Persisted", "keep")]
    client2 = TestClient(api)
    shelf = client2.get(f"/topics/{topic_id}/shelf")
    assert "Persisted" in shelf.text
