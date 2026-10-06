# 02 — Architecture

## Stack decision (Multi-User, Web-Hosted & Mobile-First)

| Layer | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI (Async) | High performance, async I/O for non-blocking LLM/network calls, dependency injection for user authentication, readable and maintainable by coding agents. |
| Database | Dual Support: PostgreSQL (Production Web-Hosted) + SQLite (Local Dev & Testing) | PostgreSQL provides connection pooling, row-level locking, and concurrent write safety for multi-user web hosting. SQLite is preserved for zero-setup local development and rapid headless testing. Schema managed by Alembic. |
| Authentication | Native Email + Password with Secure Session Cookies | Standard, self-contained, zero vendor lock-in. Uses Argon2id password hashing and signed HttpOnly, SameSite=Lax/Strict session cookies. |
| Frontend | Mobile-First PWA + Server-rendered HTML + self-hosted htmx + "The Reading Room" CSS | Combines the warmth and calm of The Reading Room design tokens with mobile-first ergonomics (bottom navigation bar, touch-friendly targets, keyboard-aware scrolling) and Progressive Web App (PWA) installability (service worker, manifest.json, push notifications). |
| AI provider & Cost | Async OpenAI-compatible adapter (`httpx.AsyncClient`) + Hybrid/BYOK Model | Non-blocking async HTTP. Multi-tenant sustainability via a Hybrid/BYOK (Bring Your Own Key) model: users can save their own OpenRouter/OpenAI key (encrypted at rest via AES-GCM in settings), with an optional server-provided free trial quota. |
| Scheduling | Decoupled Background Scheduler (APScheduler / Worker Task) | Replaces synchronous dashboard-load checks with an asynchronous scheduler that evaluates Roommate cadence, updates streaks, and dispatches web push notifications without blocking page requests. |

---

## Multi-Tenant Data Model (Core Entities)

Every user has an isolated private university. All top-level queries filter by `user_id = current_user.id` to guarantee tenant isolation.

```
users
  id, email, password_hash, name,
  encrypted_ai_key (nullable, AES-GCM encrypted user BYOK key),
  ai_quota_used (integer count of server-paid LLM calls),
  created_at

course_groups       (A semester/track a Course can be filed into)
  id, user_id (FK → users.id), name, description,
  timeframe_mode (individual|uniform), timeframe_duration (free text),
  status (active|completed|archived), created_at

courses
  id, user_id (FK → users.id), title, destination, baseline, cut_list,
  status (active|draft|paused|archived|done),
  group_id (nullable FK → course_groups.id), created_at

topics              (A "week" or unit within a Course, in sequence order)
  id, course_id (FK → courses.id), user_id (FK → users.id),
  order_index, title, milestone_description, time_box,
  status (not_started|in_progress|done)

advisor_interviews  (The raw interview transcript for a Course)
  id, course_id (FK → courses.id), user_id (FK → users.id),
  question, answer, step (destination|baseline|sequencing|cut_list|milestones)

sources             (Librarian curated sources)
  id, user_id (FK → users.id), topic_id (nullable FK → topics.id),
  course_id (nullable FK → courses.id), label, url_or_reference,
  verdict (keep|skip|later|unverified), reason, added_at, verified_at (nullable)

tutor_sessions
  id, topic_id (FK → topics.id), user_id (FK → users.id),
  started_at, ended_at, gap_note

tutor_turns
  id, session_id (FK → tutor_sessions.id), user_id (FK → users.id),
  question, user_answer, order_index

editor_reviews
  id, topic_id (FK → topics.id), user_id (FK → users.id),
  milestone_ref, submitted_text, strengths, biggest_weakness, next_edit, created_at

roommate_prompts
  id, course_id (FK → courses.id), user_id (FK → users.id),
  field, prompt_text, created_at, user_reaction (optional free text),
  secondary_course_id (nullable FK → courses.id), connection_type (external|intra_group)

_dash_visits        (User dashboard visits for unread badge tracking)
  id, user_id (FK → users.id), visit_at

activity_log        (User activity log for streak and audit)
  id, user_id (FK → users.id), course_id (nullable FK → courses.id),
  entity_type, entity_id, action, is_user, created_at
```

