"""Activity log — Phase 2 (+ D-015 structural rework).

Every meaningful user action appends one row to activity_log. The
dashboard reads it back to show "days since last activity" per Course,
so picking the project back up after a gap costs almost nothing (P6).

Tables: activity_log(id, course_id, entity_type, entity_id, action,
is_user, created_at). Two facts are stored on each row so the dashboard
never has to re-derive them:
- course_id — the one Course this action rolls up into (even when the
  action happened on a topic, source, session, review or prompt inside
  it);
- is_user — 0 for system-generated rows (e.g. a Roommate prompt being
  generated), 1 for real user engagement. "Days since activity" counts
  only is_user = 1.

entity_type/entity_id are honest entity references ('topic', 'source',
'editor_review', 'tutor_session', 'roommate', 'course', 'interview') —
never dashboard routing keys.
"""
from datetime import datetime, timezone

from app.db import get_connection


def log(course_id: int, entity_type: str, entity_id: int, action: str,
        is_user: bool = True) -> None:
    """Append one activity row under its owning Course.

    The row's user_id is copied from the owning Course, so activity is always
    attributed to the tenant that owns the course (Phase 12). course_id is
    the Course this action rolls up into. Pass is_user=False only for
    system-generated rows (automatic prompts, failed background checks) that
    must not refresh the activity clock.
    """
    with get_connection() as conn:
        owner = conn.execute(
            "SELECT user_id FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        user_id = owner["user_id"] if owner is not None else 1
        conn.execute(
            "INSERT INTO activity_log "
            "(user_id, course_id, entity_type, entity_id, action, is_user) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, course_id, entity_type, entity_id, action, int(is_user)),
        )


def last_activity_for_course(course_id: int) -> str | None:
    """Newest USER activity timestamp for a course (any of its rows).

    Returns the raw created_at string (SQLite datetime('now')) or None
    when nothing has been logged yet (e.g. pre-Phase-2 courses). Falls
    back to the course's created_at when there is no log row — the
    caller decides the fallback.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(created_at) AS last_seen FROM activity_log "
            "WHERE course_id = ? AND is_user = 1",
            (course_id,),
        ).fetchone()
        if row is None or row["last_seen"] is None:
            course = conn.execute(
                "SELECT created_at FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            if course is None:
                return None
            return course["created_at"]
        return row["last_seen"]


def days_since(stamp: str | None) -> int | None:
    """Whole days from a SQLite datetime('now') string until now (UTC).
    
    Handles both bare (%Y-%m-%d %H:%M:%S) and millisecond-appended
    (%Y-%m-%d %H:%M:%S.%f) timestamp formats.
    """
    if not stamp:
        return None
    # Strip any fractional seconds (e.g. ".389") before parsing.
    bare = stamp.split(".")[0]
    try:
        seen = datetime.strptime(bare, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    delta = now - seen
    return max(0, delta.days)


def current_streak(course_id: int) -> int:
    """Consecutive days of user activity ending today, or 0 if no activity.
    
    A "day" with activity has at least one row where course_id matches and
    is_user = 1. Gaps break the streak.
    """
    with get_connection() as conn:
        # Get all distinct activity dates for this course, newest first.
        rows = conn.execute(
            "SELECT DISTINCT DATE(created_at) AS activity_date "
            "FROM activity_log WHERE course_id = ? AND is_user = 1 "
            "ORDER BY activity_date DESC",
            (course_id,),
        ).fetchall()
    
    if not rows:
        return 0
    
    # Walk backwards from today, counting consecutive days.
    today = datetime.now(timezone.utc).date()
    streak = 0
    expected_date = today
    
    for row in rows:
        activity_date = datetime.strptime(row["activity_date"], "%Y-%m-%d").date()
        if activity_date == expected_date:
            streak += 1
            expected_date = datetime.combine(
                expected_date, datetime.min.time()
            ).replace(tzinfo=timezone.utc).date()
            # Move back one day
            import datetime as dt_module
            expected_date = expected_date - dt_module.timedelta(days=1)
        else:
            # Gap found — streak ends
            break
    
    return streak
