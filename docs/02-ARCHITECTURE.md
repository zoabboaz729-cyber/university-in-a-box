# 02 — Architecture

## Stack decision (default — see `memory-bank/decisions.md` if this has changed)

| Layer | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | Small, explicit, huge amount of training data for the coding agent to draw on, easy to test with plain HTTP calls, no build step. |
| Database | SQLite, single file (`data/university.db`) | Zero setup, trivially backed up (copy one file), plenty for one user's data over years. |
| Frontend | Server-rendered HTML + self-hosted htmx + hand-crafted CSS design tokens (Direction A — The Reading Room: warm paper palette, self-hosted Source Serif 4 and Inter fonts, persistent sidebar, animated loading indicators, no build pipeline). | A small model reliably produces correct server-rendered templates; avoids heavy frontend bundlers while delivering an original, legible reading-room atmosphere with visual lag feedback. |
| AI provider | Pluggable adapter behind one interface (`app/ai/provider.py`), configured via `.env` | Keeps the five ALTER modules decoupled from *which* LLM API answers them. The coding-agent's own models (GLM-Flash-5.3 / DeepSeek V4) are a *development-time* tool inside Cline — the running app needs its own configured API key for whichever OpenAI-compatible endpoint the user points it at. Do not assume these are the same thing. |
| Scheduling (Roommate cadence, reminders) | No scheduler process at all: the due-check is a plain function run on dashboard load (`GET /` in `app/routes/dashboard.py`, on a short-join background thread) | Avoids a job-queue/cron dependency for a single-user local app — and nothing in the app depends on it having been running continuously. (There is no `/tasks/due` endpoint; that name appears in the Phase 6 plan as an example that was not built.) |

This is a deliberately boring stack. Do not upgrade it mid-build to chase a "better"
technology unless a real limitation has been hit and logged in `memory-bank/decisions.md`.

## Data model (core entities)

```
User (single row; local app, but keep the table so multi-profile is possible later)
  id, name, created_at

CourseGroup       (Phase 11 — a semester/track a Course can be filed into)
  id, user_id, name, description, timeframe_mode (individual|uniform),
  timeframe_duration (free text, e.g. "12 weeks"), status (active|completed|archived),
  created_at
                  (timeframe_mode 'uniform' means the group declares ONE shared duration:
                   it is displayed on group cards and pre-fills the Advisor's sequencing
                   answer for courses created inside the group — free text only, no
                   week-math; see D-022/D-023)

Course
  id, user_id, title, destination, baseline, cut_list, status (active|draft|paused|archived|done)
  group_id (nullable → course_groups.id; NULL = ungrouped), created_at

Topic            (a "week" or unit within a Course, in sequence order)
  id, course_id, order_index, title, milestone_description, time_box, status (not_started|in_progress|done)

AdvisorInterview  (the raw interview that produced a Course, for transparency/editability)
  id, course_id, question, answer, step (destination|baseline|sequencing|cut_list|milestones)

Source           (Librarian)
  id, topic_id (nullable), course_id (nullable), label, url_or_reference,
  verdict (keep|skip|later|unverified), reason, added_at, verified_at (nullable)
                (exactly ONE of topic_id / course_id is non-null — a source belongs to a
                 single Topic OR to the Course as a whole. verified_at is set only by a
                 read-and-judged check (D-024); NULL means unverified and is displayed as
                 such — the app never invents a keep/skip the user's source didn't earn.)

TutorSession
  id, topic_id, started_at, ended_at, gap_note

TutorTurn
  id, session_id, question, user_answer, order_index

EditorReview
  id, topic_id, milestone_ref, submitted_text, strengths, biggest_weakness, next_edit, created_at

RoommatePrompt
  id, course_id, field (the unrelated field it bridges to), prompt_text, created_at,
  user_reaction (optional free text), secondary_course_id (nullable), connection_type
                (connection_type is 'external' — one course → an unrelated field — or
                 'intra_group' — course A ↔ course B taken together in the same group,
                 where secondary_course_id names the other course; Phase 11)

_dash_visits      (single row, id fixed at 1; timestamp of the last dashboard visit —
  id, visit_at     powers the Roommate "new since your last visit" badge. Not user content.)

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

## Outbound fetching pattern (source verification — D-024)

The app has exactly one outbound-network capability: reading a source the user added. It follows
the same boundary rule as `app/ai/`:

1. **`app/fetching/` owns all network I/O** (`http.py` — SSRF-guarded HTTP; `extract.py` — HTML/PDF
   → plain text; `youtube.py` — transcripts). Deterministic code only; no LLM calls there.
2. **Routes own the fetch, roles own the judgment.** `fetch_source_text(url)` is the single entry
   point the Librarian routes call; the role module (`roles/librarian.py`) never constructs a
   request and is never handed a URL to fetch itself.
3. **An unreadable source is a normal outcome, not an exception.** Every fetch returns a
   structured result (`ok`, `kind`, `text`, `reason`); refusals, HTTP errors, unreadable PDFs, and
   missing transcripts all come back with a user-facing reason the route shows verbatim.
4. **Guards stay in code, not in prompts:** http/https only, every resolved address checked
   against private/loopback/link-local/reserved ranges, redirects re-validated, size-capped, and
   the fetched text truncated by code before it reaches the model.

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
│   ├── fetching/               # outbound source reading (SSRF-guarded HTTP, extract, youtube)
│   ├── roles/
│   │   ├── advisor.py / librarian.py / tutor.py / editor.py / roommate.py
│   │   ├── group_store.py / course_store.py / course_manage.py   # course + group persistence
│   │   ├── interview_store.py / source_store.py / tutor_store.py / review_store.py
│   │   ├── roommate_store.py / dashboard.py / activity.py
│   │   └── prompts/             # one .md per role (plus librarian_verify.md, roommate_intra.md)
│   ├── routes/                  # one file per module (dashboard, courses, groups, advisor,
│   │                            #  advisor_review, librarian, tutor, editor, roommate, settings)
│   ├── static/                  # self-hosted CSS, htmx, woff2 fonts
│   └── templates/               # server-rendered HTML; shared partials use a _ prefix
│                                #  (_course_menu.html = the ⋮ menu, _sources.html = source rows)
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
