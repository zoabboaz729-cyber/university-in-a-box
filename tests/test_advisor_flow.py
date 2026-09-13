"""Phase 1b tests: interview flow over HTTP, provider mocked (no key needed).

Covers: /advisor/new renders; empty topic redirects back; full 5-answer flow
reaches the review page showing the mocked draft; exactly one question appears
per step; back-button edit re-saves the answer; restart-style resume (fresh
get_interview read) lands on the next unanswered step; mid-interview answers
persist in the DB (re-read from SQLite, not memory).
"""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path, init_db
from app.main import api
from app.roles import advisor

ANSWERS = {
    "destination": "reach conversational level",
    "baseline": "know a few words",
    "sequencing": "30 min a day for 8 weeks",
    "cut_list": "skip classical literature",
    "milestones": "hold a 5-minute conversation",
}

GOOD_DRAFT = (
    '{"course_title": "Test Course", "topics": ['
    '{"title": "T1", "milestone_description": "Write a one-page summary.", '
    '"time_box": "1 week"}]}'
)


class FakeProvider:
    def generate(self, system_prompt, user_message):
        return GOOD_DRAFT


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    import app.routes.advisor_review  # noqa: F401 (register review routes)
    return TestClient(api)


def answer_all(client, interview_id):
    for step in advisor.STEPS:
        response = client.post(
            f"/advisor/{interview_id}",
            data={"step": step, "answer": ANSWERS[step]},
        )
        assert response.status_code == 200


def test_new_form_and_empty_topic(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/advisor/new").status_code == 200
    response = client.post("/advisor/new", data={"topic": "   "})
    assert response.status_code == 200  # redirect followed; lands back on form


def test_full_flow_reaches_mocked_review(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    response = client.post("/advisor/new", data={"topic": "Spanish"})
    assert response.status_code == 200
    # First step shows exactly one question: destination's, no other step text.
    assert advisor.question_for("destination") in response.text
    assert advisor.question_for("baseline") not in response.text

    interview_id = 1
    for i, step in enumerate(advisor.STEPS):
        response = client.post(
            f"/advisor/{interview_id}",
            data={"step": step, "answer": ANSWERS[step]},
        )
        if i < len(advisor.STEPS) - 1:
            next_q = advisor.question_for(advisor.STEPS[i + 1])
            assert next_q in response.text
        else:
            # Last answer → review page with the mocked draft title.
            assert "Test Course" in response.text
            assert "T1" in response.text


def test_back_button_edit_resaves(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    client.post("/advisor/new", data={"topic": "Spanish"})
    interview_id = 1
    client.post(
        f"/advisor/{interview_id}",
        data={"step": "destination", "answer": "first version"},
    )
    # Edit page pre-fills the saved answer.
    page = client.get(f"/advisor/{interview_id}/edit/destination")
    assert "first version" in page.text
    # Re-save overwrites; flow continues at the next unanswered step.
    response = client.post(
        f"/advisor/{interview_id}",
        data={"step": "destination", "answer": "revised version"},
    )
    assert advisor.question_for("baseline") in response.text
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT answer FROM advisor_interviews WHERE course_id = ? AND step = ?",
            (interview_id, "destination"),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "revised version"


def test_regenerate_reruns_draft_from_saved_answers(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.routes.advisor_review.get_provider", lambda: FakeProvider())
    client.post("/advisor/new", data={"topic": "Spanish"})
    answer_all(client, 1)
    # Review page has Edit boxes + Regenerate button (per owner choice).
    page = client.get("/advisor/1/review")
    assert "Regenerate draft from my answers" in page.text
    assert 'name="title-0"' in page.text
    # Regenerate re-runs the draft call from the same saved answers.
    response = client.post("/advisor/1/regenerate")
    assert "Test Course" in response.text


def test_resume_after_restart_lands_on_next_step(monkeypatch, tmp_path):
    client = make_client(tmp_path, monkeypatch)
    client.post("/advisor/new", data={"topic": "Spanish"})
    interview_id = 1
    client.post(
        f"/advisor/{interview_id}",
        data={"step": "destination", "answer": ANSWERS["destination"]},
    )
    # Fresh GET = "reopen the app": must resume at baseline, not restart.
    page = client.get(f"/advisor/{interview_id}")
    assert advisor.question_for("baseline") in page.text
    assert "Step 2 of 5" in page.text
