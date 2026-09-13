"""Roommate prompt persistence — Phase 6 (+ Phase 11 intra-group).

One row in roommate_prompts per generated prompt (course_id, field,
prompt_text, created_at, user_reaction). Rows are written only with
complete, real LLM output — never a half-written prompt (no-slop rule).
Generation is logged with is_user=False (the app generated it, the user
didn't — a prompt appearing must not refresh days-since-activity); a
user REACTION is logged with is_user=True because that is real
engagement. Both carry the owning course_id (D-015).

Phase 11 (P5): a prompt may be an 'intra_group' cross-course bridge —
course_id is the primary course, secondary_course_id the OTHER course in
the same group. 'external' prompts (one course → unrelated field) are the
pre-Phase-11 behavior and keep secondary_course_id NULL.
"""
from app.db import get_connection
from app.roles.activity import days_since, log

from pathlib import Path

MAX_REACTION_CHARS = 2000

GROUP_CONNECTION_TYPES = ("external", "intra_group")


def prompt_newer_than(since: str | None) -> dict | None:
    """Return the newest prompt across ACTIVE courses that is newer than
    `since`. Used by the durable indicator to decide whether to show the
    "new connection(s) ready" badge."""
    if not since:
        return latest_prompt()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT p.id, p.course_id, p.field, p.prompt_text, p.created_at,
                      c.title AS course_title
               FROM roommate_prompts p
               JOIN courses c ON c.id = p.course_id
               WHERE p.created_at > ? AND c.status = 'active'
               ORDER BY p.created_at DESC
               LIMIT 1""",
            (since,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)



def save_prompt(course_id: int, field: str, prompt_text: str,
                created_at: str | None = None,
                secondary_course_id: int | None = None,
                connection_type: str = "external") -> int:
    """Persist one complete prompt. Returns the prompt id.

    `created_at` is normally omitted: a millisecond-precision UTC "now" is
    used so prompts are strictly orderable against the equally precise
    dashboard-visit timestamps (the durable badge relies on
    `prompt.created_at > visit`). Tests pass it explicitly to backdate.

    Phase 11: `connection_type` is 'external' (default) or 'intra_group';
    for intra_group prompts `secondary_course_id` names the other course
    in the same group. Both are validated before anything is written.
    """
    if not field or not field.strip():
        raise ValueError("roommate field is empty")
    if not prompt_text or not prompt_text.strip():
        raise ValueError("roommate prompt is empty")
    if connection_type not in GROUP_CONNECTION_TYPES:
        raise ValueError("unknown connection type: " + connection_type)
    if created_at is None:
        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    with get_connection() as conn:
        course = conn.execute(
            "SELECT id FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if course is None:
            raise ValueError("course not found: " + str(course_id))
        if secondary_course_id is not None:
            if secondary_course_id == course_id:
                raise ValueError("secondary course cannot be the same course")
            peer = conn.execute(
                "SELECT id FROM courses WHERE id = ?", (secondary_course_id,)
            ).fetchone()
            if peer is None:
                raise ValueError(
                    "secondary course not found: " + str(secondary_course_id))
        cursor = conn.execute(
            "INSERT INTO roommate_prompts "
            "(course_id, field, prompt_text, created_at, "
            " secondary_course_id, connection_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (course_id, field.strip(), prompt_text.strip(), created_at,
             secondary_course_id, connection_type),
        )
        prompt_id = cursor.lastrowid
    log(course_id, "roommate", prompt_id, "generated", is_user=False)
    return prompt_id


def last_prompt_at(course_id: int) -> str | None:
    """created_at of the newest prompt for a course, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT created_at FROM roommate_prompts "
            "WHERE course_id = ? ORDER BY id DESC LIMIT 1",
            (course_id,),
        ).fetchone()
        return row["created_at"] if row else None


def due_courses(cadence: int) -> list[dict]:
    """Active courses whose last prompt is missing or older than cadence.

    Ordered most-overdue first (never-prompted courses first), so a long
    gap gets refilled before anything brand-new. `cadence` is the number
    of whole days that must pass between prompts per course.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.destination, "
            "  (SELECT MAX(rp.created_at) FROM roommate_prompts rp "
            "   WHERE rp.course_id = c.id) AS last_prompt_at, "
            "  (SELECT t.title FROM topics t "
            "   WHERE t.course_id = c.id AND t.status != 'done' "
            "   ORDER BY t.order_index LIMIT 1) AS current_topic_title "
            "FROM courses c WHERE c.status = 'active' "
            "ORDER BY last_prompt_at ASC",
        ).fetchall()
    due = []
    for row in rows:
        since = days_since(row["last_prompt_at"])
        if since is not None and since < cadence:
            continue  # prompted recently enough
        due.append(dict(row))
    return due


def peer_course(course_id: int) -> dict | None:
    """The first ACTIVE course in the same group as `course_id`, or None.

    Phase 11 (P5): intra-group synthesis bridges two courses the user is
    taking together. Only ACTIVE courses qualify as the peer — a paused or
    archived course never silently drags a live one into a prompt. The
    peer's current topic (first not-done, same rule the dashboard uses)
    is included so the prompt can be concrete.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT c2.id, c2.title, c2.destination, "
            "  (SELECT t.title FROM topics t "
            "   WHERE t.course_id = c2.id AND t.status != 'done' "
            "   ORDER BY t.order_index LIMIT 1) AS current_topic_title "
            "FROM courses c1 "
            "JOIN courses c2 ON c2.group_id = c1.group_id "
            "  AND c2.id != c1.id "
            "WHERE c1.id = ? AND c1.group_id IS NOT NULL "
            "  AND c1.status = 'active' AND c2.status = 'active' "
            "ORDER BY c2.id LIMIT 1",
            (course_id,),
        ).fetchone()
        return dict(row) if row else None


