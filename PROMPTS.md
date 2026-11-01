
# PROMPTS.md — AI Usage Log

This file is the record of AI use on this codebase. At the end of every
agent session, direct the agent to write the session log with this prompt:

> Append a session log to PROMPTS.md at the repo root, under today's date,
> newest entry at the top. Record every prompt I gave you this session, in
> order, including any corrections. End the entry with a short summary:
> the outcome, any places where I deviated from a recommended answer or
> asked follow-up questions, and anything that went sideways.

Two rules:

- Entries are added only by that prompt, never unprompted.
- New entries go at the top. Never rewrite or delete an old entry —
  the log is part of your work, and an honest log of a session that went
  sideways is worth more than a tidy one.

Each entry has this shape:

    ## YYYY-MM-DD — <one-line summary>

    ### Prompts
    1. ...

    ### Summary
    - **Outcome:** what was built and what was kept
    - **Deviations:** recommendations overridden, follow-up questions asked
    - **Sideways:** failures, wrong turns, and how they were caught

## 2026-11-01 — Implementation plan from the approved PRD (`/prd-to-plan`)

*(Long prompts are condensed to their substance; nothing is added that the prompt did not say.)*

### Prompts
1. `/prd-to-plan`. Claude read `prd/applicant-tracking-system.md`, saw the repo had no Django code yet, and proposed 10 vertical-slice phases. It asked about granularity, merging or splitting phases, and whether archiving could come earlier.
2. `@prd/applicant-tracking-system.md`. Re-attached the approved PRD without answering the breakdown questions.
3. Answered Claude's follow-up question dialog with **"Move archiving earlier"**: put archive/unarchive right after adding applications, making it Phase 6 and shifting the workspace phases later.
4. Reviewed `plans/applicant-tracking-system.md` and approved the 10-phase structure, with three clarifications. Asked for only the relevant acceptance criteria and descriptions to be updated, all 10 phases, their order and the architecture to be kept, the changes to be shown, and no implementation yet:
   1. Phase 3: two openings with the same title, department, and status must still be distinguishable by their unique opening IDs.
   2. Phase 5: explicitly test that the database's `PROTECT` behavior blocks deleting an opening or candidate with applications, even when deletion is attempted outside the normal form or view.
   3. Phase 8: a stale confirmation must not overwrite a stage change another employee made after the dialog opened. Revalidate the expected original stage on POST in addition to the transition rules. Keep it simple and consistent with the architecture: no audit log or extra infrastructure.
5. "Yes, please add stale Undo protection to Phase 9." The Undo request should include the expected stage and a token identifying the stage-change state when the button was rendered, using existing application fields if practical. The server rejects a stale request without modifying anything if another employee changed or undid the application. No audit log or extra infrastructure. Add an acceptance criterion and an automated test. Keep the 10 phases and all other decisions. "After this correction, I approve the implementation plan. Do not start implementation yet."
6. Update PROMPTS.md with this session's log (this prompt).

### Summary
- **Outcome:** Wrote and got approval for `plans/applicant-tracking-system.md`. The architecture header covers the stack, the three apps with their one-way imports, the models, pk-based namespaced URLs, auth, the pure transition-rules module, and the HTMX modal/out-of-band patterns. All 10 phases were kept, in this order: (1) project setup and login-only access, (2) candidate records, (3) job openings and skills, (4) close/reopen/delete openings, (5) adding applications and protected deletion, (6) archive and unarchive candidates, (7) hiring workspace layout, (8) stage moves with confirmation, (9) Undo and last-change info, (10) search, sort, filter, and URL state. Four corrections were added: opening IDs shown to tell identical openings apart (Phase 3); a direct `PROTECT` / `ProtectedError` test outside views (Phase 5); an expected-original-stage check on the confirm POST (Phase 8); and stale Undo protection using the expected stage plus the existing `stage_changed_at` value as the state token, with automated tests for "another employee moved it" and "another employee already undid it" (Phase 9). No production Django code has been written and nothing was committed.
- **Deviations:**
  - **Archiving moved earlier:** in the dialog I recommended approving the breakdown as-is (archiving at Phase 9). The user chose to move archiving to Phase 6, right after applications.
  - **Plan clarifications:** the user asked for three changes after reviewing the plan: IDs for identical openings, direct `PROTECT` tests, and stale-confirmation protection in Phase 8.
  - **Stale Undo:** I raised this as an open question after the Phase 8 change, since Undo has no modal and could reverse another employee's change. I didn't edit Phase 9 at that point because the user had limited the changes to three items. The user then asked for it and specified an expected stage plus a state token. I chose `stage_changed_at` as the token because it already exists and changes on every move and Undo.
