"""Tutor session persistence — Phase 4.

One row in tutor_sessions per session (topic_id, started_at,
ended_at, gap_note) plus one row in tutor_turns per question
(session_id, question, user_answer, order_index). Every answer is
persisted immediately so closing mid-session loses nothing (P6).
Gap notes are only written at end-session with real LLM text —
never generic/empty (no-slop rule).
"""
from app.db import get_connection
from app.roles.activity import log


def start_session(topic_id: int, user_id: int) -> int:
    """Open a session for one of this user's topics. Returns the session id."""
    with get_connection() as conn:
        topic = conn.execute(
            "SELECT id, course_id FROM topics WHERE id = ? AND user_id = ?",
            (topic_id, user_id),
        ).fetchone()
        if topic is None:
            raise ValueError("topic not found: " + str(topic_id))
        cursor = conn.execute(
            "INSERT INTO tutor_sessions (topic_id, user_id) VALUES (?, ?)",
            (topic_id, user_id),
        )
        session_id = cursor.lastrowid
        course_id = topic["course_id"]
    log(course_id, "tutor_session", session_id, "started")
    return session_id


def delete_session(session_id: int, user_id: int) -> None:
    """Remove an empty just-created session (provider failure cleanup)."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM tutor_turns WHERE session_id = ? AND user_id = ?",
            (session_id, user_id))
        conn.execute(
            "DELETE FROM tutor_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id))


def find_open_session(topic_id: int, user_id: int) -> int | None:
    """Newest still-open session for a topic, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM tutor_sessions WHERE topic_id = ? AND user_id = ? "
            "AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
            (topic_id, user_id),
        ).fetchone()
        return row["id"] if row else None


def get_session(session_id: int, user_id: int) -> dict | None:
    """Session + ordered turns + topic context, or None (also None for
    another user's session — Phase 12)."""
    with get_connection() as conn:
        sess = conn.execute(
            "SELECT s.id, s.topic_id, s.started_at, s.ended_at, s.gap_note, "
            "t.title AS topic_title, t.milestone_description, "
            "t.course_id, c.title AS course_title "
            "FROM tutor_sessions s JOIN topics t ON t.id = s.topic_id "
            "JOIN courses c ON c.id = t.course_id "
            "WHERE s.id = ? AND s.user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if sess is None:
            return None
        turn_rows = conn.execute(
            "SELECT id, question, user_answer, order_index FROM tutor_turns "
            "WHERE session_id = ? AND user_id = ? ORDER BY order_index",
            (session_id, user_id),
        ).fetchall()
        data = dict(sess)
        data["turns"] = [dict(r) for r in turn_rows]
        return data


def list_sessions_for_topic(topic_id: int, user_id: int) -> list[dict]:
    """All sessions for a topic, newest first, with turn counts."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT s.id, s.started_at, s.ended_at, s.gap_note, "
            "(SELECT COUNT(*) FROM tutor_turns t WHERE t.session_id = s.id) "
            "AS turn_count FROM tutor_sessions s "
            "WHERE s.topic_id = ? AND s.user_id = ? ORDER BY s.id DESC",
            (topic_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]


def add_turn(session_id: int, question: str, user_id: int) -> int:
    """Persist one Tutor question. Returns the turn id. Raises ValueError when
    the session is missing or owned by another user."""
    if not question or not question.strip():
        raise ValueError("tutor question is empty")
    with get_connection() as conn:
        owner = conn.execute(
            "SELECT id FROM tutor_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if owner is None:
            raise ValueError("session not found: " + str(session_id))
        row = conn.execute(
            "SELECT MAX(order_index) AS m FROM tutor_turns "
            "WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        order_index = (row["m"] + 1) if row["m"] is not None else 0
        cursor = conn.execute(
            "INSERT INTO tutor_turns "
            "(session_id, user_id, question, order_index) VALUES (?, ?, ?, ?)",
            (session_id, user_id, question.strip(), order_index),
        )
        return cursor.lastrowid


def save_answer(turn_id: int, answer: str, user_id: int) -> None:
    """Persist the user's answer to one turn immediately."""
    if not answer or not answer.strip():
        raise ValueError("tutor answer is empty")
    with get_connection() as conn:
        turn = conn.execute(
            "SELECT tt.id, tt.session_id, tp.course_id "
            "FROM tutor_turns tt "
            "JOIN tutor_sessions s ON s.id = tt.session_id "
            "JOIN topics tp ON tp.id = s.topic_id "
            "WHERE tt.id = ? AND tt.user_id = ?",
            (turn_id, user_id),
        ).fetchone()
        if turn is None:
            raise ValueError("turn not found: " + str(turn_id))
        conn.execute(
            "UPDATE tutor_turns SET user_answer = ? WHERE id = ? AND user_id = ?",
            (answer.strip(), turn_id, user_id),
        )
        course_id = turn["course_id"]
    log(course_id, "tutor_session", turn["session_id"],
        "answered:" + str(turn_id))


def end_session(session_id: int, gap_note: str, user_id: int) -> None:
    """Close a session with its gap note. Only closes open sessions owned by
    this user."""
    if not gap_note or not gap_note.strip():
        raise ValueError("gap note is empty")
    with get_connection() as conn:
        sess = conn.execute(
            "SELECT s.id, s.ended_at, t.course_id "
            "FROM tutor_sessions s JOIN topics t ON t.id = s.topic_id "
            "WHERE s.id = ? AND s.user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if sess is None:
            raise ValueError("session not found: " + str(session_id))
        if sess["ended_at"] is not None:
            return
        conn.execute(
            "UPDATE tutor_sessions SET ended_at = datetime('now'), "
            "gap_note = ? WHERE id = ? AND user_id = ?",
            (gap_note.strip(), session_id, user_id),
        )
        course_id = sess["course_id"]
    log(course_id, "tutor_session", session_id, "ended")


def last_gap_for_course(course_id: int, conn=None) -> str | None:
    """Most recent non-empty gap note across a course's topics.

    `conn` lets a caller share one open connection across a per-course
    loop; when given it is used as-is and never closed or committed here;
    when omitted, this opens and closes its own connection as before.
    """
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT gap_note FROM tutor_sessions WHERE gap_note IS NOT NULL "
            "AND gap_note != '' AND topic_id IN "
            "(SELECT id FROM topics WHERE course_id = ?) "
            "ORDER BY id DESC LIMIT 1",
            (course_id,),
        ).fetchone()
        return row["gap_note"] if row else None
    finally:
        if own:
            conn.close()
