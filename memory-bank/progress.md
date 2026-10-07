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
| 9 — Frontend Redesign ("The Reading Room") | Done | 2026-09-13: Implemented full design system (Direction A — The Reading Room): hand-crafted CSS token stylesheet (`app/static/style.css`), self-hosted Google Fonts (`Source Serif 4` + `Inter` woff2 in `app/static/fonts/`), self-hosted `htmx.min.js` (2.0.4), persistent sidebar with live courses list on all pages, animated loading/thinking indicators for LLM calls, dead Bootstrap classes removed, mojibake lightbulb fixed, and Tutor dead-end bug resolved with `POST /tutor/{id}/retry`. Full suite: **134 passed** (100%). |
| 10 — Course Deletion & Context Menus | Done | 2026-09-13: Atomic cascading deletion across all 8 related tables (`delete_course` in `app/roles/course_manage.py`, route `POST /courses/{id}/delete`), universal 3-dots context menu on sidebar and dashboard course cards, consequence warning `<dialog>` modal in `base.html`, explicit Delete button on `/courses/{id}`, Roommate `latest_prompt` fallback, and full test suite: **139 passed** (100%). |
| 11 — Course Groups / Semesters & Multi-Course Insights | Done | 2026-09-13: `course_groups` table + `group_id` on `courses` (idempotent `_migrate()` in `app/db.py`), `app/roles/group_store.py` (create/update/delete with D-022 Option B, assignment, `sidebar_groups()`), `app/routes/groups.py` (`GET /groups`, create/update/delete, `POST /courses/{id}/group` for the 3-dots menu), `templates/groups.html` management page, collapsible group folders in the sidebar + dashboard filters, intra-group Roommate synthesis (`roommate_intra.md` prompt, `secondary_course_id` + `connection_type` on `roommate_prompts`), and `delete_course` nulls secondary references. Full suite: **160 passed** (100%). |
| Stage 3 — Owner roadmap (post-Phase-11, plan-mode) | Implemented + suite-verified (owner walkthrough + commit pending) | All 7 tasks implemented in the working tree on top of the v0.6 commit: (1) ⋮ menu → `_course_menu.html` macro (sb/dash/mnav prefixes); (2) mobile `courses-nav-modal` dialog; (3) group-creation discoverability (sidebar Groups nav, New-group button, empty-state link); (4) adaptive topic count (prompt 4–8/12 + 3–15 parser guard); (5) group timeframe pre-fill into sequencing (D-023); (6) `app/fetching/` (SSRF-safe http/extract/youtube) + `sources.course_id/verified_at` + course-level sources; (7) read-before-accept Librarian (`librarian.verify()` + `librarian_verify.md`, three explicit outcomes). Verified 2026-09-14: `python -m pytest -q` → **215 passed, 2 warnings in 25.56s**; re-verified 2026-09-16 at session start (26.51s) and again after the full docs reconciliation (24.93s) — no behavior change in either re-run (comments/docs only). Docs now match the code: D-024 added + D-011 marked superseded, `docs/02` (data model, outbound-fetching pattern, folder layout, real due-check), a new **Stage 3 section in `docs/03-BUILD-PLAN.md`**, `docs/04` §5 outbound-fetch rule, `docs/07` HTMX amendment. Do NOT mark Done until the owner walkthrough is recorded below and the work is committed. |
| 12 — Multi-Tenant Data Foundation, Dual-DB & Auth | Done | Verified 2026-10-06: repo-wide suite passes `212 passed, 2 warnings in 63.06s`. Multi-tenant identity (`users` table + session auth), `user_id` scoping, dual-engine SQLite-first DB foundation, and legacy single-user compatibility preserved for existing code/tests. |
| 13 — Async Engine, Non-Blocking Fetching & Hybrid/BYOK | Done | Verified 2026-10-06: async-capable provider flow, encrypted BYOK storage/decryption, quota-aware server key resolution, async-compatible fetch wrappers, and route-level async adoption all hold under the live app flow. Final repo-wide verification passed: `python -m pytest -q` → **212 passed, 2 warnings in 43.92s**. |
| 14 — Mobile-First PWA & Touch UX | Done | Verified 2026-10-07: mobile bottom navigation app shell, touch-first ergonomics, `manifest.json`, service worker caching, offline network banner, and keyboard-aware form scrolling are in place; repo-wide verification passed `python -m pytest -q` → **212 passed, 2 warnings in 41.26s**. |
| 15 — Decoupled Scheduler, Roommate & Web Push | Not started | Documented 2026-09-30. Decouple Roommate due-checks to async background scheduler, Web Push notifications for fresh insights and streak nudges. |
| 16 — Data Export, Account Lifecycle & Hardening | Not started | Documented 2026-09-30. One-click full data export (ZIP of JSON/Markdown), atomic GDPR account deletion, Docker multi-stage build, reverse proxy with HTTPS. |

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
  URL/ref) → the source is genuinely READ, then judged → kept verdict +
  a reason grounded in what was read; the list keeps skip rows dimmed and the
  Shelf view filters keep-only; provider/parse errors render inline with
  nothing half-written; each add logs to activity_log; restart-safe.
  **Retired detail (D-025, 2026-09-16, owner option (a)):** Phase 3 originally judged a
  source from its description + URL alone (D-011: `librarian.triage()` +
  `prompts/librarian.md`, one LLM call, no network). That path is now deleted;
  the live path is read-before-accept (`librarian.verify()`), and the verdict
  vocabulary (`VERDICTS`) lives in `app/roles/source_store.py` for stored rows.
