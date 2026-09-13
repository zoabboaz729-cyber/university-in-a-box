"""Course persistence & the confirm step — Phase 1c.

When the user confirms the edited curriculum draft, the draft course row
(status='draft', created at interview start) becomes a real Course: title from
the echoed interview answers, status flipped to 'active' (or 'paused' when the
Settings page's "start new courses paused" default is on — Phase 7 completion),
and the edited Topic rows inserted in order. The advisor_interviews transcript
is NOT touched — it stays linked to the now-active course forever
(docs/02-ARCHITECTURE.md).
"""
import os

from app.db import get_connection

ACTIVE_STATUS = "active"


def _default_status() -> str:
    """Starting status for a freshly confirmed Course.

    'active' normally; 'paused' when the owner checked "start new courses
    paused by default" on /settings. P7 stays true either way — the user
    confirms the curriculum; this only controls its starting status.
    """
    raw = os.environ.get("NEW_COURSES_START_PAUSED", "")
    if raw.strip().lower() in ("1", "true", "yes", "on"):
        return "paused"
    return ACTIVE_STATUS


def confirm_curriculum(course_id: int, course_title: str, topics: list, answers: dict) -> None:
    """Turn a draft into an active Course with ordered Topics.

    `topics` is a list of dicts: {"title", "milestone_description", "time_box"}.
    Replaces any existing topics (idempotent — safe if /confirm is posted twice).
    """
    if not course_title or not course_title.strip():
        raise ValueError("course title is empty")
    if not topics:
        raise ValueError("course has no topics")

    course_title = course_title.strip()
    with get_connection() as conn:
        # Copy the interview answers onto the course record where they belong
        # (destination/baseline/cut_list), then flip draft -> active/paused.
        conn.execute(
            "UPDATE courses SET title = ?, destination = ?, baseline = ?, "
            "cut_list = ?, status = ? WHERE id = ?",
            (
                course_title,
                answers.get("destination"),
                answers.get("baseline"),
                answers.get("cut_list"),
                _default_status(),
                course_id,
            ),
        )
        # Replace topics so re-running /confirm can't duplicate rows.
        conn.execute("DELETE FROM topics WHERE course_id = ?", (course_id,))
        for index, topic in enumerate(topics):
            conn.execute(
                "INSERT INTO topics "
                "(course_id, order_index, title, milestone_description, time_box) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    course_id,
                    index,
                    topic["title"].strip(),
                    topic["milestone_description"].strip(),
                    (topic.get("time_box") or "").strip(),
                ),
            )


def get_course(course_id: int) -> dict | None:
    """Return {"id", "title", "status", "topics": [...]} or None.

    Topics come back already ordered by order_index.
    """
    with get_connection() as conn:
        course = conn.execute(
            "SELECT id, title, status FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if course is None:
            return None
        rows = conn.execute(
            "SELECT id, title, milestone_description, time_box, status "
            "FROM topics WHERE course_id = ? ORDER BY order_index",
            (course_id,),
        ).fetchall()
    return {
        "id": course["id"],
        "title": course["title"],
        "status": course["status"],
        "topics": [
            {
                "id": row["id"],
                "title": row["title"],
                "milestone_description": row["milestone_description"],
                "time_box": row["time_box"],
                "status": row["status"],
            }
            for row in rows
        ],
    }