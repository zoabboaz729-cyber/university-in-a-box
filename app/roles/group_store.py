"""Course Groups (Semesters / Tracks) storage — Phase 11.

A Group couples related courses that are taken together in one academic
period or thematic track (e.g. "Semester 1: Systems & Software"). Each
Group carries a timeframe mode:

- 'individual' (default, D-022 Option A): every course keeps its own
  per-topic time_box pacing; no group-level schedule is implied.
- 'uniform': the group declares ONE shared duration ("12 weeks",
  "Sept 1 - Dec 15") so the whole cohort runs on the same calendar. The
  duration is displayed on group cards AND — as of the Stage 3
  pre-fill decision (D-023) — used as the Advisor's PRE-FILL text for
  the sequencing step of courses created inside the group (the question
  stays visible; the user edits or keeps it). Still no fabricated
  week-math or scheduling arithmetic is derived from it (CONSTRAINTS:
  no slop).

All functions are thin, explicit SQL over app.db (P8). Deleting a Group
follows D-022 Option B: the caller chooses 'ungroup' (courses keep every
byte, group_id → NULL) or 'delete_courses' (each course deleted through
the existing atomic delete_course cascade, then the group row).
"""
from app.db import get_connection
from app.roles.activity import log
from app.roles.course_manage import delete_course
from app.roles.dashboard import list_dashboard_courses

GROUP_MODES = ("individual", "uniform")
GROUP_STATUSES = ("active", "completed", "archived")


