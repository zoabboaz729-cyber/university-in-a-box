# 05 — Verification

"Done" is not a feeling — it's a checklist passed. Use this before marking any task, Topic,
or Phase complete in `memory-bank/progress.md`.

## Definition-of-done checklist (use for every task)
- [ ] **Functional:** the feature works end to end, manually walked through, not just
      "the code looks right."
- [ ] **Persistence:** stop the app, restart it, confirm the result is still there and
      correct — not just present in the current in-memory session.
- [ ] **Principle check:** does this behave the way `docs/00-PRINCIPLES.md` /
      `docs/01-VISION.md` describe for this role, specifically — not a generic version of it?
      (e.g. for Tutor: did it actually ask one question and wait, rather than explain?)
- [ ] **Regression:** did anything from an earlier phase break? Spot-check the phases listed
      in the regression checklist below that touch the same area.
- [ ] **No slop:** no stub, no fake data, no placeholder text left in what the user sees.
- [ ] **Docs updated:** `memory-bank/activeContext.md` and `memory-bank/progress.md`
      reflect the new state; any relevant `docs/` file matches reality.

Do not mark something done in `progress.md` until every applicable box above is genuinely
checked — a task with three checked boxes and three quietly skipped ones is not done.

## Per-role manual verification scripts

**Advisor** — Start a fresh Course for a topic you don't already have one for. Confirm: only
one question shown at a time; all five steps (destination, baseline, sequencing, cut list,
milestones) are actually asked; the resulting Course has ordered Topics with milestone text
that clearly reflects your answers, not generic boilerplate.

**Librarian** — On a Topic, add three sources: one obviously strong, one obviously weak, one
ambiguous. Confirm each gets a verdict with a real one-line reason (not a repeated stock
phrase), and the Shelf view shows only the `keep` ones.

**Tutor** — Start a session. Confirm: exactly one question appears; after you answer (even
answer incorrectly on purpose), the next question responds to what you actually said, not a
fixed script; ending the session produces a gap note that reflects the actual weak point you
showed, not a generic summary.

**Editor** — Submit something genuinely flawed on purpose. Confirm the review names a real,
specific biggest weakness (not vague praise) and gives one concrete next edit you could
actually act on. Confirm the Topic cannot be marked done without this review existing.

**Roommate** — Trigger the due-check (or wait for the cadence). Confirm the prompt actually
connects the Course's subject to something genuinely unrelated, and it's logged to the
journal and still there after a restart.

## Regression checklist (run at the end of every phase, and fully in Phase 8)
1. Create/open a Course from Phase 1 flow — still works.
2. Dashboard (Phase 2) still lists it correctly, with correct status.
3. Add a source (Phase 3) — Shelf still filters correctly.
4. Run a Tutor session (Phase 4) — still persists mid-session.
5. Submit an Editor review (Phase 5) — Topic-done gating still enforced.
6. Roommate prompt (Phase 6) — still fires on schedule and logs.
7. Restart the app entirely between each of the above — nothing resets or corrupts.

## Multi-Tenant & Web/Mobile Verification Checklist (Phases 12–16)
1. **Tenant Isolation**: Register User A and User B. Create courses, sources, and tutor sessions under User A. Log in as User B: confirm dashboard, sidebar, courses list, and groups are completely empty. Attempt to access `/courses/{user_a_course_id}` directly as User B → returns clean 404.
2. **Auth & Sessions**: Registration, login, logout, and protected route redirection to `/login` when unauthenticated. Verify session cookie has `HttpOnly` and `SameSite` flags.
3. **Dual-Database Parity**: Verify the entire test suite passes against SQLite (`data/university.db`) and against a PostgreSQL instance via `DATABASE_URL`.
4. **Hybrid/BYOK Quota Check**: Set user BYOK key in `/settings`; verify LLM calls use the decrypted key. Clear key; verify server-provided free quota increments with each call and renders clear `QuotaExceeded` message once the limit is reached.
5. **Mobile Viewport & PWA Check**: Emulate mobile viewport (`< 768px`) in Chrome/Safari: confirm bottom navigation bar renders with touch targets ≥ 48px; confirm course 3-dots actions open bottom sheet; check `manifest.json` loads cleanly; verify Service Worker registers and caches static assets.
6. **Data Sovereignty (P6/P7)**: In `/settings`, trigger Data Export (`GET /settings/export`) → confirms generated ZIP contains complete readable Markdown and JSON files. Trigger Account Deletion (`POST /settings/account/delete`) → confirms all user rows are deleted atomically across all 11 tables.

## Self-verification discipline for the coding agent
Because the coding agent (GLM-Flash-5.3 / DeepSeek V4) can be confidently wrong, prefer
*showing* verification over *asserting* it:
- When claiming a test passes, show the actual command and output, not just "tests pass."
- When claiming persistence works, describe the actual restart-and-recheck you did.
- When unsure whether behavior matches a principle, quote the specific principle line next
  to what the feature actually does, and compare them explicitly.
