# University in a Box

A personal, self-hosted app that turns AI into five roles you can lean on to teach yourself
almost anything, for real, over months — not a chat window, an actual system with memory:

- **Advisor** — interviews you and builds a personalized curriculum.
- **Librarian** — helps you triage sources instead of drowning in them.
- **Tutor** — tests your understanding one question at a time, no lecturing.
- **Editor** — gives real feedback on things you actually produce.
- **Roommate** — nudges you toward unrelated ideas so your thinking doesn't get narrow.

## How to resume work with the coding agent
Open this repo in Cline and say something like:

> Look at the project — it should be self-explanatory what's been done, where we are, and
> what's next. Continue from there.

That works because `memory-bank/activeContext.md` and `memory-bank/progress.md` are kept
up to date at the end of every session — see `.clinerules` and `AGENTS.md` for exactly how.

## Where things live
- `AGENTS.md` — start here if you're the coding agent and this is your first time in the repo.
- `docs/` — principles, vision, architecture, the phased build plan, constraints,
  verification, and monitoring. Numbered in reading order.
- `memory-bank/` — the living, constantly-updated project state. This is what makes the
  project resumable from any point without re-explaining anything.
- `app/` — the actual application code (built up phase by phase — see `docs/03-BUILD-PLAN.md`).
- `data/` — the SQLite database and backups. Not committed to version control.

## Running it locally

```
python -m venv .venv && .venv\Scripts\activate   (Windows)
python -m venv .venv && source .venv/bin/activate   (macOS/Linux)
pip install -r requirements.txt
copy .env.example .env   (Windows) / cp .env.example .env   (macOS/Linux)
uvicorn app.main:api --reload   (or app.main:app — both point at the same app)
```

Open http://127.0.0.1:8000. The dashboard lists every confirmed course
(newest first, with status, current topic, and days-since-activity) and
is the entry point to the Advisor: pick a topic, answer the five-question
interview (one question at a time — answers persist immediately), review
the draft curriculum (edit boxes + regenerate), then confirm to start the
Course. You land on the course page (`/courses/<id>`), which lists the
ordered topics with their milestones and survives closing and reopening
the app. `data/university.db` is created with all tables on first boot;
failed LLM calls and unhandled errors are logged to `data/app.log`.

The Roommate (Phase 6) drops one short cross-domain "fresh connection" line
on the dashboard on a cadence — every 3 days per active course by default
(`ROOMMATE_CADENCE_DAYS` in `.env`). Every prompt is logged to the Insights
journal at `/roommate`, where you can jot an optional reaction to each one.

The Settings page (nav link on every page) shows the masked API key
(read-only — the same `AI_API_KEY` the provider uses), the Roommate cadence
and per-course pause default (both editable, persisted to `.env`), plus the
DB path and how stale the newest `data/university.db.backup-*` file is.

## Test

```
python -m pytest -q
```

## Backing up your data
Your entire learning history lives in one file: `data/university.db`. Backup this file
periodically using your OS file manager, or one command:

**Windows (PowerShell):**
```
Copy-Item data/university.db -Destination "data/university.db.backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

**macOS/Linux:**
```
cp data/university.db data/university.db.backup-$(date +%Y%m%d-%H%M%S)
```

You can also find a "Settings" link in the nav on every page — it shows the masked
API key, Roommate cadence, per-course pause default, the DB path, and how stale the
newest backup is. Suggested backup routines live in `docs/06-MONITORING.md`.