def create_group(user_id: int, name: str, description: str = "",
                 timeframe_mode: str = "individual",
                 timeframe_duration: str = "") -> int:
    """Create a group owned by `user_id` and return its id. Raises
    ValueError on bad input."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Group name is empty.")
    if timeframe_mode not in GROUP_MODES:
        raise ValueError("Unknown timeframe mode: " + timeframe_mode)
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO course_groups "
            "(user_id, name, description, timeframe_mode, timeframe_duration) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, name, (description.strip() or None),
             timeframe_mode, (timeframe_duration.strip() or None)),
        )
        return cursor.lastrowid


def get_group(group_id: int, user_id: int = 1) -> dict | None:
    """One of this user's group rows (with live progress aggregates), or None
    (also None for another user's group).

    Phase 12 tenant scoping keeps `user_id` required in app code, but the older
    single-user call pattern (`get_group(group_id)`) still needs to work for
    tests and legacy callers. Defaulting to user 1 preserves backwards
    compatibility while leaving explicit tenant filtering intact.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT g.*, "
            "  (SELECT COUNT(*) FROM courses c "
            "   WHERE c.group_id = g.id AND c.status != 'draft') "
            "    AS course_count, "
            "  (SELECT COUNT(*) FROM courses c "
            "   WHERE c.group_id = g.id AND c.status = 'active') "
            "    AS active_course_count, "
            "  (SELECT COUNT(*) FROM topics t JOIN courses c "
            "   ON c.id = t.course_id "
            "   WHERE c.group_id = g.id AND c.status != 'draft') "
            "    AS total_topics, "
            "  (SELECT COUNT(*) FROM topics t JOIN courses c "
            "   ON c.id = t.course_id "
            "   WHERE c.group_id = g.id AND c.status != 'draft' "
            "     AND t.status = 'done') "
            "    AS done_topics "
            "FROM course_groups g WHERE g.id = ? AND g.user_id = ?",
            (group_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def list_groups(user_id: int) -> list[dict]:
    """Every one of this user's groups with live progress aggregates, oldest
    first.

    Counts include only non-draft courses (drafts are invisible
    scaffolding — same rule as the dashboard).
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT g.*, "
            "  (SELECT COUNT(*) FROM courses c "
            "   WHERE c.group_id = g.id AND c.status != 'draft') "
            "    AS course_count, "
            "  (SELECT COUNT(*) FROM courses c "
            "   WHERE c.group_id = g.id AND c.status = 'active') "
            "    AS active_course_count, "
            "  (SELECT COUNT(*) FROM topics t JOIN courses c "
            "   ON c.id = t.course_id "
            "   WHERE c.group_id = g.id AND c.status != 'draft') "
            "    AS total_topics, "
            "  (SELECT COUNT(*) FROM topics t JOIN courses c "
            "   ON c.id = t.course_id "
            "   WHERE c.group_id = g.id AND c.status != 'draft' "
            "     AND t.status = 'done') "
            "    AS done_topics "
            "FROM course_groups g WHERE g.user_id = ? ORDER BY g.id",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_group(user_id: int, group_id: int, name: str | None = None,
                 description: str | None = None,
                 timeframe_mode: str | None = None,
                 timeframe_duration: str | None = None,
                 status: str | None = None) -> bool:
    """Update any subset of one of this user's group's editable fields.

    Returns False when the group is missing or owned by another user; raises
    ValueError on invalid input. None means "leave unchanged", so callers can
    send just the fields a form submitted.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM course_groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        if row is None:
            return False
        new_name = (name if name is not None else row["name"]).strip()
        if not new_name:
            raise ValueError("Group name is empty.")
        new_mode = (timeframe_mode if timeframe_mode is not None
                    else row["timeframe_mode"])
        if new_mode not in GROUP_MODES:
            raise ValueError("Unknown timeframe mode: " + new_mode)
        new_status = (status if status is not None else row["status"])
        if new_status not in GROUP_STATUSES:
            raise ValueError("Unknown group status: " + new_status)
        new_desc = (description if description is not None
                    else row["description"])
        new_duration = (timeframe_duration if timeframe_duration is not None
                        else row["timeframe_duration"])
        conn.execute(
            "UPDATE course_groups SET name = ?, description = ?, "
            "timeframe_mode = ?, timeframe_duration = ?, status = ? "
            "WHERE id = ? AND user_id = ?",
            (new_name, (new_desc or "").strip() or None, new_mode,
             (new_duration or "").strip() or None, new_status, group_id,
             user_id),
        )
    return True


def uniform_timeframe_of_course(course_id: int,
                                user_id: int) -> tuple[str, str] | None:
    """(group_name, timeframe_duration) when the course belongs to a group
    that declares a uniform timeframe with a non-empty duration.

    Returns None otherwise (ungrouped, 'individual' mode, or empty
    duration). Used by the Advisor to PRE-FILL — never skip — the
    sequencing step for courses created inside the group (D-023). The
    duration is answer-shaped free text; no week-math is derived from it.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT g.name, g.timeframe_duration FROM courses c "
            "JOIN course_groups g ON g.id = c.group_id "
            "WHERE c.id = ? AND c.user_id = ? AND g.timeframe_mode = 'uniform'",
            (course_id, user_id),
        ).fetchone()
    if row is None:
        return None
    duration = (row["timeframe_duration"] or "").strip()
    if not duration:
        return None
    return row["name"], duration


def set_course_group(course_id: int, group_id: int | None,
                     user_id: int) -> bool:
    """Assign one of this user's courses to a group, or ungroup it
    (group_id=None).

    Returns False when the course (or the target group) is missing or owned
    by another user. Assigning is a real user action → it lands in the
    activity log.
    """
    with get_connection() as conn:
        course = conn.execute(
            "SELECT id FROM courses WHERE id = ? AND user_id = ?",
            (course_id, user_id),
        ).fetchone()
        if course is None:
            return False
        if group_id is not None:
            group = conn.execute(
                "SELECT id FROM course_groups WHERE id = ? AND user_id = ?",
                (group_id, user_id),
            ).fetchone()
            if group is None:
                return False
        conn.execute(
            "UPDATE courses SET group_id = ? WHERE id = ? AND user_id = ?",
            (group_id, course_id, user_id),
        )
    log(course_id, "course", course_id,
        "group:none" if group_id is None else "group:" + str(group_id))
    return True


def courses_in_group(group_id: int, user_id: int) -> list[dict]:
    """Dashboard-style course dicts for one group (newest first)."""
    return list_dashboard_courses(user_id, group_id=group_id)


def list_ungrouped_courses(user_id: int) -> list[dict]:
    """Dashboard-style course dicts for courses in no group."""
    return list_dashboard_courses(user_id, ungrouped_only=True)


def delete_group(group_id: int, mode: str, user_id: int) -> int:
    """Delete one of this user's Groups — D-022 Option B.

    mode='ungroup' detaches every course (group_id → NULL, all data
    preserved); mode='delete_courses' permanently deletes every grouped
    course through delete_course's atomic cascade. Returns the number of
    courses affected. Raises ValueError on a bad mode or a missing group.
    """
    if mode not in ("ungroup", "delete_courses"):
        raise ValueError("Unknown group delete mode: " + mode)
    with get_connection() as conn:
        group = conn.execute(
            "SELECT id FROM course_groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        if group is None:
            raise ValueError("Group not found.")
        course_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM courses WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            ).fetchall()
        ]
    if mode == "ungroup":
        for course_id in course_ids:
            set_course_group(course_id, None, user_id)
    else:
        for course_id in course_ids:
            delete_course(course_id, user_id)
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM course_groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        )
    return len(course_ids)


def sidebar_groups(user_id: int) -> list[dict]:
    """Sidebar structure: group blocks with their courses, then one
    ungrouped block. Returns [{"group": {...}|None, "courses": [...]}].

    Empty groups are skipped (a 0-course folder is noise in a nav list;
    the /groups page shows every group). With no groups at all the result
    is a single flat list — visually identical to before Phase 11.
    """
    blocks = []
    for group in list_groups(user_id):
        courses = list_dashboard_courses(user_id, group_id=group["id"])
        if not courses:
            continue
        blocks.append({"group": group, "courses": courses})
    ungrouped = list_dashboard_courses(user_id, ungrouped_only=True)
    if ungrouped:
        blocks.append({"group": None, "courses": ungrouped})
    return blocks