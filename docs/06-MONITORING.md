# 06 — Monitoring

Two different things need monitoring here, and they're easy to conflate: whether **the
user's learning** is actually progressing, and whether **the project itself** (the codebase,
the coding agent's work) is staying healthy and on track. Both matter for a tool meant to
last years.

## A. In-app monitoring (built in Phase 7, informed from Phase 2 onward)

**Activity log** — every meaningful action (interview step, source added, tutor turn,
editor review, milestone completion, roommate prompt) writes an `ActivityLog` row. This is
the raw material for everything below; start writing to it from Phase 2, don't retrofit it
at the end. Each row carries its owning `course_id` and an `is_user` flag (D-015): "days
since activity" (and the Phase 7 streak) count only `is_user = 1` rows, so a
system-generated Roommate prompt never makes a course look studied.

**Dashboard signals** (what the user should be able to see at a glance):
- Streak / days-since-last-activity per Course — makes stalling visible instead of silent.
  This is a direct answer to the dropout problem the project is built to counter: a Course
  quietly going untouched for weeks should be *visible*, not hidden until the user
  remembers it exists.
- Most recent Tutor gap note per active Topic — surfaces exactly what's shaky right now.
- Milestones completed vs. total, per Course — a concrete progress bar, not a vibe.
- Latest Roommate prompt (the dashboard's "Fresh connection" block, per D-014 —
  no separate read state; the newest prompt is the current one).

**Error visibility** — any failed LLM call, DB error, or unhandled exception is
logged to `data/app.log` (via `app/monitor.py`), or stdout in containerized production.
In multi-tenant mode, error logs must include `user_id` when authenticated for auditability,
while masking sensitive credentials and BYOK keys. Failures for one tenant (such as an invalid
BYOK key or quota limit) must remain isolated and never affect other tenants.

**Backup health** — in local development, Settings shows the age of the newest
`data/university.db.backup-*` file. In web-hosted production with PostgreSQL, automated
database snapshot routines (e.g., `pg_dump` cron jobs or managed cloud backups) must be
verified, and the health status displayed in the admin or system settings overview.

## B. Project-level monitoring (the coding agent monitoring itself)

This is what `memory-bank/` is for, beyond just "resuming work":

- `memory-bank/progress.md` is the ground truth for **what phase we're actually on** —
  treat any mismatch between this file and what's actually implemented as a bug in the
  documentation to fix immediately, not a minor inconsistency to shrug off.
- `memory-bank/decisions.md` is an audit trail — if the project's direction seems to have
  drifted from `docs/00-PRINCIPLES.md`, this log is where to look for when and why.
- Re-reading `docs/00-PRINCIPLES.md` periodically (at minimum, at the start of every new
  phase) is the drift check: does the current state of the app still do what P1–P8 describe,
  or has convenience quietly eroded one of them?

## Suggested weekly health-check ritual (for the user, and for the agent when asked to do one)
1. Open the dashboard — does every active Course look correct? Any stuck at zero activity
   for a long stretch?
2. Skim `memory-bank/progress.md` — does it match what actually works when clicked through?
3. Skim the last few `decisions.md` entries — any decision that, in hindsight, should be
   revisited?
4. Check the backup timestamp on Settings.

This ritual is deliberately short — a monitoring habit that's expensive to run doesn't get
run. Keep it that way even as the app grows.
