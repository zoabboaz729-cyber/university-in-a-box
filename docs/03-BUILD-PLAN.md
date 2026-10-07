# 03 — Build Plan

Build these phases **in order**. Do not start a phase until the previous one has passed its
Definition of Done in `docs/05-VERIFICATION.md`-style verification. `memory-bank/progress.md`
always states which phase is current — treat that as authoritative over this document if
they ever disagree, and reconcile them the same session you notice the mismatch.

Every phase below follows the same shape: **Goal**, **Why** (which principle it serves),
**Steps**, **Constraints specific to this phase**, **Definition of Done**.

---

## Phase 0 — Foundation
**Goal:** A running, empty skeleton app with the folder layout, DB, and docs wired up —
nothing user-facing yet beyond a blank dashboard page.

**Why:** P8 — a coding agent with limited context needs a stable skeleton to build into,
one piece at a time, rather than scaffolding and features arriving together.

**Steps:**
1. Create the folder layout from `docs/02-ARCHITECTURE.md`.
2. Set up FastAPI app that boots and serves one route (`/`) rendering a placeholder page.
3. Set up SQLite connection + create the tables from the data model (a plain `.sql` schema
   file is fine — no migration framework needed yet).
4. Add `.env.example` with the AI provider variables, and load them in `app/ai/config.py`
   (the provider adapter itself can be a stub that returns a fixed string for now).
5. Add a minimal test that boots the app and hits `/`.

**Constraints:** No ALTER logic yet. No real LLM calls yet — a stub is correct here.

**Definition of Done:** `uvicorn app.main:app` runs locally, `/` renders, the DB file is
created with all tables, one passing test exists.

---

## Phase 1 — Advisor (curriculum creation)
**Goal:** A user can type a topic, get interviewed step by step (destination → baseline →
sequencing → cut list → milestones), and end up with a persisted Course + ordered Topics.

**Why:** P1, P7 — this is the entry point to everything else; nothing downstream works
without a Course to attach to.

**Steps:**
1. Write the Advisor system prompt (`app/roles/prompts/advisor.md`) encoding the five-step
   interview and the "one question at a time" behavior.
2. Implement `app/roles/advisor.py`: given interview history so far, returns the next
   question or, once all five steps are answered, a structured curriculum draft.
3. Wire the real LLM provider call (Phase 0's stub becomes real here) — this is the first
   phase that needs a working API key configured.
4. Build the route + templates: a simple chat-like flow, one question shown at a time, the
   user's answer submitted, next question shown, until the interview is complete.
5. On completion, persist `Course`, `Topic` rows, and the raw `AdvisorInterview` rows.
6. Let the user view and lightly edit the resulting curriculum before "starting" it.

**Constraints:** Exactly one question visible at a time — do not dump all five steps'
questions at once even if that's technically easier to build. The interview transcript is
kept, not discarded once the Course exists.

**Definition of Done:** From a blank app, a user can create a full Course end to end, close
the app, reopen it, and see the same Course with its Topics still there.

---

## Phase 2 — Dashboard & progress persistence
**Goal:** A home dashboard listing active Courses, current Topic per Course, and basic
status — the thing the user (and, implicitly, the returning coding agent) looks at first.

**Why:** P6 — durability and easy resumption are core to the product, not a later polish
item; build this early so every subsequent phase has somewhere to surface itself.

**Steps:**
1. Dashboard route showing all Courses with status, current Topic, and days since last
   activity (using `ActivityLog`).
2. Topic detail page: shows the Topic's milestone, its Shelf (empty until Phase 3), its
   Tutor sessions (empty until Phase 4), its Editor reviews (empty until Phase 5).
3. Basic Course management: pause/archive/resume a Course; mark a Topic done manually for
   now (Phase 5 will gate this properly behind an Editor review).
4. Start writing to `ActivityLog` from every meaningful action from here on.

**Constraints:** Keep this page genuinely useful with zero data (new user / new Course) —
empty states matter for a long-lived daily tool; do not skip them.

**Definition of Done:** A Course created in Phase 1 shows correctly on the dashboard, its
Topic detail page renders, pause/archive/resume works and persists across restarts.

---

## Phase 3 — Librarian (source triage)
**Goal:** From a Topic page, a user can add candidate sources and get a keep/skip/later
verdict with a one-line reason, building a short Shelf.

**Why:** P2 — curation must exist before the user is expected to have "studied" anything
meaningful for the Tutor to probe.

**Steps:**
1. Librarian prompt + `app/roles/librarian.py`: given a source description/URL and the
   Topic's context, returns a verdict + one-line reason. (Note: the model does not need to
   fetch and read the URL to be useful here — judging fit/credibility from what the user
   describes plus the URL/domain is enough for v1; do not build a web-fetching pipeline in
   this phase.)
