# AGENTS.md — Master Guide for the Coding Agent

Read this file once, fully, the first time you ever touch this repo. After that, `.clinerules`
plus `memory-bank/activeContext.md` are enough for routine sessions — come back here whenever
you need the reasoning behind a rule, not just the rule.

## 1. What this project is

**University in a Box** is a personal, self-hosted application that turns an idea from a
YouTube video — that a single person can use AI to build themselves a private university —
into daily, working software. The idea is organized as five AI "roles," nicknamed **ALTER**:

- **A — Advisor**: interviews the user and builds a personalized curriculum (destination,
  baseline, sequencing, what to skip, milestones), instead of the user having to already know
  what to ask for.
- **L — Librarian**: helps the user gather and triage sources for a topic — which ones are
  credible and worth the time, which are noise — instead of the user drowning in an open feed.
- **T — Tutor**: runs one-on-one Socratic sessions on a specific topic — one question at a
  time, finds the gap in understanding, never lectures — instead of passively explaining.
- **E — Editor**: reviews something the user actually produced (an answer, a write-up, a
  decision) and gives structured critique, instead of vague encouragement.
- **R — Roommate**: surfaces connections between the user's topic and unrelated fields, to
  build range and fresh perspective, instead of only going deeper in one lane.

The full reasoning for each role, and why the app is structured this way, is in
`docs/00-PRINCIPLES.md` and `docs/01-VISION.md` — read those before writing any product code.

## 2. Your role as the coding agent

You are building real, durable software the user will open most days for months. That
changes what "done" means:

- It must survive being closed and reopened tomorrow — everything meaningful is persisted.
- It must survive a bad session from you — hence the memory-bank protocol below.
- It must resist becoming a demo. A demo is impressive once. This has to still be useful in
  month six. Prefer boring, working, and simple over clever and fragile.

You are not just executing tickets — you are also the keeper of the project's shape. If a
requested change would quietly break a principle in `docs/00-PRINCIPLES.md`, say so before
doing it, even if the user didn't ask.

## 3. The session protocol (why `.clinerules` says what it says)

You have no memory across sessions. The repo *is* your memory. Two files carry the weight:

- `memory-bank/activeContext.md` — "where am I, right now, and what's next." This is what
  makes the project self-explanatory: the user's plan is to simply say "look at the project
  and continue" — this file is what makes that possible. If it is stale, wrong, or vague, the
  whole system breaks. Guard it.
- `memory-bank/progress.md` — "what already works, what doesn't yet." Prevents you from
  re-building something that already exists, or claiming something works when it doesn't.

Everything else in `memory-bank/` (`projectbrief.md`, `productContext.md`,
`systemPatterns.md`, `techContext.md`, `decisions.md`) is slower-moving context — read it
when you need the *why* behind the current state, not every session.

## 4. How to navigate the rest of the docs

| File | Read it when... |
|---|---|
| `docs/00-PRINCIPLES.md` | Before any product decision. This is the constitution — it outranks convenience. |
| `docs/01-VISION.md` | Before building any ALTER module, to know what it must actually do. |
| `docs/02-ARCHITECTURE.md` | Before writing code — stack, data model, folder layout, how AI roles are implemented. |
| `docs/03-BUILD-PLAN.md` | To know the current phase, its goal, its steps, and its constraints. |
| `docs/04-CONSTRAINTS.md` | Anytime you're unsure if something is allowed — scope limits, model-weakness rules, safety basics. |
| `docs/05-VERIFICATION.md` | Before marking any task "done." |
| `docs/06-MONITORING.md` | When building the usage-dashboard/health features, and for your own weekly self-check ritual. |

## 5. Non-negotiable rules (see `docs/04-CONSTRAINTS.md` for the full list)

1. One phase at a time, in order, per `docs/03-BUILD-PLAN.md` — unless `activeContext.md`
   explicitly says the user redirected you.
2. Every task ends with a `memory-bank` update. No exceptions, even for "small" changes.
3. Nothing is "done" without passing `docs/05-VERIFICATION.md`'s checklist for that item.
4. Keep the codebase small-model-friendly: short files, one responsibility per module, no
   cleverness that isn't explained in a comment. See `docs/04-CONSTRAINTS.md` §2.
5. Never hardcode secrets. Never fabricate data and present it as real user progress.

## 6. When you're stuck or the request is ambiguous

Do not silently pick an interpretation and run with it for anything that affects product
behavior, data model, or scope. Instead:
1. Write the open question into `memory-bank/activeContext.md` under **Open Questions**.
2. Ask the user directly, in plain language, with your best-guess default stated.
3. If the user is not available and the ambiguity is only *implementation* detail (not
   product behavior), pick the option that is simplest and most reversible, note it as a
   decision in `memory-bank/decisions.md`, and move on.

## 7. Living documentation — this is a requirement, not a courtesy

This whole doc set is meant to evolve with the project. When you learn something that
changes a principle, a data model choice, or a phase's plan, **update the relevant doc in
the same session**, not "later." A documentation set that describes a version of the app
that no longer exists is worse than no documentation.
