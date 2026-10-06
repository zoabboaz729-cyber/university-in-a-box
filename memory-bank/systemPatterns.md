# System Patterns

*Update this when an architectural pattern is introduced, changed, or dropped. Full
rationale for the defaults below lives in `docs/02-ARCHITECTURE.md`.*

## Current patterns in use
- Phase 0 skeleton live: `routes/dashboard.py` → Jinja2 `templates/`, no business
  logic in the route; `app/db.py` owns SQLite connect + `init_db()` from plain
  `app/schema.sql`; `app/models.py` only lists table names; `app/ai/` holds
  stdlib-only `config.py` (.env reader) + real `provider.py` (OpenAI-compatible
  HTTP adapter, in use since Phase 1a).
- ActivityLog (D-015): every row carries its owning `course_id` and an
  `is_user` flag; the dashboard reads `MAX(created_at) WHERE course_id = ?
  AND is_user = 1` — no entity-type whitelist. Each store logs its honest
  entity type (source, editor_review, tutor_session, roommate, course,
  topic, interview); system rows (Roommate generation/failures) log
  is_user=False. Migration in `db._migrate` backfills old rows; the
  course_id index is created there too (never in schema.sql).
- Phase 1 (Advisor) live: `routes/advisor.py` + `routes/advisor_review.py`
  (one-question-at-a-time interview, DB-backed draft, review/confirm) and
  `routes/courses.py` (course page + topic page + pause/archive/
  resume + manual topic-done) + `routes/librarian.py` (add-a-source +
  Shelf), backed by `roles/advisor.py`,
  `roles/interview_store.py`, `roles/course_store.py`,
  `roles/course_manage.py`, `roles/dashboard.py`, `roles/activity.py`,
  `roles/librarian.py`, `roles/source_store.py`.
  `main.py` runs `init_db()` in lifespan, then mounts the dashboard,
  advisor, courses, and librarian routers. Tests mock the LLM.
- Phase 4 (Tutor) live: `routes/tutor.py` (start/view/answer/end) +
  `templates/tutor_session.html`, backed by `roles/tutor.py`,
  `roles/tutor_store.py`, `roles/prompts/tutor.md`; dashboard shows
  last_gap_note; topic page lists sessions with resume.
- Phase 6 (Roommate) live: `routes/roommate.py` (Insights journal +
  per-prompt reactions) + `templates/roommate.html`, backed by
  `roles/roommate.py` (build_prompt + cadence_days +
  generate_due_prompts orchestration), `roles/prompts/roommate.md`,
  and `roles/roommate_store.py` (persistence, due math, dedup fields,
  reactions, dashboard-visit timestamps, `last_backup_info` for the
  Settings backup-staleness note). The dashboard route runs the due-check
  on every GET / (background thread, DATA_DIR-pinned, ≤0.2s join — never
  blocks the page) and passes `latest_prompt()` to `index.html` as the "Fresh
  connection" block. `tests/conftest.py` adds autouse fixtures
  (dashboard provider raises ProviderError so older tests stay network-free;
  settings env keys reset so one test's POST can't leak into the next).
  Phase 6 tests re-patch their own FakeProvider.