def last_backup_info(data_dir=None):
    """Describe the newest data/university.db.backup-* file.

    Returns {"exists": bool, "name": str|None, "age_days": int|None} so the
    Settings page can say how stale the last backup is instead of leaving it
    invisible (docs/06-MONITORING.md section A: "the app should make it
    obvious how stale the last backup is, even if just a note on the
    Settings page"). `data_dir` is injectable for tests; the route passes
    nothing.
    """
    from datetime import datetime, timezone

    from app.db import get_db_path
    directory = Path(data_dir) if data_dir is not None else get_db_path().parent
    newest = None
    newest_mtime = None
    for child in directory.glob("university.db.backup-*"):
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        # Backup names embed a timestamp (YYYYMMDD-HHMMSS), so lexicographic
        # order matches chronological order. Two files written within the same
        # filesystem timestamp tick share an mtime — break the tie by name so
        # "newest" is deterministic instead of glob-order dependent (flaky on
        # Windows tmp dirs; see test_last_backup_info_picks_newest_and_age).
        if (
            newest is None
            or mtime > newest_mtime
            or (mtime == newest_mtime and child.name > newest.name)
        ):
            newest = child
            newest_mtime = mtime
    if newest is None:
        return {"exists": False, "name": None, "age_days": None}
    age_days = max(
        0,
        (datetime.now(timezone.utc)
         - datetime.fromtimestamp(newest_mtime, tz=timezone.utc)).days,
    )
    return {"exists": True, "name": newest.name, "age_days": age_days}


def recent_fields(course_id, n):
    """The last n fields a course has used, newest first (dedup context)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT field FROM roommate_prompts "
            "WHERE course_id = ? AND field IS NOT NULL AND field != '' "
            "ORDER BY id DESC LIMIT ?",
            (course_id, n),
        ).fetchall()
        return [row["field"] for row in rows]


def dash_visit_at() -> str | None:
    """The timestamp of the LAST dashboard render (the baseline for the
    durable "new since your last visit" badge). Returns None before the
    first visit ever.

    Reads from SQLite's clock so it stays comparable with prompt
    `created_at` values (also from SQLite's clock). Returns None when no
    visit has been recorded yet (e.g. a brand-new database).
    """
    with get_connection() as conn:
        row = conn.execute("SELECT visit_at FROM _dash_visits LIMIT 1").fetchone()
        if row is None or not row["visit_at"]:
            return None
        return row["visit_at"]


def record_dash_visit() -> None:
    """Record that the dashboard has just been rendered.

    Called AFTER we've already decided what this load renders, so this
    load's generation cannot make THIS load's badge fire. The next load
    uses this timestamp as its baseline.
    """
    from datetime import datetime, timezone
    # Millisecond precision, matching touch_visit() and the prompts saved by
    # save_prompt(): a prompt created after this visit must compare strictly
    # greater ("newer") even within the same wall-clock second.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    with get_connection() as conn:
        # id is always 1: the table only ever holds one row (CHECK (id = 1)).
        # INSERT OR REPLACE hits the PRIMARY KEY conflict on id=1 and updates
        # in place, instead of auto-incrementing to an id that violates CHECK.
        conn.execute(
            "INSERT OR REPLACE INTO _dash_visits (id, visit_at) "
            "VALUES (1, ?)",
            (now,),
        )

def list_all_prompts() -> list[dict]:
    """Every prompt, newest first, joined with its course title (journal).

    Phase 11: intra-group prompts also carry the OTHER course's title so
    the journal can show "Course A ↔ Course B" instead of guessing.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT rp.id, rp.course_id, rp.field, rp.prompt_text, "
            "rp.user_reaction, rp.created_at, rp.secondary_course_id, "
            "rp.connection_type, c.title AS course_title, "
            "c2.title AS secondary_course_title "
            "FROM roommate_prompts rp "
            "JOIN courses c ON c.id = rp.course_id "
            "LEFT JOIN courses c2 ON c2.id = rp.secondary_course_id "
            "ORDER BY rp.id DESC",
        ).fetchall()
        return [dict(row) for row in rows]


def latest_prompt() -> dict | None:
    """Newest prompt across ACTIVE courses (the dashboard block), or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT rp.id, rp.course_id, rp.field, rp.prompt_text, "
            "rp.created_at "
            "FROM roommate_prompts rp JOIN courses c ON c.id = rp.course_id "
            "WHERE c.status = 'active' ORDER BY rp.id DESC LIMIT 1",
        ).fetchone()
        return dict(row) if row else None


def save_reaction(prompt_id: int, reaction: str) -> bool:
    """Attach or adjust the optional free-text reaction on a prompt.

    Empty text clears it. Returns False when the prompt is missing;
    raises ValueError when the reaction is too long.
    """
    if len(reaction) > MAX_REACTION_CHARS:
        raise ValueError("roommate reaction too long")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT course_id FROM roommate_prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE roommate_prompts SET user_reaction = ? WHERE id = ?",
            (reaction.strip(), prompt_id),
        )
        course_id = row["course_id"]
    log(course_id, "roommate", prompt_id, "reacted")
    return True


def log_generate_failed(course_id: int, reason: str) -> None:
    """One audit row per skipped generation (Phase 7 monitoring hook)."""
    log(course_id, "roommate", course_id, "generate_failed: " + reason,
        is_user=False)