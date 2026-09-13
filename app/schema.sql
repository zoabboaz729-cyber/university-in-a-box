-- University in a Box — Phase 0 schema.
-- Tables mirror the data model in docs/02-ARCHITECTURE.md.
-- Plain .sql file, no migration framework yet.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    destination TEXT,
    baseline TEXT,
    cut_list TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    order_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    milestone_description TEXT,
    time_box TEXT,
    status TEXT NOT NULL DEFAULT 'not_started'
);

CREATE TABLE IF NOT EXISTS advisor_interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    question TEXT NOT NULL,
    answer TEXT,
    step TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advisor_interviews_course
    ON advisor_interviews(course_id);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    label TEXT NOT NULL,
    url_or_reference TEXT,
    verdict TEXT,
    reason TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tutor_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    gap_note TEXT
);

CREATE TABLE IF NOT EXISTS tutor_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES tutor_sessions(id),
    question TEXT NOT NULL,
    user_answer TEXT,
    order_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS editor_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    milestone_ref TEXT,
    submitted_text TEXT NOT NULL,
    strengths TEXT,
    biggest_weakness TEXT,
    next_edit TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS roommate_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    field TEXT,
    prompt_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    user_reaction TEXT
);

CREATE TABLE IF NOT EXISTS _dash_visits (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    visit_at  TEXT NOT NULL DEFAULT (datetime('now'))
);


CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    is_user INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- NOTE: the course_id index is created in db._migrate (after the
-- D-015 ALTER), NOT here — on a pre-D015 database this CREATE INDEX
-- would run before the column exists and break boot.
