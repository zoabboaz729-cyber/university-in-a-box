"""Course Groups (Semesters / Tracks) storage — Phase 11.

A Group couples related courses that are taken together in one academic
period or thematic track (e.g. "Semester 1: Systems & Software"). Each
Group carries a timeframe mode:

- 'individual' (default, D-022 Option A): every course keeps its own
  per-topic time_box pacing; no group-level schedule is implied.
- 'uniform': the group declares ONE shared duration ("12 weeks",
  "Sept 1 - Dec 15") so the whole cohort runs on the same calendar. The
  duration is displayed on group cards; no fabricated week-math is
  invented from it (CONSTRAINTS: no slop).

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


def create_group(name: str, description: str = "",
                 timeframe_mode: str = "individual",
                 timeframe_duration: str = "") -> int:
    """Create a group and return its id. Raises ValueError on bad input."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Group name is empty.")
    if timeframe_mode not in GROUP_MODES:
        raise ValueError("Unknown timeframe mode: " + timeframe_mode)
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO course_groups "
            "(name, description, timeframe_mode, timeframe_duration) "
            "VALUES (?, ?, ?, ?)",
            (name, (description.strip() or None),
             timeframe_mode, (timeframe_duration.strip() or None)),
        )
        return cursor.lastrowid


def get_group(group_id: int) -> dict | None:
    """One group row (with live progress aggregates), or None."""
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
            "FROM course_groups g WHERE g.id = ?",
            (group_id,),
        ).fetchone()
        return dict(row) if row else None


def list_groups() -> list[dict]:
    """Every group with live progress aggregates, oldest first.

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
            "FROM course_groups g ORDER BY g.id",
        ).fetchall()
    return [dict(row) for row in rows]


def update_group(group_id: int, name: str | None = None,
                 description: str | None = None,
                 timeframe_mode: str | None = None,
                 timeframe_duration: str | None = None,
                 status: str | None = None) -> bool:
    """Update any subset of a group's editable fields.

    Returns False when the group is missing; raises ValueError on invalid
    input. None means "leave unchanged", so callers can send just the
    fields a form submitted.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM course_groups WHERE id = ?", (group_id,)
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
            "WHERE id = ?",
            (new_name, (new_desc or "").strip() or None, new_mode,
             (new_duration or "").strip() or None, new_status, group_id),
        )
    return True


def set_course_group(course_id: int, group_id: int | None) -> bool:
    """Assign a course to a group, or ungroup it (group_id=None).

    Returns False when the course (or the target group) is missing.
    Assigning is a real user action → it lands in the activity log.
    """
    with get_connection() as conn:
        course = conn.execute(
            "SELECT id FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if course is None:
            return False
        if group_id is not None:
            group = conn.execute(
                "SELECT id FROM course_groups WHERE id = ?", (group_id,)
            ).fetchone()
            if group is None:
                return False
        conn.execute(
            "UPDATE courses SET group_id = ? WHERE id = ?",
            (group_id, course_id),
        )
    log(course_id, "course", course_id,
        "group:none" if group_id is None else "group:" + str(group_id))
    return True


def courses_in_group(group_id: int) -> list[dict]:
    """Dashboard-style course dicts for one group (newest first)."""
    return list_dashboard_courses(group_id=group_id)


def list_ungrouped_courses() -> list[dict]:
    """Dashboard-style course dicts for courses in no group."""
    return list_dashboard_courses(ungrouped_only=True)


def delete_group(group_id: int, mode: str) -> int:
    """Delete a Group — D-022 Option B.

    mode='ungroup' detaches every course (group_id → NULL, all data
    preserved); mode='delete_courses' permanently deletes every grouped
    course through delete_course's atomic cascade. Returns the number of
    courses affected. Raises ValueError on a bad mode or a missing group.
    """
    if mode not in ("ungroup", "delete_courses"):
        raise ValueError("Unknown group delete mode: " + mode)
    with get_connection() as conn:
        group = conn.execute(
            "SELECT id FROM course_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if group is None:
            raise ValueError("Group not found.")
        course_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM courses WHERE group_id = ?", (group_id,)
            ).fetchall()
        ]
    if mode == "ungroup":
        for course_id in course_ids:
            set_course_group(course_id, None)
    else:
        for course_id in course_ids:
            delete_course(course_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM course_groups WHERE id = ?", (group_id,))
    return len(course_ids)


def sidebar_groups() -> list[dict]:
    """Sidebar structure: group blocks with their courses, then one
    ungrouped block. Returns [{"group": {...}|None, "courses": [...]}].

    Empty groups are skipped (a 0-course folder is noise in a nav list;
    the /groups page shows every group). With no groups at all the result
    is a single flat list — visually identical to before Phase 11.
    """
    blocks = []
    for group in list_groups():
        courses = list_dashboard_courses(group_id=group["id"])
        if not courses:
            continue
        blocks.append({"group": group, "courses": courses})
    ungrouped = list_dashboard_courses(ungrouped_only=True)
    if ungrouped:
        blocks.append({"group": None, "courses": ungrouped})
    return blocks