- Stage 3 (post-Phase-11 owner roadmap) live, all 7 tasks implemented +
  suite-verified 2026-09-14 and re-verified 2026-09-16 after the docs
  reconciliation (215 passed, 2 warnings both times) but UNCOMMITTED: Task 1 `_course_menu.html` macro (sb/dash/mnav
  prefixes) — `base.html` uses it, `index.html` uses `course_row`; Task 2
  mobile `courses-nav-modal` dialog + `#mobile-courses-btn`; Task 3
  discoverability (sidebar Groups nav, dashboard New-group button,
  empty-state link); Task 4 adaptive topic count (prompt 4–8/12 + 3–15
  parser guard); Task 5 group timeframe pre-fill (D-023, sequencing only,
  empty-step guard); Task 6 `app/fetching/` (SSRF-safe http/extract/youtube,
  page/PDF/transcript → truncated text) + `sources.course_id/verified_at` +
  course-level sources; Task 7 read-before-accept Librarian
  (`roles/librarian.verify()` + `librarian_verify.md`, three outcomes,
  per-row Verify-now). New deps: youtube-transcript-api + pypdf. The live
  judging contract is recorded as **D-024** ("routes own the fetch, roles
  own the judgment"); the old description-only triage() path was deleted per
  owner decision (a), recorded as **D-025** (`VERDICTS` moved to its live
  consumer `app/roles/source_store.py`, which validates stored rows with it).
- Phase 7 completion live: `app/monitor.py` (stdlib logging →
  `data/app.log`, idempotent per DATA_DIR) wired in `main.py` lifespan +
  unhandled-exception middleware + `ai/provider.py` final-retry warning;
  `routes/settings.py` (masked key via `load_config()`, cadence +
  pause-default persisted to `.env` via `write_env_value`, backup +
  db-path context) → `templates/settings.html`; `roles/course_store.py`
  honors `NEW_COURSES_START_PAUSED` for new Courses.

## Key technical decisions currently in effect
See `memory-bank/decisions.md` for the full log with dates and reasoning. Current defaults:
- FastAPI + SQLite + server-rendered HTML/HTMX, no build pipeline.
- One system prompt file per ALTER role, stored as text, not inlined in code.
- Pluggable AI provider behind one adapter interface; the running app's LLM is configured
  independently of whichever model is writing the code inside Cline.

## Component relationships (as of the Phase 7 completion pass)
- `routes/dashboard.py` → `templates/index.html` — lists non-draft courses
  newest-first via `roles/dashboard.py`; Start button links to /advisor/new.
  Due-check runs in a DATA_DIR-pinned background thread (≤0.2s join) with a
  durable "new since your last visit" badge (`_dash_visits` + millisecond
  timestamps); nav on every page is Dashboard · Insights · Settings.
- `routes/advisor.py` (topic start + step show + answer submit) →
  `templates/advisor_new.html`, `templates/advisor_step.html`; answers persist
  via `roles/interview_store.py` onto a draft course row.
- `routes/advisor_review.py` — review + regenerate + confirm, registered onto
  the advisor router. /confirm is async (`await request.form()`, D-009) and
  calls `roles/course_store.confirm_curriculum` to flip draft→active (or
  draft→paused when `NEW_COURSES_START_PAUSED` is on).
- `routes/courses.py` → `templates/course.html` at `/courses/{id}`
  (+ `/topics/{id}` → `templates/topic.html`; status POSTs via
  `roles/course_manage.py`); registered in `main.py` (D-009).
- `roles/advisor.py` (five-step pacing + draft parsing + prompt file),
  `roles/interview_store.py` (draft/transcript persistence),
  `roles/course_store.py` (confirm_curriculum, get_course).
- `ai/provider.py` is the real OpenAI-compatible adapter (since 1a);
  `ai/config.py` reads `.env`; ProviderError renders inline on the draft step;
  failed calls after retry are written to `data/app.log`.
- `main.py` lifespan → `db.init_db()` + `monitor.setup_logging()`; mounts
  dashboard, advisor, courses, editor, librarian, roommate, settings, tutor
  routers; unhandled exceptions are logged to `data/app.log` via middleware.
- `routes/dashboard.py` → `roles/roommate.generate_due_prompts` (due-check on
  every load) + `roles/roommate_store.latest_prompt` → `templates/index.html`
  "Fresh connection" block → links to `/roommate`.
- `routes/roommate.py` → `templates/roommate.html` (journal); reaction POST →
  `roles/roommate_store.save_reaction`. Journal never calls the LLM.
- `routes/settings.py` → `templates/settings.html`: masked key (via
  `load_config()`), cadence + pause-default (persisted to `.env`), DB path +
  backup staleness (`roommate_store.last_backup_info`).

## Multi-Tenant & Web/Mobile Patterns (Phases 12–16)
- **Tenant Isolation Pattern**: Every data access function receives `user_id: int` as an explicit parameter and executes SQL containing `WHERE user_id = :user_id`. Direct lookups by entity ID (e.g. `course_id`, `topic_id`) must always verify ownership via `WHERE id = :id AND user_id = :user_id`.
- **Authentication & Route Guard Pattern**: FastAPI dependency `get_current_user` validates session cookie and returns the active `User` model. All protected routers inject this dependency; unauthenticated requests receive a clean 303 redirect to `/login`.
- **Dual-Database Engine Pattern**: `app/db.py` inspects `DATABASE_URL`. If configured, it connects to PostgreSQL using connection pooling; otherwise, it falls back to SQLite at `data/university.db` for local development and test runs. Alembic manages schema migrations across both.
- **Hybrid/BYOK Resolution Pattern**: Prior to making an LLM call, the active key is resolved: user-configured BYOK key (decrypted in memory via AES-GCM) is preferred; otherwise, the server checks the user's `ai_quota_used < MAX_FREE_QUOTA`, increments quota, and uses the host key. If quota is exceeded and no BYOK key exists, a user-facing `QuotaExceeded` error is raised.
- **Mobile-First PWA App Shell Pattern**: Viewports `< 768px` render a persistent bottom navigation bar (`Courses`, `Insights`, `Groups`, `Settings`) and open context menus in accessible bottom sheets. Touch targets maintain ≥ 48×48px. `manifest.json` and `sw.js` enable standalone mobile installability with asset precaching.
- **Decoupled Async Scheduling Pattern**: Background scheduler runs independently of page loads to evaluate due courses, generate Roommate prompts, and dispatch Web Push notifications.

## Anti-patterns explicitly avoided (see docs/04-CONSTRAINTS.md)
- No unscoped database queries that omit `user_id = current_user.id`.
- No plain-text storage or logging of user BYOK API keys.
- No blocking synchronous HTTP or LLM calls in FastAPI route handlers (`httpx.AsyncClient` required).
- No heavy JavaScript SPA frameworks (React/Next.js/Vue) — preserve server-rendered Jinja2 + HTMX simplicity.
- No business logic in route handlers or templates.
- No ORM magic hiding what SQL actually runs.
- No role module calling another role module directly — they compose only through
  persisted data and the routes layer, so each stays independently testable.