2. Route + template: add-a-source form, list of sources with verdicts, filter to Shelf
   (`keep`-only) view.
3. Persist `Source` rows.

**Constraints:** Do not silently auto-delete `skip` sources — keep them, dimmed, so the
user can see what was considered and why.

**Definition of Done:** A Topic accumulates sources with verdicts, the Shelf view correctly
shows only `keep`, everything persists across restarts.

---

## Phase 4 — Tutor (Socratic sessions)
**Goal:** From a Topic page, a user can start a session where the Tutor asks one question
at a time, adapts to answers, and the session ends with a persisted gap note.

**Why:** P3 — this is where the app actually tests understanding rather than assuming it.

**Steps:**
1. Tutor prompt + `app/roles/tutor.py`: strict one-question-at-a-time behavior, must use the
   Topic's milestone/Shelf as context, must produce a short gap note when the session ends.
2. Route + template: a session view showing one question, an answer box, the next question
   appearing after submission; a clear "end session" action.
3. Persist `TutorSession` and each `TutorTurn`; show the gap note on the Topic detail page.
4. Surface the most recent gap note on the dashboard for that Course.

**Constraints:** The Tutor must never answer its own question or lecture in place of asking
one — write this explicitly into the prompt and spot-check it in verification (see
`docs/05-VERIFICATION.md`).

**Definition of Done:** A full session can be run start to end, is fully persisted (including
mid-session — do not lose a session if the app is closed partway through), and the gap note
appears on both the Topic and dashboard views.

---

## Phase 5 — Editor (feedback on real output) + Milestone gating
**Goal:** A user can paste/submit something they produced against a Milestone, get
structured feedback, and only then mark that Milestone/Topic done.

**Why:** P4 — closes the loop between producing something and knowing whether it's actually
good, and ties Topic completion to real evidence instead of a self-reported checkbox.

**Steps:**
1. Editor prompt + `app/roles/editor.py`: takes submitted text + the Milestone description,
   returns strengths / single biggest weakness / one concrete next edit — not generic praise.
2. Route + template: submission form on the Topic page, review displayed, history of past
   reviews for that Topic kept visible.
3. Change "mark Topic done" (from Phase 2) to require at least one Editor review to exist
   for that Topic before it can be marked done — replace the manual-only path.

**Constraints:** Feedback must always include exactly one "biggest weakness" and one
concrete next edit — never a bare list of positives with nothing actionable.

**Definition of Done:** A Topic cannot be marked done without a review on record; the review
history is visible and persists.

---

## Phase 6 — Roommate (cross-domain prompts)
**Goal:** On a cadence, the app surfaces a short cross-domain connection prompt tied to an
active Course, logged to an Insights journal the user can scroll.

**Why:** P5 — range doesn't happen by accident; it has to be nudged on a schedule.

**Steps:**
1. Roommate prompt + `app/roles/roommate.py`: given the Course's topic area, returns one
   short prompt connecting it to a genuinely different field.
2. A simple due-check mechanism (e.g., a `/tasks/due` route checked whenever the dashboard
   loads, comparing to the last `RoommatePrompt` timestamp for that Course) — no external
   job scheduler needed for a local single-user app.
3. Route + template: Insights journal page listing past prompts, newest first, with an
   optional free-text reaction field per prompt.
4. Show the latest unread prompt on the dashboard.

**Constraints:** Keep the cadence conservative by default (a couple of times a week per
active Course) and make it configurable — do not spam.

**Definition of Done:** Prompts appear on schedule when the dashboard is opened, are logged,
and the journal correctly lists history across restarts.

---

## Phase 7 — Daily-use polish
**Goal:** The details that decide whether this gets used daily for months, not the details
that impress once.

**Why:** P6.

**Steps:**
1. Streak / activity indicator on the dashboard (based on `ActivityLog`).
2. A simple backup routine: a documented (and ideally one-command) way to copy `data/university.db`
   somewhere safe; note it in the README.
3. Empty-state and error-state review across every page built so far — nothing should ever
   render a blank page or an unhandled exception to the user.