- **Sideways:**
  - The user's second prompt re-attached the PRD instead of answering the breakdown questions. I asked again through a question dialog rather than guessing whether that meant approval.
  - Moving archiving earlier meant archive tests in Phase 6 run before stage moves exist. I told the user those tests will need to set closed stages directly; the plan itself doesn't spell this out.
  - While writing the plan, stories 29 (closing leaves applications untouched) and 32 (no deleting an opening with applications) moved from Phase 4 to Phase 5, because they need Application records. I told the user.
  - `plans/` is untracked in git, so I couldn't show a `git diff` of the corrections. I quoted the added text for each phase instead.
  - My first edit to PROMPTS.md failed because the anchor text spanned a line break that didn't match the file. I retried with a single-line anchor, and no earlier entry was changed.

## 2026-11-01 — Grill interview, logic + UI prototypes, and approved PRD for the ATS

*(Session ran 2026-10-30 to 2026-11-01. Long prompts are condensed to their substance; nothing is added that the prompt did not say.)*

### Prompts
1. `/grill-me` — interview me one question at a time, assume I'm a beginner, state what each question settles, list options with trade-offs, recommend one. (No plan document existed in the repo.)
2. Option A (there is a handout). Pasted the CIDM 3312 Project #1 requirements: Django internal ATS; fixed stack (Python, Django, SQLite, uv, Tailwind + DaisyUI via django-tailwind-cli, HTMX, Ruff, Django tests or pytest); staff-only users; candidates with sources; open/closed openings; no duplicate applications; the eight stages; HTMX stage moves without full reload; many-to-many skills; design decisions to make (candidate lifecycle, closing/reopening, allowed transitions, dashboard, app boundaries); two required `/prototype` prototypes (logic and UI) completed during the grill, before the PRD. Treat as fixed constraints; don't implement or write the PRD yet.
3. Option C for transition strictness (forward with skips, one-step back, exits from any active stage). No Hired without Offer. Wanted to examine terminal stages and accidental transitions in the logic prototype. Also: staff can edit an Applied application's info without advancing it; editing candidate info at later stages doesn't change stage; a Continue/Cancel confirmation when advancing; accidental advances correctable under the rules.
4. Option B for terminal stages (final with one-step undo). Confirmation dialog before finalizing; undo restores the previous stage; include these in the logic prototype; keep it simple.
5. "I want to revise my previous decision about final hiring stages." *(correction)*
6. Revision: Hired permanent with no undo, still with Confirm/Cancel. For active-stage undo, Option B (return to the actual previous stage, even after skips). Rejected and Withdrawn undecided — evaluate them separately. Update decisions before the logic prototype.
7. Option B for Rejected: one undo to the actual previous stage, confirm before rejecting, Hired stays permanent because hiring is a final commitment while rejection can be accidental. Continue to Withdrawn.
8. Option B for Withdrawn: one undo for accidental withdrawals or a candidate changing their mind; no separate reapplication system. Final list: Hired permanent; Rejected and Withdrawn one undo; all three confirmed. Ready to evaluate in the logic prototype.
9. Tested the logic prototype in the browser (skips, confirmations, undo) — worked as expected. Question 5: Option A (one undo per move, not one rejection undo per application). Continue to closing openings.
10. "0" *(ambiguous answer to Question 6)*
11. Option C for closing openings: stop new applications, existing candidates continue; no auto-rejection because the team may just want to finish evaluating.
12. Option B for reopening: reopen freely; Confirm/Cancel when closing or reopening; no written reason required.
13. Option C for candidate removal: archive is normal; permanent delete only with zero applications; agreed to `PROTECT`.
14. Option A for archiving with active applications: block archiving and list the active applications; archiving must not auto-withdraw because Withdrawn is the candidate's decision; archived candidates can't receive new applications until unarchived.
15. Option A for sources: `TextChoices` (Job Board, Referral, Company Website, Other), optional `source_detail`, one primary source, no Source model.
16. Option A for skills: select existing skills and add new ones inline via HTMX; unique ignoring capitalization; remove a skill from an opening without deleting it; no general skill deletion.
17. Approved the three dashboard variants (Kanban, table, openings-first workspace) for the UI prototype; evaluation criteria: navigation, efficiency with many applicants, protection against accidental stage changes; include confirmations, undo, permanent-Hired warning, closed-opening visibility; no fourth variant; keep separate from Django code; "I will invoke /prototype myself as required by the assignment."
18. `/prototype`
19. Pasted the UI-prototype brief (the one Claude drafted in its reply to step 17).
20. Chose a combination of B and C: keep C's sidebar, stage summary, applicant list, and detail panel; add B's search, sorting, filtering. Reasons: navigation (C), efficiency (B), mistake prevention (C's detail panel plus confirmations). Rejected A because eight columns take too much horizontal space. Keep prototypes as evidence; continue to app boundaries.
21. Option B for app boundaries (`candidates`, `openings`, `hiring`). Confirmed both dashboard assumptions: stage changes only in the detail panel; search/sort/filter within the selected opening plus an All Openings option showing job titles.
22. Option C for the archive rule (`hiring` defines "active", `candidates` controls archiving); agreed that `hiring` blocks applications to closed openings and archived candidates. *Follow-up:* asked for an explanation of how `candidate.applications.active()` works across apps and how circular imports are avoided.
23. Option B for opening deletion: only with zero applications, `PROTECT`, skill links removed but not skills.
24. Option A for transition rules: separate `hiring` transitions module; `move_to()`/`undo()` save; views and HTMX use the same rules; normal workflows change stages only through the model methods.
25. Option B for confirmations: server-rendered DaisyUI modals via HTMX; clear messages for normal, skipped, and final decisions; permanent warning for Hired; re-validate on Confirm; no confirmation for Undo.
26. Option B for refresh after a move: detail panel, list, stage counts, and sidebar update together via `hx-swap-oob`; filter/sort/search state in URL query parameters.
27. Option A for authentication: built-in auth, admin-created accounts, no public registration, equal permissions, no hiring-manager role. Approved `stage_changed_by` / `stage_changed_at`, updated on moves and Undo, most recent change only.
28. Option C for creating applications: from both the candidate profile and the opening workspace, one shared form; start in Applied; block duplicates, closed openings, archived candidates (database-level uniqueness); candidates must exist first.
29. Option B for testing: pytest with pytest-django because of familiarity from earlier coursework; agreed to the four test priorities; follow the course TDD process (approve tests, RED, GREEN).
30. Option A for candidate identity: required unique email ignoring case with a clear validation message pointing to the existing record; approved the candidate fields.
31. Option A for openings: titles not unique; sidebar shows title, department, status; each opening has its own ID; approved the opening fields; department stays plain text.
32. `/to-prd`
33. Two PRD clarifications *(correction)*: (1) state that access is restricted to authorized, administrator-approved hiring employees, not any authenticated account; (2) editing an archived candidate doesn't unarchive them — unarchiving is a separate deliberate action required before new applications. Update only relevant sections and show what changed.
34. Add both tests to the PRD (tier 2: editing an archived candidate keeps them archived; tier 4: a deactivated account can't log in or access protected pages). Approved the PRD provided nothing else changed. Don't start the implementation plan.
35. Append this session log to PROMPTS.md (this prompt).

### Summary
- **Outcome:** Completed the grill interview (24 numbered design questions covering transitions, terminal stages, undo, closing/reopening openings, candidate archive/delete, sources, skills, dashboard, app boundaries, cross-app archive rule, opening deletion, transition-rule location, HTMX confirmations and refresh, auth, application creation, testing, candidate and opening fields). Built two throwaway prototypes, kept as design evidence: `prototypes/stage-transitions.html` (logic prototype, tested by the user in the browser) and `prototypes/dashboard-variants.html` (UI prototype, three variants). Wrote and, after two rounds of corrections, got approval for `prd/applicant-tracking-system.md`. No production code was written and nothing was committed.
- **Deviations:**
  - **Hired made permanent:** I recommended (and the user first chose) "final with one undo" for all three end stages; the user revised this so Hired has no undo, then decided Rejected and Withdrawn separately (both one undo, matching my recommendations).
  - **pytest:** I recommended Django's built-in test runner; the user chose pytest + pytest-django because of prior familiarity.
  - **Dashboard B + C:** I proposed three separate variants and expected a winner or combination; the user chose a combination (C's layout with B's search/sort/filter) and rejected Kanban. The user also declined a fourth variant.
  - All other questions followed my recommended option, with additions from the user (confirmations on close/reopen, listing blockers when archiving, an All Openings job-title column).
  - **Follow-up questions:** asked for an explanation of `candidate.applications.active()` and circular-import avoidance before accepting the architecture; requested two PRD clarifications and two added tests after the first draft.
- **Sideways:**
  - No plan existed in the repo at the start, so the first question asked where requirements came from; the user then pasted the handout.
  - The user reversed the terminal-stage decision after I had already moved on to the undo question (Question 4); I parked Question 4, re-asked the terminal-stage question with more options, and resumed after it was settled.
  - The logic prototype was built inside the grill session following the prototype skill's LOGIC.md instructions, without the user typing `/prototype` for it; only the UI prototype was started by the user invoking `/prototype`. The assignment says both should use `/prototype`, so this may need noting in the Design Defense.
  - I couldn't script-check the logic prototype's rules because Node.js isn't installed; I traced the scenarios by hand and said so, and the user's browser testing confirmed the behavior.
  - Building the logic prototype surfaced an unanticipated case (reject → undo → reject → undo); it became Question 5 rather than being decided silently.
  - The answer "0" to Question 6 was ambiguous; I asked for clarification instead of guessing, and the user answered C.
  - After `/prototype` I built the UI prototype immediately from the brief in context; the user then pasted that same brief. I didn't rebuild — I mapped each brief item to what was built and flagged one wording difference (the brief said "candidate table"; the prototype uses one row per application, deliberately).
  - The first PRD draft didn't explicitly restrict access to administrator-approved accounts or say that editing an archived candidate leaves them archived; the user caught both, I edited only the relevant sections, then added the two matching tests at the user's request.
