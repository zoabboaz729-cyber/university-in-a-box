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


def list_dashboard_courses(user_id: int, group_id: int | None = None,
                           ungrouped_only: bool = False) -> list[dict]:
    """All of this user's non-draft courses, newest first, with resume pointers.

    Phase 11: `group_id` narrows to one Course Group; `ungrouped_only`
    returns only courses in no group. Both filters are optional and
    combine naturally with the Phase 2 behavior. Phase 12: results are
    always scoped to `user_id`.

    Perf: one connection serves the whole per-course loop. The four
    per-course helpers (activity/streak/gap/review) receive it so a
    9-course dashboard opens ONE connection instead of ~37. `with conn:`
    only commits and does NOT close, so the connection is closed by hand
    in a finally.
    """
    conn = get_connection()
    try:
        base_sql = ("SELECT id, title, status, created_at, group_id "
                    "FROM courses WHERE status != 'draft' AND user_id = ?")
        params = [user_id]
        if ungrouped_only:
            base_sql += " AND group_id IS NULL"
        elif group_id is not None:
            base_sql += " AND group_id = ?"
            params.append(group_id)
        base_sql += " ORDER BY id DESC"
        course_rows = conn.execute(base_sql, params).fetchall()
        result = []
        for course in course_rows:
            course_id = course["id"]
            topics = conn.execute(
                "SELECT id, title, status FROM topics "
                "WHERE course_id = ? AND user_id = ? ORDER BY order_index",
                (course_id, user_id),
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
                        last_activity_for_course(course_id, conn=conn)
                    ),
                    "streak_days": current_streak(course_id, conn=conn),
                    "last_gap_note": last_gap_for_course(course_id, conn=conn),
                    "last_review_note": last_review_note_for_course(
                        course_id, conn=conn),
                }
            )
        return result
    finally:
        conn.close()
