# Tech Context

*Update when dependencies, dev setup, or technical constraints change.*

## Technologies (default — see docs/02-ARCHITECTURE.md for rationale)
- Python + FastAPI (backend/routing)
- SQLite (single-file database, `data/university.db`)
- Server-rendered HTML + self-hosted htmx 2.0.4 + hand-crafted CSS design tokens (`app/static/style.css`, Direction A — The Reading Room: warm paper palette, self-hosted Source Serif 4 and Inter woff2 fonts, persistent course sidebar, animated loading indicators, no build pipeline). Static assets mounted at `/static`.
- An OpenAI-compatible LLM API for the app's runtime AI features, configured via `.env`
  (provider/model/key — owner decision 2026-09-09, see D-006: default = OpenRouter
  with a `:free` model; any OpenAI-compatible endpoint works by changing the same
  four vars). Since the Phase 7 completion pass the Settings page (`/settings`) shows
  the masked key read-only (the SAME `AI_API_KEY` the provider uses — it never accepts
  a key for editing, only cadence + the per-course pause default are editable there)

## Dev setup (verified as of Phase 1c)
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Dependencies

- `requirements.txt`: fastapi>=0.110, uvicorn[standard]>=0.29, jinja2>=3.1,
  httpx>=0.27, pytest>=8.0, python-multipart>=0.0.18 (form parsing for the
  interview POSTs; added Phase 1b), youtube-transcript-api>=1.0 + pypdf>=4.0
  (Stage 3 source fetching: YouTube transcripts + PDF text extraction).
  Verified installed: pytest 9.1.1 (plus current
  fastapi/starlette/jinja2/httpx from pip cache) on Python 3.14, 2026-09-09.
- No python-dotenv: `app/ai/config.py` parses `.env` with the stdlib only.
- Outbound fetching lives in `app/fetching/` (http + extract + youtube) with
  SSRF guards; routes own the fetch, roles own the judgment (D-024).
- `pypdf` and `youtube-transcript-api` are installed in `.venv` and were
  import-exercised by the full suite on 2026-09-16 (215 passed) — a missing
  one would fail collection, not just a fetch test.

## Known constraints
- Coding done via Cline with free-tier models (GLM-Flash-5.3, DeepSeek V4) — see
  `docs/04-CONSTRAINTS.md` §2 for how this shapes code style and task sizing.
- Runtime AI provider likely also free/low-cost tier — expect rate limits; the app must
  degrade gracefully (see `docs/04-CONSTRAINTS.md` §2 and `docs/06-MONITORING.md`).
- Local-first, single machine — no assumption of always-on hosting or multiple devices
  unless the project owner asks for that later.

## Open technical questions
- RESOLVED 2026-09-09 (see D-006): default runtime provider = OpenRouter
  (OpenAI-compatible, free `:free` models). The Phase 7 completion pass kept key/model
  switching as a `.env` edit (the Settings page shows the masked key read-only and only
  persists cadence + pause default) — no pending choice here either.
