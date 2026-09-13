# 00 — Principles

These are the load-bearing beliefs behind this project. Every architecture choice, every
phase in the build plan, and every feature decision should trace back to one of these. When
two things this document could plausibly support are in tension, use the **priority order**
at the bottom to break the tie.

## P1 — Personalization beats generic content
A curriculum that fits nobody in particular is worth little. The Advisor exists because
"teach me corporate finance" is a bad prompt — an interview that establishes destination,
current baseline, sequencing, what to skip, and how success will be measured is what turns
a topic into a plan a specific person can actually follow.
*Implication:* every course the app produces is generated through the interview, never a
static template the user just picks off a shelf.

## P2 — Curation is a first-class feature, not a nice-to-have
Most people cannot reliably tell credible material from noise — this is not a knock on
intelligence, it's a known, measurable gap. An app that just hands the user a search box is
reproducing the exact problem it's meant to solve.
*Implication:* the Librarian module must actively help the user narrow a pile of sources
down to a short, trusted shelf per topic — it does not just store links.

## P3 — Understanding is tested, not assumed
Reading or watching something is not the same as understanding it. One-on-one tutoring —
one question at a time, finding the actual gap, refusing to move on until it clicks — is
what closes that gap, and it used to be unaffordable at scale.
*Implication:* the Tutor never lectures. It asks a question, waits for the user's real
answer, and adapts the next question to what was actually said — not a script.

## P4 — Feedback loops beat one-shot output
Producing something and never having it examined means errors compound silently. Good
feedback is specific, timely, and tied to something the user actually produced.
*Implication:* the Editor only works on real user output (an answer, a milestone
submission, a decision) — never on hypothetical or unsubmitted work.

## P5 — Range is deliberately engineered, not left to chance
Depth in one lane makes someone competent; unrelated exposure is what makes their thinking
original. This has to be scheduled and nudged, because nobody does it on their own.
*Implication:* the Roommate proactively surfaces a cross-domain connection on a cadence —
it is not just a mode the user has to remember to invoke.

## P6 — The system must outlast a single session's motivation
Most people who start an open course never finish it. A tool that only helps while the
user is already motivated hasn't solved anything.
*Implication:* progress, milestones, and state must be durable and visible, so picking the
project back up after a gap costs the user (and the agent) almost nothing.

## P7 — Agency stays with the user
The AI scaffolds; it does not decide the destination or do the learning for the user. The
app's job is to make starting and continuing easier, never to replace the user's own
judgment or effort with its own.
*Implication:* every module ends by handing control back — a question, a next step, a
decision for the user to make — never a final verdict presented as unquestionable truth.

## P8 — Build for a small model, not an ideal one
The coding agent building this (GLM-Flash-5.3 / DeepSeek V4, free-tier) is capable but not
infallible, and works best on small, well-scoped, well-documented tasks. A design that only
works if the coding agent is perfect will fail in practice.
*Implication:* favor simple, boring, explicit code and small files over abstraction that
requires holding a lot of context at once. See `docs/04-CONSTRAINTS.md`.

## Priority order when principles conflict
1. **P7 (agency)** and **P6 (durability)** — never sacrificed for anything else.
2. **P1–P5 (the ALTER behaviors themselves)** — the product is these or it's nothing.
3. **P8 (buildability)** — a principle honored by code that never ships helps no one; simplify
   the implementation before simplifying away the behavior.

If a proposed shortcut would violate P6 or P7, stop and flag it even if the user didn't ask.
