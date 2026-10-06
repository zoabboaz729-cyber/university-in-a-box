# Decisions Log

*One entry per real decision — architectural, product, or scope. Not for routine code
changes. Newest at the top. These are defaults set during planning; they're changeable, not
commandments — but changing one should get its own entry explaining why.*

### D-030 — Mobile-First PWA with "The Reading Room" Design Tokens & HTMX
**Date:** 2026-09-30 (Roadmap planning; owner approved)
**Context:** The owner requested a "web and mobile first" experience. A mobile-native rewrite in React Native or Flutter would discard the clean, model-friendly Jinja2/HTMX templates and create heavy build/pipeline complexity (violating P8).
**Decision:** Adopt a Progressive Web App (PWA) architecture built on our existing "Reading Room" aesthetic:
1. Mobile-first app shell: persistent bottom navigation bar on mobile viewports (< 768px), bottom-sheet context menus for course 3-dots actions, keyboard-aware scrolling for tutor sessions.
2. Web App Manifest (`manifest.json`) and lightweight Service Worker (`sw.js`) enabling installability on iOS and Android home screens with standalone display mode.
3. Cache-first strategy for self-hosted fonts, style tokens, and HTMX scripts.
4. Keep server-rendered templates and HTMX; no frontend build step.
**Consequences:** True mobile installability and native-like responsiveness while keeping the codebase 100% server-rendered, lightweight, and model-friendly.

---

### D-029 — Dual Database Architecture: PostgreSQL for Production, SQLite for Local Dev/Testing
**Date:** 2026-09-30 (Roadmap planning; owner approved)
**Context:** Multi-user web hosting introduces concurrent writes across dozens of users creating courses, logging tutor turns, and verifying sources simultaneously. SQLite locks the file during writes (`SQLITE_BUSY`) and cannot scale across multiple web worker processes. However, requiring PostgreSQL for local development and test runs increases friction.
**Decision:** Implement dual-database support in `app/db.py`:
1. Use PostgreSQL with connection pooling (`psycopg` / `asyncpg` / SQLAlchemy Core) when `DATABASE_URL` is set in production.
2. Fall back cleanly to SQLite (`data/university.db` or `:memory:`) for local development and headless test runs.
3. Schema managed and migrated via Alembic.
**Consequences:** Production gains enterprise-grade concurrency, row-level locking, and connection pooling; test suite runs instantly without external database dependencies.

---

### D-028 — Native Email + Password Authentication with Secure Session Cookies
**Date:** 2026-09-30 (Roadmap planning; owner approved)
**Context:** Multi-user platform requires secure identity and session management without vendor lock-in or third-party OAuth app setup requirements.
**Decision:** Implement native Email + Password authentication in `app/auth/`:
1. Password hashing using Argon2id (`argon2-cffi`).
2. Session cookies using signed, HttpOnly, SameSite=Lax (or Strict), Secure cookies (`itsdangerous`).
3. Dependency injection `get_current_user` in FastAPI to enforce authentication across all learning routes and isolate data queries.
**Consequences:** Zero external auth dependencies; full self-containment; standard login, registration, and logout flows.

---

### D-027 — Hybrid / BYOK (Bring Your Own Key) AI Cost Model
**Date:** 2026-09-30 (Roadmap planning; owner approved)
**Context:** In a multi-user hosted service, unmetered AI usage (Advisor interviews, Tutor sessions, Librarian verifications, Roommate prompts) by many users would lead to unsustainable API costs if paid entirely by the host.
**Decision:** Implement a Hybrid / BYOK (Bring Your Own Key) model:
1. Users can configure their own OpenRouter/OpenAI API key (and custom base URL/model) in Settings.
2. User BYOK keys are encrypted at rest in the database using AES-GCM via `APP_SECRET_KEY` and decrypted only in memory when dispatching LLM calls.
3. New users receive an initial server-paid free trial quota (e.g. 1 course, 3 tutor sessions). Once exhausted, they are prompted to provide their personal key in Settings.
**Consequences:** The platform can host unlimited users without financial risk; users have complete transparency and control over their LLM costs and model choices.

---

### D-026 — Pivot from Local-First Single-User to Multi-Tenant Web-Hosted Platform
**Date:** 2026-09-30 (Roadmap planning; owner approved)
**Context:** The owner requested transforming University in a Box from a local-first single-user application to a web-hosted, multi-user, mobile-first platform.
**Decision:** Pivot architecture to multi-tenant web hosting (Phases 12–16) while preserving ALTER pedagogical integrity, user data sovereignty (P6/P7), and small-model maintainability (P8). D-004 is formally superseded by this phase roadmap.
**Consequences:** Every table is partitioned and indexed by `user_id`. Queries strictly filter on `user_id = current_user.id`. The build plan gains Phases 12–16.

---

