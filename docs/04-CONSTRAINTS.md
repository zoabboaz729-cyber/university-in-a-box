# 04 — Constraints

These are hard rules. "I thought it would be better this way" is not a valid reason to break
one — if a constraint genuinely seems wrong, raise it with the user and log the change in
`memory-bank/decisions.md` rather than silently overriding it.

## 1. Scope discipline
- Work only inside the current phase from `docs/03-BUILD-PLAN.md` / `memory-bank/progress.md`.
- Do not refactor a previous phase's working code as a side effect of building a new one,
  unless the new phase's steps explicitly call for it. If you notice something worth fixing,
  write it down (in `activeContext.md` under a "Noticed" section) instead of doing it now.
- Do not add a sixth "role" or a feature outside ALTER without the user explicitly asking.

## 2. Model-weakness mitigations (GLM-Flash-5.3 / DeepSeek V4, free tier)
These models are capable but do better on small, explicit, well-scoped tasks than on large,
ambiguous ones. Build accordingly:
- Prefer many small files over few large ones — aim to keep individual files short enough
  that the whole file's purpose fits in a short comment at the top.
- One responsibility per function/module. Avoid clever abstractions that require holding
  several files in mind at once to understand any one of them.
- Write explicit code over implicit "magic" (explicit SQL over deep ORM chains, explicit
  conditionals over dense one-liners).
- Before starting a task, restate in your own words (in `activeContext.md` or the session)
  what "done" looks like for it — this catches misunderstandings before code is written, not
  after.
- If a response from the LLM provider (in-app AI calls, not your own reasoning) comes back
  malformed or empty, handle it explicitly — retry once, then show the user a clear error.
  Never let a bad LLM response silently corrupt persisted data.
- Rate/quota limits are real on free tiers: batch or debounce in-app AI calls where
  reasonable (e.g., don't fire a request per keystroke), and fail gracefully with a visible
  message rather than a silent hang.

## 3. Data & persistence
- Every meaningful user action (interview answer, source added, tutor turn, editor
  submission, milestone completion) is persisted immediately, not batched until "session end."
- Never lose an in-progress Tutor session or Advisor interview if the app is closed midway —
  persist as you go, not only at completion.
- The SQLite file is the single source of truth. No feature should require the app to have
  been running continuously to make sense of the data.

## 4. No slop
- No fake or seeded data presented as if it were real user history in the shipped product.
  Seed data used for development must be clearly labeled and easy to wipe (e.g. a
  `scripts/seed_demo_data.py` that is never run automatically).
- No feature that "looks" done but doesn't actually persist, doesn't actually call the
  configured AI provider, or silently no-ops. If something is a stub, label it visibly as
  not-yet-implemented rather than presenting it as working.
- No copy-pasted placeholder text ("Lorem ipsum", "TODO: implement") left in anything the
  user-facing UI actually renders once a phase is marked done.

## 5. Security & config basics
- No API keys or secrets committed to the repo. `.env` is gitignored; `.env.example` holds
  only variable names and dummy values.
- The app is local/single-user by default — do not add network-exposed listeners beyond
  localhost without the user explicitly asking for remote access, and if that's ever asked
  for, treat it as a new phase with its own constraints, not a quick tweak.
- The one outbound-network capability is reading a source the user explicitly added (D-024).
  Keep it that way: all such I/O goes through `app/fetching/` behind its SSRF guards (http/https
  only; private/loopback/link-local/reserved addresses and unsafe redirects refused; size-capped;
  text truncated by code before it reaches the model). Never fetch a URL the model invented, never
  let a role module construct a request, and never let refusal paths become crashes.

## 6. Testing bar
- Every phase needs at least a minimal automated test that would fail if the phase's core
  behavior broke (see `docs/05-VERIFICATION.md` for the shape of this).
- LLM-dependent logic should be tested with the provider call mocked/stubbed — tests should
  not depend on a live API key to pass.

## 7. Documentation obligations
- Every session that changes product behavior, data model, or architecture updates the
  relevant `docs/` file the same session — not "in a follow-up."
- `memory-bank/activeContext.md` and `memory-bank/progress.md` are updated at the end of
  **every** session without exception, per `.clinerules`.
