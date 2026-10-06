# Tech Context

*Update when dependencies, dev setup, or technical constraints change.*

## Technologies (Multi-User, Web-Hosted & Mobile-First)
- Python + FastAPI (async backend/routing, dependency injection for auth)
- Dual-Database: PostgreSQL for web-hosted production with connection pooling (`psycopg` / `asyncpg` / SQLAlchemy Core) and Alembic migrations; SQLite (`data/university.db`) maintained for local dev and fast headless testing.
- Server-rendered HTML + self-hosted htmx 2.0.4 + hand-crafted CSS design tokens (`app/static/style.css`, The Reading Room aesthetic).
- Mobile-First PWA: Web App Manifest (`manifest.json`), service worker (`sw.js`) for static caching, bottom navigation bar on mobile viewports (< 768px), touch-friendly targets, and push notification infrastructure.
- Authentication & Security: Native Email + Password with Argon2id (`argon2-cffi`), signed HttpOnly session cookies (`itsdangerous`), and AES-GCM encryption for user BYOK keys.
- AI Provider & Cost: Async OpenAI-compatible adapter (`httpx.AsyncClient`) with Hybrid/BYOK model: encrypted user keys in settings, with server fallback/free trial quota tracker.
- Decoupled Scheduler: Background task worker (APScheduler / async worker) for Roommate cadence checks and push notifications.

## Dev setup
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Dependencies

- Current: `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `jinja2>=3.1`, `httpx>=0.27`, `pytest>=8.0`, `python-multipart>=0.0.18`, `youtube-transcript-api>=1.0`, `pypdf>=4.0`.
- Roadmap (Phases 12–16): `argon2-cffi` (password hashing), `itsdangerous` (session cookie signing), `cryptography` (AES-GCM for BYOK keys), `alembic` + `psycopg[binary]` / `asyncpg` (PostgreSQL production), `slowapi` (rate limiting).

## Known constraints
- Multi-tenant data isolation invariant: every query reading/mutating learning data must filter on `user_id = current_user.id`.
- Dual-database compatibility: raw SQL or query builders must remain compatible with both PostgreSQL and SQLite.
- PWA must retain the zero-build-step server-rendered Jinja2/HTMX stack — no React/Next.js overhead.
- Rate/quota limits on AI endpoints: free trial quotas tracked strictly; BYOK keys encrypted at rest.

## Open technical questions
- Dual-DB abstraction helper: thin SQLAlchemy Core or explicit dual-dialect SQL wrapper in `app/db.py` to preserve raw SQL debuggability (P8).
- Push notification service: VAPID-based Web Push with browser push services.