### D-025 — Delete the description-only triage() path (owner option (a))
**Date:** 2026-09-16 (Stage 3 close-out; owner chose option (a) from activeContext "Open questions")
**Context:** After Stage 3 Task 7 rewired every Librarian route to `librarian.verify()`,
`triage()` + `_parse_verdict()` + `SourceVerdict` + `PROMPT_FILE` (roles/librarian.py),
`prompts/librarian.md`, and the 3 triage tests were unreachable from any app code — only
their own tests exercised them. The owner asked for the trade-offs; option (a) was deletion.
**Decision:** Delete the dead path: `triage()`, `_parse_verdict()`, `SourceVerdict`,
`PROMPT_FILE`, `prompts/librarian.md`, and the 3 triage tests in `tests/test_librarian.py`.
`VERDICTS` was NOT deleted — it moved into its live consumer `app/roles/source_store.py`,
which validates the verdict column with it (existing rows, including pre-Task-7 legacy
rows, still carry keep/skip/later, and the Shelf filter is verdict = 'keep').
**Consequences:** One judgment path per role (`verify()` + `librarian_verify.md`). The
only no-read judgment left is the explicit user-chosen `unverified` keep — never a model
verdict on unread text. This supersedes the "kept as-is" note on D-011.

---

### D-024 — The Librarian READS a source before accepting it (reverses "the model never fetches the URL")
**Date:** 2026-09-14 (Stage 3 Task 7, owner roadmap; entry written 2026-09-16 — the code already
cited this entry, but it had never been added to the log)
**Context:** Phase 3 (D-011) had the Librarian make one judgment call from a source's
label/URL/description alone and explicitly never read the source (`roles/librarian.py` said so).
The owner's Stage 3 roadmap asked for a source recommendation + verification engine; the Stage 2
investigation confirmed no web-fetching capability existed anywhere in the app, and Task 7
delivered the read-before-accept flow.
**Decision:**
1. Nothing is stored as *verified* without having been read. The route fetches the URL
   (`app/fetching/`, SSRF-guarded: http/https only, private/loopback/link-local/reserved
   addresses refused, redirects re-validated), then `librarian.verify()` judges fit,
   credibility, and access from the fetched text — HTML page, PDF text, or YouTube transcript.
2. Exactly one of three explicit outcomes per attempt — never a crash, never a silent accept:
   (a) **verified-accept** — row persisted (new) or updated (existing) with `verified_at` set,
   judgment shown on the row; (b) **verified-reject** — visible reasons, nothing persisted (an
   existing row is removed and the message says so); (c) **unavailable** — the fetch/extract/
   transcript failed, so the app asks the user to retry, discard, or keep it permanently badged
   `unverified` (`verified_at` stays NULL, verdict `unverified` — never a fabricated keep/skip).
3. A source attaches to exactly ONE scope: a Topic OR the Course as a whole
   (`sources.topic_id` / `sources.course_id`, app-layer rule, `topic_id` now nullable).
4. Rows that predate verification (`verified_at` NULL) become verified per-row, on demand, via
   the Verify-now action — never a silent bulk re-fetch.
5. Boundary rule (same shape as `app/ai/`): routes own the fetch, roles own the judgment; no
   network I/O is constructed inside roles or templates, and the model is never handed a URL to
   fetch itself.
**Implemented:** `app/fetching/` (`http.py`, `extract.py`, `youtube.py`), 
`app/roles/prompts/librarian_verify.md`, `librarian.verify()`, rewritten `app/routes/librarian.py`
(4 POST routes + Shelf), `sources.course_id` / `sources.verified_at` (schema + idempotent
`db._migrate()`), templates `librarian_unavailable.html` / `librarian_verdict.html` /
`_sources.html`. Full suite 215 passed (2026-09-14).
**Consequences:** The Phase 3 statement that the Librarian never fetches anything no longer holds
— see the "Superseded" note on D-011. Cost per added/re-verified source is one fetch + one LLM
call (the text is truncated by code in `app.fetching`, never by a summarizing LLM call). An
unreadable source is a first-class, user-visible outcome rather than an error page.
`roles/librarian.py` and `routes/librarian.py` cite THIS entry.

