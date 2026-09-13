# Active Context

**Update this file at the end of every session, without exception. This is the first file
any coding-agent session should read — it should be enough, on its own, to know exactly
where the project stands and what to do next.**

## Current state
**2026-09-13 (Phase 11 Course Groups / Semesters session): COMPLETED & VERIFIED.**
Full suite: **160 passed, 2 warnings in 22.66s** (21 new tests in
`tests/test_groups.py`; 100% pass rate, zero regressions). What was built:
1. **Schema** (`app/schema.sql` + `app/db.py::_migrate()`): `course_groups`
   table (name, description, `timeframe_mode` 'individual'|'uniform',
   `timeframe_duration`, `status`), `courses.group_id` (NULL = ungrouped),
   and `roommate_prompts.secondary_course_id` + `connection_type`
   ('external'|'intra_group') — all idempotent, existing DBs evolve on boot.
2. **Data layer** `app/roles/group_store.py`: create/get/list/update groups
   with live progress aggregates; `set_course_group` (validated, logged);
   `delete_group` implementing **D-022 Option B** (`mode='ungroup'` detaches
   courses; `mode='delete_courses'` runs each through the atomic
   `delete_course` cascade); `sidebar_groups()` for collapsible nav.
3. **Routes** `app/routes/groups.py` + **page** `templates/groups.html`:
   `GET /groups` manage page (create with optional course filing, edit,
   delete with the Option-B choice form), plus
   `POST /courses/{course_id}/group` reachable from every 3-dots menu and
   the course page (safe same-site `next` redirect).
4. **UI**: sidebar renders collapsible group folders with per-course
   progress (dashboard/index filters by group); course page shows + changes
   group membership; Reading Room tokens throughout (`style.css` additions).
5. **Roommate intra-group synthesis (P5)**: `app/roles/roommate.py` +
   `app/roles/prompts/roommate_intra.md` generate topic-to-topic bridge
   prompts between two active courses sharing a group, journaled and
   reactive like external prompts; `delete_course` nulls dangling
   `secondary_course_id` references.
6. Owner design calls (D-022): group deletion = Option B (explicit choice);
   timeframe default = Option A ('individual' pacing, optional 'uniform').

**2026-09-13 (Phase 10 Course Deletion & Context Menus session): COMPLETED & VERIFIED.**
All requirements for course deletion and contextual actions have been executed and tested:
1. **Atomic Cascading Deletion**: Implemented `delete_course(course_id)` in `app/roles/course_manage.py` running an atomic transaction across all 8 related tables (`topics`, `sources`, `tutor_sessions`, `tutor_turns`, `editor_reviews`, `advisor_interviews`, `roommate_prompts`, and `activity_log`) ensuring zero orphaned rows.
2. **Deletion Endpoint**: Handled via `POST /courses/{course_id}/delete` in `app/routes/courses.py` with safe HTTP 303 redirect to `/`.
3. **Universal 3-Dots Menu (`⋮`)**: Integrated on every course row in the persistent sidebar (`base.html`) and dashboard (`index.html`), allowing fast access to "Open course" and "Delete course".
4. **Consequences Warning Modal**: Accessible `<dialog id="delete-course-modal">` in `base.html` styled with Reading Room tokens (`--paper-card`, `--danger`), explicitly enumerating all consequences with Cancel (zero side-effect) and Confirm Delete buttons.
5. **Course Page Delete Action**: Added explicit "Delete course" action button on `/courses/{id}`.
6. **State & Dependent System Adaptation**: Roommate `latest_prompt()` cleanly falls back to remaining active courses (or None); dashboard recalculates active counts and streak days; direct URLs return friendly 404 pages.
7. **Test Suite**: **139 passed, 2 warnings in 21.83s** (5 new unit & integration tests covering cascade, routes, fallback, and UI elements; 100% pass rate).

Phase 9 (Frontend Redesign session): **FULL REDESIGN COMPLETED & VERIFIED (Direction A — The Reading Room).**

Phase 8 is **DONE (2026-09-12, prior session)**. Final steps, in order:
1. The owner manually walked the entire frontend and confirmed every workflow
   matches progress.md — recorded in progress.md's "Full-loop walkthrough result".
2. Final pre-commit full-suite run: **133 passed, 2 warnings in 15.18s**
   (detached Start-Process run; the known load-flake passed this time).
3. DONE: git init + initial commit **"v0.5: The initial application"**
   (99 files, 8,501 insertions; message per owner instruction — the owner's
   original text had a typo, corrected by amend + force-push to the private
   GitHub remote). Verified per BUILD-PLAN Phase 8 step 4: `git status`
   clean, commit in log, no `.env`/`*.db`/`.venv/`/logs/backups/owner-scratch
   tracked.
   `.gitignore` hardened this session: added `data/university.db.backup-*`
   and the owner scratch notes `.free_models.txt` / `.piplist.txt` (kept
   untracked, not deleted). Three leftover test-output junk files deleted
   (`fulltest_output.txt`, `full_after_fix.txt`, `verify_fix.txt`).
Remote: https://github.com/zoabboaz729-cyber/university-in-a-box.git (private),
branch `master`, in sync. Author identity is repo-local: Zoab Boaz
<309829610+zoabboaz729-cyber@users.noreply.github.com> — the GitHub noreply
form is used deliberately so the repo can be made public later without
exposing the owner's real email in commit metadata.

