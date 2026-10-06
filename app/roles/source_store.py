"""Source persistence — Phase 3, extended Stage 3 Task 6.

One row per candidate source. A source attaches to exactly ONE scope:
a topic (topic_id) or a whole course (course_id) — enforced here at the
app layer, the codebase's documented FK-integrity pattern. Skip sources
are KEPT and shown dimmed — never silently deleted (build-plan
constraint).

verdict is storage vocabulary, checked in add_source(): 'keep' | 'skip' |
'later' (the Shelf filter is verdict = 'keep') plus 'unverified' (kept but
not read — D-024). reason is the stored one-line explanation; the read-before-accept flow
writes librarian.judgement_text() there
("Read: … Fit: … Credibility: … Access: …"). Pre-Task-7 rows written by
the deleted description-only triage path (D-025) stored
"Good for X. <reason>".

verified_at: set when the source has actually been fetched and judged
(Stage 3 Task 7); NULL means unverified and is displayed as such.
"""
from app.db import get_connection
from app.roles.activity import log

# Verdict vocabulary for the sources table. 'keep' | 'skip' | 'later' are
# the stored judgments; 'unverified' (UNVERIFIED_VERDICT below) is the
# kept-but-unread state. Canonical home since the description-only
# triage() path was deleted (D-025) — previously imported from
# app.roles.librarian.
VERDICTS = ("keep", "skip", "later")

_SOURCE_COLUMNS = (
    "id, topic_id, course_id, label, url_or_reference, verdict, "
    "reason, added_at, verified_at"
)

# A kept-but-unread source gets this verdict instead of a fabricated
# keep/skip/later: the row has no judgment behind it, and the stored data
# says so rather than inventing one (Stage 3 Task 7 outcome 3 is the
# user's explicit choice to keep a source the app could not read).
UNVERIFIED_VERDICT = "unverified"


def add_source(topic_id: int | None, label: str, reference: str, verdict: str,
               reason: str, user_id: int, verified_at: str | None = None,
               course_id: int | None = None) -> int:
    """Insert one source row in exactly one scope and return its id.

    Exactly one of topic_id / course_id must be non-null (ValueError
    otherwise). The scope must belong to `user_id` (ValueError otherwise).
    verified_at is settable for the verification flow; NULL means the source
    is kept but visibly unverified.
    """
    if not label or not label.strip():
        raise ValueError("source label is empty")
    if verdict not in VERDICTS and verdict != UNVERIFIED_VERDICT:
        raise ValueError("unknown verdict: " + verdict)

    if not reason or not reason.strip():
        raise ValueError("source reason is empty")
    if (topic_id is None) == (course_id is None):
        raise ValueError(
            "exactly one of topic_id / course_id must be set")
    with get_connection() as conn:
        if topic_id is not None:
            topic = conn.execute(
                "SELECT id, course_id FROM topics WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            ).fetchone()
            if topic is None:
                raise ValueError("topic not found: " + str(topic_id))
            owner_course_id = topic["course_id"]
        else:
            course = conn.execute(
                "SELECT id FROM courses WHERE id = ? AND user_id = ?",
                (course_id, user_id),
            ).fetchone()
            if course is None:
                raise ValueError("course not found: " + str(course_id))
            owner_course_id = course_id
        cursor = conn.execute(
            "INSERT INTO sources (user_id, topic_id, course_id, label, "
            "url_or_reference, verdict, reason, verified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, topic_id, course_id, label.strip(),
             (reference or "").strip(), verdict, reason.strip(), verified_at),
        )
        source_id = cursor.lastrowid
    log(owner_course_id, "source", source_id, "added")
    return source_id


def list_sources(topic_id: int, user_id: int,
                 keep_only: bool = False) -> list[dict]:
    """All sources for a topic, newest first (skip rows kept, dimmed in UI)."""
    return _list_where("topic_id = ? AND user_id = ?", (topic_id, user_id),
                       keep_only)


def list_course_sources(course_id: int, user_id: int,
                        keep_only: bool = False) -> list[dict]:
    """All course-level sources (topic_id IS NULL), newest first."""
    return _list_where(
        "course_id = ? AND topic_id IS NULL AND user_id = ?",
        (course_id, user_id), keep_only)


def _list_where(where: str, params: tuple, keep_only: bool) -> list[dict]:
    sql = f"SELECT {_SOURCE_COLUMNS} FROM sources WHERE {where}"
    if keep_only:
        sql += " AND verdict = 'keep'"
    sql += " ORDER BY id DESC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def get_source(source_id: int, user_id: int) -> dict | None:
    """One source row by id, or None (also None for another user's row)."""
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_SOURCE_COLUMNS} FROM sources "
            "WHERE id = ? AND user_id = ?",
            (source_id, user_id),
        ).fetchone()
    return dict(row) if row is not None else None


def mark_verified(source_id: int, verdict: str, reason: str,
                  verified_at: str, user_id: int) -> bool:
    """Record a passing verification: verdict + reason + verified_at.

    Returns False when the row is gone or owned by another user. This is the
    ONLY way a row's verified_at becomes non-NULL for an existing row — the
    add path sets it at insert time instead.
    """
    if verdict not in VERDICTS:
        raise ValueError("unknown verdict: " + verdict)
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE sources SET verdict = ?, reason = ?, verified_at = ? "
            "WHERE id = ? AND user_id = ?",
            (verdict, reason.strip(), verified_at, source_id, user_id),
        )
        return cursor.rowcount > 0


def delete_source(source_id: int, user_id: int) -> bool:
    """Drop one source row (Task 7 reject / discard outcomes). False if gone
    or owned by another user."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM sources WHERE id = ? AND user_id = ?",
            (source_id, user_id),
        )
        return cursor.rowcount > 0
