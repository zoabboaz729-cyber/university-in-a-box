"""Phase 3 tests part 2: HTTP routes + restart survival.
Stage 3 Task 7 rewrites these around the THREE explicit outcomes of adding
a source: verified-accept, verified-reject, and unavailable (retry / keep
as unverified / discard). Fetching is mocked at the app.fetching boundary
and the model at get_provider, so there is no live network here and no
assertion depends on a real model's opinion.
"""
import sqlite3
from html import unescape

from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.fetching import FetchedSource
from app.main import api
from app.roles.source_store import add_source, get_source
from tests.test_dashboard import seed_course

VERIFY_GOOD = ('{"accepted": true, "fit": "worked examples matching the '
               'milestone", "credibility": "a real, sourced explainer", '
               '"access": "free", '
               '"reason": "Read it — worked examples match the milestone."}')

VERIFY_REJECT = ('{"accepted": false, "fit": "covers a different topic", '
                 '"credibility": "thin marketing page", '
                 '"access": "unknown", '
                 '"reason": "Read it — it is a sales page, not study."}')


class FakeProvider:
    """Returns a fixed judgment and records the text it was shown."""

    def __init__(self, reply=VERIFY_GOOD):
        self.reply = reply
        self.calls = 0
        self.last_message = None

    def generate(self, system_prompt, user_message):
        self.calls += 1
        self.last_message = user_message
        return self.reply


class FakeFetcher:
    """Stands in for app.fetching.fetch_source_text — no network."""

    def __init__(self, ok=True, text="Readable page text.",
                 reason="the site blocked the request", kind="page"):
        self.result = FetchedSource(ok=ok, kind=kind, text=text, reason=reason)
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self.result


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    return TestClient(api)


def wire(monkeypatch, provider=None, fetcher=None):
    """Replace the route module's fetch + provider seams."""
    monkeypatch.setattr("app.routes.librarian.get_provider",
                        lambda: provider or FakeProvider())
    monkeypatch.setattr("app.routes.librarian.fetch_source_text",
                        fetcher or FakeFetcher())


def make_topic(title="Route Course"):
    _, topic_ids = seed_course(title, topics=[("Route Topic", "not_started")])
    return topic_ids[0]


def stored_rows(topic_id):
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM sources WHERE topic_id = ?", (topic_id,)).fetchall()


# --- Outcome 1: verified-accept -------------------------------------------

def test_outcome_one_verified_accept_stores_and_shows_judgment(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    provider = FakeProvider()
    wire(monkeypatch, provider)
    topic_id = make_topic()
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Great Book",
                                 "reference": "https://example.com/g"},
                           follow_redirects=False)
    assert response.status_code == 303
    page = unescape(client.get(f"/topics/{topic_id}").text)
    assert "Great Book" in page
    assert "worked examples matching the milestone" in page
    assert "Access: free (the model's judgment)." in page
    assert "Unverified — not read" not in page
    # One fetch, one LLM call, made from the text that was read.
    assert provider.calls == 1
    assert "Readable page text." in provider.last_message
    rows = stored_rows(topic_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "keep"
    assert rows[0]["verified_at"]
    reason = rows[0]["reason"]
    assert reason.startswith("Read: ")  # the model's own one-line reason
    assert "Fit: " in reason and "Access: free" in reason


def test_outcome_one_sends_the_scope_descriptor_to_the_model(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    provider = FakeProvider()
    wire(monkeypatch, provider)
    topic_id = make_topic()
    client.post(f"/topics/{topic_id}/sources",
                data={"label": "L", "reference": "https://example.com/l"})
    assert "Route Topic" in provider.last_message


# --- Outcome 2: verified-reject -------------------------------------------

def test_outcome_two_reject_shows_reasons_and_stores_nothing(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    wire(monkeypatch, FakeProvider(VERIFY_REJECT))
    topic_id = make_topic()
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Sales Page",
                                 "reference": "https://example.com/ad"})
    assert response.status_code == 200
    html = unescape(response.text)
    assert "read it and said no" in html
    assert "sales page" in html
    assert stored_rows(topic_id) == []


def test_missing_label_is_refused_without_fetching(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    fetcher = FakeFetcher()
    wire(monkeypatch, fetcher=fetcher)
    topic_id = make_topic()
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "   ",
                                 "reference": "https://example.com/x"})
    assert response.status_code == 200
    assert "short label" in response.text
    assert fetcher.urls == []