4. Settings page: AI provider config visibility (masked key), Roommate cadence, per-Course
   pause defaults.

**Constraints:** No new ALTER-role behavior in this phase — this is hardening, not features.

**Definition of Done:** Closing and reopening the app after a week of no use shows a
coherent, correct dashboard with no errors; a backup can be taken and restored successfully.

---

## Phase 8 — Verification pass & documentation finalization
**Goal:** Confirm the whole ALTER loop works end to end for a brand-new topic, and bring
every doc (including this one, if reality has drifted) up to date.

**Why:** P6, P8 — the project must be genuinely resumable and genuinely working, not just
believed to be.

**Steps:**
1. Run the full regression checklist in `docs/05-VERIFICATION.md` against every phase.
   Since the Phase 7 completion pass this is also automated: `tests/test_regression_loop.py`
   walks Advisor → Librarian → Tutor → Editor → Roommate + restart persistence + streak +
   settings on a throwaway DB with a scripted provider (docs/05 items 1–7, re-runnable via
   `python -m pytest tests/test_regression_loop.py -q`).
2. Walk one full topic through Advisor → Librarian → Tutor → Editor → Roommate manually and
   record the walkthrough result in `memory-bank/progress.md`.
3. Reconcile every doc in `docs/` and `memory-bank/` against actual current behavior; fix
   any drift.
4. Initialize the git repository (first version control for the project): `git init`, harden
   `.gitignore` (secrets, DB, venv, logs, editor files), initial commit of the working tree.
   Success metrics: `git status` clean after commit; `git log` shows the initial commit; no
   `.env`, `*.db`, or `.venv/` paths staged.

**Definition of Done:** The regression checklist passes clean, the full-loop walkthrough is
recorded, and no doc contradicts the running app.

---

## Phase 9 — Frontend redesign ("The Reading Room")
**Goal:** Comprehensive visual and interaction overhaul using "The Reading Room" aesthetic (warm paper, serif headlines, durable sidebar, HTMX responsive interactions).

**Why:** P6, P7 — A serious daily self-study workspace should feel like a quiet, intentional reading library rather than a generic web dashboard.

**Steps:**
1. Hand-crafted CSS design tokens (`app/static/style.css`) with palette, typography, and card primitives.
2. Self-hosted offline Google Fonts (`Source Serif 4` and `Inter` woff2).
3. Self-hosted `htmx.min.js` (2.0.4) for loading indicators and inline UI.
4. Persistent sidebar with dynamic course list on every page.
5. Socratic tutor retry endpoint `POST /tutor/{id}/retry` and unhandled bug fix.

**Definition of Done:** All 11 templates modernized, offline-ready, 100% test pass rate.

---

## Phase 10 — Course deletion & contextual management
**Goal:** Ability to safely and permanently delete a Course and its associated records with full user agency, consequence warnings, and universal 3-dots context menus.

**Why:** P7 (User agency) — Users exploring the app with test/sample courses need the agency to delete them without leaving orphan data or ghost stats; P6 (Durability) — Database integrity must be maintained atomically.

**Steps:**
1. Implement `delete_course(course_id)` in `app/roles/course_manage.py` with an atomic SQLite transaction deleting turns, tutor sessions, sources, editor reviews, topics, interviews, roommate prompts, activity logs, and the course.
2. Route `POST /courses/{course_id}/delete` with safe redirect.
3. Universal 3-dots (`⋮`) context menu on every course in the persistent sidebar and dashboard.
4. Consequence warning `<dialog>` modal explaining exactly what will be permanently erased.
5. Explicit "Delete course" action on `/courses/{id}`.
6. Dependent module adaptation: Roommate `latest_prompt()` fallback, streak recalculation, and 404 responses.

**Definition of Done:** Deletion cleans all 8 child tables atomically; modal requires explicit confirmation; full regression suite green with dedicated deletion tests.

---

## Phase 11 — Course Groups / Semesters & multi-course insights
**Goal:** Enable coupling related courses into Groups (e.g. "Semester 1", "Computer Systems Track") with customizable timeframe synchronization and intra-group Roommate cross-course synthesis.

**Why:** P5 (Range is deliberately engineered) & P1 (Personalization) — Students learn in cohorts or semesters; connecting concepts across concurrent courses elevates understanding and reduces scheduling friction.

