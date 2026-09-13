"""Source persistence — Phase 3.

One row per candidate source in sources(topic_id, label,
url_or_reference, verdict, reason, added_at). Skip sources are KEPT and
shown dimmed — never silently deleted (build-plan constraint). The
good_for phrase lives inside reason as "Good for X. <reason>" so no
schema change is needed (architecture: resist speculative columns).
"""
from app.db import get_connection
from app.roles.activity import log
from app.roles.librarian import VERDICTS


def add_source(topic_id: int, label: str, reference: str, verdict: str,
               reason: str) -> int:
    """Insert one source row. Returns its id. Raises ValueError on bad input."""
    if not label or not label.strip():
        raise ValueError("source label is empty")
    if verdict not in VERDICTS:
        raise ValueError("unknown verdict: " + verdict)
    if not reason or not reason.strip():
        raise ValueError("source reason is empty")
    with get_connection() as conn:
        topic = conn.execute(
            "SELECT id, course_id FROM topics WHERE id = ?", (topic_id,)
        ).fetchone()
        if topic is None:
            raise ValueError("topic not found: " + str(topic_id))
        cursor = conn.execute(
            "INSERT INTO sources (topic_id, label, url_or_reference, "
            "verdict, reason) VALUES (?, ?, ?, ?, ?)",
            (topic_id, label.strip(), (reference or "").strip(),
             verdict, reason.strip()),
        )
        source_id = cursor.lastrowid
        course_id = topic["course_id"]
    log(course_id, "source", source_id, "added")
    return source_id


def list_sources(topic_id: int, keep_only: bool = False) -> list[dict]:
    """All sources for a topic, newest first (skip rows kept, dimmed in UI)."""
    with get_connection() as conn:
        if keep_only:
            rows = conn.execute(
                "SELECT id, label, url_or_reference, verdict, reason, added_at "
                "FROM sources WHERE topic_id = ? AND verdict = 'keep' "
                "ORDER BY id DESC",
                (topic_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, label, url_or_reference, verdict, reason, added_at "
                "FROM sources WHERE topic_id = ? ORDER BY id DESC",
                (topic_id,),
            ).fetchall()
        return [dict(row) for row in rows]
