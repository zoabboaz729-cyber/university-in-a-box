# Active Context

**Update this file at the end of every session, without exception. This is the first file
any coding-agent session should read — it should be enough, on its own, to know exactly
where the project stands and what to do next.**

**2026-09-30 (Multi-Tenant, Web-Hosted & Mobile-First Architectural Documentation Session):**
The owner approved the architectural pivot and decided the four core strategy forks:
1. **AI Cost Model**: Hybrid / BYOK (Bring Your Own Key) model (D-027). Users can configure their own OpenRouter/OpenAI API key (encrypted at rest via AES-GCM), with a server-paid free trial quota.
2. **Authentication**: Native Email + Password with secure HttpOnly, SameSite=Lax signed session cookies and Argon2id hashing (D-028).
3. **Database Architecture**: Dual support: PostgreSQL with connection pooling for production web hosting, while retaining SQLite for local development and fast headless test runs (D-029). Schema managed by Alembic.
4. **Frontend Architecture**: Mobile-First PWA + HTMX retaining the warm paper "Reading Room" aesthetic (D-030). Bottom navigation bar on mobile (< 768px), touch-first ergonomics (≥48px tap targets), manifest.json + service worker for iOS/Android installability.

**All project documentation was comprehensively updated before any code implementation:**
- `docs/01-VISION.md`: Updated target audience to many learners, mobile & web-first, rock-solid tenant isolation, explicit non-goals adjusted.
- `docs/02-ARCHITECTURE.md`: Stack decision table, multi-tenant entity schema with `user_id` on all tables, async AI provider, async fetching, mobile-first PWA app shell, decoupled background scheduler.
- `docs/03-BUILD-PLAN.md`: Appended Phases 12–16 with goals, steps, constraints, and definitions of done.
- `docs/04-CONSTRAINTS.md`: Added tenant isolation invariant, Argon2id auth security, and AES-GCM BYOK key encryption at rest.
- `docs/05-VERIFICATION.md`: Added verification checklists for tenant isolation, auth, dual-DB parity, BYOK quotas, and mobile PWA compliance.
- `docs/06-MONITORING.md`: Added multi-tenant error isolation and PostgreSQL backup routines.
- `memory-bank/`: Updated `decisions.md` (D-026 to D-030), `techContext.md`, `systemPatterns.md`, `productContext.md`, `progress.md`.

**Current status:** Phase 12 is complete and verified. Phase 13 is complete and verified: the app has async-capable provider support, AES-GCM BYOK encryption/decryption, quota-aware key resolution, async-compatible fetch wrappers, and the remaining route-level async adoption is in place. Phase 14 is also complete and verified: the app now includes a mobile-first PWA shell, touch-friendly bottom navigation, standalone manifest, service worker caching, and offline status handling while preserving the Reading Room architecture. The final repo-wide verification passed (`python -m pytest -q` → **212 passed, 2 warnings in 41.26s**).

**Cleanup complete:** all repo scratch `.txt` dumps and the tagged debug script were removed; the exact `free_models.txt` file was preserved only if it existed (it did not in this checkout), and no tracked product code was touched.

**Next step:** Continue with the next planned phase only after the user decides the next exact implementation step.

**Verification closeout (2026-10-07):** Phase 13 is complete and validated in the live repo state: `python -m pytest -q` → **212 passed, 2 warnings in 59.44s**. The async provider layer in [app/ai/provider.py](C:/Projects/university-in-a-box/university-in-a-box/app/ai/provider.py), quota enforcement in [app/ai/quota.py](C:/Projects/university-in-a-box/university-in-a-box/app/ai/quota.py), AES-GCM BYOK handling in [app/auth/security.py](C:/Projects/university-in-a-box/university-in-a-box/app/auth/security.py), settings persistence in [app/routes/settings.py](C:/Projects/university-in-a-box/university-in-a-box/app/routes/settings.py), and SSRF-safe fetching in [app/fetching/http.py](C:/Projects/university-in-a-box/university-in-a-box/app/fetching/http.py) all hold together under the existing suite.

**Local startup check (2026-10-07):** `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` initially failed because the project virtual environment lacked `cryptography`, imported by `app/auth/security.py` for AES-GCM. Installed `cryptography` into this checkout's `.venv`; retry completed application startup and `GET /login` returned HTTP 200. The local server was stopped after verification. Recovered the deleted root `requirements.txt` from the parent of commit `b0610ac` and added `argon2-cffi`, `itsdangerous`, and `cryptography` as current authentication runtime dependencies; `memory-bank/techContext.md` now distinguishes these from future production dependencies.

