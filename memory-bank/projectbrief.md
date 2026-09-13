# Project Brief

*This file rarely changes. It's the foundation the other memory-bank files build on. If it
needs to change, that's a significant enough moment to also log in `decisions.md`.*

## What
University in a Box — a self-hosted, single-user app implementing the ALTER framework
(Advisor, Librarian, Tutor, Editor, Roommate) as real, persistent software, not a set of
prompts. Full detail: `docs/01-VISION.md`.

## Source material
Derived from a YouTube video describing a self-education framework built around five AI
roles (the "university in a box" idea, nicknamed ALTER). The transcript was provided
directly by the project owner as the sole source; there is no other spec.

## Who it's for
The project owner, personal daily/weekly use over months and years across many topics.
Not a multi-tenant product.

## How it's being built
Built inside Cline using free-tier coding models (GLM-Flash-5.3 / DeepSeek V4). Because
these are capable-but-weak, well-scoped models, the project is deliberately documented and
phased so any single session — regardless of which model runs it — can pick up correctly
from `memory-bank/activeContext.md` alone. See `AGENTS.md` and `.clinerules`.

## Non-negotiable scope boundary
Exactly the five ALTER roles, implemented as described in `docs/01-VISION.md`, as a durable
local web app. No sixth role, no multi-tenant/auth system, no content marketplace, without
the project owner explicitly asking. See `docs/01-VISION.md` "Explicit non-goals."