- Tests: `python -m pytest -q` → **212 passed, 2 warnings** as of 2026-09-16 post-D-025
  deletion (was 215 with the 3 triage tests; 100% pass rate; the count was 160
  at Phase 11 — 21 of those in `tests/test_groups.py` — and Stage 3 added
  `tests/test_fetching.py` plus read-before-accept Librarian route/unit coverage).
- Phase 10 (Course Deletion & Context Menus): courses can be permanently deleted
  via `POST /courses/{id}/delete` and `delete_course()` in `course_manage.py`.
  Deletion cascades atomically across all 8 related tables (`topics`, `sources`,
  `tutor_sessions`, `tutor_turns`, `editor_reviews`, `advisor_interviews`,
  `roommate_prompts`, and `activity_log`) with zero dangling rows or phantom streaks.
  Every course in the persistent sidebar and dashboard features an accessible
  3-dots (`⋮`) context menu; course page includes an explicit "Delete course"
  action; deletion is guarded by a Reading Room consequence `<dialog>` modal
  warning the user that curriculum topics, librarian shelf, tutor history,
  editor critiques, and insights will be erased; `latest_prompt()` falls back
  seamlessly to remaining courses; direct URLs return friendly 404 pages.
- Phase 11 (Course Groups / Semesters & Multi-Course Insights): a Course Group
  ("Semester 1", a track, a cohort) couples related courses. Schema:
  `course_groups` (name, description, `timeframe_mode` 'individual'|'uniform',
  `timeframe_duration`, `status`) + `courses.group_id` (NULL = ungrouped) —
  added by the idempotent `_migrate()` so existing DBs evolve on next boot.
  Data layer `app/roles/group_store.py` (P8: thin explicit SQL) with live
  progress aggregates (course/topic counts incl. done-topics per group);
  timeframe default is 'individual' (D-022 Option A: each course keeps its
  own per-topic time_box pacing; 'uniform' only displays a shared declared
  duration — no fabricated week-math). Routes `app/routes/groups.py`:
  `GET /groups` management page (`templates/groups.html`) to create groups
  (optionally filing checked courses), edit name/description/timeframe/status,
  move courses, and delete a group with D-022 Option B — an explicit choice
  between "Ungroup courses" (courses preserved, group_id → NULL) and
  "Delete group and all its courses" (each course through the atomic
  `delete_course` cascade, then the group row). Assignment is also reachable
  from every course's 3-dots menu and the course page via
  `POST /courses/{course_id}/group` (validated; logs to activity_log;
  safe same-site `next` redirect). Sidebar renders collapsible group folders
  via `sidebar_groups()` (0-course groups skipped; no groups at all looks
  exactly like pre-Phase 11); dashboard supports group filters
  (`list_dashboard_courses(group_id=…, ungrouped_only=True)`). Roommate (P5)
  gains intra-group synthesis: when two active courses share a group, prompts
  can bridge topic-to-topic across them (`app/roles/prompts/roommate_intra.md`),
  persisted with `secondary_course_id` + `connection_type`
  ('external'|'intra_group') and reactive in the journal like external prompts;
  `delete_course` nulls other courses' `secondary_course_id` references so no
  dangling bridge survives. New tests: `tests/test_groups.py` (21).
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
- **Stage 3 (owner roadmap) is the only open item:** all 7 tasks are implemented, suite-verified
  and now documented, but Stage 3 is deliberately NOT marked Done — the owner UI walkthrough and
  the commit are outstanding (see the Stage 3 row above and `activeContext.md`'s Next step).
  Untracked and not yet committed: `docs/07-FRONTEND-AUDIT.md` and `docs/Frontend-Mockup` (an
  extension-less HTML mockup file).
- **Agent-side pre-flight done 2026-09-16** (on a throwaway copy of the real DB, no LLM calls, no
  writes to real data): every Stage 3 UI affordance renders from the owner's actual data — ⋮ menus
  on sidebar/dashboard/mobile (×18 across 3 call sites), mobile `courses-nav-modal`, `Groups` nav
  link + "New group", the "Create inside a group" Advisor entry point, and the course-level source
  form. Two facts for the walkthrough: the real DB holds **0 source rows** (so the Librarian step
  is a from-scratch add, and the per-row "Verify now" path needs an unreadable source kept as
  `unverified` first), and topic id 1 does not exist (topics are 22–55).
- Beyond that, nothing in the build plan. Future work should be proposed as new phases appended
  to `docs/03-BUILD-PLAN.md` (after its Stage 3 section, per the "After Phase 11" note) — e.g.
  multi-topic Roommate cross-linking, spaced repetition on gap notes, course export, exam
  simulation.

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
  (add-a-source → read-then-judge verdict → keep-only Shelf), Tutor (start/resume a
  one-question-at-a-time session → gap note), Editor (submit work → structured
  review → done-gating until a review exists), Roommate (fresh-connection
  prompt on dashboard load → Insights journal + reactions), plus the dashboard
  status controls (pause/archive/resume), streak display, and the Settings
  page. No discrepancies found — the docs and the running app match.
  (Backup/restore remains mechanically proven by `tests/test_backup_restore.py`;
  the walkthrough covered the UI workflows.)
