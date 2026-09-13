"""Editor review persistence — Phase 5.

One row in editor_reviews per review (topic_id, milestone_ref,
submitted_text, strengths, biggest_weakness, next_edit, created_at).
Rows are written only with complete, real feedback — never a
half-written review (no-slop rule). Logged with its honest entity type
'editor_review' plus the owning course_id (D-015), so the dashboard's
days-since-activity counts review activity without any masquerade.
"""
from app.db import get_connection
from app.roles.activity import log


def save_review(topic_id: int, milestone_ref: str, submitted_text: str,
                review) -> int:
    """Persist one complete review. `review` is an app.roles.editor.Review.
    Returns the review id."""
    if not submitted_text or not submitted_text.strip():
        raise ValueError("editor submission is empty")
    for name in ("strengths", "biggest_weakness", "next_edit"):
        value = getattr(review, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("editor " + name + " is empty")
    with get_connection() as conn:
        topic = conn.execute(
            "SELECT id, course_id FROM topics WHERE id = ?", (topic_id,)
        ).fetchone()
        if topic is None:
            raise ValueError("topic not found: " + str(topic_id))
        cursor = conn.execute(
            "INSERT INTO editor_reviews (topic_id, milestone_ref, "
            "submitted_text, strengths, biggest_weakness, next_edit) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (topic_id, milestone_ref, submitted_text.strip(),
             review.strengths.strip(), review.biggest_weakness.strip(),
             review.next_edit.strip()),
        )
        review_id = cursor.lastrowid
        course_id = topic["course_id"]
    log(course_id, "editor_review", review_id, "created")
    return review_id


def list_reviews_for_topic(topic_id: int) -> list[dict]:
    """All reviews for a topic, newest first (the visible history)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, topic_id, milestone_ref, submitted_text, "
            "strengths, biggest_weakness, next_edit, created_at "
            "FROM editor_reviews WHERE topic_id = ? ORDER BY id DESC",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def has_editor_review(topic_id: int) -> bool:
    """True when at least one review exists for the topic (the done-gate)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM editor_reviews WHERE topic_id = ? LIMIT 1",
            (topic_id,),
        ).fetchone()
        return row is not None


def last_review_note_for_course(course_id: int) -> str | None:
    """Newest review across a course's topics as one short dashboard line."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT biggest_weakness, next_edit FROM editor_reviews "
            "WHERE topic_id IN (SELECT id FROM topics WHERE course_id = ?) "
            "ORDER BY id DESC LIMIT 1",
            (course_id,),
        ).fetchone()
        if row is None:
            return None
        return ("Biggest weakness: " + row["biggest_weakness"]
                + " Next edit: " + row["next_edit"])