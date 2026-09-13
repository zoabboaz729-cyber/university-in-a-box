# Active Context

**Update this file at the end of every session, without exception. This is the first file
any coding-agent session should read — it should be enough, on its own, to know exactly
where the project stands and what to do next.**

## Current state
**2026-09-13 (Phase 9 Frontend Redesign session): FULL REDESIGN COMPLETED & VERIFIED.**
All requirements approved in the implementation plan have been executed:
1. **Design System**: Hand-crafted CSS design tokens (`app/static/style.css`) implementing **Direction A — The Reading Room** (warm paper tones, responsive grid, card and pill components, progress bars).
2. **Offline Local-First Fonts**: Self-hosted Google Fonts (`Source Serif 4` and `Inter` woff2 files in `app/static/fonts/`).
3. **HTMX & Loading States**: Self-hosted `htmx.min.js` (2.0.4) in `app/static/`. Buttons disable immediately on submit, preventing duplicate submissions, and display animated pulsing "thinking" indicators (`.dots i`) during LLM calls.
4. **Tutor Dead-End Bug Fixed**: Resolved with new endpoint `POST /tutor/{session_id}/retry` in `app/routes/tutor.py` and a "Try again" action button on `tutor_session.html`.
5. **Persistent Navigation**: Sidebar shell in `base.html` permanently displays all user courses and real-time progress on every page via a clean Jinja2 global helper `sidebar_courses`.
6. **All 11 Templates Modernized**: Dead Bootstrap classes stripped, layout modernized, and the mojibake `ðŸ’¡` byte sequence fixed to valid UTF-8 `💡`.
7. **Test Suite**: **134 passed, 2 warnings in 15.90s** (100% pass rate). Fully backward-compatible with all existing contracts.

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
## Current phase
**Phase 8 is DONE.** The initial commit (message "v0.5: The initial
application", 99 files) exists on `master`, is pushed to the private GitHub
remote, and has a clean status with no secrets/DB/venv tracked. Any new work
must be proposed as a new phase appended to `docs/03-BUILD-PLAN.md` per its
"After Phase 8" section.

## Next step
**Owner:** create an empty repo on GitHub (no README/.gitignore/license —
the repo already has them), then:
```
git branch -M main
git remote add origin https://github.com/<you>/university-in-a-box.git
git push -u origin main
```
After the push, any new work needs its own plan per BUILD-PLAN "After Phase
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
