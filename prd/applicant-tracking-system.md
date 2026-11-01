# PRD: Applicant Tracking System (CIDM 3312 Project #1)

## Problem Statement

An internal hiring department has no shared system for tracking who has applied to which job openings and where each applicant stands in the hiring process. Staff need one place to record candidates and where they came from, publish and manage job openings with their required skills, and move applications through a defined set of hiring stages.

Without enforced rules, applicants can be duplicated, moved into impossible states (for example, hired without an offer), or lost when records are deleted. A single misclick on a stage change can't be corrected, and there's no visibility into openings that have stopped accepting applicants but still have candidates waiting on decisions. Staff also need to work through a large number of applicants without hunting through long, unfiltered lists or waiting on full page reloads.

## Solution

A Django web application used only by logged-in hiring employees (candidates never log in). Staff manage three kinds of records:

- **Candidates:** contact information and one primary source (Job Board, Referral, Company Website, or Other, plus an optional detail such as "LinkedIn" or "Referred by J. Smith").
- **Job openings:** title, department, optional description and location, Open/Closed status, and any number of shared skills.
- **Applications:** link one candidate to one opening and move through the stages Applied, Screening, Interview, Final Review, Offer, Hired, Rejected, and Withdrawn.

The main screen is an **openings-first hiring workspace**. A sidebar lists every opening (with an "All Openings" entry) showing title, department, Open/Closed status, and active-applicant count, with a warning flag on closed openings that still have active applicants. Selecting an opening shows stage summary counts, a searchable, sortable, filterable applicant list, and a detail panel for the selected application. Stage changes happen only in the detail panel.

Every stage change asks for confirmation in a modal whose message reflects the move: a normal advance, a skip, ending an application, or a permanent hire. Accidental moves can be undone once, back to the stage the application actually came from. Hired is permanent. Everything updates in place with HTMX, without full page reloads.

Records with hiring history are never destroyed. Candidates are archived instead of deleted, openings are closed instead of deleted, and the database itself refuses to delete anything that has applications.

## User Stories

### Access

1. As a hiring employee, I want to log in with an account an administrator created and approved for me, so that only authorized hiring staff, not just any account that can authenticate, can see candidate and hiring information.
2. As an administrator, I want to create employee accounts myself, with no public sign-up, so that nobody outside the hiring department can get access.
3. As a hiring employee, I want every page of the system to require login, so that candidate data is never exposed to anonymous visitors.
4. As a hiring employee, I want the same permissions as every other hiring employee, so that I can complete any part of the hiring workflow without waiting on someone else.

### Candidates

5. As a hiring employee, I want to create a candidate with first name, last name, email, and source, so that I can begin tracking a new person.
6. As a hiring employee, I want to optionally record a candidate's phone number, a source detail, and notes, so that I can keep useful context without being forced to fill in every field.
7. As a hiring employee, I want to choose the candidate's source from a fixed list (Job Board, Referral, Company Website, Other), so that sources are consistent and can be filtered reliably.
8. As a hiring employee, I want to record a source detail such as "LinkedIn," "Indeed," or "Referred by J. Smith," so that the specific origin is captured without creating new categories.
9. As a hiring employee, I want the system to reject a new candidate whose email (ignoring capitalization) already exists, and to point me to the existing record, so that the same person isn't entered twice.
10. As a hiring employee, I want to edit a candidate's information at any time, so that I can correct mistakes or update contact details.
11. As a hiring employee, I want editing a candidate's details to never change the stage of any of their applications, so that corrections don't accidentally move someone through the pipeline.
12. As a hiring employee, I want to archive a candidate, so that they no longer appear in active candidate lists while their information and application history are preserved.
13. As a hiring employee, I want archiving to be blocked while the candidate has any active application, and to be shown exactly which applications still need to be resolved, so that I don't silently abandon someone mid-process.
14. As a hiring employee, I want archiving never to change any application's stage automatically, so that stages change only through deliberate, confirmed actions.
15. As a hiring employee, I want to unarchive a candidate as a separate, deliberate action, and I want editing an archived candidate's information to leave them archived, so that a candidate only returns to active use, and can only receive new applications, when someone intentionally unarchives them.
16. As a hiring employee, I want to permanently delete a candidate who has no applications, so that I can clean up records created by mistake.
17. As a hiring employee, I want the system to prevent deleting any candidate who has one or more applications, so that hiring records are never lost.

### Job openings and skills

