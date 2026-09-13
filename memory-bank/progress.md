# Progress

*Ground truth for "what phase are we on" and "what actually works right now." Update at the
end of every session. If this ever disagrees with `docs/03-BUILD-PLAN.md`, this file is
right about current status; fix the disagreement the same session you notice it.*

## Phase status

| Phase | Status | Notes |
|---|---|---|
| 0 — Foundation | Done | Verified 2026-09-09: `python -m pytest -q` → 1 passed; `/` renders; all 10 tables created. |
| 1 — Advisor | Done | 1a (prompt+module+real provider), 1b (interview flow + draft review), 1c (confirm → Course + ordered Topics + `/courses/{id}`). Verified 2026-09-10: 25 tests pass. Optional last check = owner's live-LLM walkthrough (needs `.env` key). |
| 2 — Dashboard & persistence | Done | Verified 2026-09-11: `python -m pytest -q` → 34 passed. GET / lists non-draft courses newest-first with resume pointers; topic page + pause/archive/resume + manual topic-done + ActivityLog. |
| 3 — Librarian | Done | Verified 2026-09-11: 42 tests pass. Add-a-source + keep/skip/later verdict + one-line reason; Shelf filters keep-only; skip rows kept dimmed; restart-safe. |
| 4 — Tutor | Done | Verified 2026-09-11: 54 passed (was 42; +12 new). One-question-at-a-time sessions with milestone+Shelf context, mid-session persistence + resume, gap note on Topic + dashboard. |
| 5 — Editor | Done | Verified 2026-09-11: 71 passed (was 54; +17 new). Submit-for-review on Topic page; strengths / one biggest weakness / one next edit; topic-done gated on a review (server-side); last review note on dashboard; restart-safe. |
| 6 — Roommate | Done | Verified 2026-09-11: 104 passed (was 71; +33 new). Due-check on dashboard load generates one cross-domain prompt per due active course (default 3-day cadence, `ROOMMATE_CADENCE_DAYS`); Fresh connection block on dashboard; Insights journal + optional reactions; per-course failure isolation; restart-safe. |
| 7 — Daily-use polish | Done | Verified by the Phase 7 completion pass (owner-authorized |
| | | 2026-09-13): `python -m pytest -q` → 130 passed. Six items finished: (1) Settings page masked |
| | | key now reads `AI_API_KEY` via `load_config()`; cadence + per-course pause default persist to |
| | | `.env` (line-preserving write, checkbox UI, Settings link in base nav); (2) error logging: |
| | | `app/monitor.py` → `data/app.log`, lifespan hook, dashboard-thread + per-course + provider |
| | | + unhandled-exception coverage; (3) backup/restore mechanically proven (copy → fresh dir → |
| | | rows intact, `tests/test_backup_restore.py`); (4) backup staleness note on `/settings` |
| | | (newest `data/university.db.backup-*` + age; docs/06-MONITORING §A); (5) full-loop regression |
| | | `tests/test_regression_loop.py` (Advisor → Librarian → Tutor → Editor → Roommate + restart + |
| | | streak/settings; docs/05 items 1–7 automated); (6) git step moved to Phase 8 (BUILD-PLAN step 4). |
| | | Also fixed: non-blocking dashboard + durable badge (D-016), test env-leak guard (conftest |
| | | pins ROOMMATE_CADENCE_DAYS + pause-default), `sqlite3.Row` reads. Streak/activity indicator, |
| | | README backup commands, template empty states as before. |
| 8 — Verification & docs finalization | Done | 2026-09-12: owner-verified frontend walkthrough recorded in progress.md; regression loop automated (`tests/test_regression_loop.py`); final pre-commit suite **133 passed** (2 warnings, 15.18s); git init + initial commit **"v0.5: The initial application"** (99 files; clean status; no `.env`/`*.db`/`.venv/` tracked), pushed to the private GitHub remote. |

Status values: `Not started` / `In progress` / `Done` / `Blocked (reason)`.

## What currently works
- Phase 0 skeleton: app boots, `/` renders the dashboard, `data/university.db`
  created with all 10 tables, `.env.example` + stdlib `.env` loader.
- Phase 1 (Advisor), full loop: topic → five-step one-question-at-a-time
  interview with immediate per-answer persistence and restart-safe resume →
  draft curriculum from one real LLM call → review page with per-topic edit
  boxes + Regenerate → confirm → persisted `courses` row (flipped draft→active)
  + ordered `topics` rows (title / milestone / time_box) + untouched
  `advisor_interviews` transcript → `/courses/{id}` course page. Provider,
  parse, and validation errors render inline, never a stack trace.
- Phase 2 (Dashboard): GET / lists every non-draft course newest-first with
  link, status, created date, topics done/total, current (first not-done)
  topic, and days-since-activity; Dashboard nav link on every page;
  pause/archive/resume + manual topic-done persist and
  log to activity_log; restart survival proven by fresh-connection test.
- Phase 3 (Librarian): from a Topic page, add-a-source form (label +
  URL/ref) → one LLM triage call → keep/skip/later verdict + good-for +
  one-line reason persisted to sources; full list keeps skip rows dimmed,
  Shelf view filters keep-only; provider/parse errors render inline with
  nothing half-written; each add logs to activity_log; restart-safe.
- Tests: `python -m pytest -q` → 133 tests as of 2026-09-13 (130 from the
  Phase 7 completion pass + D-019/D-020 additions; one known load-flake
  `test_roommate_routes.py::test_dashboard_does_not_block_on_generation`
  can fail under full-suite load and passes solo).
