"""Stage 3 Task 6 tests: fetching infrastructure + source schema.

Everything mocks at the httpx / youtube / DNS boundaries — no live
network in the suite. SSRF refusals exercise the real validation code
against blocked address classes; successful fetches, redirect chains,
and size overflow run through a fake httpx client.
"""
import ipaddress
import socket
import sqlite3

import pytest

from app.db import _migrate, get_db_path, init_db
from app.fetching import extract
from app.fetching.http import FetchError, fetch_url
from app.fetching.youtube import youtube_video_id


# --- fakes ---------------------------------------------------------------

def fake_getaddrinfo(host, *args, **kwargs):
    """Resolve literals to themselves and names to a public IP, so the
    suite never touches DNS while the real validation code runs."""
    special = {"localhost": "127.0.0.1", "metadata.internal": "169.254.169.254"}
    addr = special.get(host)
    if addr is None:
        try:
            addr = str(ipaddress.ip_address(host))
        except ValueError:
            addr = "93.184.216.34"  # public example IP
    return [(socket.AF_INET, 0, socket.IPPROTO_TCP, "", (addr, 0))]


class FakeResponse:
    def __init__(self, status_code=200, headers=None, chunks=(b"<p>hi</p>",)):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = list(chunks)

    def iter_bytes(self, n):
        yield from self._chunks


class FakeStream:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *args):
        return False


class FakeClient:
    """Stands in for httpx.Client; responses served in order."""
    requested: list = []
    responses: list = []

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def stream(self, method, url):
        FakeClient.requested.append(url)
        return FakeStream(FakeClient.responses.pop(0))