**Steps:**
1. Database migration: `course_groups` table with `timeframe_mode` ('individual' vs 'uniform') and `group_id` foreign key on `courses`.
2. Group management data access layer and routes: create, edit, assign courses, delete group (Option B: choice between ungrouping courses vs deleting courses).
3. Timeframe synchronization: support uniform semester pacing or individual course pacing (Option A default).
4. Roommate intra-group synthesis: generate cross-course connection prompts bridging two active courses in the same group.
5. Sidebar and dashboard group headers, collapsible course trees, and collective progress tracking.

**Definition of Done:** Group CRUD operational, courses can be grouped/ungrouped, uniform or individual pacing honored, and Roommate generates cross-course connections when courses share an active group.

---

## Stage 3 — Owner roadmap (post-Phase 11)

**Goal:** Seven owner-requested improvements to navigation, the Advisor, and the Librarian,
delivered together on top of the v0.6 commit. (Called "Stage 3" because it came from the owner's
own roadmap rather than this document — the phase numbering above it is unchanged.)

**Why:** P7 (agency — every course/group action reachable, including on a phone), P1
(personalization — curriculum shape follows the learner's scope, not a fixed count), P2 (narrow
the pile for real — a source is judged from what it actually says, not from its URL).

**Steps (all seven implemented):**
1. One ⋮ course menu: `templates/_course_menu.html` macro, used by the sidebar, the dashboard
   rows, and the mobile dialog (instead of three near-duplicate menus).
2. Mobile course navigation: `courses-nav-modal` dialog + `#mobile-courses-btn`, so courses and
   their menus are reachable on a phone — the ≤760px media query previously hid the sidebar list
   entirely, making the ⋮ menus unreachable there.
3. Group discoverability: a `Groups` sidebar nav entry, a "New group" button on the dashboard, and
   an empty-state link to `/groups` (group creation used to be reachable only after a course
   existed).
4. Adaptive topic count: `prompts/advisor.md` now asks for 4–8 topics (up to 12 for large scopes)
   and the parser guard accepts 3–15, replacing the old fixed-count behavior.
5. Group timeframe pre-fill (D-023): a `uniform` group's stated duration pre-fills the Advisor's
   sequencing answer for courses created inside that group — pre-fill, not skip; only when the
   step is still empty; free text only, no duration math.
6. Outbound source reading (D-024): `app/fetching/` (SSRF-guarded HTTP, HTML/PDF text extraction,
   YouTube transcripts), `sources.course_id` + `sources.verified_at` migrations, and course-level
   sources (a source can attach to the whole Course, not just a Topic).
7. Read-before-accept Librarian (D-024): `librarian.verify()` + `prompts/librarian_verify.md`;
   exactly one of three explicit outcomes per attempt — verified-accept, verified-reject, or
   unavailable (retry / keep permanently badged `unverified` / discard), at both topic and course
   level, with a per-row Verify-now action for rows stored before verification existed.

**Constraints specific to this stage:** one fetch + one LLM call per source attempt; no
scheduling/week math anywhere; no sixth role; navigation work stays plain server-rendered HTML
(no bundler, no new listener), and existing routes/URLs keep working.

**Definition of Done:** the seven behaviors work end to end on a running app; `python -m pytest -q`
is green; the owner has walked the new UI paths (⋮ menus on sidebar/dashboard/mobile,
group-creation discoverability, adaptive topic counts on a real curriculum, group timeframe
pre-fill, and the full Librarian read-before-accept flow at topic and course level) and the result
is recorded in `memory-bank/progress.md`; the work is committed.

**Status:** implemented and suite-verified (**215 passed, 2 warnings** — 2026-09-14, re-verified
2026-09-16); **owner walkthrough and commit still outstanding** (see `memory-bank/activeContext.md`).

---

## Phase 12 — Multi-Tenant Data Foundation, Dual-DB (PostgreSQL + SQLite) & Auth (Email + Password)

**Goal:** Enable many distinct users to securely register, log in, and manage their own isolated courses, groups, and learning transcripts, with dual-database support (PostgreSQL for production web hosting, SQLite for local development and testing).

**Why:** P7 (User agency) & P6 (Durability) — Every learner deserves their own private, isolated university. Multi-user hosting requires rock-solid data partitioning and authenticated access.

