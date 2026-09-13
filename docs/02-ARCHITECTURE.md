# 02 — Architecture

## Stack decision (default — see `memory-bank/decisions.md` if this has changed)

| Layer | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | Small, explicit, huge amount of training data for the coding agent to draw on, easy to test with plain HTTP calls, no build step. |
| Database | SQLite, single file (`data/university.db`) | Zero setup, trivially backed up (copy one file), plenty for one user's data over years. |
| Frontend | Server-rendered HTML + HTMX + minimal CSS (no build pipeline) | A small model reliably produces correct server-rendered templates; a full SPA (React/Vue state management, bundlers) is a much easier place for a weak model to introduce subtle, hard-to-diagnose bugs. Add a proper frontend framework later only if this genuinely becomes limiting — see `docs/04-CONSTRAINTS.md` on scope discipline. |
| AI provider | Pluggable adapter behind one interface (`app/ai/provider.py`), configured via `.env` | Keeps the five ALTER modules decoupled from *which* LLM API answers them. The coding-agent's own models (GLM-Flash-5.3 / DeepSeek V4) are a *development-time* tool inside Cline — the running app needs its own configured API key for whichever OpenAI-compatible endpoint the user points it at. Do not assume these are the same thing. |
| Scheduling (Roommate cadence, reminders) | A simple in-process scheduler checked on app load / a `/tasks/due` endpoint hit by a cron-like mechanism | Avoids pulling in a heavy job-queue system for a single-user local app. |

This is a deliberately boring stack. Do not upgrade it mid-build to chase a "better"
technology unless a real limitation has been hit and logged in `memory-bank/decisions.md`.

## Data model (core entities)

```
User (single row; local app, but keep the table so multi-profile is possible later)
  id, name, created_at

Course
  id, user_id, title, destination, baseline, cut_list, status (active|draft|paused|archived|done)
  created_at

Topic            (a "week" or unit within a Course, in sequence order)
  id, course_id, order_index, title, milestone_description, time_box, status (not_started|in_progress|done)

AdvisorInterview  (the raw interview that produced a Course, for transparency/editability)
  id, course_id, question, answer, step (destination|baseline|sequencing|cut_list|milestones)

Source           (Librarian)
  id, topic_id, label, url_or_reference, verdict (keep|skip|later), reason, added_at

TutorSession
  id, topic_id, started_at, ended_at, gap_note

TutorTurn
  id, session_id, question, user_answer, order_index

EditorReview
  id, topic_id, milestone_ref, submitted_text, strengths, biggest_weakness, next_edit, created_at

RoommatePrompt
  id, course_id, prompt_text, created_at, user_reaction (optional free text)

ActivityLog       (for the Monitoring/dashboard — see docs/06-MONITORING.md)
  id, course_id, entity_type, entity_id, action, is_user, created_at
                (course_id + is_user make "days since activity" and the
                 Phase 7 streak computable in one query line — D-015;
                 entity_type/entity_id are honest entity references)
```

Keep every table this simple. Resist adding speculative columns "for later" — extend when a
phase in `docs/03-BUILD-PLAN.md` actually needs it, and note the migration in
`memory-bank/decisions.md`.

## AI role implementation pattern

Each ALTER role is its own module under `app/roles/` (`advisor.py`, `librarian.py`,
`tutor.py`, `editor.py`, `roommate.py`). Each module:

1. Owns **one system prompt**, stored as its own text file under `app/roles/prompts/`, not
   inlined in Python — this is what makes the prompts editable and reviewable independent of
   code, and what "living documentation for the AI's own behavior" means in practice.
2. Exposes a small, typed function (e.g. `advisor.next_question(course, history) -> Question`)
   that the FastAPI routes call — routes should never construct role logic inline.
3. Writes its own persisted output through the data model above — never leaves the only
   record of a role's work sitting in an LLM response that scrolls away.
4. Is testable independent of the LLM: given a fixed fake response, does the surrounding code
   (routing, persistence, rendering) behave correctly? Mock the LLM call in tests.

Each prompt file should encode the *behavioral contract* from `docs/01-VISION.md` explicitly
(e.g. the Tutor prompt must instruct one question at a time and forbid lecturing) — write
these deliberately, don't let a generic "be a helpful tutor" prompt drift in.

## Folder layout (target — build it incrementally per the phases in 03-BUILD-PLAN.md)

```
university-in-a-box/
├── app/
│   ├── main.py                 # FastAPI app, route registration
│   ├── db.py                   # SQLite connection/session handling
│   ├── models.py                # data model (see above)
│   ├── ai/
│   │   ├── provider.py         # pluggable LLM adapter interface
│   │   └── config.py           # reads .env for provider/key/model
│   ├── roles/
│   │   ├── advisor.py / librarian.py / tutor.py / editor.py / roommate.py
│   │   └── prompts/             # one .txt or .md per role
│   ├── routes/                  # one file per module (dashboard, courses, tutor, ...)
│   └── templates/               # HTMX-driven server-rendered HTML
├── data/                        # SQLite file + backups live here (gitignored)
├── tests/                        # mirrors app/ structure
├── docs/                          # this folder
├── memory-bank/                    # living project state
└── .env.example
```

## What this architecture explicitly avoids and why
- No microservices — one process, one user, no need for the operational overhead.
- No heavy frontend framework — see stack table above.
- No ORM abstraction layer beyond simple, explicit SQL or a thin helper — a weak model
  writing raw, readable SQL is more debuggable than one fighting an ORM's magic.
- No premature multi-user support — would complicate the data model and auth for no current
  benefit; note it as a possible future direction in `memory-bank/decisions.md` instead.
