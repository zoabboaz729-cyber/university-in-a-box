"""Phase 8 — full ALTER loop regression (docs/05-VERIFICATION checklist 1-7).

ONE test walks every phase in sequence on a fresh temp DB with a scripted
FakeProvider, then "restarts" (a brand-new TestClient on the same DB) and
confirms nothing reset, no new Roommate prompt fired, and the dashboard
still reads correctly. This is the automated, re-runnable form of Phase 8's
manual regression checklist.

Call order of the scripted LLM replies:
  0  Advisor draft (built when the 5th interview answer is submitted)
  1  Roommate first prompt (dashboard load after course confirm)
  2-4 Librarian verdicts for the three added sources
  5-7 Tutor: opening question, follow-up, gap note
  8  Editor review
"""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.main import api
from app.roles import advisor
from app.roles.tutor_store import get_session

import app.routes.advisor_review  # noqa: F401,E402 (registered by main too)

ANSWERS = {
    "destination": "reach conversational level",
    "baseline": "know a few words",
    "sequencing": "30 min a day for 8 weeks",
    "cut_list": "skip classical literature",
    "milestones": "hold a 5-minute conversation",
}

DRAFT = (
    '{"course_title": "Test Course", "topics": ['
    '{"title": "T1", "milestone_description": "Write a one-page summary.", '
    '"time_box": "1 week"}]}'
)
ROOMMATE = (
    '{"field": "architecture", "prompt": "Consider how an architect would '
    'separate the load-bearing structure of your topic from its decorative '
    'parts - which parts of Spanish must carry meaning, and which are '
    'ornament you can defer?"}'
)
LIB_KEEP = '{"verdict": "keep", "good_for": "core grounding", "reason": "covers the fundamentals clearly"}'
LIB_SKIP = '{"verdict": "skip", "good_for": "none", "reason": "clickbait with no sources"}'
LIB_LATER = '{"verdict": "later", "good_for": "extension", "reason": "useful only after the basics"}'
TUTOR_Q1 = '{"question": "What exactly does the subjunctive express that English lacks?"}'
TUTOR_Q2 = '{"question": "And how would you translate this sentence using it, out loud?"}'
GAP_NOTE = '{"gap_note": "The user\'s grasp of the Spanish subjunctive is still fragile."}'
EDITOR_REVIEW = (
    '{"strengths": "The structure is clear.", '
    '"biggest_weakness": "The opening claim needs evidence.", '
    '"next_edit": "Add one concrete example to the opening."}'
)

REPLIES = [
    DRAFT, ROOMMATE,
    LIB_KEEP, LIB_SKIP, LIB_LATER,
    TUTOR_Q1, TUTOR_Q2, GAP_NOTE,
    EDITOR_REVIEW,
]