18. As a hiring employee, I want to create a job opening with a title and department, and optionally a description and location, so that I can start accepting applicants for a role.
19. As a hiring employee, I want new openings to start as Open, so that they can receive applications right away.
20. As a hiring employee, I want to edit a job opening, so that I can correct or update its details.
21. As a hiring employee, I want to create openings with the same title as existing ones, so that the company can hire for the same role more than once or run parallel openings.
22. As a hiring employee, I want openings to be identified by more than their title (department and status in lists, plus a unique record identity), so that I can tell same-titled openings apart.
23. As a hiring employee, I want to attach any number of existing skills to an opening, so that its requirements are clear.
24. As a hiring employee, I want to add a new skill directly from the opening form without leaving the page, so that I don't lose my work when a skill is missing.
25. As a hiring employee, I want skill names to be unique regardless of capitalization, so that "Python" and "python" can't both exist.
26. As a hiring employee, I want the same skill to be shared across many openings, so that skills stay consistent across the department.
27. As a hiring employee, I want to remove a skill from an opening without deleting the skill itself, so that other openings using it are unaffected.
28. As a hiring employee, I want to close an opening after confirming in a dialog, so that it stops accepting new applications.
29. As a hiring employee, I want closing an opening to leave its existing applications untouched and still movable through the normal stages, so that the team can finish evaluating applicants it already has.
30. As a hiring employee, I want to reopen a closed opening after confirming in a dialog, so that it can accept new applications again if the company needs more applicants or it was closed by mistake.
31. As a hiring employee, I want to permanently delete an opening that has no applications, so that I can remove openings created by mistake.
32. As a hiring employee, I want the system to prevent deleting any opening that has applications, so that hiring history is preserved and I close the opening instead.
33. As a hiring employee, I want deleting an unused opening to remove only its skill associations, never the skills themselves, so that other openings keep their skills.

### Applications

34. As a hiring employee, I want to add an application from a candidate's profile by choosing an opening, so that I can record that this person applied for a role.
35. As a hiring employee, I want to add an application from an opening's workspace by choosing a candidate, so that I can record applicants while working on a specific role.
36. As a hiring employee, I want both ways of adding an application to follow exactly the same rules, so that the result is the same no matter where I start.
37. As a hiring employee, I want every new application to start in Applied, so that all applicants enter the pipeline the same way.
38. As a hiring employee, I want the choices offered when adding an application to include only open openings and non-archived candidates, excluding any opening the candidate has already applied to, so that I'm only offered valid options.
39. As a hiring employee, I want the system to refuse a duplicate application for the same candidate and opening, even if something slips past the form, so that each candidate has at most one application per opening.
40. As a hiring employee, I want the system to refuse new applications to a closed opening, so that closing an opening actually stops intake.
41. As a hiring employee, I want the system to refuse new applications for an archived candidate, so that archived candidates stay out of the pipeline until they are unarchived.
42. As a hiring employee, I want a candidate to be able to apply to several different openings, so that one person can be considered for multiple roles.
43. As a hiring employee, I want to create the candidate record before adding an application, so that every application belongs to a fully recorded candidate.

### Stage transitions

44. As a hiring employee, I want to move an application forward to the next stage, so that I can record progress.
45. As a hiring employee, I want to skip ahead to any later active stage up to Offer, so that strong candidates can bypass unnecessary steps.
46. As a hiring employee, I want Hired to be reachable only from Offer, so that nobody is recorded as hired without receiving an offer.
47. As a hiring employee, I want to reject an application from any active stage, so that I can end the process whenever the company decides not to proceed.
48. As a hiring employee, I want to mark an application Withdrawn from any active stage, so that I can record a candidate's decision to leave the process.
49. As a hiring employee, I want ordinary backward moves to be impossible, so that the pipeline can't be walked backward freely.
50. As a hiring employee, I want a confirmation dialog with Confirm and Cancel before any stage change is saved, so that I review the move before it happens.
51. As a hiring employee, I want the confirmation message to make clear whether I'm advancing, skipping stages, ending an application, or hiring, so that I understand the consequence of what I'm confirming.
52. As a hiring employee, I want the Hired confirmation to clearly warn that the decision is permanent and can't be undone, so that I don't hire someone by accident.
53. As a hiring employee, I want Cancel to change nothing, so that backing out of a dialog is always safe.
54. As a hiring employee, I want the system to re-check the rules when I confirm, so that an outdated dialog can't produce an invalid stage change.
55. As a hiring employee, I want to undo the most recent stage change once, so that I can fix a misclick.
56. As a hiring employee, I want Undo to return the application to the stage it actually came from, even if stages were skipped, so that a mistaken skip is truly reversed.
57. As a hiring employee, I want Undo to be unavailable a second time in a row, so that Undo can't be used to move backward freely.
58. As a hiring employee, I want a new move to make Undo available again for that move, so that every move has its own single chance at correction.
59. As a hiring employee, I want to undo a Rejected application back to its actual previous stage, so that an accidental rejection can be corrected.
60. As a hiring employee, I want to undo a Withdrawn application back to its actual previous stage, so that an accidental withdrawal can be corrected, or a candidate who changes their mind can rejoin without a duplicate application.
61. As a hiring employee, I want Hired to be permanent with no Undo and no further moves, so that hiring decisions are final commitments.
62. As a hiring employee, I want Undo to happen immediately without a confirmation dialog, so that correcting a mistake is quick.
63. As a hiring employee, I want to see who last changed an application's stage and when, including Undo operations, so that I can follow up on recent decisions.

