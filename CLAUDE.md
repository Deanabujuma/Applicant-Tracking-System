# CLAUDE.md — Applicant Tracking System (CIDM 3312 Project #1)

Internal Django ATS for logged-in hiring employees: candidates, job openings with shared skills, and applications moving through hiring stages. Sources of truth: `prd/applicant-tracking-system.md` (PRD) and `plans/applicant-tracking-system.md` (approved 10-phase plan). `prototypes/` holds throwaway design evidence, not production code.

## Stack (fixed course constraints)
Python, Django, SQLite, uv, Tailwind CSS + DaisyUI via django-tailwind-cli, HTMX, Ruff. Tests: pytest + pytest-django.

## Apps and boundaries
- `candidates`: Candidate, Source choices, archive/unarchive, candidate deletion rules.
- `openings`: JobOpening, Skill, Open/Closed status, close/reopen, inline skill creation.
- `hiring`: Application, stages, pure transition-rules module, `move_to()` / `undo()`, application creation, workspace.
- One-way dependency: `hiring` imports `candidates` and `openings`; they never import `hiring` (FKs use string model references; archiving uses `candidate.applications.active()`).

## Stage rules
- Active: Applied → Screening → Interview → Final Review → Offer. Closed: Hired, Rejected, Withdrawn.
- Forward one step or skip up to Offer; Hired only from Offer; Rejected/Withdrawn from any active stage; no backward moves.
- Hired is permanent: no moves, no Undo. Undo returns to the actual previous stage once, then is unavailable until a new move.
- Stages change only through `move_to()` / `undo()`, which consult the rules module; no transition logic in views or JavaScript.
- Every move needs a Confirm/Cancel modal (Undo has none). POSTs re-validate and reject stale requests (expected stage; Undo also checks `stage_changed_at`).

## Auth and data protection
- Every view requires login. Accounts are admin-created only; no registration, no roles; deactivated accounts lose access.
- Application FKs use `on_delete=PROTECT`; anything with applications can't be deleted (archive candidates, close openings instead). DB constraints enforce unique (candidate, opening), case-insensitive unique candidate email and skill name.
- Archiving and closing never change application stages.

## Workflow
- Implement one approved plan phase at a time; don't start the next phase without approval.
- TDD: propose tests for review and approval, run them and observe them fail (RED), then implement until they pass (GREEN).
- Maintain `PROMPTS.md`: add a session log only when asked, newest at the top, never rewrite or delete old entries.