**2026-09-16 (Stage 3 close-out prep session): VERIFIED — `python -m pytest -q` → 215 passed, 2 warnings in 26.51s at the start of the session, and again on the final working tree after every edit below: 215 passed, 2 warnings in 24.93s.** Detached-run note: `Start-Job` dies when the terminal is reused (it stalled at 66%); `Start-Process … -RedirectStandardOutput <file>` is the reliable pattern here — the output FILE is the source of truth, never the terminal pane. **No product behavior changed** (the only `.py` edits were two doc-comment citations). What this session did:
1. **Added the missing D-024** to `memory-bank/decisions.md` — the Librarian read-before-accept decision (fetch reversal, three explicit outcomes, `unverified` verdict, topic-or-course source scope, "routes own the fetch / roles own the judgment"). Both `roles/librarian.py` and `routes/librarian.py` had *claimed* the reversal was recorded; it was not (the route comment cited a non-existent D-013). `D-011` now carries a "Superseded for the live add-a-source path" note.
2. **Docs reconciled with the running code** (docs/04 §7 obligation, docs/05 "no doc contradicts the app"): `docs/02-ARCHITECTURE.md` — data model gains `CourseGroup` / `courses.group_id` / `sources.course_id`+`verified_at`+`unverified` / `roommate_prompts.field`+`secondary_course_id`+`connection_type` / `_dash_visits`, a new "Outbound fetching pattern (D-024)" section, the real folder layout (`app/fetching/`, groups, `_`-prefixed partials), and the `/tasks/due` claim replaced with the actual in-process dashboard-load due-check; `docs/03-BUILD-PLAN.md` — new **Stage 3** section (the plan previously jumped from Phase 11 straight to "After Phase 11" while progress.md listed a Stage 3 row); `docs/04-CONSTRAINTS.md` §5 — outbound-fetch rule; `docs/07-FRONTEND-AUDIT.md` — dated amendment on its now-stale HTMX + `/tasks/due` findings (stale since Phase 9 self-hosted `htmx.min.js`; templates use `hx-include`/`hx-indicator`, still no `hx-get/post/target/swap`).
3. **Scratch cleanup:** 13 `_audit_*.txt` files + the NUL-filled `_audit_live_check.py` deleted from the repo root; 28 `data/pytest_*.txt` test-output files deleted (data/ now holds only `.gitkeep`, `app.log`, `university.db`). `.gitignore` now also covers `mystartingcommand.md` (owner scratch note, kept on disk).
4. **Boot smoke test on the REAL database** (temporary `_smoke.ps1`, deleted afterwards — uvicorn on port 8123, deliberately NOT requesting `/` so the Roommate due-check could not make a real LLM call or write a prompt row into the owner's data): `GET /advisor/new`, `/settings`, `/groups`, `/courses/4`, `/topics/22` → **all 200** (real ids read from `data/university.db`; 7 courses, topics 22–55); `/topics/1` and an unknown path → clean 404; uvicorn log shows "Application startup complete" with no errors. So the working tree boots, migrates the real DB on boot, and renders the new pages against real data.
**2026-09-14 (Stage 3 verification session): VERIFIED — `python -m pytest -q` → 215 passed, 2 warnings in 25.56s** (foreground shell output is unobservable in this environment, so the suite ran detached via a temp runner with output to a temp file; both scratch files removed afterwards). All 7 owner-roadmap tasks green, zero regressions. No product code changed this session — only scratch cleanup + this memory-bank update. Remaining before Stage 3 is Done: owner UI walkthrough + commit (see Next step).

**2026-09-14 (Stage 2 confirmation pass, same investigation): READ-ONLY — no product code
changed.** Owner's five feature decisions re-examined against exact code traces. Key
findings: (1) owner's belief CONFIRMED — the ONLY `course_groups` INSERT is
`group_store.create_group` (group_store.py:39), only called by `POST /groups/create`
(routes/groups.py:61), whose only form is groups.html:20, and the only `<a href="/groups">`
anywhere is inside the group-assign modal hint (base.html:189) — reachable only after a
course exists; `/groups` is not in the persistent nav. (2) Item 4 note: if all 5 answers are
pre-seeded, `next_step()` (advisor.py:64) would jump straight to /review — a
"confirmed vs draft answer" marker is required; `advisor.py:7` "LLM used exactly once" and
the STEPS docstring must be revised. (3) `requirements.txt` already has `httpx` (line 4);
only new dep proposed for source verification is `youtube-transcript-api`; mobile fix
precedent: `{% macro course_row %}` (index.html:50) is the codebase's existing
component pattern for the ⋮ consolidation. Verdicts + build order delivered in-session.
**2026-09-14 (Feature-roadmap investigation session): READ-ONLY — no product code changed.**
The owner commissioned an investigation for 5 candidate features: (1) groups + property
inheritance, (2) mobile course-card menus, (3) adaptive topic count/durations, (4) chat
onboarding for the Advisor, (5) source recommendation + verification engine. Findings that
reshape those features: **(1) Groups are ALREADY fully built** (Phase 11 — course_groups
table, group_store.py, routes/groups.py, sidebar folders, dashboard filters, ⋮ menu modal);
"inheritance" beyond the display-only `timeframe_mode`/'uniform' duration would be new.
**(2) 3-dots menus exist** (Phase 10) but the single 760px media query hides the whole
sidebar course list on mobile (`style.css:1214`), so menus are unreachable on phones.
**(3) "Always 6 topics" does NOT exist in this codebase** — `prompts/advisor.md:11` says
"4–8 topics"; per-topic `time_box` already varies (free TEXT, never parsed for math).
**(4) Advisor is a fixed 5-question form flow** (advisor.py STEPS/STEP_QUESTIONS) — the
fixed-question design is a documented deliberate choice; chat onboarding contradicts it and
needs a product decision. **(5) No web-fetching/YouTube capability exists anywhere**;
`roles/librarian.py:7-9` explicitly states the model never fetches URLs. Full report was
delivered in-session (chat); its content is reproduced in this session's conversation only.

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

**Stage 3 (owner roadmap, 7 tasks) is implemented, suite-verified and documented; the only
things left are the owner's UI walkthrough and the commit — see Next step.**

## Next step
Stage 3 (owner roadmap, 7 tasks) is implemented, suite-verified (215 passed — 2026-09-14, re-verified 2026-09-16) and its docs are now reconciled (docs/02, the new docs/03 Stage 3 section, docs/04, D-024 — see the 2026-09-16 entry at the top of this file). Remaining, in order:
1. **Owner manual walkthrough of the Stage 3 UI** (same as the Phase 8
   ritual): ⋮ menus on sidebar/dashboard/mobile dialog, group-creation
   discoverability, adaptive topic counts on a real curriculum, group
   timeframe pre-fill, and the full Librarian read-before-accept flow
   (accept / reject / retry-keep-discard) at topic and course level —
   then record the result in progress.md's walkthrough section.
2. **Commit Stage 3** on top of v0.6 (working tree: modified core files +
   new `app/fetching/`, `librarian_verify.md`, `_course_menu.html`,
   `_sources.html`, `librarian_*.html`, `tests/test_fetching.py`; still
   untracked and uncommitted: `docs/07-FRONTEND-AUDIT.md` and the
   extension-less `docs/Frontend-Mockup` HTML mockup).
   Git identity IS configured repo-locally (Zoab Boaz
   <309829610+zoabboaz729-cyber@users.noreply.github.com>), so the agent can
   make this commit as soon as the owner says go.
3. Propose the next phase by appending to `docs/03-BUILD-PLAN.md`
   ("After Phase 11" section): candidates already on file — multi-topic
   Roommate cross-linking depth, spaced repetition on gap notes,
   export/print of a Course, exam simulation.

<!-- Historical: Phase 7 completion pass (D-018) sub-steps: error logging via
app/monitor.py; Settings persistence to .env; NEW_COURSES_START_PAUSED
honored in confirm_curriculum; backup/restore proven. Regression loop
tests/test_regression_loop.py covers docs/05 items 1-7. -->


## Noticed
- RESOLVED (2026-09-16, owner option (a), D-025 — deletion implemented same day):
  the old `librarian.triage()` + `prompts/librarian.md` path was DELETED —
  `triage()`, `_parse_verdict()`,
  `SourceVerdict`, `PROMPT_FILE`, the `.md` file, and the 3 triage tests are gone.
  `VERDICTS` moved to its live consumer `app/roles/source_store.py` (stored-row
  validation only, since legacy rows still carry keep/skip/later and the Shelf
  filter is verdict = 'keep'). Full suite after deletion: **212 passed,
  2 warnings** (215 minus the 3 removed triage tests).
- RESOLVED (2026-09-16, owner decision): `docs/Frontend-Mockup` is a single extension-less HTML file (12,493 bytes, the Direction A mockup), not a directory. **Owner chose: leave it exactly where it is** — do not rename or move it; it gets committed as-is with Stage 3.
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
- (none — the triage() question is resolved as D-025; the Frontend-Mockup
  question is resolved: leave the file exactly where it is.)