### Hiring workspace (dashboard)

64. As a hiring employee, I want a sidebar listing every job opening with its title, department, Open/Closed status, and active-applicant count, so that I can see the state of all hiring at a glance.
65. As a hiring employee, I want closed openings that still have active applicants to be clearly flagged, both in the sidebar and on the opening's page, so that those applicants aren't forgotten.
66. As a hiring employee, I want to select an opening and see summary counts of its applications by stage, so that I understand how the role is progressing.
67. As a hiring employee, I want to click a stage in the summary to filter the applicant list to that stage, so that I can focus on one part of the pipeline.
68. As a hiring employee, I want to search, sort, and filter the applicant list within the selected opening, so that I can find applicants quickly even when there are many.
69. As a hiring employee, I want an "All Openings" option that lets me search and filter across the whole department, with each application showing its job title, so that I can find a person without knowing which opening they applied to.
70. As a hiring employee, I want to select an applicant from the list and see their details, current stage, source, and available actions in a detail panel, so that I review the right application before acting.
71. As a hiring employee, I want stage changes to be possible only from the detail panel, not directly from the list, so that I don't change the wrong applicant's stage by accident.
72. As a hiring employee, I want the detail panel to show only the actions the rules currently allow, grouped as moving forward and ending the application, with Undo shown only when it's available, so that I'm never offered an invalid move.
73. As a hiring employee, I want the detail panel, applicant list, stage counts, and sidebar to all update together after a stage change or Undo, without a full page reload, so that no part of the screen shows outdated information.
74. As a hiring employee, I want my current opening, search, sort, and filter settings kept in the page address, so that refreshing or bookmarking the page returns me to the same view.

## Implementation Decisions

### Stack (fixed course constraints)

- Python, Django, SQLite, uv for project and dependency management, Tailwind CSS with DaisyUI through django-tailwind-cli, HTMX for partial page updates, and Ruff for linting and formatting.
- Automated tests use **pytest with pytest-django**. This was chosen over Django's built-in test runner because the developer is already familiar with pytest.

### Django app boundaries

- **`candidates`**: the Candidate model, source choices, archiving, unarchiving, and deletion rules, plus candidate list, detail, create, and edit views.
- **`openings`**: the JobOpening and Skill models, Open/Closed status, closing and reopening, opening deletion rules, inline skill creation, plus opening create and edit views.
- **`hiring`**: the Application model, the stage-transition rules, Undo, application creation (both entry points), and the hiring workspace dashboard.
- **Dependency direction is one way:** `hiring` depends on `candidates` and `openings`, and they never import from `hiring`. Application refers to Candidate and JobOpening through foreign keys declared in `hiring` using string model references.

### Models and database rules

- **Candidate:** first name, last name, email, and source are required. Phone, source detail, and notes are optional. Archived flag (default false), created and updated timestamps. Email is unique ignoring capitalization, enforced by a database constraint.
- **Source:** Django `TextChoices` with Job Board, Referral, Company Website, Other. One primary source per candidate. No Source model.
- **JobOpening:** title and department are required (department is plain text, not a model). Description and location are optional. Status (Open by default, or Closed), created and updated timestamps. Titles are not unique. Many-to-many relationship to Skill, which may be empty.
- **Skill:** a name that is unique ignoring capitalization, enforced by a database constraint. No in-app deletion (Django admin only).
- **Application:** candidate and opening foreign keys, both with `on_delete=PROTECT` and a reverse relation named `applications`. Also stage, previous stage (nullable), stage-changed-by (the staff user), stage-changed-at, and created and updated timestamps. A database unique constraint on (candidate, opening).
- **Stages:** `TextChoices` for Applied, Screening, Interview, Final Review, Offer, Hired, Rejected, Withdrawn. Applied through Offer are *active*. Hired, Rejected, and Withdrawn are *closed*.
- **Protected deletion:** `PROTECT` on both foreign keys means a candidate or opening with any application can't be deleted. Records without applications can be deleted permanently. Deleting an opening removes its skill links but not the skills.

