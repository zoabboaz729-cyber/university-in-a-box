"""Basic Course management — Phase 2 (step 3 of the build plan).

Pause / archive / resume a Course, and mark a Topic done manually.
Phase 5 will gate topic-done behind an Editor review; until then the
dashboard offers an explicit manual toggle (labelled as such in the UI)
so a long-lived daily tool can record progress at all.

Every action appends to activity_log so "days since last activity"
stays truthful.
"""
from app.db import get_connection
from app.roles.activity import log

COURSE_STATUSES = ("active", "paused", "archived", "done")
TOPIC_STATUSES = ("not_started", "in_progress", "done")


def set_course_status(course_id: int, status: str) -> bool:
    """Set a course's status. Returns False when the course is missing."""
    if status not in COURSE_STATUSES:
        raise ValueError("unknown course status: " + status)
    with get_connection() as conn:
        course = conn.execute(
            "SELECT id, status FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if course is None or course["status"] == "draft":
            return False
        conn.execute(
            "UPDATE courses SET status = ? WHERE id = ?", (status, course_id)
        )
    log(course_id, "course", course_id, "status:" + status)
    return True


def set_topic_status(topic_id: int, status: str) -> bool:
    """Set a topic's status. Returns False when the topic is missing."""
    if status not in TOPIC_STATUSES:
        raise ValueError("unknown topic status: " + status)
    with get_connection() as conn:
        topic = conn.execute(
            "SELECT id, course_id FROM topics WHERE id = ?", (topic_id,)
        ).fetchone()
        if topic is None:
            return False
        conn.execute(
            "UPDATE topics SET status = ? WHERE id = ?", (status, topic_id)
        )
    log(topic["course_id"], "topic", topic_id, "status:" + status)
    return True


def get_topic(topic_id: int) -> dict | None:
    """One topic with its parent course id/title, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT t.id, t.course_id, t.title, t.milestone_description, "
            "t.time_box, t.status, c.title AS course_title "
            "FROM topics t JOIN courses c ON c.id = t.course_id "
            "WHERE t.id = ?",
            (topic_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