# --- Outcome 3: unavailable → retry / keep unverified / discard -------------

def test_outcome_three_unavailable_offers_all_three_choices(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    fetcher = FakeFetcher(ok=False, text="", reason="the site blocked us")
    wire(monkeypatch, fetcher=fetcher)
    topic_id = make_topic()
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Blocked", "reference": "https://x.y/z"})
    assert response.status_code == 200
    assert "the site blocked us" in response.text
    assert "Retry now" in response.text
    assert "Keep as unverified" in response.text
    assert "Discard" in response.text
    assert "decision" in response.text
    # Nothing is ever stored as verified without having been read.
    assert stored_rows(topic_id) == []


def test_outcome_three_keep_unverified_stores_a_badged_row(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    wire(monkeypatch,
         fetcher=FakeFetcher(ok=False, text="", reason="no transcript"))
    topic_id = make_topic()
    response = client.post(
        f"/topics/{topic_id}/sources",
        data={"label": "Unread Video", "reference": "https://x.y/z",
              "decision": "keep_unverified"}, follow_redirects=False)
    assert response.status_code == 303
    page = client.get(f"/topics/{topic_id}")
    assert "Unverified — not read" in page.text
    assert "Verify now" in page.text
    rows = stored_rows(topic_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "unverified"
    assert rows[0]["verified_at"] is None
    assert "no transcript" in rows[0]["reason"]


def test_outcome_three_discard_stores_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    wire(monkeypatch, fetcher=FakeFetcher(ok=False, text="", reason="nope"))
    topic_id = make_topic()
    client.post(f"/topics/{topic_id}/sources",
                data={"label": "Dropped", "reference": "https://x.y/z",
                      "decision": "discard"})
    assert stored_rows(topic_id) == []


# --- Explicit failures (never a silent accept, never a crash) ---------------

def test_judgment_parse_failure_is_a_clear_error_and_stores_nothing(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    wire(monkeypatch, FakeProvider("this is not JSON at all"))
    topic_id = make_topic()
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Junk Judgment",
                                 "reference": "https://example.com/j"})
    assert response.status_code == 200
    assert "judgment could not be read" in response.text
    assert stored_rows(topic_id) == []


def test_ssrf_url_is_refused_through_the_add_source_form(
        tmp_path, monkeypatch):
    """The real app.fetching guard runs here (it refuses before any
    connection), so the form shows a visible refusal and stores nothing."""
    client = make_client(tmp_path, monkeypatch)
    # Only the provider is faked: the refusal must happen before the LLM.
    monkeypatch.setattr("app.routes.librarian.get_provider",
                        lambda: FakeProvider())
    topic_id = make_topic()
    response = client.post(f"/topics/{topic_id}/sources",
                           data={"label": "Sneaky",
                                 "reference": "http://127.0.0.1:8000/settings"})
    assert response.status_code == 200
    assert ("Couldn't read that source" in response.text
            or "not added" in response.text)
    assert "Retry now" in response.text
    assert stored_rows(topic_id) == []


# --- Course-level sources behave identically --------------------------------

def test_course_level_source_is_verified_and_listed_on_the_course_page(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    provider = FakeProvider()
    wire(monkeypatch, provider)
    course_id, _ = seed_course("Course Scope",
                               topics=[("C Topic", "not_started")])
    response = client.post(f"/courses/{course_id}/sources",
                           data={"label": "Whole Course Book",
                                 "reference": "https://example.com/w"},
                           follow_redirects=False)
    assert response.status_code == 303
    page = unescape(client.get(f"/courses/{course_id}").text)
    assert "Course sources" in page
    assert "Whole Course Book" in page
    assert "Access: free (the model's judgment)." in page
    assert provider.calls == 1
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM sources WHERE course_id = ?",
                           (course_id,)).fetchone()
    assert row["topic_id"] is None
    assert row["verified_at"]


def test_course_level_source_can_be_kept_unverified(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    wire(monkeypatch, fetcher=FakeFetcher(ok=False, text="", reason="blocked"))
    course_id, _ = seed_course("Course Scope 2",
                               topics=[("C Topic", "not_started")])
    client.post(f"/courses/{course_id}/sources",
                data={"label": "Blocked Course Source",
                      "reference": "https://x.y/z",
                      "decision": "keep_unverified"})
    page = client.get(f"/courses/{course_id}")
    assert "Blocked Course Source" in page.text
    assert "Unverified — not read" in page.text