### Stage-transition rules

- The rules live in a **pure module inside `hiring`** that works on stage values with no database access. It mirrors the rules module of the logic prototype and answers: which moves are allowed from a stage, why a given move is not allowed, whether Undo is available, and what kind of move it is (advance, skip, end, or hire) so confirmation messages can be built.
- Rules:
  - From any active stage, move forward to any later active stage up to Offer (one step or a skip).
  - Hired only from Offer.
  - Rejected and Withdrawn from any active stage.
  - No backward moves except Undo.
  - Hired: no moves and no Undo.
  - Rejected and Withdrawn: no moves. Undo only, if available.
- **Undo** returns the application to its stored previous stage and then clears the previous stage, so Undo can't happen twice in a row. Every successful move stores the stage it left, so each move earns exactly one Undo. Undo is never available from Hired.
- **The Application model methods `move_to()` and `undo()` are the only normal way stages change.** They ask the rules module, update the stage, previous stage, stage-changed-by, and stage-changed-at fields, and save. A rule violation raises an error instead of saving.
- Views and templates use the same rules module to decide which actions to show. No transition logic exists in views or JavaScript.

### Cross-app rule: archiving

- `hiring` defines what "active" means with a custom Application QuerySet method, `active()`, which returns applications in active stages, exposed through Application's default manager.
- `candidates` owns the archive action. `Candidate.archive()` asks through the reverse relation, `candidate.applications.active()`. If any exist, it refuses and reports them so the page can list them. Otherwise it sets the archived flag. `candidates` never imports `hiring`. It depends only on the reverse accessor Django attaches at startup.
- Archiving never changes application stages. Unarchiving clears the flag.
- Editing an archived candidate's information doesn't change the archived flag. Unarchiving is a separate, deliberate action, and it must happen before new applications can be created for that candidate.

### Application creation

- One shared Django form, used both from the candidate profile (choose an opening) and from the opening workspace (choose a candidate).
- New applications always start in Applied. There is no stage field on the form.
- Choices are limited to open openings and non-archived candidates, excluding openings the candidate already applied to. The form also validates these rules on submit, and the database constraint backs up the duplicate rule.
- Rules enforced in `hiring` when an application is created: the opening must be Open, the candidate must not be archived, and there must be no existing application for the same pair.

### Openings: close, reopen, skills

- Close and reopen toggle the status freely, each behind a Confirm/Cancel dialog. Closing doesn't affect existing applications. No reason field is required.
- The opening form lets staff select existing skills and add a new skill inline through HTMX without leaving the form. A duplicate name (ignoring capitalization) shows a validation message.

### Hiring workspace and HTMX behavior

- The layout comes from the UI prototype: the openings-first workspace (sidebar, stage summary, applicant list, detail panel) combined with the table variant's search, sorting, and filtering for the applicant list. The Kanban variant was rejected because eight stage columns take too much horizontal space.
- The sidebar lists all openings with title, department, Open/Closed status, active-applicant count, and a warning flag for closed openings that still have active applicants, plus an "All Openings" entry. In All Openings, each application shows its job title.
- Clicking a stage count filters the list. Search, sort, and filter apply within the selected opening, or across all openings.
- **Filter state lives in the URL** (selected opening, search text, stage filter, sort) as query parameters. HTMX pushes the URL as filters change, so refreshing or bookmarking restores the view and server re-renders always know the current filters.
- **Confirmation modals are server-rendered DaisyUI modals.** Clicking a stage action makes an HTMX GET request that returns a modal whose message is built from the rules module: normal advance, skip (naming that stages are skipped), end application (noting one Undo is available), or Hired (warning that it's permanent and can't be undone). Confirm sends an HTMX POST that performs the move. Cancel closes the modal and changes nothing.
- **The POST re-validates** through `move_to()`, so a stale modal can't perform an invalid move. An invalid move returns an error message instead of changing data.
- Undo is a direct HTMX POST with no modal.
- **After a move or Undo**, one response re-renders the workspace partial (stage summary, applicant list, detail panel) and also updates the sidebar using an HTMX out-of-band swap. The same workspace partial is used for the initial page load and for filter changes.
- Close and reopen use the same server-rendered confirm-modal pattern.

### Authentication

