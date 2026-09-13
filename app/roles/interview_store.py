"""Interview persistence — Phase 1b.

One row per answered step in advisor_interviews, keyed by a draft course_id
created at interview start (course row exists with status='draft' until the
user confirms the curriculum in 1c). Answers persist immediately per
docs/04-CONSTRAINTS.md section 3, so closing mid-interview loses nothing.
"""
from app.db import get_connection
from app.roles.advisor import STEPS

DRAFT_STATUS = "draft"


def start_interview(topic: str) -> int:
    """Create the draft course row. Returns its id (the interview id)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO courses (title, status) VALUES (?, ?)",
            (topic.strip(), DRAFT_STATUS),
        )
        return cursor.lastrowid


def get_interview(course_id: int) -> dict | None:
    """Return {topic, answers} or None if the draft doesn't exist."""
    with get_connection() as conn:
        course = conn.execute(
            "SELECT id, title FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if course is None:
            return None
        rows = conn.execute(
            "SELECT step, answer FROM advisor_interviews WHERE course_id = ?",
            (course_id,),
        ).fetchall()
    return {"topic": course["title"], "answers": {r["step"]: r["answer"] for r in rows}}


def save_answer(course_id: int, step: str, question: str, answer: str) -> None:
    """Insert or overwrite one step's answer (back-button edits re-save)."""
    if step not in STEPS:
        raise ValueError("unknown interview step: " + step)
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM advisor_interviews WHERE course_id = ? AND step = ?",
            (course_id, step),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO advisor_interviews "
                "(course_id, question, answer, step) VALUES (?, ?, ?, ?)",
                (course_id, question, answer.strip(), step),
            )
        else:
            conn.execute(
                "UPDATE advisor_interviews SET question = ?, answer = ? WHERE id = ?",
                (question, answer.strip(), existing["id"]),
            )