**Steps:**
1. **Dual-DB Connection Layer & Alembic**: Implement `app/db.py` to support `DATABASE_URL` pointing to PostgreSQL with connection pooling (`psycopg` / `asyncpg` / SQLAlchemy Core) while keeping SQLite fallback (`data/university.db`) for local dev/testing. Initialize Alembic for schema migrations.
2. **Multi-Tenant Schema Migration**: Update `users` table (`email`, `password_hash`, `name`, `encrypted_ai_key`, `ai_quota_used`, `created_at`). Ensure all tables (`course_groups`, `courses`, `topics`, `advisor_interviews`, `sources`, `tutor_sessions`, `tutor_turns`, `editor_reviews`, `roommate_prompts`, `activity_log`, `_dash_visits`) strictly carry `user_id` foreign keys with indexes.
3. **Authentication & Session Module (`app/auth/`)**: Password hashing using Argon2id (`argon2-cffi`), secure signed session cookies (`itsdangerous` / signed HttpOnly cookies), and user model helpers.
4. **Auth Routes & UI**: `GET`/`POST` `/register`, `/login`, `/logout`, and password change in `/settings`, styled with Reading Room design tokens.
5. **Data Layer Tenant Isolation**: Refactor all store queries (`course_store.py`, `group_store.py`, `course_manage.py`, `advisor.py`, `interview_store.py`, `source_store.py`, `tutor_store.py`, `review_store.py`, `roommate_store.py`, `activity.py`, `dashboard.py`) to mandate `user_id` and enforce `WHERE user_id = :user_id`.
6. **Route Protection**: FastAPI dependency `get_current_user` injected across all protected routers; unauthenticated requests redirect cleanly to `/login`.

**Constraints:** Zero cross-tenant data leaks. Unauthenticated requests must never access or modify any learning data. SQLite test suite must run clean without requiring a live Postgres instance.

**Definition of Done:** Users can register, log in, log out; User A cannot view, modify, or delete User B's courses or transcripts; regression test suite runs green in SQLite mode with authenticated test fixtures.

---

## Phase 13 — Async Engine, Non-Blocking Fetching & Hybrid/BYOK Quota Management

**Goal:** Convert all LLM operations and outbound source fetching to non-blocking async (`httpx.AsyncClient`) and implement the Hybrid/BYOK (Bring Your Own Key) key and quota management system.

**Why:** P8 (Buildability) & Multi-User Scalability — Synchronous 60-second provider and fetch calls block server worker threads under multi-user load. A sustainable hosted service requires protecting server AI budgets via user keys and controlled free quotas.

**Steps:**
1. **Async AI Provider**: Refactor `app/ai/provider.py` to use `httpx.AsyncClient` with `async def generate()` and non-blocking retry logic.
2. **Async Source Fetching**: Convert `app/fetching/http.py`, `extract.py`, and `youtube.py` to async I/O while preserving SSRF validation guards.
3. **Hybrid/BYOK Crypto & Settings**: Implement AES-GCM encryption helpers (`app/auth/security.py`) to encrypt and decrypt user-provided API keys using `APP_SECRET_KEY`. Add UI in `/settings` allowing users to store their personal OpenAI/OpenRouter key and custom base URL/model.
4. **Quota Engine (`app/ai/quota.py`)**: Track `ai_quota_used` for users on the server-provided key. If a user exceeds `MAX_FREE_QUOTA` and has not configured a BYOK key, render an informative `QuotaExceeded` message directing them to add their key in Settings.
5. **Async Route Handlers**: Convert all role routes (`advisor`, `courses`, `librarian`, `tutor`, `editor`, `roommate`) to `async def` and pass the active user context to the quota/key resolver.

**Constraints:** User BYOK keys must never be logged or stored in plain text. Outbound fetches must remain strictly SSRF-guarded. Free quotas must increment atomically.

**Definition of Done:** Multiple concurrent requests run asynchronously without thread blocking; BYOK keys work seamlessly; users without keys can use their free quota and receive a clear prompt to add a key once exhausted.

---

## Phase 14 — Mobile-First PWA & Touch UX (Reading Room App Shell, Bottom Nav & Service Worker)

**Goal:** Transform the frontend into an ergonomic, mobile-first web app installable on iOS and Android as a Progressive Web App (PWA), maintaining the warm paper "Reading Room" aesthetic.

**Why:** P6 (Durability) & P7 (Agency) — Learners study on phones, tablets, and desktops. A mobile-first design makes opening the app daily effortless.

