# 01 — Vision

## Who this is for
Originally conceived for a single self-hosted learner, the system is evolving to support
**many learners** via a **web-hosted, web-and-mobile-first** platform. Each user gets their
own isolated private university, maintaining the same depth, personal agency, and durable
memory over months and years.

## The core loop
1. User tells the Advisor a topic → gets a personalized, staged curriculum (a **Course**
   made of **Weeks/Topics**, each with a **Milestone**).
2. For each topic, the Librarian helps assemble a short, trusted **Shelf** of sources.
3. The user studies, then opens a **Tutor session** on that topic to actually test
   understanding, one question at a time.
4. When the user produces something (an answer, a summary, a decision, a project artifact),
   the Editor reviews it against the milestone's bar.
5. On a cadence (not only on demand), the Roommate drops an unrelated-domain connection tied
   to whatever the user is currently studying, to build range.
6. All of this is visible on a **Dashboard**: active courses, this week's milestone, streak,
   last Tutor gap, last Editor note, next Roommate prompt.

This loop has to survive being abandoned for three weeks and picked back up — nothing about
it should require the user to remember context the app itself already has.

## ALTER → concrete modules

### Advisor
- Entry point: "I want to learn X."
- Runs a structured interview, one question at a time, covering: destination, baseline,
  sequencing, cut list, milestones (mirrors the five decisions the source material names).
- Output: a persisted **Course** record with ordered **Topics**, each with a milestone
  description and a rough time box. Editable after creation — curricula are not fixed for life.
- The interview itself is stored (not just its output), so the user can see *why* the
  curriculum looks the way it does.

### Librarian
- Attached to a Course or a single Topic.
- The user adds candidate sources (a link, a note about a book, a paper, a video).
- For each source, the Librarian records: what it's good for, a credibility/fit judgment,
  and a keep/skip/later verdict — with a one-line reason, not just a star rating.
- Produces a short **Shelf** per topic: the handful of sources actually worth the user's
  time, not an ever-growing bookmark pile.

### Tutor
- Started against a specific Topic (needs a Shelf or at least a stated baseline to probe).
- One question at a time. Waits for the user's answer. Follows up based on what was actually
  said. Never delivers a lecture in place of a question.
- Each session is logged: the questions, the user's answers, and a short **gap note** — the
  specific thing the session revealed the user doesn't yet have solid.
- Gap notes feed back into the Course (e.g., surfaced on the dashboard, or nudging the next
  Tutor session to start there).

### Editor
- Takes a piece of user-produced output (typed in, or pasted) tied to a Milestone.
- Gives structured feedback: what's strong, the single biggest weakness, one concrete next
  edit — not a wall of generic praise.
- Each review is logged against the Milestone, and a Milestone can be marked complete only
  after at least one Editor pass (configurable, but this is the default).

### Roommate
- Runs on a cadence (e.g., a couple of times a week) tied to the user's active Course(s).
- Surfaces one short prompt connecting the current topic to an unrelated field, and logs it
  to a lightweight **Insights journal** the user can scroll back through.
- Deliberately low-friction: reading it should take seconds; engaging further is optional.

## What success looks like at the product level
- The user opens the app on most days it's relevant, not just once, whether on their phone or desktop.
- Courses started are more often finished (or deliberately archived) than abandoned mid-way
  without a trace — the app should make it obvious when something has stalled.
- The user can point at concrete Tutor gap notes and Editor reviews as evidence of actual
  understanding, not just "I read some stuff."
- Picking the project back up after a gap (for the user *or* the coding agent) takes minutes,
  not a re-read of everything.
- Multi-user isolation is rock solid: zero possibility of leaking learning transcripts or API keys between learners.

## Explicit non-goals (do not build these unless the user asks)
- Not a public course marketplace or content aggregator — the app organizes and tests, it does not
  supply pre-made courses.
- Not a general-purpose chatbot — every AI interaction happens through one of the five ALTER
  roles, with its own persisted structure, not a free-form chat box bolted onto everything.
- Not a bloated native mobile app build pipeline — we use a lightweight, responsive, installable
  Progressive Web App (PWA) shell preserving our clean Jinja2/HTMX server-rendered stack.
