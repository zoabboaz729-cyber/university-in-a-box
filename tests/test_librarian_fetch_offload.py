"""Regression tests for the Librarian fetch offload (fix/librarian-offload-fetch).

The Librarian's add/re-verify route used to call the *blocking* sync fetcher
(app.fetching.fetch_source_text) directly inside its ``async def`` handler.
That (a) froze the event loop for the whole HTTP timeout and (b) crashed on a
YouTube URL, because the sync fetcher internally does ``asyncio.run(...)``
which cannot start a loop while one is already running -> 500 instead of a
clean outcome-3 page.

The fix runs the sync fetcher in a worker thread via ``asyncio.to_thread``.
These tests pin that behavior with NO network: the fetcher seam
(app.routes.librarian.fetch_source_text) is replaced by controlled fakes and
the provider by a FakeProvider, reusing the helpers from
tests/test_librarian_routes.py.
"""
import asyncio

from app.fetching import FetchedSource
from app.fetching.http import FetchError

from tests.test_librarian_routes import (
    FakeProvider,
    make_client,
    make_topic,
    stored_rows,
    wire,
)

GOOD_TEXT = "Readable page text."


class _LoopProbeFetcher:
    """Sync fetcher that records whether a loop was running when it ran.

    ``asyncio.get_running_loop()`` raises RuntimeError in a plain worker
    thread (no loop) but succeeds on the event loop. After the fix the fetch
    runs in a worker thread, so the probe must see RuntimeError.
    """

    def __init__(self):
        self.runtime_error_raised = None
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        try:
            asyncio.get_running_loop()
            self.runtime_error_raised = False
        except RuntimeError:
            self.runtime_error_raised = True
        return FetchedSource(ok=True, kind="page", text=GOOD_TEXT, reason="")


# (a) the fetch runs OFF the event loop, and the route still succeeds --------
def test_sync_fetch_runs_off_the_event_loop(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    provider = FakeProvider()
    fetcher = _LoopProbeFetcher()
    wire(monkeypatch, provider, fetcher=fetcher)
    topic_id = make_topic()

    response = client.post(
        f"/topics/{topic_id}/sources",
        data={"label": "Offloaded", "reference": "https://example.com/o"},
        follow_redirects=False,
    )

    # The fetch ran in a worker thread, not on the event loop.
    assert fetcher.runtime_error_raised is True
    assert fetcher.urls == ["https://example.com/o"]
    # And the route still produced its normal verified-accept outcome.
    assert response.status_code == 303
    assert provider.calls == 1
    assert GOOD_TEXT in provider.last_message
    rows = stored_rows(topic_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "keep"
    assert rows[0]["verified_at"]


# (b) a fetcher that internally does asyncio.run(...) — the YouTube path -----
def test_sync_fetch_may_call_asyncio_run_without_crashing(tmp_path, monkeypatch):
    async def _trivial():
        return "ok"

    def youtube_style_fetch(url):
        # The real YouTube path (app.fetching.youtube.fetch_transcript) does
        # exactly this: asyncio.run(...) inside the sync fetcher. On the event
        # loop that raises RuntimeError -> 500; in a worker thread it succeeds.
        assert asyncio.run(_trivial()) == "ok"
        return FetchedSource(ok=True, kind="transcript",
                             text="Transcript body.", reason="")

    client = make_client(tmp_path, monkeypatch)
    provider = FakeProvider()
    wire(monkeypatch, provider, fetcher=youtube_style_fetch)
    topic_id = make_topic()

    response = client.post(
        f"/topics/{topic_id}/sources",
        data={"label": "Video", "reference": "https://youtu.be/abc123"},
        follow_redirects=False,
    )

    # No 500: the nested asyncio.run succeeded in the worker thread.
    assert response.status_code == 303
    assert provider.calls == 1
    rows = stored_rows(topic_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "keep"
    assert rows[0]["verified_at"]


# (c) an async-def fetcher is still awaited (the coroutine branch) -----------
def test_async_fetcher_is_awaited(tmp_path, monkeypatch):
    async def async_fetch(url):
        return FetchedSource(ok=True, kind="page", text=GOOD_TEXT, reason="")

    client = make_client(tmp_path, monkeypatch)
    provider = FakeProvider()
    wire(monkeypatch, provider, fetcher=async_fetch)
    topic_id = make_topic()

    response = client.post(
        f"/topics/{topic_id}/sources",
        data={"label": "Async", "reference": "https://example.com/a"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert provider.calls == 1
    assert GOOD_TEXT in provider.last_message
    rows = stored_rows(topic_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "keep"
    assert rows[0]["verified_at"]


# (d) a FetchError still yields the "couldn't read that source" outcome ------
def test_fetch_error_still_yields_couldnt_read_outcome(tmp_path, monkeypatch):
    def fetcher_reports_fetch_error(url):
        # Mirrors the REAL fetch_source_text: the network layer raises
        # FetchError and the fetcher turns it into an ok=False result — it is
        # never allowed to escape to the route (which only catches TypeError).
        # Raised locally here, so no network is touched.
        try:
            raise FetchError("the site blocked the request")
        except FetchError as exc:
            return FetchedSource(ok=False, kind="", text="", reason=str(exc))

    client = make_client(tmp_path, monkeypatch)
    wire(monkeypatch, fetcher=fetcher_reports_fetch_error)
    topic_id = make_topic()

    response = client.post(
        f"/topics/{topic_id}/sources",
        data={"label": "Blocked", "reference": "https://x.y/z"},
    )

    assert response.status_code == 200
    assert "Couldn't read that source" in response.text
    assert "the site blocked the request" in response.text
    assert "Retry now" in response.text
    assert stored_rows(topic_id) == []