### Earlier this session — D-019 boot fix (2026-09-13)
`uvicorn app.main:app` 500'd on every request because the bottom-of-file
`import app.routes.advisor_review` rebound the module-global `app` alias to the
`app` package module. Fixed with a `from`-import + explanatory comment;
verified `GET /` → 200 on a live uvicorn boot and full suite **132 passed**
(suite count is now 132 — two tests beyond the 130 recorded at the D-018 pass;
both runs green). The owner also ran the app with the GLOBAL Python 3.14
uvicorn rather than the `.venv` — see D-019 consequences for the preferred
launch command.

Phase 7 is **DONE via the owner-authorized completion pass (2026-09-13)** — all three
half-built items finished with no shortcuts (see D-018): Settings reads
`AI_API_KEY` + persists cadence/pause-default to `.env`; `data/app.log` error logging
live; backup/restore mechanically proven; `/settings` carries the backup-staleness
note. Full suite: **130 passed** (118 baseline + 12 new; verified 2026-09-13 via
background jobs: 14/14 new-slice tests, then the full 130).

**Remaining before Phase 8 is done** (Phase 8 is In progress per progress.md):
1. DONE this session: 14 `pytest_*.txt` junk files deleted from repo root; `.gitignore`
2. DONE 2026-09-12: the owner manually walked through the entire frontend of
   the running app and confirmed every workflow matches what progress.md
   documents (all five ALTER roles + dashboard controls + Settings). The
   "Full-loop walkthrough result" section in progress.md is now filled in.
3. DONE this session (partially): git init + staging — 99 files staged, no
   `.env`/`*.db`/`.venv/`/logs/backups/owner-scratch staged; `.gitignore`
   hardened (DB backup pattern + owner scratch notes). The commit is left
   for the owner (git identity not configured on this machine).
4. DONE this session: final pre-commit full-suite run → 133 passed
   (2 warnings, 15.18s); this file + progress.md closed out.

## Current phase
**Phase 11 is DONE.** Course Groups/Semesters: schema, group CRUD with the
D-022 Option-B deletion choice, timeframe modes (individual default /
uniform display), sidebar group folders + dashboard filters, and
intra-group Roommate synthesis — all implemented and backed by tests
(160 passed; see progress.md Phase 11 row for the component map).

## Next step
No build-plan phase remains. Recommended next actions, in order:
1. **Owner manual walkthrough of the Groups UI** (same as the Phase 8
   ritual): create a group, file courses from the 3-dots menu, toggle
   timeframe mode, delete a group both ways, and check the sidebar/dashboard
   render — then record the result in progress.md's walkthrough section.
2. **Commit Phase 10 + Phase 11** (both are uncommitted on top of
   "v0.5: The initial application"; `git status` currently shows the
   modified core files + new `group_store.py`, `groups.py`, `groups.html`,
   `roommate_intra.md`, `tests/test_groups.py`, `tests/test_course_delete.py`).
3. Propose the next phase by appending to `docs/03-BUILD-PLAN.md`
   ("After Phase 11" section): candidates already on file — multi-topic
   Roommate cross-linking depth, spaced repetition on gap notes,
   export/print of a Course, exam simulation.

8" (e.g. multi-topic Roommate cross-linking, spaced repetition on gap notes,
export/print of a Course).

<!-- Historical: Phase 7 completion pass (D-018) sub-steps: error logging via
app/monitor.py; Settings persistence to .env; NEW_COURSES_START_PAUSED
honored in confirm_curriculum; backup/restore proven. Regression loop
tests/test_regression_loop.py covers docs/05 items 1-7. -->


## Noticed
- NEW (D-020 session): `test_roommate_routes.py::test_dashboard_does_not_block_on_generation`
  is a load flake — it asserts the dashboard renders in < 0.4s while the slow
  provider call takes 0.5s; under full-suite load it measured 0.4067s and
  failed once, then passed alone. If it recurs, widen the threshold or make
  the assertion robust rather than "rerun until green."
- RESOLVED (D-015): tutor_session rows did NOT count toward the
  dashboard's days-since-activity, and Editor reviews were logged as
  'topic' to work around it. activity_log now carries course_id +
  is_user; the whitelist is gone. Keep `last_activity_for_course` on
  course_id + is_user from now on — never re-add entity-type logic.
- RESOLVED this session (D-016): `app/routes/dashboard.py` had multiple
  duplicated route defs stacked from incremental edits; a slow leftover
  background thread could write into whatever DB the process pointed at
  later (leaked test prompts into the real data/university.db once).
  Route is a single clean def; thread pins DATA_DIR; real DB was
  scrubbed of the one leaked row. Lesson: don't leave fire-and-forget
  threads that re-read process env at wake time.
- Terminal wrapper vs. pytest: foreground `run_commands` calls can't observe
  long-running commands (output capture times out even when the command itself
  is fine). The reliable pattern this session: launch pytest via `Start-Job`
  writing to a file, then read the file in a LATER turn (the job object does
  not survive between turns — `Get-Job` won't find it — but the output file
  does). Full suite completes in ~13s when run this way.

## Open questions
- (none)
