"""SQLite connection and schema init.

The SQLite file is the single source of truth (see docs/02-ARCHITECTURE.md).
Plain SQL in schema.sql — no migration framework yet (Phase 0).
"""
import os
import sqlite3
from pathlib import Path

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def get_db_path() -> Path:
    """Resolve the DB file location. Reads DATA_DIR fresh each call so tests
    can point it at a temp dir via the DATA_DIR env var."""
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    if not data_dir.is_absolute():
        # Repo root = parent of the app/ package directory.
        data_dir = Path(__file__).resolve().parent.parent / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "university.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent, tiny migrations for pre-existing databases.

    schema.sql only defines tables for FRESH databases (CREATE IF NOT EXISTS
    won't add a column to an existing table). Pre-release databases therefore
    need one-off ALTERs. Add a step here whenever a later phase evolves a
    table. Each step checks first, so this is safe to run on every boot.
    """
    topic_cols = {row[1] for row in conn.execute("PRAGMA table_info(topics)")}
    if "time_box" not in topic_cols:
        # Phase 1c: persist the Advisor draft's per-topic time box.
        conn.execute("ALTER TABLE topics ADD COLUMN time_box TEXT")

    prompt_cols = {row[1] for row in conn.execute("PRAGMA table_info(roommate_prompts)")}
    if "field" not in prompt_cols:
        # Phase 6: the unrelated-domain label (journal display + dedup).
        conn.execute("ALTER TABLE roommate_prompts ADD COLUMN field TEXT")

    activity_cols = {row[1] for row in conn.execute("PRAGMA table_info(activity_log)")}
    if "course_id" not in activity_cols:
        # D-015: activity rows now carry their owning Course and a
        # user/system flag so the dashboard never re-derives them.
        conn.execute(
            "ALTER TABLE activity_log ADD COLUMN course_id "
            "INTEGER REFERENCES courses(id)"
        )
    if "is_user" not in activity_cols:
        conn.execute(
            "ALTER TABLE activity_log ADD COLUMN is_user "
            "INTEGER NOT NULL DEFAULT 1"
        )
    # Backfill for rows written before D-015. Every mapping is derivable
    # from the existing tables; the UPDATEs are idempotent (only fill
    # NULL course_id, only zero system rows).
    conn.execute(
        "UPDATE activity_log SET course_id = entity_id "
        "WHERE course_id IS NULL AND entity_type IN ('course', 'interview')"
    )
    conn.execute(
        "UPDATE activity_log SET course_id = "
        "(SELECT course_id FROM topics WHERE id = activity_log.entity_id) "
        "WHERE entity_type = 'topic' AND course_id IS NULL "
        "AND EXISTS (SELECT 1 FROM topics "
        "WHERE id = activity_log.entity_id)"
    )
    conn.execute(
        "UPDATE activity_log SET course_id = "
        "(SELECT t.course_id FROM sources s JOIN topics t "
        "ON t.id = s.topic_id WHERE s.id = activity_log.entity_id) "
        "WHERE entity_type = 'topic' AND course_id IS NULL "
        "AND EXISTS (SELECT 1 FROM sources "
        "WHERE id = activity_log.entity_id)"
    )
    conn.execute(
        "UPDATE activity_log SET course_id = "
        "(SELECT t.course_id FROM editor_reviews r JOIN topics t "
        "ON t.id = r.topic_id WHERE r.id = activity_log.entity_id) "
        "WHERE entity_type = 'topic' AND course_id IS NULL "
        "AND EXISTS (SELECT 1 FROM editor_reviews "
        "WHERE id = activity_log.entity_id)"
    )
    conn.execute(
        "UPDATE activity_log SET course_id = "
        "(SELECT t.course_id FROM tutor_sessions s JOIN topics t "
        "ON t.id = s.topic_id WHERE s.id = activity_log.entity_id) "
        "WHERE entity_type = 'tutor_session' AND course_id IS NULL"
    )
    conn.execute(
        "UPDATE activity_log SET course_id = "
        "(SELECT course_id FROM roommate_prompts "
        "WHERE id = activity_log.entity_id) "
        "WHERE entity_type = 'roommate' AND action = 'generated' "
        "AND course_id IS NULL"
    )
    conn.execute(
        "UPDATE activity_log SET course_id = entity_id "
        "WHERE entity_type = 'roommate' AND action LIKE 'generate_failed%' "
        "AND course_id IS NULL"
    )
    # System-generated rows (a prompt being generated, a failed check)
    # must never refresh the dashboard's days-since-activity clock.
    conn.execute(
        "UPDATE activity_log SET is_user = 0 "
        "WHERE entity_type = 'roommate' AND (action = 'generated' "
        "OR action LIKE 'generate_failed%')"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_log_course "
        "ON activity_log(course_id)"
    )

    # ---- Phase 11: Course Groups / Semesters ----
    # The course_groups TABLE itself is created by schema.sql on every boot
    # (CREATE IF NOT EXISTS); only column evolution on pre-existing tables
    # belongs here.
    course_cols = {row[1] for row in conn.execute("PRAGMA table_info(courses)")}
    if "group_id" not in course_cols:
        # Phase 11: which Course Group (Semester/Track) a course belongs to.
        # NULL = ungrouped. Integrity is enforced in the app layer (same
        # pattern as every other FK column in this codebase).
        conn.execute("ALTER TABLE courses ADD COLUMN group_id INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_courses_group ON courses(group_id)"
    )

    prompt_cols = {row[1] for row in conn.execute("PRAGMA table_info(roommate_prompts)")}
    if "secondary_course_id" not in prompt_cols:
        # Phase 11 (P5): the OTHER course an intra-group prompt bridges.
        conn.execute(
            "ALTER TABLE roommate_prompts ADD COLUMN secondary_course_id INTEGER"
        )
    if "connection_type" not in prompt_cols:
        # Phase 11: 'external' (course → unrelated field) vs 'intra_group'
        # (course A ↔ course B in the same group).
        conn.execute(
            "ALTER TABLE roommate_prompts ADD COLUMN connection_type "
            "TEXT NOT NULL DEFAULT 'external'"
        )

    # ---- Stage 3 Task 6: source verification -----------------------------
    # sources needs course_id + verified_at, and topic_id must become
    # nullable (a source attaches to a Topic OR the Course). SQLite cannot
    # ALTER a column's NOT NULL flag, so this is a rebuild: new table →
    # copy every row → drop → rename. Idempotent (skipped once columns
    # exist and topic_id is nullable); every existing row survives.
    # PRAGMA rows are (cid, name, type, notnull, ...) — indexed, not keyed,
    # to match the steps above and stay indifferent to row_factory.
    source_info = {row[1]: row for row in conn.execute("PRAGMA table_info(sources)")}
    if ("topic_id" not in source_info
            or "course_id" not in source_info
            or "verified_at" not in source_info
            or source_info["topic_id"][3]):
        conn.execute(
            "CREATE TABLE sources_migrated ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "topic_id INTEGER REFERENCES topics(id), "
            "course_id INTEGER REFERENCES courses(id), "
            "label TEXT NOT NULL, "
            "url_or_reference TEXT, "
            "verdict TEXT, "
            "reason TEXT, "
            "added_at TEXT NOT NULL DEFAULT (datetime('now')), "
            "verified_at TEXT)"
        )
        conn.execute(
            "INSERT INTO sources_migrated "
            "(id, topic_id, course_id, label, url_or_reference, verdict, "
            " reason, added_at, verified_at) "
            "SELECT id, topic_id, NULL, label, url_or_reference, verdict, "
            "       reason, added_at, NULL FROM sources"
        )
        conn.execute("DROP TABLE sources")
        conn.execute("ALTER TABLE sources_migrated RENAME TO sources")

def init_db() -> Path:
    """Create all tables if they don't exist yet. Safe to call on every boot."""
    path = get_db_path()
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema)
        _migrate(conn)
    return path