**Steps:**
1. **Mobile Bottom Navigation**: Implement a mobile-first app shell in `app/templates/base.html` and `style.css`: persistent bottom navigation bar on mobile viewports (`< 768px`) with direct access to Courses, Insights, Groups, and Settings, while retaining the desktop sidebar on larger screens.
2. **Touch-First Ergonomics**: Update all buttons, cards, and modal triggers to meet touch guidelines (minimum 48×48px tap targets); bottom-sheet modal for course 3-dots actions (`⋮`) on mobile.
3. **Keyboard-Aware Socratic Flow**: Auto-scroll tutor and interview question panels into view when mobile software keyboards open.
4. **PWA Manifest (`app/static/manifest.json`)**: App identity, icons (192px & 512px), theme color (`--bg-paper`), background color, `display: standalone`.
5. **Service Worker (`app/static/sw.js`)**: Cache-first strategy for static assets (fonts, `style.css`, `htmx.min.js`, icons) for instant cold boots on mobile.

**Constraints:** No heavy SPA framework (no React/Next.js); keep server-rendered Jinja2 + HTMX architecture intact. Offline fallback renders a clean "Reading Room offline" note.

**Definition of Done:** Passes Lighthouse PWA criteria; installable to home screen on iOS and Android; navigation is natural and responsive on mobile viewports; full desktop layout remains intact.

---

## Phase 15 — Decoupled Background Scheduler, Proactive Roommate & Web Push

**Goal:** Decouple Roommate due-checks from synchronous web requests into a background scheduler and deliver cross-domain prompts and streak nudges via Web Push notifications.

**Why:** P5 (Range is deliberately engineered) — Serendipitous connections and study streaks should reach the learner where they are, rather than only appearing when they manually open the dashboard.

**Steps:**
1. **Background Scheduler (`app/scheduler/`)**: In-process async background scheduler (APScheduler / FastAPI lifespan worker) running periodic checks across all users' active courses.
2. **Decoupled Roommate Generation**: Evaluate course cadence independently of page visits; generate and journal cross-domain prompts asynchronously.
3. **Web Push Notification Infrastructure**: Support VAPID keys, service worker push event listeners, and user push subscription management in `/settings`.
4. **Proactive Study Nudges**: Dispatch push notifications for newly generated Roommate insights and streak milestone reminders.

**Constraints:** Zero notification spam. Notifications must be opt-in from `/settings` and easily disabled. Generation failures for one user must never affect other users.

**Definition of Done:** Roommate insights generate on schedule without manual page loads; web push notifications can be subscribed to and received on mobile.

**Status (verified 2026-10-07):** The scheduler is started from FastAPI lifespan and stopped cleanly on shutdown; the app keeps the Roommate due-check out of request-time flow; `/settings` now exposes a push opt-in switch and stores the browser subscription only when the user is signed in; the service worker handles incoming push and notification click events. Repo-wide verification passes: `python -m pytest -q` → **212 passed, 2 warnings**.

---

## Phase 16 — User Data Export, GDPR Account Lifecycle & Production Hardening

**Goal:** Honor user data sovereignty with one-click data exports, complete self-serve account deletion, and production containerization for secure web hosting.

**Why:** P6 (Durability) & P7 (Agency) — Users own their learning transcripts. In a hosted environment, they must be able to take all their data with them or erase it completely.

**Steps:**
1. **Full Data Export (`GET /settings/export`)**: Generate a clean downloadable ZIP archive containing the user's entire learning history: courses, interview transcripts, shelf sources, tutor transcripts, gap notes, and editor reviews in both JSON and Markdown formats.
2. **Account Deletion (`POST /settings/account/delete`)**: Atomic cascading deletion across all 11 tables for that user, purging encrypted keys and active sessions.
3. **Production Containerization**: Multi-stage `Dockerfile` and `docker-compose.yml` orchestrating the FastAPI application, PostgreSQL database, and Caddy reverse proxy with automatic HTTPS and HTTP/2.
4. **Security & Rate Limiting**: Integration of `slowapi` rate limiting on authentication and LLM endpoints; security headers (HSTS, CSP, X-Frame-Options, secure cookies).

**Constraints:** Zero orphaned data on deletion. Export must produce standard, readable Markdown files that the user can read in Obsidian, Notion, or any text editor.

**Definition of Done:** User can export and download their entire learning archive; account deletion is verified to wipe all user rows from the database; Docker containers build and launch successfully.

---

## Beyond Phase 16

Future capabilities (multi-topic Roommate cross-linking depth, spaced-repetition on gap notes, course export to EPUB/PDF, exam simulation) can be scheduled once the multi-tenant web platform is live and verified.