---
### D-023 — Group timeframe pre-fills the Advisor sequencing answer (pre-fill, not skip; text only)
**Date:** 2026-09-14 (Stage 3 Task 5; owner decision baked in per Stage 2 recommendation)
**Context:** Owner wanted properties defined on a Group to become defaults for courses
created inside it. The only group property that is answer-shaped is `timeframe_duration`
on `uniform` groups. Two boundary crossings were reviewed in Stage 2: (a) pre-fill vs.
hard-skip of the sequencing question, (b) display-only status of the duration.
**Decision:**
1. PRE-FILL, not skip: the sequencing question stays visible with the group's
   duration filled in as the answer, plus a visible hint ("Pre-filled from
   {group name}'s timeframe — edit as needed."). The deterministic five-step
   interview contract, `next_step`, and `save_answer` are untouched.
2. Text inheritance only: the duration is free text flowing through the
   existing form → save_answer path. No new columns, no duration arithmetic,
   no scheduling/week-math of any kind (numeric `time_box` stays out of scope).
3. Guard: pre-fill applies ONLY to an empty step — an already-answered step
   always shows the user's own answer (back-button edits included).
**Implemented:** `group_store.uniform_timeframe_of_course()` +
`Advisor "Create inside a group" <select>` (only rendered when the account
has ≥1 group) + `render_step` pre-fill logic + visible hint in
`advisor_step.html`. `group_store.py` docstring amended (no longer claims
pure display-only). Owner note: hard-skip was explicitly rejected — it buys
almost nothing and hides inherited context from the user.
**Consequences:** Courses created inside a uniform group start from the
group's stated timeframe; editing before submitting persists the edited
value. Scheduling math remains out of scope until a numeric-`time_box`
parent decision is made.

---

### D-022 — Course Groups / Semesters architecture & multi-course insights choices
**Date:** 2026-09-13 (Phase 11 planning; approved by owner)
**Context:** The owner approved coupling courses into Groups (e.g. "Semester 1",
"Systems Track") to allow cohort organization, shared timeframe pacing, and
cross-course Roommate synthesis. Two key design decisions required owner choice:
(1) what happens to courses when a group is deleted, and (2) group timeframe mode
default.
**Decision:**
1. Group deletion follows Option B: offer the user an explicit choice between
   "Ungroup courses" (preserves courses, sets `group_id = NULL`) and "Delete group
   and all its courses" (cascades delete across all grouped courses), displaying
   clear consequence warnings for both options.
2. Group timeframe follows Option A: default to individual course pacing
   (courses set their own time boxes), with an optional toggle for uniform semester
   duration (e.g., "12 weeks") across all courses in the group.
**Consequences:** Evolving the schema with a `course_groups` table and a `group_id`
column on `courses`. Enables intra-group cross-course synthesis in Roommate (P5).
**Implemented (same day, Phase 11 session):** all of the above shipped —
`group_store.py` / `routes/groups.py` / `templates/groups.html` / `db.py`
migration / `roommate_intra.md`; `delete_course` also nulls other courses'
`secondary_course_id` so intra-group bridges never dangle. Full suite
160 passed.

---

### D-021 — Course Deletion & Universal 3-Dots Context Menu
**Date:** 2026-09-13 (Phase 10; owner-requested for cleaning test/fake courses)
**Context:** User validated early workflows with fake/test courses; now desires to
clear clutter and delete courses permanently. Deletion must adhere to P7 (agency),
P6 (durability), and P8 (simple, explicit SQL over implicit magic). Deleting a course
must cascade cleanly across all 8 dependent child tables (topics, librarian sources,
tutor sessions, tutor turns, editor reviews, advisor interviews, roommate prompts,
and activity log) so no dangling/orphaned rows or phantom streaks remain.
**Decision:**
1. Atomic cascading deletion implemented via `delete_course(course_id)` in
   `app/roles/course_manage.py` and routed at `POST /courses/{course_id}/delete`.
2. UI interaction pattern: every course in the persistent sidebar and dashboard
   carries an accessible 3-dots (`⋮`) context menu with "Open course" and "Delete course".
   The course details page (`course.html`) also provides an explicit "Delete course" action.
3. Consequence Warning Modal: native `<dialog id="delete-course-modal">` in `base.html`
   styled with Reading Room design tokens (`--paper-card`, `--danger`). Lists all
   consequences explicitly (all topics, sources, sessions, reviews, prompts, streaks wiped).
   Cancel closes with zero side effects; confirm submits `POST /courses/{id}/delete`.
4. Dependent systems adapt: Roommate `latest_prompt()` falls back seamlessly to the
   next active course prompt (or None); dashboard recalculates active counts and streaks;
   direct URL visits return friendly 404s.
**Consequences:** 134 → 139 passing tests (all 5 new tests pass; 100% full-suite pass rate).
Clean, modern contextual control across all course touchpoints.

---

### D-020 — The "start a new course" entry point existed only as a URL; restored as dashboard button + nav link
**Date:** 2026-09-13 (Phase 8; owner-reported "I can't see where to start a new course")
**Context:** The full Phase-1 Advisor flow (topic form → five-step interview →
draft review → confirm → Course) was built, tested, and routed — but no
template linked to `/advisor/new`. The dashboard empty state even said
"create your first course above" with nothing above it, and `systemPatterns.md`
claimed a "Start button links to /advisor/new" that wasn't in `index.html`.
Likely lost/never landed during incremental template edits; no test guarded
the link, so nothing caught it.
**Decision:** Entry point lives in TWO places, per owner's choice: a prominent
"Start a new course" button on the dashboard (visible whether or not courses
exist) and a "New course" link in the base nav. Guarded by
`tests/test_dashboard.py::test_dashboard_shows_start_new_course_entry_point`
(dashboard empty + populated + every nav page). Empty-state wording updated to
point at the button.
**Consequences:** Lesson, not just a fix: any UI entry point a test doesn't
assert can silently vanish between sessions. When adding a nav link or
dashboard control, extend the regression test in the same change. Docs that
describe UI must be verified against the template, not memory.

---

### D-019 — `import app.routes.advisor_review` at the bottom of main.py clobbered the `app` alias
**Date:** 2026-09-13 (Phase 8; owner-reported 500 on every request from `uvicorn app.main:app`)
**Context:** The D-018 completion pass moved the advisor_review side-effect
import to the bottom of `app/main.py`, after the `app = api` backwards-
compatibility alias (D-008). Python's `import a.b.c` binds the top-level name
`a` in the importing module, so that import rebound the module-global `app`
from the FastAPI instance to the `app` package MODULE. uvicorn then resolved
`app.main:app` to a module, classified it ASGI2, and every request 500'd with
"TypeError: 'module' object is not callable" (plus "lifespan appears
unsupported"). When the same import lived at the top of the file, line 58's
`app = api` executed afterwards and re-bound `app` correctly — which masked the
hazard until the import moved below the alias. Verified empirically:
`type(app.main.app)` was `<class 'module'>` before the fix.
**Decision:** Keep the `app = api` alias; make the bottom-of-file side-effect
import a `from`-import (`from app.routes import advisor_review`) with a comment
explaining the rebinding trap. Verified after the fix: `type(app.main.app)` is
FastAPI, `uvicorn app.main:app` boots and serves `/` → 200, full suite
132 passed (2026-09-13).
**Consequences:** Rule: in `app/main.py`, never use a top-level `import app…`
statement below the `app = api` alias; side-effect imports must use the
`from`-form. Environment note from the same report: the owner launched the
GLOBAL Python 3.14 uvicorn (traceback paths under
`Python314\Lib\site-packages`), not the project `.venv` — prefer
`.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` so the venv's
dependency set is what actually runs.

---

### D-018 — Phase 7 completion pass: finish the three half-built items (no shortcuts)
**Date:** 2026-09-13 (owner-authorized; Phase 7 was marked Done prematurely)
**Context:** Phase 7's record claimed four items, but recon showed three were
half-built: (1) the Settings page read a bogus `OPENROUTER_API_KEY` (always
"(not set)"), never loaded `.env`, wrote cadence only to `os.environ` (lost on
restart), and left the documented "per-Course pause defaults" step as a "Coming in
a future phase" placeholder; (2) `docs/06-MONITORING.md` promised `data/app.log`
error logging that existed nowhere; (3) backup/restore was documented but never
mechanically proven (Phase 7 DoD's "restored successfully" half). Related drift:
`techContext.md` promised key switching in Settings (read-only is the honest
shape — key rotation stays a `.env` edit), the weekly ritual's "check the backup
timestamp" had no timestamp to check, and two `.clinerules`-era references to a
deleted PHASE-7-VERIFICATION.md file dangled.
**Decision:** Finish all three properly before Phase 8: (1) masked key via
`load_config()` (SAME `AI_API_KEY` the provider reads) + `write_env_value`
(line-preserving `.env` writes, creates a missing `.env`) for cadence (validated
≥ 1 day) and the pause default as a real checkbox honored by
`confirm_curriculum` (`active`, or `paused` when on) + Settings link in base nav;
(2) new `app/monitor.py` (stdlib logging → `data/app.log`, idempotent per
DATA_DIR) wired into lifespan, dashboard background-thread catch-all, per-course
Roommate failures, provider final-retry, and an unhandled-exception middleware;
(3) `tests/test_backup_restore.py` (copy live DB → fresh dir → rows intact,
`init_db` a no-op) + `/settings` backup-staleness note (DB path + newest
`data/university.db.backup-*` + age via `roommate_store.last_backup_info`).
Backing tests: `tests/test_settings.py` (10), `tests/test_monitoring.py` (2),
`tests/test_regression_loop.py` (1 full ALTER loop, docs/05 items 1–7 automated),
plus a conftest guard resetting the two settings env keys per test (POST
/settings writes `os.environ` for real) and `sqlite3.Row` fixes. Git init stays a
Phase 8 step (BUILD-PLAN step 4) per the owner's call.
**Consequences:** 118 → 130 passing. Settings, logging, and backup now match
their docs; the regression loop is a re-runnable fact, not a hand-wave.

---

### D-017 — Test isolation fix: explicit _dash_visits cleanup between tests
**Date:** 2026-09-12 (Phase 7 slice 1, bug fix)
**Context:** The badge-clearing test `test_durable_indicator_clears_after_refresh` failed
when run as part of the full test suite, but passed in isolation. Root cause: the `_dash_visits`
table (single-row visit timestamp tracker) was persisting across test boundaries due to
the slow background thread in `test_dashboard_does_not_block_on_generation` (0.5s simulated
delay, 0.2s join timeout). Although the thread was pinned to its original DATA_DIR, the
visit timestamp from a prior test would remain in the *shared OS-level SQLite connection
state* even after monkeypatch environment cleanup, causing the next test to see stale badge
states.
**Decision:** Add an autouse pytest fixture in test_roommate_routes.py that clears
`_dash_visits` after each test (not before, so cleanup doesn't affect later tests or the
test setup itself). The DELETE is wrapped in try/except to handle cross-test database
transitions gracefully.
**Consequences:** All 118 tests now pass reliably in any order. Badge state isolation is
guaranteed between tests even if background threads outlive test cleanup.

---

### D-016 — Non-blocking dashboard generation + durable "new since your last visit" badge
**Date:** 2026-09-12 (Phase 7 slice 1)
**Context:** The dashboard route had drifted — several sessions of
incremental edits had left multiple stacked copies of `def index` and
`APIRouter()` in `app/routes/dashboard.py` (the LAST def won at runtime,
suppressing the others). Two real product problems hid underneath:
(1) Phase 6 ran the roommate due-check synchronously inside GET /, so a
slow/dead provider could hold the page hostage; (2) the "Fresh
connection" block showed the newest prompt but gave no durable way to
notice a prompt that appeared AFTER the last render. Also, timestamp
precision was inconsistent (SQLite prompt rows at second precision,
visit rows at millisecond precision), which silently broke the
`prompt.created_at > visit` badge comparison within the same second.
**Decision:** (1) `app/routes/dashboard.py` is one clean route. (2) The
due-check runs in a daemon thread joined ≤0.2s — a fast provider's
prompt renders on the same load; a slow provider still gets the page
back in well under 0.4s (B3 verified). (3) NEW dashboard visits are
baseline-anchored: `dash_visit_at()` is read BEFORE the render's visit
is recorded, `record_dash_visit()` and `touch_visit()` stamp
millisecond UTC, and `save_prompt` defaults to millisecond UTC too —
so a prompt created after the last visit always compares strictly
greater. `days_since` strips fractional seconds so legacy
second-precision rows still parse. (4) The background thread PINS
DATA_DIR to the request's value for its whole pass and only restores
it if nobody changed it meanwhile — a slow leftover thread can never
write into the next test's database (this leaked one 'slow' test
prompt into the real `data/university.db` before the fix; that row was
scrubbed). (5) Tests updated to drive generation with a usable reply,
backdate prompts explicitly for due-checks, and assert badge
show/clear semantics; a duplicated dead copy of the slow-provider test
was deleted.
**Consequences:** 109 → 118 passing. GET / is fast and never blocks on
the provider; "New connection — refresh to see" is durable but
self-clearing (a refresh moves the baseline). Real DB was returned to
exactly its pre-session state (one leaked row removed).

---

### D-015 — Route 3 (owner-approved): activity_log gains course_id + is_user; honest entity types; dashboard query now 2 lines
**Date:** 2026-09-11 (post-Phase 6, pre-Phase 7)
**Context:** Tutor (Phase 4) activity rows were invisible to
`last_activity_for_course`, so a course being actively tutored showed a
stale "days since activity" — the dashboard's core dropout signal lied
exactly when the user was most engaged. Phase 5's Editor had dodged the
same bug by logging under entity_type 'topic' (a dashboard routing key,
not an honest type) per D-013; both were recorded under "Noticed".
Phase 7's streak/activity indicators would have been built on the same
brittle whitelist OR-chain.
**Decision:** (1) activity_log gains `course_id` (the owning Course,
denormalized) and `is_user` (1 = real user engagement; 0 = system rows
such as Roommate generation or failed checks). db._migrate ALTERs the
columns in, then idempotently backfills every legacy row through the
existing entity relations (course/interview → self; topic → its course,
disambiguated against sources and editor_reviews; tutor_session → its
topic's course; roommate generated → its prompt's course; failed → self),
and creates the course_id index THERE — not in schema.sql, because on an
old DB a schema-level index would reference a not-yet-existing column
and break boot (caught by a migration regression test). (2) Every store
now passes its honest entity_type/entity_id plus course_id
(source/editor_review/tutor_session/roommate/course/topic/interview) —
the Editor stops borrowing 'topic'. log() is now
`log(course_id, entity_type, entity_id, action, is_user=True)`.
(3) `last_activity_for_course` collapses to
`SELECT MAX(created_at) WHERE course_id = ? AND is_user = 1`; the 3-arm
whitelist OR-chain is gone and a future module cannot forget a type.
(4) Roommate behavior is unchanged: generation stays excluded
(is_user=0), reactions count (is_user=1).
**Consequences:** One idempotent migration; 13 log() call sites updated
mechanically; only two pre-existing tests assert on activity_log rows
and both still pass; new tests prove old-DB upgrade + backfill, a tutor
answer refreshing the clock, and system rows never refreshing it.
Suite 104 → 109. Phase 7's streak now builds on a truthful base.

---
**Date:** 2026-09-11 (Phase 6 build)
**Context:** Phase 6 needs cadence cross-domain prompts per active
Course, a due-check on dashboard load, and an Insights journal. The
`roommate_prompts` table existed since Phase 0 but had no place for the
"which unrelated field" label, and "latest unread prompt" on the
dashboard was ambiguous (no read-state exists in the schema).
**Decision:** (1) The LLM returns {"field", "prompt"} (field ≤ 40,
prompt ≤ 500 chars); "field" gets a new `field TEXT` column —
`schema.sql` for fresh DBs + one idempotent ALTER in `db._migrate` (the
Phase 1c time_box precedent). The journal shows the field label, and
each generation is sent the last 8 fields so repeats are both prompted
away and rejected post-parse ("roommate field already used"). (2) The
due-check runs synchronously on GET / (build-plan step 2 — no job
scheduler): only status='active' courses; due when never prompted or
`days_since(last_prompt) >= cadence` (default 3 days,
`ROOMMATE_CADENCE_DAYS`, min 1); most-overdue first so a long gap gets
refilled. Generation failures are caught per course, logged as
entity_type 'roommate' action 'generate_failed' (never inflates a
course's days-since-activity), and the dashboard always renders. (3)
Dashboard display (owner chose Option A): one compact "Fresh connection"
block showing the newest prompt across ACTIVE courses — no read-state
machinery; docs/06 updated to match. (4) The journal (`/roommate`) never
calls the LLM — passive history; reaction POSTs
(`/roommate/prompts/{id}/reaction`) log as entity_type 'course' so real
user engagement counts. (5) Orchestration lives in
`roles/roommate.generate_due_prompts(provider)` (the role composes with
its own store, per 02-ARCHITECTURE "the role writes its own persisted
output"), keeping the dashboard route to a one-line call.
**Consequences:** One idempotent migration. Generation casts a
synchronous LLM call on GET / (per the build plan; a down endpoint
fails fast and the page still renders). `tests/conftest.py` adds an
autouse fixture so the 71 pre-existing dashboard tests stay network-free
without edits.

---
**Date:** 2026-09-11 (Phase 5 build)
**Context:** Phase 5 needs (a) structured review of real user output
against a milestone and (b) topic-done gated on a review being on
record. The gate could live in `course_manage.set_topic_status` (data
layer) or in `routes/courses.py` (its only caller). The
`editor_reviews` table has existed since Phase 0 — no schema change.
**Decision:** (1) Gate enforced in `routes/courses.py`: `status=done`
is blocked with an inline message and unchanged DB state when
`has_editor_review()` is False; reopen stays ungated; topics already
done before Phase 5 are not retroactively re-gated.
`set_topic_status`'s contract is unchanged. (2) The Editor prompt
returns {"strengths", "biggest_weakness", "next_edit"}; parse
validation enforces all three non-empty with caps (450/300/300 chars)
— structurally guarantees "exactly one weakness + one concrete next
edit", per the build-plan constraint. (3) On provider/parse failure
the submission is re-rendered pre-filled in the textarea and nothing
is written (same nothing-half-written rule as Librarian/Tutor);
submissions over 8000 chars are rejected before any LLM call.
(4) Review activity is logged with entity_type 'topic' so the
dashboard's days-since-activity counts it (tutor_session rows do NOT
count today — recorded under "Noticed", not fixed). (5) Per the
owner's decision during design review, the dashboard also surfaces
`last_review_note` (the "last Editor note" from docs/01-VISION), even
though the build plan's Phase 5 steps didn't require it.
**Consequences:** If a second caller of `set_topic_status` ever
appears, the gate must move or be duplicated there. Manual
topic-done is gone; every future done-marking needs a review.

---
### D-012 — Phase 4: one open session per topic; gap note stays short text
**Date:** 2026-09-11 (Phase 4 build)
**Context:** Tutor needs resume-after-close without orphan sessions, and
the dashboard needs a compact "last gap" signal. Alternatives: allow
parallel open sessions, or store a structured gap (weakness + next step
as separate columns).
**Decision:** (1) One open session per topic — POST /tutor/start
redirects to the existing open session instead of creating a second.
(2) Gap note stays a single 1–3 sentence TEXT (same column, no schema
change); follow-up adaptation lives in the next question itself, not a
separate per-turn feedback column. (3) Same error discipline as
Advisor/Librarian: retry once on malformed JSON; start failure deletes
the empty session; answer/end failures keep the session open with saved
work intact. (4) Dashboard adds last_gap_note per course (newest
non-empty gap across its topics).
**Consequences:** No migration needed (tutor_* tables existed since
Phase 0). If parallel sessions or structured gaps are ever wanted,
that's a new decision entry.

---
### D-011 — Phase 3: one LLM triage call per source; good_for folded into reason
**Superseded twice: first for the live add-a-source path by D-024 (Stage 3 Task 7,
2026-09-14), then fully RETIRED by D-025 (2026-09-16, owner option (a)):**
`triage()` + `_parse_verdict()` + `SourceVerdict` + `PROMPT_FILE` +
`prompts/librarian.md` + the 3 triage tests are deleted. The live contract is
D-024 + D-025; the verdict vocabulary (`VERDICTS`) lives on in
`app/roles/source_store.py` for stored rows only.
**Date:** 2026-09-11 (Phase 3 build)
**Context:** The vision wants per-source what-it's-good-for + verdict +
one-line reason, but the schema has sources(reason) and no good_for
column. The build plan says judge from description + URL/domain, no
web fetching.
**Decision:** (1) The LLM returns {verdict, good_for, reason}; the route
persists reason as "Good for X. Y" in the existing reason column — no
schema change. (2) Skip rows are kept and rendered dimmed, never
deleted. (3) Same error discipline as Advisor: retry once on malformed
JSON; provider errors render inline with nothing half-written.
**Consequences:** Shelf = keep-only filter over the same table. If
good_for ever needs its own column, migrate then.

---

### D-010 — Phase 2: dashboard lists non-draft courses; current = first not-done topic
**Date:** 2026-09-11 (Phase 2 build)
**Context:** The build plan asks for active Courses + current Topic +
days-since-activity on GET /, plus a topic detail page, pause/archive/
resume, manual topic-done, and ActivityLog writes.
**Decision:** (1) Dashboard lists every non-draft course (active/paused/
archived/done), newest first; drafts stay invisible until confirmed.
(2) Current topic = first topic whose status != 'done' in order_index
order, with done/total counts alongside. (3) Topic page shows milestone
+ explicit "Empty until Phase 3/4/5" placeholders (no fake data).
(4) Manual topic-done toggle is labelled as manual in the UI; Phase 5
will gate it behind an Editor review. (5) New writes (interview start/
answer, confirm, status changes) append to activity_log; dashboard shows
days-since-last-activity with fallback to courses.created_at.
**Consequences:** Resume pointer moves automatically as topics are marked
done. ActivityLog is write-only from here on; later phases just log.

---

### D-009 — Phase 1c: register courses router; /confirm is async; land on course page
**Date:** 2026-09-10 (Phase 1c build)
**Context:** 1c was scaffolded in the 1b session (`course_store.py`,
`/confirm` POST, `courses.py`, `course.html`), but nothing had ever exercised
it — `main.py` never registered the courses router (the post-confirm
redirect target `/courses/{id}` would have 404'd), and `/confirm` called
`request.form()` synchronously, which in the installed Starlette is async
(`AwaitableOrContextManagerWrapper`, not iterable) so the POST would have
raised. The owner's recorded "open question" (land on a course page vs.
return to the dashboard) had never been answered; the scaffold has always
labeled the course page as "what the user lands on after confirming."
**Decision:** (1) `main.py` now registers `courses_router`. (2) `/confirm` is
now `async def` and uses `await request.form()`. (3) After confirming, the
user lands on the minimal course page `/courses/{id}` (dashboard listing is
Phase 2). (4) Validation failures (blank course title / no complete topic)
re-render the review page from the values in the POST — no extra LLM call, no
typed text lost, all edit boxes preserved. Verified by 9 new tests
(`tests/test_course_confirm.py`).
**Consequences:** Course creation is now a tested path end to end. If the
owner prefers dashboard-landing, the redirect target is a one-line change.

---

### D-005 — Phase 0: stdlib-only .env parsing, no python-dotenv
**Date:** 2026-09-09 (Phase 0 build)
**Context:** `app/ai/config.py` needs to read `.env` for provider/key/model.
**Decision:** Tiny KEY=VALUE parser in the standard library instead of adding a
python-dotenv dependency — one fewer package for the weak-model build to manage.
**Consequences:** No quoted/multiline value support; fine for the five flat vars in
`.env.example`. Revisit if config grows complex.

---

### D-006 — Runtime LLM: OpenAI-compatible pluggable provider, OpenRouter-free default, user-switchable
**Date:** 2026-09-09 (Phase 0 close-out, per owner answer)
**Context:** Owner wants: start on a free model, but any user can later switch
free ↔ paid or paste their own key/model without code changes.
**Decision:** Keep the single adapter (`app/ai/provider.py`) speaking OpenAI-compatible
chat-completions against four settings (`AI_PROVIDER/AI_BASE_URL/AI_MODEL/AI_API_KEY`,
`.env` now, Settings page from Phase 7). Ship `.env.example` defaulting to
`https://openrouter.ai/api/v1` + a `:free` model so the app runs free out of the box;
document that paid or self-hosted (e.g. Ollama's OpenAI-compatible endpoint) just means
changing those values. Phase 1 wires the real HTTP call behind this interface.
**Consequences:** No provider SDK dependency; free-model names drift, so the exact
default `:free` model string may need refreshing; Settings page (Phase 7) must expose
model + masked key + base URL, not just cadence.

---

### D-007 — Free model slugs churn: verify against /models, surface API error bodies
**Date:** 2026-09-10 (Phase 1a smoke test)
**Context:** `deepseek/deepseek-chat:free` returned 404 with body "unavailable
for free … use deepseek/deepseek-chat (paid) instead". The bare 404 hid this.
**Decision:** (1) Default model is now `cohere/north-mini-code:free`,
verified with a real 200 + completion against the owner's key the same day
(replacing two dead defaults: deepseek retired, gemma upstream-429). Refresh via
`scripts/list_free_models.py` + verify with `scripts/try_model.py <slug>`
before shipping a new default. (2) `ProviderError`
now includes the first 300 chars of the API's error body so the next dead slug
is diagnosable without a diagnostic script.
**Consequences:** Default `:free` slug may need refreshing every few months —
treat "smoke test 404s" as "pick a new free slug", not as an app bug.

---

### D-008 — FastAPI instance is `api`, not `app` (shadowing trap)
**Date:** 2026-09-10 (Phase 1b build)
**Context:** `C:\Projects\` (the workspace root's parent) contains an installed
`app` package. With pytest's rootdir-based sys.path, `from app.main import app`
bound the shadowing MODULE (`<module 'app' from ...\app\__init__.py>`) instead
of the FastAPI instance — TestClient then failed with "TypeError: 'module'
object is not callable". Confirmed via debug print of type/repr/path.
**Decision:** The instance in `app/main.py` is named `api`; `app = api` stays
as a backwards-compatible alias for `uvicorn app.main:app`. All in-repo imports
and tests use `api`.
**Consequences:** Run uvicorn as `uvicorn app.main:api` (or `:app`, both work).
If the shadowing `C:\Projects\app\` ever disappears, the alias still works —
no reason to rename back.

### D-001 — Stack: FastAPI + SQLite + server-rendered HTML/HTMX, no build pipeline
**Date:** Project planning (pre-Phase 0)
**Context:** Needed a stack a small/free coding model (GLM-Flash-5.3 / DeepSeek V4) can
build reliably over a long period, for a single-user, long-lived, local-first app.
**Decision:** Boring, explicit, no-build-step stack over a full SPA framework or a
microservice split. See `docs/02-ARCHITECTURE.md` for full rationale.
**Consequences:** Faster, more reliable builds by a weak model; frontend interactivity is
more limited than a full SPA — acceptable for this app's needs (forms, lists, simple
question/answer flows). Revisit only if a specific UI need genuinely can't be done this way.

### D-002 — AI provider is pluggable and decoupled from the Cline coding models
**Date:** Project planning (pre-Phase 0)
**Context:** The project owner builds this app inside Cline using GLM-Flash-5.3 / DeepSeek
V4 as coding assistants. That is a separate concern from which LLM API the *running app*
calls for its Advisor/Librarian/Tutor/Editor/Roommate features.
**Decision:** One adapter interface (`app/ai/provider.py`) behind all five role modules;
provider/model/key configured via `.env`, chosen independently.
**Consequences:** The specific runtime provider is still an open question — see
`memory-bank/techContext.md` "Open technical questions." Must be resolved before Phase 1
can make real (non-stub) calls.

### D-003 — Five ALTER roles are separate persisted modules, not one chat interface
**Date:** Project planning (pre-Phase 0)
**Context:** The source material describes five distinct roles with distinct behavioral
contracts (interview vs. curation vs. Socratic questioning vs. critique vs. cross-domain
prompting). A single generic chat box would blur these and lose the structure that makes
each one useful.
**Decision:** Each role is its own module, own prompt file, own data tables, own routes —
see `docs/02-ARCHITECTURE.md` "AI role implementation pattern."
**Consequences:** More upfront structure than a single chat feature; in exchange, each
role's output is durable, inspectable, and independently improvable.

### D-004 — Local-first, single-user, no auth/multi-tenant system
**Date:** Project planning (pre-Phase 0)
**Context:** Built for the project owner's own daily/long-term use, not for distribution.
**Decision:** No auth system, no multi-user data model, no hosting/deployment concerns in
scope unless explicitly requested later.
**Consequences:** Much smaller build surface. If multi-user or remote access is ever
wanted, treat it as a new, explicitly-scoped phase — not a quiet extension of the data model.
