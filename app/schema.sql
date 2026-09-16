-- University in a Box — Phase 0 schema.
-- Tables mirror the data model in docs/02-ARCHITECTURE.md.
-- Plain .sql file, no migration framework yet.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS course_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT,
    timeframe_mode TEXT NOT NULL DEFAULT 'individual', -- 'uniform' vs 'individual'
    timeframe_duration TEXT,                          -- e.g. "12 weeks", "Sept 1 - Dec 15"
    status TEXT NOT NULL DEFAULT 'active',            -- 'active', 'completed', 'archived'
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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- Phase 11: the Course Group (Semester/Track) this course belongs to.
    -- NULL = ungrouped. App-level integrity (same pattern as other FKs here).
    group_id INTEGER REFERENCES course_groups(id)
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
    -- Exactly one of topic_id / course_id is non-null (app-layer rule):
    -- a source attaches to a single Topic OR to the Course as a whole.
    -- topic_id is nullable since Stage 3 Task 6 (course-level sources).
    topic_id INTEGER REFERENCES topics(id),
    course_id INTEGER REFERENCES courses(id),
    label TEXT NOT NULL,
    url_or_reference TEXT,
    verdict TEXT,
    reason TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- Stage 3 Task 6: set when the source has actually been fetched and
    -- judged by the Librarian's verify(); NULL = unverified (shown as such).
    verified_at TEXT
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
    user_reaction TEXT,
    -- Phase 11 (P5): intra-group cross-course prompts bridge two courses
    -- taken together in the same group. secondary_course_id = the OTHER
    -- course; connection_type = 'external' (one course → unrelated field)
    -- or 'intra_group' (course A ↔ course B in the same group).
    secondary_course_id INTEGER REFERENCES courses(id),
    connection_type TEXT NOT NULL DEFAULT 'external'
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
