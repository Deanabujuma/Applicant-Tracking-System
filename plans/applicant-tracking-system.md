# Plan: Applicant Tracking System

> Source PRD: `prd/applicant-tracking-system.md` (CIDM 3312 Project #1)

## Architectural decisions

Durable decisions that apply across all phases:

- **Stack**: Python, Django, SQLite, uv, Tailwind CSS + DaisyUI via django-tailwind-cli, HTMX, Ruff. Tests use pytest + pytest-django, following the course TDD process (tests approved → RED → GREEN).
- **Owning apps**:
  - `candidates` — Candidate model, Source choices, archive/unarchive, candidate deletion rules, candidate list/detail/create/edit views.
  - `openings` — JobOpening and Skill models, Open/Closed status, close/reopen, opening deletion rules, inline skill creation, opening create/edit views.
  - `hiring` — Application model, Stage choices, the pure stage-transition rules module, `move_to()` / `undo()`, application creation (both entry points), and the hiring workspace.
  - Dependency direction is one way: `hiring` → `candidates`, `openings`. `candidates` and `openings` never import `hiring`; Application declares its foreign keys with string model references.
- **Models**:
  - `Candidate`: first name, last name, email, source (required); phone, source detail, notes (optional); archived flag (default false); created/updated timestamps. Case-insensitive unique email enforced by a database constraint.
  - `Source`: `TextChoices` — Job Board, Referral, Company Website, Other. No Source model.
  - `JobOpening`: title, department (plain text) required; description, location optional; status Open (default) / Closed; created/updated timestamps. Titles not unique. M2M to `Skill` (may be empty).
  - `Skill`: name, case-insensitive unique via a database constraint. No in-app deletion (Django admin only).
  - `Application`: FK `candidate` and FK `opening`, both `on_delete=PROTECT` with `related_name="applications"`; stage; previous stage (nullable); stage-changed-by (user); stage-changed-at; created/updated timestamps. Database unique constraint on (candidate, opening).
  - `Stage`: `TextChoices` — Applied, Screening, Interview, Final Review, Offer (active); Hired, Rejected, Withdrawn (closed).
  - Application's default manager exposes a custom QuerySet with `active()`.
- **URLs** (app-namespaced, pk-based because opening titles are not unique):
  - `/accounts/login/`, `/accounts/logout/` — Django auth; no registration route.
  - `/candidates/`, `/candidates/new/`, `/candidates/<pk>/`, `/candidates/<pk>/edit/`, plus POST actions for archive, unarchive, delete under `/candidates/<pk>/…`.
  - `/openings/`, `/openings/new/`, `/openings/<pk>/edit/`, plus confirm-modal GET + POST for close, reopen, delete under `/openings/<pk>/…`; inline skill creation under `/openings/skills/…`.
  - `/` — hiring workspace (`hiring` namespace). Filter state in query params: `?opening=<pk|all>&q=&stage=&sort=`.
  - Application create, move-confirm modal (GET), move (POST), and undo (POST) under `/applications/…`.
- **Authentication / authorization**: Django built-in auth. Every view requires login. Accounts are created only by an administrator in Django admin; deactivating an account (`is_active=False`) revokes access. All employees have identical permissions — no roles or groups.
- **Transition rules**: one pure module in `hiring` (no DB access) mirroring the logic prototype. It answers allowed moves, why a move is blocked, whether Undo is available, and the move kind (advance / skip / end / hire). Model methods, views, templates, and confirmation messages all consult it; no transition logic in views or JavaScript.
- **HTMX patterns**: server-rendered DaisyUI confirm modals (GET returns modal, Confirm POSTs, Cancel changes nothing). After a move or Undo, one response re-renders the workspace partial and updates the sidebar via out-of-band swap. The same workspace partial serves initial load and filter changes.

---

## Phase 1: Project setup and login-only access

**User stories**: 1, 2, 3, 4

### What to build

Create the Django project with uv, the three empty apps, Tailwind/DaisyUI and HTMX wired into a base layout, Ruff config, and pytest + pytest-django. Add Django login/logout with a styled login page and no registration route. Every view requires login. A placeholder workspace page at `/` proves the redirect to login and the authenticated landing work end to end.

### Acceptance criteria

- [ ] `uv run pytest` runs and passes; `uv run ruff check` and `ruff format --check` pass.
- [ ] Anonymous request to `/` redirects to the login page.
- [ ] An admin-created, active user can log in and reach `/`; logout returns to login.
- [ ] A deactivated user cannot log in and cannot reach any protected page.
- [ ] No public sign-up URL exists.
- [ ] Base template loads Tailwind/DaisyUI and HTMX.

---

## Phase 2: Candidate records

**User stories**: 5, 6, 7, 8, 9, 10

### What to build

The `Candidate` model and `Source` choices with migration, and login-required list, detail, create, and edit pages in `candidates`. Required and optional fields behave as the PRD specifies. Creating a candidate whose email matches an existing one (ignoring case) is rejected with a message linking to the existing record; the database constraint backs this up.

### Acceptance criteria

- [ ] A candidate can be created with first name, last name, email, and source only; phone, source detail, and notes are optional.
- [ ] Source is chosen from the fixed four-value list.
- [ ] Duplicate email differing only in case is rejected by the form, with a link to the existing candidate.
- [ ] The database constraint rejects a case-insensitive duplicate email even when the form is bypassed.
- [ ] A candidate can be edited and the list/detail pages reflect the changes.
- [ ] All candidate pages require login.

---

## Phase 3: Job openings and skills

**User stories**: 18, 19, 20, 21, 22, 23, 24, 25, 26, 27

### What to build

The `JobOpening` and `Skill` models with migration, and login-required list, create, and edit pages in `openings`. New openings start Open. Lists show title, department, and status so same-titled openings are distinguishable, and each opening also displays its unique opening ID so openings that match on title, department, and status can still be told apart. The opening form selects existing skills and lets staff add a new skill inline via HTMX without losing form input; a case-insensitive duplicate skill name shows a validation message.

### Acceptance criteria

- [ ] An opening can be created with title and department only and starts as Open.
- [ ] Two openings with the same title can coexist and are distinguishable in the list by department and status.
- [ ] Two openings with the same title, department, and status are still distinguishable by their unique opening IDs, shown in the list and on each opening's page.
- [ ] Any number of existing skills can be attached; removing a skill from an opening leaves the skill in place for other openings.
- [ ] A new skill can be added inline from the opening form via HTMX; the form's other input is preserved.
- [ ] A skill name differing only in case from an existing one is rejected (form message and database constraint).
- [ ] All opening pages require login.

---

## Phase 4: Close, reopen, and delete openings

**User stories**: 28, 30, 31, 33

### What to build

Close and reopen actions on an opening, each behind a server-rendered DaisyUI confirm modal (HTMX GET for the modal, POST to confirm, Cancel changes nothing). Delete for an opening, also behind a confirm modal; deleting removes the opening and its skill links but never the skills.

### Acceptance criteria

- [ ] Closing an Open opening asks for confirmation and sets it to Closed on Confirm.
- [ ] Reopening a Closed opening asks for confirmation and sets it to Open on Confirm.
- [ ] Cancel on any of these modals changes nothing.
- [ ] Deleting an opening removes it; its skills still exist afterward.
- [ ] Close, reopen, and delete endpoints require login and accept only POST for state changes.

---

## Phase 5: Adding applications and protected deletion

**User stories**: 16, 17, 29, 32, 34, 35, 36, 37, 38, 39, 40, 42, 43

### What to build

The `Application` model and `Stage` choices in `hiring`, with PROTECT foreign keys, the `applications` reverse relation, and the (candidate, opening) unique constraint. One shared application form used from two entry points: the candidate detail page (choose an opening) and the opening's page (choose a candidate). New applications always start in Applied; there is no stage field. Choices include only Open openings and non-archived candidates, excluding openings the candidate already applied to, and the same rules are validated on submit. Candidate delete is added (for candidates with no applications); both candidate and opening delete are refused with a clear message when applications exist. Independently of the views, the database's PROTECT behavior blocks deleting a candidate or opening that has applications, even when deletion is attempted directly (e.g. calling `.delete()` on the model or a queryset). Closing an opening leaves its applications untouched.

### Acceptance criteria

- [ ] An application can be added from a candidate's profile and from an opening's page; both produce the same result and start in Applied.
- [ ] Choices exclude closed openings, archived candidates, and openings the candidate already applied to.
- [ ] Submitting a closed opening, an archived candidate, or a duplicate pair is rejected by the form.
- [ ] The database constraint rejects a duplicate (candidate, opening) even when the form is bypassed.
- [ ] One candidate can hold applications to several different openings.
- [ ] A candidate with no applications can be permanently deleted; one with applications cannot, and the user is told why.
- [ ] An opening with applications cannot be deleted, and the user is told to close it instead.
- [ ] A test confirms that deleting a candidate or an opening that has applications directly, outside any form or view (model instance or queryset `.delete()`), raises Django's `ProtectedError` and leaves the candidate, opening, and applications intact.
- [ ] Closing an opening does not change any of its applications' stages.

---

## Phase 6: Archive and unarchive candidates

**User stories**: 12, 13, 14, 15, 41

### What to build

The `active()` QuerySet method on Application in `hiring`. `Candidate.archive()` in `candidates` checks `candidate.applications.active()` through the reverse relation (no import of `hiring`): if any exist it refuses and reports them so the page can list exactly which applications still need resolving; otherwise it sets the archived flag. Unarchive is a separate action that clears the flag. Archived candidates drop out of the active candidate list and out of application-form choices. Editing an archived candidate leaves them archived. Tests live with `hiring`'s tests since they need Application records.

### Acceptance criteria

- [ ] `active()` returns only applications in Applied through Offer.
- [ ] Archiving a candidate with an active application is refused, and the page lists those applications.
- [ ] Archiving a candidate whose applications are all closed (or who has none) succeeds.
- [ ] Archiving never changes any application's stage.
- [ ] Archived candidates are hidden from the active candidate list and from application choices; new applications for them are refused.
- [ ] Editing an archived candidate keeps them archived; unarchiving is a separate action that restores them.
- [ ] `candidates` contains no import from `hiring`.

---

## Phase 7: Hiring workspace layout

**User stories**: 64, 65, 66, 69 (job-title column), 70

### What to build

The openings-first workspace at `/`, following the approved UI prototype. A sidebar lists every opening with title, department, Open/Closed status, and active-applicant count, plus an "All Openings" entry; closed openings with active applicants are flagged in the sidebar and on the opening's page. Selecting an opening (`?opening=<pk|all>`) shows stage summary counts and the applicant list. In All Openings each row shows its job title. Selecting an applicant opens a read-only detail panel with the candidate's details, current stage, and source. The workspace is rendered from a reusable partial so later phases can swap it via HTMX.

### Acceptance criteria

- [ ] The sidebar lists every opening with title, department, status, and active-applicant count, plus All Openings.
- [ ] A closed opening with active applicants is visibly flagged in the sidebar and on its page; a closed opening with none is not.
- [ ] Selecting an opening shows correct per-stage counts and its applicants.
- [ ] All Openings lists applications across every opening, each showing its job title.
- [ ] Selecting an applicant shows their details, stage, and source in the detail panel.
- [ ] The applicant list offers no stage-change controls.
- [ ] Selected opening is reflected in the URL; the workspace requires login.

---

## Phase 8: Stage moves with confirmation

**User stories**: 11, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 61, 71, 72, 73

### What to build

The pure transition-rules module in `hiring` (no DB access) matching the logic prototype, and `Application.move_to()`, which consults the rules, stores the stage it left as previous stage, records stage-changed-by and stage-changed-at, saves, and raises on a rule violation. The detail panel shows only allowed actions, grouped as moving forward and ending the application. Each action fetches a server-rendered confirm modal whose message is built from the move kind: advance, skip (naming skipped stages), end (noting one Undo is available), or Hired (warning it is permanent). The modal records the application's stage at the time it was opened, and Confirm POSTs both the target stage and that expected original stage. On POST the server first checks that the application's current stage still equals the expected original stage, then re-validates the move through `move_to()`. If another employee changed the stage after the modal was opened, or the move is otherwise invalid, the POST returns an error and changes nothing. This uses only the existing stage field, with no version column, locking infrastructure, or audit log. A successful move re-renders the workspace partial and updates the sidebar via out-of-band swap. Hired shows no actions.

### Acceptance criteria

- [ ] Rules (no DB): forward one step or skip up to Offer from any active stage; Hired only from Offer; Rejected/Withdrawn from any active stage; no backward moves; no moves from Hired, Rejected, or Withdrawn.
- [ ] `move_to()` updates stage, previous stage, stage-changed-by, and stage-changed-at, and raises without saving on an invalid move.
- [ ] The detail panel offers exactly the moves the rules allow, grouped into forward and ending actions.
- [ ] The modal message differs correctly for advance, skip, end, and Hired; the Hired modal warns it is permanent.
- [ ] Cancel changes nothing.
- [ ] A POST for a move that is no longer valid is rejected with an error and no data change.
- [ ] A stale confirmation can't overwrite another employee's change. If the application's stage changed after the modal was opened, the POST is rejected with an error even when the requested move would be valid from the new stage. The stage, previous stage, stage-changed-by, and stage-changed-at all stay as the other employee left them.
- [ ] The move response includes the workspace partial and an out-of-band sidebar update; counts, list, panel, and sidebar all reflect the new stage.
- [ ] Editing a candidate's details does not change any application's stage.

---

## Phase 9: Undo and last-change info

**User stories**: 55, 56, 57, 58, 59, 60, 62, 63

### What to build

Undo in the rules module and `Application.undo()`: return to the stored previous stage, clear it so Undo can't repeat, and record stage-changed-by and stage-changed-at. The detail panel shows Undo only when available and triggers it with a direct HTMX POST (no modal), with the same workspace + out-of-band sidebar response as a move. The Undo button carries the expected current stage plus a state token, which is the application's existing stage-changed-at value as it was when the button was rendered. Every move and Undo updates that timestamp, so it identifies the stage-change state. Before performing Undo, the server checks that the application's current stage and stage-changed-at still match both values. If another employee has moved or undone the application in the meantime, the stale request is rejected with an error and nothing changes. No new fields, version column, locking infrastructure, or audit log are added. The panel shows who last changed the stage and when, including Undo.

### Acceptance criteria

- [ ] Undo returns to the actual previous stage, including after a skip.
- [ ] Undo from Rejected and from Withdrawn returns to the actual previous stage.
- [ ] Undo is unavailable immediately after an Undo; a new move makes it available again.
- [ ] Undo is never available from Hired.
- [ ] Undo happens immediately with no confirmation modal.
- [ ] Undo records stage-changed-by and stage-changed-at, and the panel shows who/when for the latest change.
- [ ] The Undo response includes the workspace partial and an out-of-band sidebar update.
- [ ] An Undo POST when Undo is not available is rejected with no data change.
- [ ] A stale Undo can't reverse another employee's change. If the application's stage or stage-changed-at no longer matches the expected stage and state token from when the Undo button was rendered, the POST is rejected with an error. The stage, previous stage, stage-changed-by, and stage-changed-at stay unchanged. Automated tests cover two cases: another employee moved the application after the button rendered, and another employee already performed the Undo.

---

## Phase 10: Search, sort, filter, and URL state

**User stories**: 67, 68, 69, 74

### What to build

Search, sort, and stage filtering on the workspace applicant list, following the table variant of the UI prototype. Clicking a stage count filters the list to that stage. Search and filters apply within the selected opening or across All Openings. All filter state (`opening`, `q`, `stage`, `sort`) lives in query parameters; HTMX pushes the URL as filters change, and server renders (including post-move and post-Undo responses) honor the current filters.

### Acceptance criteria

- [ ] Clicking a stage count filters the applicant list to that stage.
- [ ] Search filters applicants by name/email within the selected opening and across All Openings.
- [ ] Sorting the applicant list works and is reflected in the URL.
- [ ] Changing filters updates the URL via HTMX without a full page reload.
- [ ] Loading a URL with `opening`, `q`, `stage`, and `sort` reproduces the same view.
- [ ] After a move or Undo, the re-rendered workspace keeps the current filters.
