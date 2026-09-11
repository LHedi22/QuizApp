# CLAUDE.md — Exam Version Generator & Scanner

You are building this project from an empty repository, following
`docs/REBUILD_SPEC.md` — the single source of truth for scope, requirements,
architecture, and the phase plan. Read it in full before doing anything else,
including this session's first action.

## Working rules for every session

1. **Work one phase at a time**, in the order in REBUILD_SPEC.md §5. Don't start a
   later phase's work early, even if it looks convenient or "just this one piece."
2. **Before starting a phase**, write or update `docs/phases/phase-N.md`: break that
   phase's "Key DoD themes" into concrete subtasks, each with its own Definition of
   Done that is verified by actually running something — a test, a migration, a
   script, a rendered file you inspect — never by assertion or "this should work."
3. **One commit per completed subtask**, message referencing the phase and subtask
   (e.g. `phase-2: reject rows with wrong option count (R1.4)`).
4. **After every subtask**, append an entry to `docs/PROGRESS.md`: what was done, the
   command/output that proves the DoD passed, and anything discovered that affects
   later phases. This log is the project's memory across sessions — write it like the
   next session (or the next person) has to work from it alone.
5. **Stop and ask before proceeding** if you hit anything touching: the scoring
   formula (§2 R7), a hard-to-change data model column (Appendix A), or the
   answer-sheet geometry / `config/sheet_template.json` (§3.2A). Everything else, use
   your judgment and note the assumption in PROGRESS.md instead of blocking.
6. **`[LOCKED]` items are non-negotiable.** `[RECOMMENDED — confirmed default]` items
   are the chosen path — build them, don't relitigate them — but if you hit a concrete
   reason mid-build that one is actually unworkable, stop and say so rather than
   quietly deviating.
7. `/app/omr` and `/app/grading` must stay importable with zero web-framework
   imports — pure Python, testable in isolation.
8. `version.question_order` / `version.option_order` are immutable after creation.
   No route, no admin action, no migration shortcut may touch them post-creation.
   This is enforced structurally (test it directly), not by convention.
9. Don't mark a phase's OMR-related DoD done against synthetic images alone — the
   real-capture corpus (`/corpus`, Phase 0) is the measurement standard from Phase 5
   onward, per REBUILD_SPEC.md §5.

## Where things live

- Spec (source of truth): `docs/REBUILD_SPEC.md`
- Phase breakdowns: `docs/phases/phase-N.md`
- Progress log: `docs/PROGRESS.md`
- Shared geometry config: `config/sheet_template.json` — authored in Phase 1 (numbers
  only), read by ingestion validation (Phase 2), the PDF renderer (Phase 4), and the
  OMR pipeline (Phase 5/6). One file, never three copies that can drift.
- Real-capture test corpus: `/corpus` — committed in Phase 0, including photocopy
  generations and upside-down captures per §6 Q10/Q18.

## Current state

**All of §5's phases are built and verified, except Phase 10 (intentionally
deferred by the spec's own text).** Phases 0, 1–9, 11, and 12 are each
complete — see their `docs/phases/phase-N.md` exit checklists and the dated
entries in `docs/PROGRESS.md` for the DoD proof behind every one. Phase 10
(the bounded LLM review-queue suggestion aid) stays unbuilt because the spec
says to build it "only if the Phase 9 review queue proves a real time sink" —
that hasn't been established by real usage yet.

The app runs via `docker compose` (see `README.md` "Run it" / `deploy/RUNBOOK.md`)
and has been used end-to-end for real: quiz creation → xlsx ingestion →
version generation → PDF download → photo scan → OMR grading → review →
results. `pytest -q` is at 490+ passing tests; `scripts/ci.sh` is green
(lint, full suite, clean-DB migrate, backup/restore round-trip).

There is no more scripted work left in the phase plan. Further changes at
this point are either genuine bug/UX fixes surfaced by real use (logged in
`docs/PROGRESS.md` as dated, non-phase-numbered entries) or new scope the
user explicitly asks for.
