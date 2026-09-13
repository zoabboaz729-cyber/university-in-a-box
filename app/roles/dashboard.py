"""Dashboard data — Phase 2.

One small query layer for GET / so the route stays thin (no business
logic in routes per systemPatterns). Shows every non-draft Course,
newest first; drafts are invisible until confirmed (P7: the user
decides a curriculum is real by confirming it).

"Current topic" choice (logged as D-010): the first topic whose status
is not 'done', in order_index order. No progress-tracking machinery
exists yet (Tutor/Editor gating lands in Phases 4-5), so "first
not-done" is the simplest correct resume pointer. Topics done/total
is a cheap COUNT alongside and is included.
"""
from app.db import get_connection
from app.roles.activity import days_since, last_activity_for_course, current_streak
from app.roles.review_store import last_review_note_for_course
from app.roles.tutor_store import last_gap_for_course

# Draft rows are mid-interview scaffolding, not real courses — never list them.
LIST_STATUSES = ("active", "paused", "archived", "done")


def list_dashboard_courses() -> list[dict]:
    """All non-draft courses, newest first, with resume pointers."""
    with get_connection() as conn:
        course_rows = conn.execute(
            "SELECT id, title, status, created_at FROM courses "
            "WHERE status != 'draft' ORDER BY id DESC"
        ).fetchall()
        result = []
        for course in course_rows:
            course_id = course["id"]
            topics = conn.execute(
                "SELECT id, title, status FROM topics "
                "WHERE course_id = ? ORDER BY order_index",
                (course_id,),
            ).fetchall()
            total = len(topics)
            done = sum(1 for t in topics if t["status"] == "done")
            # First not-done topic in sequence order is "current".
            current = next(
                (
                    {"id": t["id"], "title": t["title"], "status": t["status"]}
                    for t in topics
                    if t["status"] != "done"
                ),
                None,
            )
            result.append(
                {
                    "id": course_id,
                    "title": course["title"],
                    "status": course["status"],
                    "created_at": course["created_at"],
                    "total_topics": total,
                    "done_topics": done,
                    "current_topic": current,
                    "days_since_activity": days_since(
                        last_activity_for_course(course_id)
                    ),
                    "streak_days": current_streak(course_id),
                    "last_gap_note": last_gap_for_course(course_id),
                    "last_review_note": last_review_note_for_course(course_id),
                }
            )
        return result