- Phase 7 completion items:masked API key reads `AI_API_KEY` via
  `load_config()` (regression: it once read a bogus `OPENROUTER_API_KEY` and
  always showed "(not set)"); cadence (validated ≥ 1 day) + per-course pause
  default persist to the repo `.env` via line-preserving `write_env_value`
  (missing `.env` is now created, so a fresh checkout keeps the setting) and
  are honored by `course_store.confirm_curriculum` (new Courses start
  `active`, or `paused` when the default is on); error logging writes to
  `data/app.log` (`app/monitor.py`, idempotent per DATA_DIR, lifespan hook
  + background-thread + per-course + provider-retry + unhandled-exception
  coverage); backup routine mechanically proven (copy live DB → restore into
  a fresh dir → rows intact, `init_db` a no-op); `/settings` shows the DB
  path + newest `data/university.db.backup-*` staleness note
  (docs/06-MONITORING §A).
- Phase 4 (Tutor): from a Topic page, start/resume a Socratic session —
  one question at a time grounded in milestone + keep-only Shelf, each
  answer persisted immediately, end writes a short gap note shown on the
  Topic page and as last-gap on the dashboard; provider/parse errors
  render inline (start writes nothing, answer/end keep session open);
  double-start resumes the open session; restart-safe. Tutor activity
  counts toward the dashboard's days-since-activity (D-015).
- Phase 5 (Editor): from a Topic page, paste/submit work produced
  against the milestone → one LLM review → strengths + exactly one
  biggest weakness + one concrete next edit, persisted to
  editor_reviews and listed newest-first with the original submission;
  "Mark done" is blocked (server-side, with UI hint) until at least
  one review exists; reopen is ungated; dashboard shows the latest
  review note per course; provider/parse errors render inline with
  the submission preserved in the form; restart-safe.
- Phase 6 (Roommate): every dashboard load runs the due-check — for
  each ACTIVE course whose last prompt is missing or older than the
  cadence (default 3 days, `ROOMMATE_CADENCE_DAYS`), one LLM call
  returns {"field", "prompt"} connecting the current topic to a
  genuinely different field (repeat fields are rejected). Prompts
  persist to roommate_prompts with a structured field label; the
  dashboard shows the newest one across active courses as a "Fresh
  connection" block linking to the Insights journal (`/roommate`),
  which lists every prompt newest-first with an optional per-prompt
  reaction. Provider/parse failures skip that course (logged as
  `generate_failed`) and the page still renders; reactions log as
  course activity; pause/archive/draft/done courses never generate;
  restart-safe (migration adds the `field` column to existing DBs).
- Phase 7 (Daily-use polish): dashboard course list displays 
  `streak_days` (consecutive days of user activity ending today, or 0 
  if no activity) via `current_streak()` which walks activity_log 
  backward from today counting is_user=1 rows; template shows 
  "on a N-day streak" when N > 0. Settings page `/settings` displays 
  the DB path, a backup-staleness note (newest
  `data/university.db.backup-*` + age in days), current
  ROOMMATE_CADENCE_DAYS + masked API key, accepts new cadence 
  (validated ≥ 1 day) and the per-course pause default, and persists
  both to the repo `.env` (survives restart). README.md includes
  platform-specific backup commands. All templates 
  (index, course, topic, tutor_session, roommate, advisor_*, error) 
  have appropriate empty state messaging; no stubs or placeholder text 
  exposed to users. The dashboard carries a "Start a new course" button
  and the base nav a "New course" link to `/advisor/new` (D-020 — both
  were missing until 2026-09-13; regression test
  `test_dashboard_shows_start_new_course_entry_point` guards them). Maintenance: removed duplicate roommate_store 
  functions (last_visit_at/touch_visit duplicated dash_visit_at/record_dash_visit), 
  removed dead db.py migration check, updated all test references. 
  Verified by the completion pass: 130 tests pass, all principles verified, no 
  regressions.

## What's left
- Nothing in the build plan — Phase 8 is done and the initial commit is
  pushed to the private GitHub remote. Future work should be proposed as new
  phases appended to `docs/03-BUILD-PLAN.md` per its "After Phase 8" section
  (e.g. multi-topic Roommate cross-linking, spaced repetition on gap notes,
  course export).

## Known issues
- (none blocking — two Starlette/httpx TestClient deprecation warnings
  tracked in activeContext "Noticed". D-015 resolved the tutor-session
  activity-count gap; see decisions.md.)

## Full-loop walkthrough result (filled in during Phase 8)
- Owner-verified manual walkthrough, 2026-09-12: the owner went through the
  entire frontend of the running app by hand and confirmed every workflow the
  application exposes behaves exactly as recorded in "What currently works"
  above — Advisor (start-a-new-course entry point → five-step one-at-a-time
  interview → draft review/edit → confirm → course page), Librarian
  (add-a-source → triage verdict → keep-only Shelf), Tutor (start/resume a
  one-question-at-a-time session → gap note), Editor (submit work → structured
  review → done-gating until a review exists), Roommate (fresh-connection
  prompt on dashboard load → Insights journal + reactions), plus the dashboard
  status controls (pause/archive/resume), streak display, and the Settings
  page. No discrepancies found — the docs and the running app match.
  (Backup/restore remains mechanically proven by `tests/test_backup_restore.py`;
  the walkthrough covered the UI workflows.)