- Django's built-in authentication. All views require login. Accounts are created by an administrator (through Django admin), with no public registration and no candidate accounts.
- ATS access is restricted to **authorized, administrator-approved hiring employees**, not to any account that happens to authenticate. The only way an account can exist is for an administrator to create it for a hiring employee, and an administrator can revoke access by deactivating the account (Django's built-in active flag), which stops it from logging in.
- All logged-in hiring employees have the same permissions. There are no roles or groups.

### Testing

- pytest with pytest-django, following the course's TDD process: tests are reviewed and approved before implementation, observed failing (RED), then made to pass (GREEN).
- Priority tiers:
  1. **Transition rules (no database):** Hired only from Offer, Hired permanent, skips allowed up to Offer, no backward moves, Rejected and Withdrawn reachable from every active stage, Undo to the actual previous stage, no double Undo, Undo available again after a new move, no Undo from Hired.
  2. **Model and database rules:** `move_to()` and `undo()` update previous stage, stage-changed-by, and stage-changed-at. Duplicate application constraint. Case-insensitive unique email and skill name. `PROTECT` blocks deleting candidates and openings with applications, while records without applications can be deleted. Deleting an opening keeps its skills. Archive is blocked by active applications and reports them. Editing an archived candidate's information leaves them archived.
  3. **Form validation:** no applications to closed openings, for archived candidates, or duplicates. New applications start in Applied. Choices are limited correctly.
  4. **Views and HTMX:** login required on all views. A deactivated employee account can't log in and can't access protected ATS pages. The confirm modal shows the right message for each move type, including the permanent-Hired warning. A stale or invalid POST is rejected. Move and Undo responses include the workspace partial and the out-of-band sidebar update. Filter state from the URL is respected.
- Archiving tests need Application records, so they live with `hiring`'s tests, next to the code that defines "active."

## Out of Scope

- Candidate logins, a candidate-facing portal, or public job postings or applications.
- Public registration or self-service employee accounts.
- Roles or permission levels (for example, only hiring managers may hire). This is a possible future improvement.
- Full stage-change history or an audit log. Only the most recent change (who and when) and one previous stage are stored.
- More than one Undo in a row, or a per-application limit on rejection undos.
- Undoing or reversing a Hired decision.
- Time-limited Undo.
- A separate reapplication process for withdrawn candidates. Undo covers a candidate who changes their mind.
- Automatic stage changes when an opening closes or a candidate is archived (no auto-rejection or auto-withdrawal).
- A required reason or explanation when closing, reopening, rejecting, or undoing.
- A Kanban board view and drag-and-drop stage changes.
- Changing stages directly from the applicant list.
- Bulk stage changes.
- Creating a new candidate from inside the opening workspace or the application form.
- A Source model, multiple sources per candidate, or staff-managed source categories.
- A Department model.
- In-app skill deletion or a standalone skill management page.
- Unique job opening titles.
- Duplicate-person detection beyond case-insensitive unique email.
- Email notifications, scheduling interviews, resume uploads, and reporting or analytics beyond the dashboard stage counts.

## Further Notes

- **Design evidence:** two throwaway prototypes were built during the design interview and are kept in the repository's prototypes folder, separate from production code:
  - The **logic prototype** (stage transitions) validated the transition, confirmation, and Undo rules through guided scenarios: happy path, skip and undo, no double undo, accidental rejection, cancel, withdrawn then returning, Hired is permanent, blocked moves, the reject-undo-reject loop, and edits not affecting stages. The production rules module should match its behavior.
  - The **UI prototype** compared three dashboard directions (Kanban, table, openings-first workspace). The approved direction combines the workspace layout with the table's search, sorting, and filtering.
- **Key rationale for the Design Defense:**
  - Hired is permanent because hiring is a final commitment. Rejected and Withdrawn get one Undo because they can be entered by accident, and Withdrawn reflects a candidate decision that may be reversed.
  - Undo goes to the actual previous stage so a mistaken skip is truly reversed, and it is single-use so it can't turn into free backward movement.
  - Nothing with hiring history can be deleted. Archive and close are the reversible ways to retire records.
  - No hidden bulk changes: closing an opening or archiving a candidate never changes an application's stage.
  - Stage rules live in one place (a pure module in `hiring`), used by the model, the views, and the confirmation messages, so the buttons shown and the moves allowed can't disagree.
  - `candidates` decides whether archiving is allowed; `hiring` decides what "active" means. This keeps a single source of truth for stages without circular imports.
- **Deviations from recommendations during design:** pytest was chosen over Django's built-in test runner (the developer's familiarity from prior coursework). The end-stage decision was revised mid-interview: Hired became permanent, and Rejected and Withdrawn were evaluated and decided separately.