@pytest.fixture
def fake_net(monkeypatch):
    monkeypatch.setattr("app.fetching.http.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("app.fetching.http.httpx.Client", FakeClient)
    FakeClient.requested = []
    FakeClient.responses = []
    return FakeClient


# --- SSRF refusals --------------------------------------------------------

def test_refuses_loopback(fake_net):
    with pytest.raises(FetchError):
        fetch_url("http://127.0.0.1:8000/")
    with pytest.raises(FetchError):
        fetch_url("http://localhost/")


def test_refuses_private_ranges(fake_net):
    for url in ("http://192.168.1.1/", "http://10.0.0.5/",
                "http://172.16.0.9/"):
        with pytest.raises(FetchError):
            fetch_url(url)


def test_refuses_link_local_metadata(fake_net):
    with pytest.raises(FetchError):
        fetch_url("http://169.254.169.254/latest/meta-data/")


def test_refuses_ipv6_loopback(fake_net):
    with pytest.raises(FetchError):
        fetch_url("http://[::1]:8000/")


def test_refuses_file_and_ftp_schemes(fake_net):
    for url in ("file:///etc/passwd", "ftp://example.com/x"):
        with pytest.raises(FetchError):
            fetch_url(url)


# --- redirect cap, size cap, success --------------------------------------

def test_redirect_cap(fake_net):
    redirect = FakeResponse(301, {"location": "http://example.com/hop"})
    fake_net.responses = [redirect, redirect, redirect, redirect]
    with pytest.raises(FetchError, match="redirect"):
        fetch_url("http://example.com/start")


def test_redirects_followed_with_revalidation(fake_net):
    fake_net.responses = [
        FakeResponse(302, {"location": "/final"}),
        FakeResponse(200, {"content-type": "text/html"}, (b"<p>arrived</p>",)),
    ]
    page = fetch_url("http://example.com/start")
    assert page.final_url == "http://example.com/final"
    assert b"arrived" in page.body
    assert fake_net.requested == [
        "http://example.com/start", "http://example.com/final"]


def test_redirect_to_blocked_target_is_refused(fake_net):
    """A redirect must not smuggle in a target the guards would reject:
    loopback, cloud metadata, or a non-http scheme. The blocked URL is
    never requested."""
    for target in ("http://127.0.0.1:8000/",
                   "http://169.254.169.254/latest/meta-data/",
                   "file:///etc/passwd"):
        fake_net.requested.clear()  # class-level list, shared across the loop
        fake_net.responses = [FakeResponse(302, {"location": target})]
        with pytest.raises(FetchError):
            fetch_url("http://example.com/start")
        assert fake_net.requested == ["http://example.com/start"]


def test_size_cap_aborts(fake_net):
    big = FakeResponse(200, {"content-type": "text/html"},
                       chunks=(b"a" * 64_000,) * 40)  # 2.56MB total
    fake_net.responses = [big]
    with pytest.raises(FetchError, match="2MB"):
        fetch_url("http://example.com/big")


def test_http_error_is_a_fetch_error(fake_net):
    fake_net.responses = [FakeResponse(404)]
    with pytest.raises(FetchError, match="404"):
        fetch_url("http://example.com/missing")


def test_success_records_content_type(fake_net):
    fake_net.responses = [
        FakeResponse(200, {"content-type": "text/html; charset=utf-8"})]
    page = fetch_url("http://example.com/")
    assert page.status_code == 200
    assert "text/html" in page.content_type


# --- extraction + truncation ----------------------------------------------

def test_html_extraction_keeps_prose_drops_script():
    html = """
    <html><head><title>My Title</title>
    <style>body { color: red; }</style></head>
    <body>
      <script>alert("evil");</script>
      <h1>Chapter One</h1>
      <p>Real prose   with   extra spaces.</p>
      <a href="/x">nav link</a>
      <p>Second paragraph.</p>
    </body></html>
    """
    text = extract.html_to_text(html)
    assert "My Title" in text
    assert "Chapter One" in text
    assert "Real prose with extra spaces." in text
    assert "Second paragraph." in text
    assert "alert" not in text
    assert "color: red" not in text


def test_truncation_exactness_head_biased():
    short = "hello world"
    assert extract.truncate(short) == short  # under the cap: untouched
    long_text = ("x" * 7000) + "MIDDLE" + ("y" * 7000)
    result = extract.truncate(long_text)
    assert result.startswith("x" * 100)   # head kept
    assert result.endswith("y" * 100)     # tail kept (references live there)
    assert "[... middle of document truncated ...]" in result
    assert len(result) <= extract.MAX_FETCH_CHARS + 100


def test_pdf_extraction(tmp_path):
    """Build a one-page PDF fixture with pypdf itself and extract its text."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject, DictionaryObject, NameObject)

    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    page = writer.pages[0]
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 24 Tf 72 720 Td (Hello verification) Tj ET")
    page[NameObject("/Contents")] = content
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    buf = io.BytesIO()
    writer.write(buf)

    text = extract.pdf_to_text(buf.getvalue())
    assert "Hello verification" in text


# --- youtube --------------------------------------------------------------

def test_youtube_video_id_parsing():
    assert youtube_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"
    assert youtube_video_id("https://youtu.be/abc123") == "abc123"
    assert youtube_video_id("https://www.youtube.com/shorts/abc123") == "abc123"
    assert youtube_video_id("https://vimeo.com/12345") is None
    assert youtube_video_id("https://youtube.com/playlist?list=x") is None


def test_youtube_failure_returns_unavailable_never_raises(monkeypatch):
    from app.fetching import youtube

    class Boom:
        def list(self, video_id):
            raise RuntimeError("YouTube changed their markup")

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", Boom)
    result = youtube.fetch_transcript(
        "https://www.youtube.com/watch?v=abc123")
    assert result.ok is False
    assert result.text == ""
    assert "transcript unavailable" in result.reason


def test_youtube_success_joins_snippets(monkeypatch):
    from app.fetching import youtube

    class FakeFetched:
        def __iter__(self):
            return iter([type("S", (), {"text": "one"}),
                         type("S", (), {"text": "two"})])

    class FakeTranscript:
        def fetch(self):
            return FakeFetched()

    class FakeList:
        def __iter__(self):
            return iter([FakeTranscript()])

    class FakeApi:
        def list(self, video_id):
            return FakeList()

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", FakeApi)
    result = youtube.fetch_transcript("https://youtu.be/abc123")
    assert result.ok is True
    assert result.text == "one two"


# --- source store: exactly-one-of + course scope + migration --------------

def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()


def test_add_source_enforces_exactly_one_scope(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    from app.roles import source_store
    from tests.test_dashboard import seed_course
    course_id, topic_ids = seed_course("C", topics=[("T", "not_started")])
    with pytest.raises(ValueError, match="exactly one"):
        source_store.add_source(topic_ids[0], "Both", "ref", "keep",
                                "reason", course_id=course_id)
    with pytest.raises(ValueError, match="exactly one"):
        source_store.add_source(None, "Neither", "ref", "keep", "reason")


def test_course_level_source_roundtrip(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    from app.roles import source_store
    from tests.test_dashboard import seed_course
    course_id, topic_ids = seed_course("C", topics=[("T", "not_started")])
    source_store.add_source(None, "Course-wide source", "https://x.example",
                            "keep", "Good for the whole course.",
                            verified_at="2026-09-14 10:00:00",
                            course_id=course_id)
    rows = source_store.list_course_sources(course_id)
    assert len(rows) == 1
    assert rows[0]["label"] == "Course-wide source"
    assert rows[0]["course_id"] == course_id
    assert rows[0]["topic_id"] is None
    assert rows[0]["verified_at"] == "2026-09-14 10:00:00"
    # Course-level rows never leak into a topic's list.
    assert source_store.list_sources(topic_ids[0]) == []


def test_sources_migration_preserves_existing_rows(tmp_path, monkeypatch):
    """A pre-Task-6 DB (topic_id NOT NULL, no new columns) migrates on boot
    and every existing row survives with its data intact.

    The fixture starts from the real schema — on a real pre-Task-6 disk every
    other table exists too — and then rewinds ONLY the sources table to its
    old shape, which is exactly what the migration has to cope with.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    conn = sqlite3.connect(get_db_path())
    conn.executescript("""
        DROP TABLE sources;
        CREATE TABLE sources (id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL, label TEXT NOT NULL,
            url_or_reference TEXT, verdict TEXT, reason TEXT,
            added_at TEXT NOT NULL DEFAULT (datetime('now')));
    """)
    conn.execute("INSERT INTO courses (id, title) VALUES (1, 'Old Course')")
    conn.execute(
        "INSERT INTO topics (id, course_id, order_index, title) "
        "VALUES (1, 1, 0, 'Old Topic')")
    conn.execute(
        "INSERT INTO sources (topic_id, label, url_or_reference, verdict, reason) "
        "VALUES (1, 'Old Row', 'ref', 'keep', 'good reason')")
    conn.commit()
    _migrate(conn)
    # PRAGMA rows are (cid, name, type, notnull, dflt_value, pk).
    info = {row[1]: row for row in conn.execute("PRAGMA table_info(sources)")}
    assert {"course_id", "verified_at"} <= set(info)
    assert not info["topic_id"][3]  # NOT NULL relaxed → course-level rows
    rows = conn.execute(
        "SELECT id, topic_id, course_id, label, verdict, verified_at "
        "FROM sources").fetchall()
    assert rows == [(1, 1, None, "Old Row", "keep", None)]
    # A second boot must be a no-op: still idempotent, rows still intact.
    _migrate(conn)
    rows = conn.execute(
        "SELECT id, topic_id, course_id, label, verdict, verified_at "
        "FROM sources").fetchall()
    assert rows == [(1, 1, None, "Old Row", "keep", None)]
    conn.close()