class FakeProvider:
    """Returns scripted replies in order; the last reply stays for extras."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    provider = FakeProvider(REPLIES)
    # conftest's autouse fixture patches the dashboard provider to
    # NoNetworkProvider; re-patching the SAME attribute from the test wins
    # (later monkeypatch.setattr replaces the fixture's), so the dashboard
    # due-check consumes the scripted ROOMMATE reply instead of failing.
    monkeypatch.setattr("app.routes.dashboard.get_provider", lambda: provider)
    for module in (
        "app.routes.advisor_review",
        "app.routes.editor",
        "app.routes.librarian",
        "app.routes.tutor",
    ):
        monkeypatch.setattr(module + ".get_provider", lambda: provider)
    return TestClient(api), provider


# __ADVISOR_AND_LIBRARIAN__


def test_full_alter_loop_and_restart(tmp_path, monkeypatch):
    client, provider = make_client(tmp_path, monkeypatch)

    # --- Phase 1: Advisor (five-step interview, one question at a time) ---
    resp = client.post("/advisor/new", data={"topic": "Spanish pronouns"})
    assert resp.status_code == 200
    interview_id = 1
    for i, step in enumerate(advisor.STEPS):
        resp = client.post(
            f"/advisor/{interview_id}",
            data={"step": step, "answer": ANSWERS[step]},
        )
        assert resp.status_code == 200
        if i < len(advisor.STEPS) - 1:
            # Exactly the NEXT step's question; never a dump of all five.
            assert advisor.question_for(advisor.STEPS[i + 1]) in resp.text
        if i < len(advisor.STEPS) - 2:
            # The last step's question only appears on its own step.
            assert advisor.question_for(advisor.STEPS[-1]) not in resp.text
    assert "Test Course" in resp.text  # draft rendered on the last answer

    resp = client.post(
        f"/advisor/{interview_id}/confirm",
        data={
            "course_title": "Test Course",
            "title-0": "T1",
            "milestone-0": "Write a one-page summary.",
            "timebox-0": "1 week",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    course_id = interview_id  # the draft row doubles as the confirmed Course
    topic_id = 1

    # --- Phase 2: Dashboard lists the confirmed course ---
    page = client.get("/").text
    assert "Test Course" in page
    assert f'href="/courses/{course_id}"' in page
    # The dashboard load ran the Phase 6 due-check and the generated prompt
    # actually persisted. (Calls == 2: the advisor's draft call fired when the
    # 5th answer's redirect was followed to the review page, then the
    # due-check consumed the scripted ROOMMATE reply. Confirming the
    # curriculum itself is pure SQL — no extra call there.)
    #
    # The due-check runs in a background thread (dashboard returns without
    # waiting for the insert to commit), and provider.calls increments before
    # the row lands — so poll briefly for the row instead of assuming the
    # 0.2s join already flushed it.
    import time as _time

    assert provider.calls == 2
    prompt_row = None
    deadline = _time.time() + 5
    while _time.time() < deadline:
        with sqlite3.connect(get_db_path()) as conn:
            conn.row_factory = sqlite3.Row
            prompt_row = conn.execute(
                "SELECT field FROM roommate_prompts ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if prompt_row is not None:
            break
        _time.sleep(0.05)
    assert prompt_row is not None and prompt_row["field"] == "architecture"

    # --- Phase 3: Librarian ---
    # NOTE: the scripted reply queue must skip past the advisor DRAFT (call 0)
    # and the Roommate due-check (call 1) before the three LIB_* verdicts.
    # provider.calls is left alone — the test only asserts the persisted rows.
    for i, (label, ref) in enumerate(
        [("Strong textbook", "https://book.example.org"),
         ("Click bait blog", "https://blog.example/xyz"),
         ("Maybe article", "https://papers.example/abc")]
    ):
        resp = client.post(
            f"/topics/{topic_id}/sources",
            data={"label": label, "reference": ref},
            follow_redirects=False,
        )
        assert resp.status_code == 303, (
            f"source {i} not accepted (status {resp.status_code}): "
            f"{resp.text[:300]}"
        )
    from app.roles.source_store import list_sources
    rows = list_sources(topic_id)
    verdicts = {r["label"]: r["verdict"] for r in rows if r["verdict"]}
    assert verdicts["Strong textbook"] == "keep"
    assert verdicts["Click bait blog"] == "skip"
    assert verdicts["Maybe article"] == "later"
    shelf = client.get(f"/topics/{topic_id}/shelf").text
    assert "Strong textbook" in shelf
    assert "Click bait blog" not in shelf  # skip rows never reach the Shelf

    # --- Phase 4: Tutor (one question at a time → gap note) ---
    resp = client.post(f"/topics/{topic_id}/tutor/start", follow_redirects=False)
    assert resp.status_code == 303
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id FROM tutor_sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    session_id = row["id"]
    sess = get_session(session_id)
    turn = sess["turns"][0]
    assert turn["question"].count("?") == 1  # exactly one question
    resp = client.post(
        f"/tutor/{session_id}/answer",
        data={"turn_id": turn["id"],
              "answer": "I keep getting the subjunctive wrong."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    sess = get_session(session_id)
    assert len(sess["turns"]) == 2            # follow-up persisted
    assert sess["turns"][0]["user_answer"].startswith("I keep getting")
    resp = client.post(f"/tutor/{session_id}/end", follow_redirects=False)
    assert resp.status_code == 303
    sess = get_session(session_id)
    assert sess["ended_at"] is not None
    assert "subjunctive" in sess["gap_note"].lower()
    topic_page = client.get(f"/topics/{topic_id}").text
    assert "subjunctive" in topic_page.lower()  # gap note shown on Topic
    dash = client.get("/").text
    assert "last gap" in dash              # ... and on the Dashboard
    # __EDITOR_ROOMMATE_RESTART__

    # --- Phase 5: Editor (topic-done gated on a review) ---
    gated = client.post(f"/topics/{topic_id}/status", data={"status": "done"})
    assert gated.status_code == 200
    assert "needs at least one Editor review" in gated.text
    resp = client.post(
        f"/topics/{topic_id}/editor/submit",
        data={"submission": "My one-page summary about the subjunctive, "
                            "with a vague opening claim."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    topic_page = client.get(f"/topics/{topic_id}").text
    assert "needs evidence" in topic_page      # fake review rendered
    assert "Add one concrete example" in topic_page
    resp = client.post(
        f"/topics/{topic_id}/status", data={"status": "done"},
        follow_redirects=False,
    )
    assert resp.status_code == 303             # now gated on, so allowed
    dash = client.get("/").text
    assert "all topics done" in dash
    assert "needs evidence" in dash.lower() or "weakness" in dash.lower()

    # --- Phase 6: Roommate journal + reaction ---
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id FROM roommate_prompts ORDER BY id DESC LIMIT 1"
        ).fetchone()
    prompt_id = row["id"]
    journal = client.get("/roommate").text
    assert "architecture" in journal           # the field label is shown
    resp = client.post(
        f"/roommate/prompts/{prompt_id}/reaction",
        data={"reaction": "Good nudge"}, follow_redirects=False,
    )
    assert resp.status_code == 303
    journal = client.get("/roommate").text
    assert "Good nudge" in journal             # reaction persisted

    # --- Phase 7: Settings reachable + streak/activity on dashboard ---
    settings_page = client.get("/settings").text
    assert "Roommate Cadence" in settings_page
    assert "start paused" in settings_page or "Start new courses" in settings_page
    dash = client.get("/").text
    assert "streak" in dash                    # today's activity = 1-day streak
    assert 'href="/settings"' in dash          # Settings link on dashboard

    # --- Restart & do-not-lose-anything check (docs/05 item 7) ---
    del client
    client2 = TestClient(api)                  # brand-new connection to same DB
    calls_before = provider.calls
    page = client2.get("/").text
    assert "Test Course" in page
    assert "all topics done" in page
    assert provider.calls == calls_before      # prompt still fresh: no new LLM call
    journal2 = client2.get("/roommate").text
    assert "Good nudge" in journal2            # reaction survived the restart