---

## AI Role Implementation & Hybrid/BYOK Engine

Each ALTER role module (`advisor.py`, `librarian.py`, `tutor.py`, `editor.py`, `roommate.py`):
1. Owns **one system prompt** stored as a markdown file under `app/roles/prompts/`.
2. Calls the **async AI provider** (`await provider.generate(prompt, message)`).
3. Resolves the active API key per request:
   - If the user has a configured BYOK key: decrypts the user's key and uses their endpoint.
   - If the user has no BYOK key: verifies the user's `ai_quota_used < MAX_FREE_QUOTA`, increments the quota, and uses the server's master key.
   - If quota is exceeded and no BYOK key is set: raises a user-friendly `QuotaExceededError` directing them to Settings to add their key.
4. Preserves atomic, immediate persistence of all role interactions.

---

## Outbound Fetching Pattern (Async & SSRF Guarded)

1. **`app/fetching/` owns all outbound network I/O** via `httpx.AsyncClient` (`http.py`, `extract.py`, `youtube.py`).
2. **SSRF Defense**: Enforces http/https protocols only; checks all resolved DNS IP addresses against loopback, private, link-local, and reserved ranges; re-validates redirects; caps response payloads.
3. **Async Non-Blocking**: Fetching occurs asynchronously without blocking concurrent user web requests.

---

## Mobile-First PWA Architecture

1. **App Shell**: Desktop sidebar collapses to an ergonomic bottom navigation bar on mobile viewports (`< 768px`) with direct access to Courses, Insights, Groups, and Settings.
2. **Touch Ergonomics**: All interactive buttons, cards, and menu triggers adhere to a minimum 48×48px tap target with active state haptic/visual feedback.
3. **PWA Capabilities**:
   - `manifest.json` defining app icons, display mode (`standalone`), and theme colors.
   - Lightweight Service Worker caching static fonts, stylesheets, and HTMX scripts for instant load and offline resilience.
   - Web Push Notification integration for Roommate prompt notifications and streak nudges.

---

## Folder Layout

```
university-in-a-box/
├── alembic/                    # Database migrations (PostgreSQL & SQLite)
├── app/
│   ├── main.py                 # FastAPI app, lifespan, route registration
│   ├── auth/                   # Authentication & user session management
│   │   ├── security.py         # Password hashing (Argon2id), session crypto, BYOK encryption
│   │   └── dependencies.py     # get_current_user dependency injection
│   ├── db.py                   # Dual-engine connection pool (PostgreSQL / SQLite)
│   ├── models.py               # Data models & schemas
│   ├── ai/
│   │   ├── provider.py         # Async OpenAI-compatible adapter (httpx.AsyncClient)
│   │   ├── quota.py            # Hybrid/BYOK key resolver and quota tracker
│   │   └── config.py           # Environment config
│   ├── fetching/               # Async outbound reading (SSRF-guarded HTTP, extract, youtube)
│   ├── roles/                  # ALTER roles & data stores (filtered by user_id)
│   ├── routes/                 # Auth, courses, advisor, librarian, tutor, editor, roommate, settings
│   ├── scheduler/              # Decoupled background task runner for Roommate & notifications
│   ├── static/                 # CSS tokens, HTMX, fonts, PWA manifest, service worker
│   └── templates/              # Server-rendered HTML with mobile-first partials
├── data/                       # Local SQLite file & backups (gitignored)
├── tests/                      # Mirrors app structure; tests run with SQLite in-memory or file
├── docs/                       # Project documentation
├── memory-bank/                # Living project state
└── .env.example
```

---

## What this Architecture Explicitly Avoids
- **No heavy JavaScript framework**: Avoids React/Next.js/Vue build complexity; keeps all templating in Jinja2 + HTMX for maximum model-friendly maintainability.
- **No public social feed or marketplace**: Keeps each user's space private and sacred.
- **No cloud vendor lock-in**: Deployable to any standard Docker container, VPS, or cloud host.
