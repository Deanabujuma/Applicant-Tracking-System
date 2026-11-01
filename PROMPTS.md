
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

## 2026-11-01 — Phase 5 (adding applications and protected deletion) via `/implement`

*(Continues the same session as the Phase 4 entry below. That entry's last prompt (19) also asked to begin Phase 5 and propose up to three test-first behaviors and the decisions, so the prompts here start from its approval. Long prompts are condensed to their substance; nothing is added that the prompt did not say.)*

### Prompts
1. Approved the three Phase 5 test-first behaviors and decisions 1–4 (1: all Application fields now, with `stage_changed_by` using PROTECT and set, with `stage_changed_at`, when the application is created; 2: one shared form at `/applications/new/?candidate=` or `?opening=`, linked from both detail pages; 3: a candidate delete that follows the Phase 4 confirm pattern, with clear refusal messages; 4: read-only Applications lists on the detail pages). Two clarifications: the candidate or opening fixed by the URL must be checked on the server, so query strings and forged POST data can't get around the rules; and stage, previous_stage, stage_changed_by, and stage_changed_at must never be fields an employee can edit. Write Test 1 (database delete protection: `candidate.delete()`, `opening.delete()`, and both querysets' `.delete()` each raise `ProtectedError`, and everything stays intact) with the minimum model and migration, and show RED.
2. Approved Test 1 RED. Implement GREEN: switch both foreign keys from CASCADE to PROTECT; make `previous_stage` `null=True, blank=True, default=None`, as the plan says; have Test 1 check `previous_stage is None`; regenerate `hiring/0001_initial.py` instead of adding a second migration; don't reset, delete, or recreate the local database, and confirm the migration state is consistent.
3. Approved Test 1 GREEN. Write Test 2 (the shared form and its rules: both entry points, the same form, Applied, no forged stage fields, archived candidates and Closed openings refused, duplicates refused, choices limited, the fixed side checked on the server and not overridable by POST, nothing created on failure) and show RED.
4. Approved Test 2 RED. Implement GREEN: one `ApplicationForm`; the `application_create` view at `/applications/new/`; the two query-string entry points; only the chosen field on the form; limited choices; the whole pair checked on the server; clear errors; Applied with the metadata set by the application; a shared template and links from both detail pages; a redirect with a one-time success message; safe handling of missing, ambiguous, or nonexistent IDs; the database constraint kept as the final safeguard.
5. Approved Test 2 GREEN. Write Test 3 (deleting from the pages: the opening's confirmed Delete POST is refused with "close it instead"; the new candidate delete is refused with an explanation; a candidate without applications can still be deleted; the candidate confirmation is read-only on GET, needs a confirmed POST, and has Cancel; database PROTECT kept; nothing unrelated deleted) and show RED.
6. Approved Test 3 RED. Implement GREEN: catch `ProtectedError` in `delete_opening`; the candidate delete at `/candidates/<pk>/delete/` with the Phase 4 confirmation pattern (an HTMX fragment or a full page, a POST to delete, Cancel, CSRF, a Delete button), refusing with an error when applications exist; no nested forms or extra JavaScript; everything unrelated unchanged.
7. Approved Test 3 GREEN. First check that `delete_opening` calls `opening.delete()` exactly once, inside the try/except (the pasted diff looked duplicated). Then add read-only Applications lists on both detail pages, with links to the related records, stages, and an empty state, kept simple. Add regression tests: the database duplicate constraint, several openings per candidate, closing leaving stages unchanged, application creation (bad or missing query strings, nonexistent IDs, login, deactivated users, CSRF, success messages), candidate delete (login, 404, 405, CSRF, success), errors shown once, links hidden for archived candidates and Closed openings, the lists and their empty states, and no `hiring` imports in `candidates` or `openings`.
8. Approved the lists and the 39 regression tests. Before committing, inspect `openings/views.py` directly and confirm with a programmatic check that `delete_opening` has exactly one `opening.delete()`, inside the try/except, showing the real source lines and not a diff; remove any duplicate and rerun the affected tests. Keep Phase 5 uncommitted during a short manual browser check.
9. Reported the manual browser testing as approved: an application for Ana Lopez on Opening #1 Data Analyst was created, appears in the Applications section as Applied, and the success message displayed correctly; the Delete confirmation was opened and Cancel worked. The protected deletion POST itself was *not* tried manually, so record that accurately (the automated tests cover it). Update PROMPTS.md, run all checks, review git status, commit Phase 5, push, confirm the push and a clean tree, report the commit and test count, then begin Phase 6 with `/implement`, propose up to three test-first behaviors and only the decisions that need approval, and stop (this prompt).

### Summary
- **Outcome:**
  - **`hiring` models:**
    - `Stage` (`TextChoices`).
    - `Application` with string-referenced `candidate` and `opening` foreign keys, both `on_delete=PROTECT` with `related_name="applications"`.
    - Stage metadata that employees can't edit (`editable=False`): `stage` defaulting to Applied, `previous_stage` nullable with a default of None, `stage_changed_by` (a user foreign key, PROTECT), and `stage_changed_at`.
    - The unique (candidate, opening) constraint with a shared `DUPLICATE_APPLICATION_MESSAGE`.
    - A single regenerated migration, `hiring/0001_initial.py`.
  - **The shared `ApplicationForm`:**
    - One side is fixed by the URL, with a single field for the other side.
    - Only eligible choices are offered, but `clean()` checks the whole pair for an archived candidate, a Closed opening, or a duplicate, with clear messages.
    - `save()` sets Applied, the employee, and the current time, and turns a database `IntegrityError` into the duplicate error.
  - **The `application_create` view at `/applications/new/`:** 400 for a missing, ambiguous, or non-numeric query string, 404 for nonexistent IDs, and a redirect to the starting page with a success message.
  - **Detail pages:** "Add application" (hidden for archived candidates), "Add applicant" (hidden for Closed openings), and read-only Applications lists.
  - **Protected deletes:**
    - `openings.delete_opening` catches `ProtectedError` and redirects with "…has applications, so it can't be deleted. Close it instead."
    - The new `candidates.delete_candidate` follows the Phase 4 confirmation pattern (its own modal and full-page templates, a Delete button) and refuses with "…has applications, so they can't be deleted."
    - Neither app imports `hiring`.
  - **Tests:**
    - Test 1 (database delete protection) and Test 3 (the pages refuse the delete), plus Test 2, which runs once for each entry point.
    - 39 regression tests.
    - 201 passing in all. Ruff, `check`, `makemigrations --check`, and `migrate --check` clean.
  - **Manual testing (as reported):** creating an application from a candidate, seeing it as Applied on the opening with the success message, and Cancel in the Delete confirmation all worked. The refused delete POST was not tried in the browser; it is covered by Test 3 and the regression tests.
- **Deviations:**
  - The user overrode my proposal to store an empty string for `previous_stage` and required a nullable field with a default of None, as in the plan.
  - The user added two safety clarifications to the approved decisions (the fixed side checked on the server; the stage fields never editable).
  - The user asked for a programmatic check of `delete_opening` because a pasted diff looked like it had two delete calls.
- **Sideways:**
  - Test 1's RED needed a temporary `CASCADE` on both foreign keys so it would fail on an assertion. The code comment said so, and GREEN replaced it with PROTECT.
  - Making `previous_stage` nullable after the first `0001` was already applied locally meant the database column would no longer match. The table was empty (0 applications), so I ran `migrate hiring zero`, which dropped only that new table, regenerated `0001`, and applied it again. The column was confirmed as NULL, and the existing candidates, openings, and skills were untouched. The database file was not reset.
  - My first `ApplicationForm` draft used two lambdas with `# noqa: E731`, which breaks the no-`noqa` rule. They were replaced with module-level functions before any test run.
  - Test 3's RED needed `client.raise_request_exception = False`, so the unhandled `ProtectedError` came back as the 500 page an employee would see (an assertion failure) instead of crashing the test.
  - The apparently duplicated `opening.delete()` was only my edit script's search-and-replace text (old, then new). An `ast` check showed exactly one call, inside the try/except, so nothing was removed.
  - Ruff ISC004 in the regression tests was fixed by moving the message into a variable.

## 2026-11-01 — Phase 4 (close, reopen, delete openings) and the opening-specific Skills redesign

*(Continues the same session as the Phase 3 entry below. Long prompts are condensed to their substance; nothing is added that the prompt did not say. The redesign was requested partway through Phase 4 and is committed separately, before the Phase 4 commit.)*

### Prompts
1. Begin Phase 4 with `/implement`: review the plan, propose up to three test-first behaviors that put safety first, list only the decisions that need approval, and recommend the simplest implementation. Keep closing and deleting clearly separate; an opening with applications must never be deletable; deleting an opening must never delete Skills. Stop for approval.
2. Approved the three behaviors and decisions A–E (A: Confirm is a normal POST, then a redirect and a flash message; B: a request for the state the opening is already in changes nothing and shows an info message; C: no Application model yet, so `ProtectedError` handling and its test are moved to Phase 5 and written into the plan; D: an ordinary GET gets a full confirmation page; E: the buttons go on the opening detail page only). Five safeguards: GET never changes or deletes anything; don't create Application early, and record the PROTECT requirement and its user-facing error for Phase 5; Cancel must really close the dialog without a request (checked in the browser); close/reopen are one-way and idempotent, with an info message; changing status keeps every other field and the skills, touching only `status` and `updated_at`. Write Test 1 only and show RED.
3. Approved Test 1 RED and the Phase 5 note. Implement GREEN: `close()`/`reopen()` returning True or False; `save(update_fields=["status", "updated_at"])`; separate URLs; POST redirects to the detail page; success and info messages; GET changes nothing. Stop before Test 2.
4. Approved Test 1 GREEN and the mechanical fix to its message check. Write Test 2 (the close, reopen, and delete confirmations: an HTMX fragment, action-specific warnings, a POST form with CSRF, a `method="dialog"` Cancel, GET changes nothing, a full page without HTMX) and show RED.
5. Approved Test 2 RED. Implement GREEN: GET shows the confirmation; changes only by POST with CSRF; a shared `_confirm_modal.html`; separate Confirm and Cancel forms, not nested; a fragment for HTMX and a full page otherwise; Close or Reopen plus Delete buttons on the detail page that load into `#modal`; keep the one-way behavior and info messages. No extra JavaScript or dependencies.
6. Approved Test 2 GREEN (the real modal and Cancel to be checked in the browser). Write Test 3: two openings share Python and SQL; a confirmed POST deletes A; A and its skill links are gone; both Skills remain; B keeps both skills with every field and timestamp unchanged; redirect to the list with a one-time success message. Show RED.
7. Approved Test 3 RED. Implement GREEN: GET and POST on `delete_opening`; GET read-only; save the label first; normal model deletion; skills kept; message "Deleted opening #N Title."; redirect to `openings:list`; keep CSRF, login, and confirmation protections; `ProtectedError` stays in Phase 5.
8. Test 3 GREEN already reviewed and approved. Add the ordinary regression tests: login, deactivated users, 404, messages, the detail buttons, status protected from the edit form, the full-page fallback, read-only GETs, 405 for other methods, and CSRF.
9. One message with two pasted requests. The first asked for a way to remove skills from just one opening on its Edit page, recommending the existing checkbox-and-save if that already did it. The second revised it: no global Manage Skills page in the normal UI; each opening's Edit page shows only its own skills; Add Skill adds to the current opening only; a Remove control below the skills and Add Skill; removing unlinks from this opening only; handle unsaved changes safely; new openings get skills only when saved; reuse the existing many-to-many. Explain how this affects the PRD, plan, tests, HTMX Add Skill, and uniqueness, and recommend the simplest design. No code. Keep Phase 4 testing separate.
10. Approved the redesign and its three test-first behaviors. Decisions: (1) remove Manage Skills (views, URLs, templates, link) and register `Skill` in Django Admin; (2) one Remove dropdown and button below Add Skill; (3) a native datalist for suggestions only; (4) keep creating a new Skill immediately when Add is clicked, but don't assign it until Save, and document that Cancel can leave an unused Skill; (5) a separate commit, made only after TDD and browser testing, then Phase 4 finished separately. Keep old PROMPTS entries; mark superseded requirements clearly in the PRD and plan; keep useful tests. Update the PRD and plan first and show the changes.
11. Approved the PRD and plan with two corrections: say clearly that Add Skill may create a Skill right away but no opening or assignment changes until Save; and replace wording that claimed the redesign was already committed. Then write redesign Test 1 (each Edit page shows only that opening's skills; a new opening shows none; no catalog checkboxes) and show RED.
12. Approved Test 1 RED. Implement GREEN: hidden inputs instead of checkboxes; a "Skills for this opening" `<ul id="assigned-skills">`; "No skills yet"; keep pending skills through HTMX re-renders and validation errors; no model changes. Explain any older test failures as intended changes or regressions, without deleting tests to make them pass.
13. Approved Test 1 GREEN and the plan for the two failing older tests. Update the checkbox assertions in the first older test now, leave the duplicate test for the next GREEN, and write Test 2 (case-insensitive reuse of the existing record, no duplicate, pending form only, nothing saved, "already on this opening", other input kept, fragment, datalist, forged IDs rejected) and show RED.
14. Approved Test 2 RED. Implement GREEN (case-insensitive lookup and reuse, new names still validated, the "already on this opening" message, forged IDs dropped, the datalist, a fragment, nothing saved, blank and length checks kept, the constraint kept) and update the older duplicate test for the reuse behavior.
15. Approved Test 2 GREEN. Write Test 3 (remove Python from Opening #1's pending form only; the fragment shows only Excel; nothing changes before Save; after Save #1 has only Excel and #2 is fully unchanged; the Python record remains; Cancel changes nothing; the dropdown sits below Add Skill with only pending skills; other input kept; bad IDs can't remove other skills) and show RED. Don't remove Manage Skills yet.
16. The same message as prompt 15, sent again.
17. Approved Test 3 RED. Implement GREEN: a login-required, POST-only `/openings/skills/remove/` (`openings:skill_remove`) that changes only the pending selection, ignores bad IDs, returns `_skills_field.html`, and shows the Remove section only when there are skills; Save is the only change and Cancel discards.
18. Approved Test 3 GREEN. Review the 15 Manage Skills tests one by one, then remove the feature, register `Skill` in Admin, make sure the old URLs don't work, keep the model-level deletion tests, and add regression tests: anonymous and deactivated users, GET on POST-only endpoints, blank and too-long names, invalid forms keeping pending skills, the Remove section hidden when empty, Create assigning only on Save, CSRF, removing the last skill, and other openings unaffected.
19. Reported manual browser testing as complete and approved: the opening-specific Skills feature (adding, removing, saving, canceling) and the Phase 4 Close, Reopen, and Delete confirmations on several openings all worked. With a deadline tonight: update PROMPTS.md, review the git changes (no database, generated CSS, or unrelated files), run all checks, make the redesign commit and then the Phase 4 commit, push both, check the tree is clean, then begin Phase 5 with `/implement` and stop for approval after proposing up to three behaviors and the decisions (this prompt).

### Summary
- **Outcome:**
  - **Phase 4** (`openings`):
    - `JobOpening.close()`/`reopen()`: one-way and idempotent, saving only `status` and `updated_at`.
    - GET-and-POST `close_opening`, `reopen_opening`, `delete_opening`: GET only shows a confirmation (an HTMX fragment, or a full `confirm_page.html`); a POST with CSRF makes the change, then redirects with a success or info message. Delete removes the opening and its skill links, never Skills.
    - A shared `_confirm_modal.html` shown with `<dialog class="modal" open>` (not `modal-open`, so the `method="dialog"` Cancel really hides it).
    - Detail-page buttons with an `href` fallback.
    - Tests: 5 test-first (Test 2 runs for close, reopen, and delete) and 58 regression tests.
    - The Phase 5 note in the plan: the opening delete view must catch `ProtectedError` and tell the employee to close the opening instead.
  - **Opening-specific Skills redesign** (a second user-requested change, 2026-11-01):
    - The form shows only the opening's own skills (badges plus hidden inputs).
    - Add Skill reuses a case-insensitive match or creates a new Skill, adding it to the pending form only, with an "already on this opening" message and a datalist of suggestions.
    - A new POST-only Remove endpoint and dropdown change only the pending form; Save is the only change.
    - The Manage Skills page, views, URLs, templates, and link are removed; `Skill` is registered in Django Admin.
    - The PRD and plan mark stories 75–76 and their criteria as superseded and add stories 77–79 and new criteria.
    - Tests: 3 test-first and 21 regression tests. In the original 15 Manage Skills tests, 3 data-safety tests were kept (now deleting through the model) and 12 UI cases were replaced by tests that the old URLs return 404, that non-staff employees can't delete in Admin, that `Skill` is registered, and that no page links to Manage Skills. Two Phase 3 tests had their checkbox assertions updated; one was renamed from `…rejects_case_only_duplicate…` to `…reuses_case_only_duplicate…` because that behavior was intentionally changed.
  - **Results:** 158 tests passing; Ruff, `manage.py check`, and `makemigrations --check` clean; manual browser testing approved by the user.
- **Deviations:**
  - Prompt 9 revised its own first request within the same message, from removing skills on the Edit page to a full redesign, withdrawing the Manage Skills feature built and committed in Phase 3.
  - Prompt 11 corrected two pieces of wording in the PRD and plan.
  - The user chose the immediate creation of new Skills, knowing Cancel can leave an unused one.
  - HEAD and OPTIONS on the close, reopen, and delete endpoints return 405; the user was told and didn't change it.
- **Sideways:**
  - Phase 4 Test 1's first RED raised a `ValueError` unpacking two queued messages, an error rather than an assertion failure. Fixed by checking the latest message (`[-1]`); the user approved.
  - A Python heredoc turned `\b` into backspace characters in Test 2 (Ruff PLE2510). Fixed with a scratchpad script, and the RED was run again.
  - A regression helper created "Python" twice and hit the unique constraint. Fixed with `get_or_create`.
  - Ruff ISC004 (implicit string concatenation) and two RUF059 warnings (unused unpacked variables) were fixed by changing the tests, not by suppressing the rules.
  - `git rm` staged the two template deletions before commit time. They were unstaged right away.
  - Prompt 16 repeated prompt 15. Test 3 had already been written, so nothing was redone; its RED was run again.
  - Several files changed in both pieces of work, so separating the two commits meant staging versions of `views.py`, `urls.py`, and the plan without their Phase 4 parts.

## 2026-11-01 — Phase 3 (job openings and skills, plus Manage Skills) via `/implement`

*(Continues the same session as the Phase 2 entry below. The requirement-change prompt (prompt 10 here) is also logged in its own entry, recorded when it was made. Long prompts are condensed to their substance; nothing is added that the prompt did not say.)*

### Prompts
1. Begin Phase 3 with `/implement`, using the approved PRD and plan. Before writing code: review the acceptance criteria and design, propose up to three test-first behaviors explaining each and why it matters, list the decisions that really need approval, and recommend the simplest implementation that fits the existing architecture. Stop for approval. No Phase 4, commit, or push.
2. Approved the three behaviors, all four main decisions (an opening detail page at `/openings/<pk>/`; an inline skill saved as soon as you click Add skill; status not on the form; IDs shown as `#<pk>` with an ID column), and the minor choices. Two clarifications: (1) the HTMX Add skill action must keep all unsaved form input and ticked skills, and must not create or update the `JobOpening`; (2) removing a skill from an opening must only remove that link, never delete the shared `Skill` or change its links to other openings. Begin Test 1 only: set up the models and migration, then write Test 1 and show RED.
3. The same message as prompt 2, sent again.
4. Approved Test 1 and its RED. Build the minimum for GREEN: `JobOpeningForm` with title, department, location, description, and skills as a checkbox list and no status; `JobOpeningUpdateView` and a minimal `JobOpeningDetailView`; `get_absolute_url()`, namespaced URLs, and the project include; form and detail templates. Saving must only change that opening's own skill links. Run all checks and stop before Test 2.
5. Approved Test 1 GREEN. Make the one-line Phase 2 fix so the browser tab says "Edit candidate" when editing, kept narrow. Then write Test 2: the skill is saved with spaces removed and capitals kept; the returned fragment has the new skill ticked and earlier ticks kept; the response is a fragment, not a full page; and no `JobOpening` is created or updated. Show RED with the exact reason. Keep it simple, with no form inside a form and no page reload.
6. Approved Test 2 and its RED. Build the proposed GREEN: `SkillForm` with validation and normal trimming; a POST-only inline endpoint at `/openings/skills/new/` returning `_skills_field.html`; earlier ticks kept and the new skill ticked; unticked skills left unticked; the New skill box and Add skill button using `hx-post`, `hx-target`, and `hx-swap` with no form inside a form; no `JobOpening` created or updated; Django CSRF and the shared HTMX setup. Make sure the endpoint can't be fed made-up skill IDs or get around normal skill validation. Run all checks and stop before Test 3.
7. Approved Test 2 GREEN. Keep the small Enter-key handler, as long as it only stops the full opening form from being submitted by accident. Write Test 3: "python" submitted when "Python" exists creates no duplicate, shows a clear error in the fragment, keeps the earlier ticks, and returns a fragment. Show RED with the exact reason and stop.
8. Approved Test 3 and its RED. Build the proposed GREEN: `SkillForm.clean_name()` with `name__iexact`; the shared `DUPLICATE_SKILL_MESSAGE`; the `Lower("name")` constraint kept as the final safeguard; `skill_form.name.errors` and non-field errors shown in `_skills_field.html` with normal escaping; ticks and the typed name kept on failure; useful errors for blank and too-long names. Run all checks and stop before the list and create pages.
9. Approved Test 3 GREEN; all three planned test-first behaviors are complete. Finish Phase 3: the list at `/openings/` ordered by title, department, pk, showing ID, title, department, status, and skills; the create page at `/openings/new/` needing only title and department and defaulting to Open; an Openings header link; detail, edit, and inline skill kept consistent. Add normal tests for: creating with only title and department; two openings with the same title; identical openings told apart by ID; the skill database constraint; status not changeable through the form; login on every opening page and the inline endpoint; and the list order. Run all checks, rebuild CSS if needed, and stop before manual testing.
10. Requirement change: add a Manage Skills page and safe, permanent in-app skill deletion. Update the PRD, plan, and PROMPTS.md first, propose up to three test-first behaviors, and stop. *(Full text in the requirement-change entry below.)*
11. Approved the Manage Skills design, the three test-first behaviors, and both decisions: (1) count all openings using a skill, Open and Closed; (2) show a one-time Django success message after deletion with the skill name and the number of openings affected. Write Test 1 only: with a skill used by one Open and one Closed opening, a GET shows the name, "2 openings", and a POST confirmation form, and changes nothing. Show RED and explain.
12. Approved Manage Skills Test 1 and its RED. Build the minimum for GREEN: `SkillDeleteView` using `DeleteView`; the namespaced URL `/openings/skills/<pk>/delete/`; `skill_confirm_delete.html` extending the base template; the name and total opening count, Open and Closed; an explicit POST form with CSRF; a Cancel link that changes nothing; loading the page never deletes or unlinks. Run all checks, stop before Test 2, and don't build the list or success message.
13. Approved Manage Skills Test 1 GREEN. Write Test 2: two openings share Python and SQL; a confirmed POST deletes Python; Python and its links are gone; both openings still exist, keep SQL, and have unchanged fields and `updated_at`; SQL still exists; the redirect goes to the planned Manage Skills URL; a one-time success message names Python and the number of openings affected. Show RED with the exact assertion that fails. Don't break the existing deletion behavior to force a RED. Include `makemigrations --check`.
14. Approved Manage Skills Test 2 and its RED, and approved a minimal Manage Skills list view and route in this GREEN step so the redirect lands on a working page. Build GREEN: redirect to `openings:skill_list`; a minimal list at `/openings/skills/` without the full table or delete links; a one-time success message with the name and count, both captured before deletion; messages shown safely in the base template; Cancel going to Manage Skills and changing nothing. Update Test 2's message-display checks to use `/openings/skills/`, keeping the original RED/GREEN evidence. Run all checks and stop before Test 3.
15. Approved Manage Skills Test 2 GREEN, including the corrected escaping assertion. Keep the quotation marks in the success message, with Django's normal escaping. Write Test 3: skills used by 2, 1, and 0 openings all appear on `/openings/skills/` with correct counts including Closed openings, each with a Delete link to its own confirmation page, sorted A–Z ignoring capitals. Show RED and the exact assertion that fails.
16. Approved Manage Skills Test 3 and its RED. Build GREEN: `SkillListView` counting with `Count("openings")`; alphabetical order ignoring capitals kept; a DaisyUI table of Skill · Used by · Delete; correct singular or plural wording for 0, 1, and more; a Delete link per skill; a Manage Skills link on the Openings page. Run all checks, then add normal tests for Cancel, login, deactivated users, non-existent skills, repeated deletes, and navigation. Run everything again, report totals, and stop before manual testing.
17. Reported Phase 3 manual browser testing as complete and approved: the Job Openings page loads; a Data Analyst opening was created; the detail and edit pages work; adding Python through HTMX worked without losing the form's other input; duplicate skill validation showed the correct error; Manage Skills let the user permanently delete an unwanted skill after a confirmation warning that it can't be undone, which the user confirmed. Finish Phase 3: update PROMPTS.md, review git status and all changes including the PRD and plan, exclude database files, generated CSS, and unrelated files, run all checks, commit, push to `origin/main`, and report (this prompt).

### Summary
- **Outcome:**
  - **Phase 3 complete in the `openings` app.**
    - **Models:** `OpeningStatus` (`TextChoices`); `Skill` with the case-insensitive `UniqueConstraint(Lower("name"))` and a shared duplicate message; `JobOpening` with optional description and location, status defaulting to Open, `skills` many-to-many (`related_name="openings"`), and tuple `Meta` ordering by title, department, pk. One migration, `0001_initial.py`.
    - **Forms:** `JobOpeningForm` with no status field and skills as a checkbox list; `SkillForm` with `clean_name()`.
    - **Pages:** class-based list, create, detail (`/openings/<pk>/`), and edit views; the inline HTMX Add skill endpoint; Manage Skills (`/openings/skills/`) with a GET confirmation page and a deleting POST at `/openings/skills/<pk>/delete/`; a one-time success message.
    - **Shared changes:** Openings header link, a Manage skills button, and a messages area in `base.html`; the Phase 2 edit-tab title fix.
  - **TDD results (six behaviors, each RED then GREEN):**
    - **Test 1** (removing a shared skill from one opening leaves the skill and the other opening alone): RED `assert 404 == 302`. GREEN with `JobOpeningForm` and the update and detail views.
    - **Test 2** (inline Add skill: trimmed name, capitals kept, fragment only, new skill and earlier ticks ticked, unticked skills left unticked, no `JobOpening` created or updated): RED `assert 404 == 200`. GREEN with `SkillForm`, the POST-only `add_skill_inline` view, and the `_skills_field.html` partial (`hx-post`, `hx-include`, `hx-params`, `hx-target`, `hx-swap="outerHTML"`).
    - **Test 3** (inline duplicate "python" refused with a message in the fragment, selection kept): RED on the missing message. GREEN with `clean_name()` and error display in the partial.
    - **Manage Skills Test 1** (the confirmation GET shows the name and "2 openings", Open and Closed, with one POST form, and changes nothing): RED `assert 404 == 200`. GREEN with `SkillDeleteView` (`DeleteView` plus `Count("openings")`) and `skill_confirm_delete.html`.
    - **Manage Skills Test 2** (a confirmed POST deletes Python and its links; both openings unchanged including `updated_at`; SQL survives; redirect to Manage Skills; a one-time success message): RED `assert '/openings/' == '/openings/skills/'`. GREEN with `success_url` set to `openings:skill_list`, a `form_valid()` that captures the name and count before deleting, a minimal `SkillListView`, and the messages area in `base.html`.
    - **Manage Skills Test 3** (all skills A–Z ignoring capitals with correct 2, 1, and 0 counts and their own delete links): RED inside `row_for()`, `expected one table row containing '>agile<'`. GREEN with the counted, explicitly ordered `SkillListView` and the table template.
  - **Other tests:** 20 for the opening pages and 12 for Manage Skills, written normally. Final: 71 tests passed; Ruff check and format check clean; `manage.py check` clean; `makemigrations --check` reports no changes. Tailwind CSS rebuilt.
  - **Endpoint safety:** scratchpad probes, not committed, confirmed:
    - made-up skill IDs (`"abc"`, `"99999"`, `"-1"`) are dropped
    - blank, too-long, and duplicate names are rejected, each with one escaped message, with the typed name and ticks kept
    - GET gets 405, anonymous visitors are redirected to login, and a missing CSRF token gets 403
    - the edit page contains no form inside a form
  - **Manual browser tests (user):** all passed (see prompt 17).
- **Deviations:**
  - **User-requested skill deletion:** this reversed the approved PRD rule ("No in-app deletion (Django admin only)", and out of scope). The PRD and plan were updated with dated notes, stories 75–76, and five acceptance criteria before any code was written.
  - **Detail page:** the opening detail page `/openings/<pk>/` wasn't in the plan's URL list. It was approved as decision 1 and added to the plan with the skill-deletion update.
  - **Two additions approved as they came up:** the Enter-key handler on the New skill box, to stop it submitting the whole opening form; and `hx-params` to send only `new_skill_name` and `skills`.
  - **Minimal Manage Skills list first:** at the user's approval it was added during Manage Skills Test 2's GREEN, so the redirect reached a real page; Test 3 then built out the full table.
  - **Escaped message text:** the success message keeps its quotation marks, and its display check compares against the escaped text, at the user's direction.
  - **Literal paths again:** the test-first tests used the plan's fixed paths instead of `reverse()`, so each RED was an assertion failure rather than a `NoReverseMatch` error.
- **Sideways:**
  - **A `noqa` I shouldn't have used:** my first `JobOpeningForm` silenced `RUF012` with `# noqa` on `Meta.widgets`, which went against the decision to keep that rule on. I replaced it with an explicitly declared `skills` field before reporting.
  - **Phase 2 tab-title bug:** I found that the candidate edit page's browser tab still said "New candidate", because a Phase 2 edit had missed that line. I reported it, and the user approved a one-line fix.
  - **Test helper crash:** Test 2's first `checkbox_tag` helper would have crashed with a `TypeError` on a missing checkbox. I changed it to assert before running the RED.
  - **Duplicate prompt:** prompt 3 repeated prompt 2. I re-checked the state and redid nothing.
  - **Missing CSS class:** `input-bordered` compiled to nothing, because the DaisyUI version bundled with the Tailwind binary doesn't have it, so I removed it. A weak `"IT" in page` assertion was tightened to check the table cells.
  - **PRD slip:** while updating the PRD for skill deletion, I added an Out of Scope sentence the user never asked for. I removed it before reporting; it's logged in the requirement-change entry.
  - **Temporary targets:** Manage Skills Test 1's GREEN pointed Cancel and `success_url` at the Openings list until the skills list existed. Test 2's RED then came from that redirect, because `DeleteView` already deleted the skill and its links correctly.
  - **Manage Skills Test 2's first GREEN run** failed on the test, not the app: the message's quotes rendered as `&quot;`. The display checks were repaired with `escape()`, and the user approved that.
  - **Real bug caught by Manage Skills Test 3:** adding `Count("openings")` made Django drop `Skill.Meta.ordering`, so the list came back in creation order. I fixed it with an explicit `.order_by(Lower("name"), "pk")`; Test 3's mixed-case names exposed it.
  - **Never-RED tests:** the 32 normal tests passed on their first run, as expected for tests that aren't test-first.

## 2026-11-01 — Requirement change during Phase 3: in-app skill deletion

*(Recorded at the user's explicit request when the change was made, before any implementation. The full Phase 3 session log will be added when Phase 3 is finished.)*

### Prompts
1. "I want to make an explicit change to the approved Phase 3 requirements." Employees must be able to permanently delete unwanted skills through the ATS website, without Django Admin or PowerShell. Add a Manage Skills page for logged-in employees, linked from the Openings area, showing each skill's name and how many openings use it, with a Delete action. Require explicit confirmation showing the skill name and how many openings will lose it. Opening the confirmation page must delete nothing, and only a confirmed POST may delete. Deletion removes the skill's links to openings without deleting or modifying the openings. Cancel changes nothing. Unauthorized or anonymous users can't delete. Use the existing class-based views, templates, and styling, with no new dependencies. Update the Phase 3 requirements and acceptance criteria first, record the change in PROMPTS.md, propose up to three test-first behaviors, and stop for approval. No implementation, tests, commit, push, or Phase 4.

### Summary
- **Outcome:**
  - **PRD:** the Skill rule changed from "No in-app deletion (Django admin only)" to in-app deletion after confirmation, with the original text kept in a note. Stories 75–76 were added (numbered after 74 so existing references stay valid). An implementation bullet and a tier-2 testing item were added. "In-app skill deletion or a standalone skill management page" was struck from Out of Scope, with a dated note.
  - **Plan:** the architecture header now has the Skill deletion rule and the `/openings/skills/` and `/openings/skills/<pk>/delete/` URLs. It also now lists `/openings/<pk>/`, the detail page approved earlier in Phase 3, which the URL line was missing. Phase 3 adds stories 75–76, a description of the change, and five acceptance criteria.
  - The design and test-first behaviors were proposed for approval. Nothing is implemented yet.
- **Deviations:** the user reversed an approved PRD decision. Skill deletion had been Django-admin-only and listed as out of scope; it's now an in-app feature in Phase 3.
- **Sideways:** while editing the PRD's Out of Scope list, I added a sentence the user never asked for ("Renaming skills in-app remains out of scope"). I removed it before reporting, so the PRD records only the user's change.

## 2026-11-01 — Phase 1 commit and push, and Phase 2 (candidate records) via `/implement`

*(Continues the same session as the Phase 1 entry below. Long prompts are condensed to their substance; nothing is added that the prompt did not say.)*

### Prompts
1. Approved the Phase 1 PROMPTS.md entry. Run `git status`, check that only the intended Phase 1 files would be committed, confirm `db.sqlite3`, `.venv`, the built Tailwind CSS, and the Tailwind binary are excluded, and show the status and a proposed commit message. Don't commit or push.
2. Approved the 39 files and the commit message. Stage and commit only those files, including PROMPTS.md, keeping the Co-Authored-By line. Show the commit ID and a clean working tree. Don't push.
3. Push the Phase 1 commit (`f740f01`) to `origin/main`, then verify the branch matches and the tree is clean. Don't begin Phase 2.
4. Begin Phase 2 with `/implement`, following `CLAUDE.md` and the course TDD process. Review the acceptance criteria, propose up to three test-first behaviors, explain each, and list any decisions the PRD and plan don't settle. Stop for approval. No Phase 3, no unrelated changes.
5. Approved the three behaviors and decisions 1–9, with two clarifications: (1) remove surrounding spaces from emails during normal input validation and keep the form's duplicate check consistent with the database's case-insensitive constraint, with no new normalization system or dependencies; (2) order the list by `last_name`, `first_name`, then pk. Keep `is_archived` in the model but don't implement archiving until Phase 6. Start with Test 1: write it, run it, show RED, and stop.
6. Approved Test 1 and its RED. Add the `Lower("email")` constraint, create the migration, re-run Test 1 for GREEN, and run the Phase 1 tests. Explain and stop before Test 2.
7. Approved the recommended Ruff fix: add the migrations pattern to `extend-exclude`, change `Candidate.Meta.ordering` and `constraints` to tuples, and keep `RUF012` on everywhere else. Don't hand-edit the generated migration. Run pytest, Ruff, and `makemigrations --check`, then stop.
8. Chose Option 1: regenerate `candidates/migrations/0001_initial.py` with `makemigrations`, since it was neither applied nor committed. Don't rewrite it by hand, delete other migrations, or reset the local database. Run all checks and stop.
9. Approved the regenerated migration and Test 1 GREEN. Write Test 2 (create with only the required fields), show RED, explain why it fails, and stop.
10. Approved Test 2 and its RED. Build the minimum for GREEN: a `CandidateForm` ModelForm, create and detail views, namespaced candidate URLs and the project URL include, form and detail templates extending the base template, and email trimming that keeps capitalization. Run Test 2, the full suite, Ruff, and Django checks, then stop before Test 3.
11. Approved Test 2 GREEN. Write Test 3 (duplicate email rejected with a link to the existing record), show RED, explain precisely why it fails, and stop. The test must check that no duplicate is created and that the link is safe and usable.
12. Approved Test 3 and its RED. Build the proposed GREEN: `CandidateForm.clean_email()` with a case-insensitive check, skipping the candidate being edited; a clear message; a link drawn with normal template escaping; no `mark_safe` and no raw HTML in messages; and the database constraint kept as the final safeguard. Run all checks and stop before the list and edit pages.
13. Approved Test 3 GREEN. Finish the rest of Phase 2: the list at `/candidates/` ordered by last name, first name, pk; the edit page using `CandidateForm`; a Candidates header link; tests for valid and invalid sources, for editing without changing one's own email, for changing to another candidate's email being rejected with a link, and for login on every candidate page. Run all checks, summarize, and stop before manual browser testing.
14. Reported the manual browser tests as `jdoe`: the list was empty at first; Ana Lopez was created with only the required fields; the detail page was correct; a duplicate email in different capitals got the right error and link; Ana's phone, source detail, and notes were edited; and the list had only one record. Finish Phase 2: update PROMPTS.md, review `git status`, run all checks, commit, push to `main`, and report the hash, push confirmation, and final status (this prompt).

### Summary
- **Outcome:**
  - **Phase 1 committed and pushed:** `f740f01`, 39 files.
  - **Phase 2 complete in the `candidates` app.**
    - **Model and migration:** the `Source` `TextChoices` (job_board, referral, company_website, other); the `Candidate` model with the approved fields and `is_archived` (default false, not used until Phase 6); tuple `Meta` ordering `("last_name", "first_name", "pk")`; and `UniqueConstraint(Lower("email"))` with a shared `DUPLICATE_EMAIL_MESSAGE`. One migration, `0001_initial.py`, created by `makemigrations`.
    - **Form:** `CandidateForm` with `clean_email()`, which does the case-insensitive check, skips the candidate being edited, and saves the matching candidate as `form.duplicate_candidate` so the template can link to it.
    - **Pages:** class-based list, create, detail, and edit views under the `candidates` namespace, with DaisyUI templates and a Candidates header link.
  - **TDD results:**
    - **Test 1** (the database rejects emails that differ only by capitals): RED with `Failed: DID NOT RAISE IntegrityError`. The `Lower("email")` constraint made it GREEN.
    - **Test 2** (create with only the required fields, email spaces removed but capitals kept, redirect to a detail page showing the source label): RED with `assert 404 == 302`, because no candidate routes existed. The form, views, URLs, and templates made it GREEN. The trimming came from Django's `EmailField` (`strip=True`) with no extra code.
    - **Test 3** (a case-only duplicate is refused, nothing is saved, and an escaped link to the existing record is shown): RED on `assert 'href="/candidates/1/"' in page`. The constraint already blocked the save and showed the message, but there was no link. `clean_email()` and the template link made it GREEN. A scratchpad probe confirmed the error appears once, on the email field, with no second error from the constraint.
  - **Other Phase 2 tests:** 20 normal tests covering source choices, list order and links, editing, own-email and other-email edits, and login on every candidate page and on anonymous POSTs. Final: 33 tests passed; Ruff check and format check clean; `manage.py check` clean; `makemigrations --check` reports no changes.
  - **Manual browser tests (user, as `jdoe`):** all passed (see prompt 14).
- **Deviations:**
  - **User clarifications to my proposal:** the stable pk tie-breaker in the list order, and an explicit rule that email trimming stays within normal validation and matches the constraint.
  - **Ruff `RUF012`:** Ruff 0.17's default rules flagged Django `Meta` and migration lists. I recommended excluding migrations from Ruff and using tuples in `Meta`; the user approved and asked to keep `RUF012` on elsewhere.
  - **Extra migration avoided:** I didn't foresee that switching `ordering` from a list to a tuple would make Django want a new migration. I offered three options, and the user chose to regenerate `0001_initial.py` rather than add a migration that changed nothing in the database.
  - **Cosmetic widget dropped:** to keep the GREEN minimal and avoid suppressing `RUF012`, I removed a 4-row notes `Textarea` widget instead of keeping it.
  - **Literal paths in Test 2:** it uses the plan's fixed paths (`/candidates/new/`, `/candidates/<pk>/`) rather than `reverse()`, so the RED would be an assertion failure and not a `NoReverseMatch` error.
- **Sideways:**
  - **Phase 1 push check:** after the push, my check command errored (`fatal: Needed a single revision`) because I passed two revisions to `git rev-parse --short`. The push itself had succeeded; re-running one revision at a time confirmed local and remote both at `f740f01`.
  - **Ruff surprises:** Ruff failed twice in Phase 2: on `RUF012` after Test 1's GREEN, and on import order plus the widget dict after Test 2's GREEN. Both were reported; the first was settled by the user, and the second was a mechanical fix.
  - **Duplicate-error probe:** my first two attempts to run the scratchpad probe failed with setup errors because it ran outside the project's pytest config. Adding `--ds=config.settings` fixed it.
  - **Test file write:** a shell heredoc used to write `test_candidate_pages.py` failed to parse, so nothing was written. I wrote the file with the Write tool instead.
  - **Never-RED tests:** the 20 normal Phase 2 tests passed on their first run, since they aren't test-first. I said so and offered to deliberately break some to show they catch failures; this wasn't taken up.
  - **Local database:** the user's local database needed `migrate` before manual testing, because `candidates.0001` hadn't been applied.

## 2026-11-01 — CLAUDE.md, and Phase 1 (project setup and login-only access) via `/implement`

*(Continues the same session as the plan entry below. Long prompts are condensed to their substance; nothing is added that the prompt did not say.)*

### Prompts
1. Create a `CLAUDE.md` at the repo root, about 20–30 lines, using the approved PRD and plan as sources of truth. Cover purpose and stack, the three apps and their boundaries, stage rules (permanent Hired, one-step Undo), auth and database protection, the TDD workflow (review tests → RED → GREEN), one approved phase at a time, and maintaining PROMPTS.md. Don't invent commands, structures, or conventions. Don't implement Phase 1. Show the full contents for review.
2. Approved `CLAUDE.md` as written; keep the field name `stage_changed_at` consistent with the plan. No further changes, and don't begin Phase 1.
3. `git add CLAUDE.md`
4. `git commit -m "Add approved CLAUDE.md project instructions"`
5. `git push`
6. Begin Phase 1 with `/implement`, using the plan and `CLAUDE.md`. Follow TDD: first propose the Phase 1 tests and explain each, then stop for approval before writing implementation code. No later phases. No extra architectural decisions without explaining them and asking first.
7. Approved all three test behaviors and decisions 1–7 (`LoginRequiredMiddleware`, a `config/` settings package, the placeholder `/` in `hiring`, per-app `tests/` folders, a pinned saved copy of HTMX, django-tailwind-cli's DaisyUI option, POST logout). Keep the admin-created-account approach with no roles. The login page must stay open to anonymous users. Use the supported DaisyUI setup without Node.js. Start with Test 1 only: write it, run it, show RED, stop.
8. In Claude's question dialog about the uv workspace, chose **"Standalone project (Recommended)"**.
9. Approved Test 1 and its RED. Approved the login/logout-only URLs and asked to verify no other auth routes are included. Implement `LoginRequiredMiddleware` and the minimum code for GREEN; show the result, run regression checks, explain the changes, and stop.
10. Approved Test 1 GREEN. Write Test 2, show RED, explain the failure, and stop. Keep the Ruff cleanup as a separate task before Phase 1 finishes.
11. Approved Test 2 and its RED, the project-level `templates/` folder, and hiring employees as active, non-staff users (`is_active=True`, `is_staff=False`), with admins keeping their Django admin privileges. Asked for those account properties to be asserted in Test 2. Implement the minimum for GREEN (base template, username display, POST logout form) with Tailwind/DaisyUI and HTMX where appropriate. Show GREEN and run the full suite.
12. Approved Test 2 GREEN; don't mark Phase 1 complete yet. Agreed to exclude the built `static/css/tailwind.css` from Git if the build steps are documented and reproducible. Write Test 3, show RED, and stop. No commits.
13. Keep both Test 3 checks as regression tests, and don't add code just to produce a RED. Record in the Phase 1 log that Test 3 passed straight away because of Django's built-in auth, and that the temporary backend experiment showed the tests catch a regression. Then do the remaining Phase 1 work only: verify no sign-up routes or links; verify Tailwind/DaisyUI and HTMX are set up and load; clean up the Ruff issues in generated files; run pytest, Django checks, and Ruff; give run instructions; do browser checks or explain the manual ones. Explain significant changes first. No Phase 2, no commit or push.
14. Reported the manual browser test results and asked for a review of all Phase 1 acceptance criteria against them and the automated checks. Results: the login page displayed with Tailwind/DaisyUI styling; the administrator logged in and out; a regular active, non-staff account `jdoe` was created and could reach the workspace but was denied Django admin; deactivation was tested in separate regular and InPrivate browser sessions, and `jdoe` lost workspace access; after reactivation `jdoe` could log in again.
15. Approved Phase 1 as complete (all six acceptance criteria met). Finish one step at a time, starting with this PROMPTS.md update (this prompt). No commit, push, or Phase 2.

### Summary
- **Outcome:**
  - **CLAUDE.md:** written (29 lines), approved without changes, committed as `99cf8d3`, and pushed.
  - **Phase 1 built and approved complete.** Contents:
    - a standalone uv project (Django 6.1.2, django-tailwind-cli, pytest, pytest-django, Ruff) with its own `uv.lock`
    - the `config/` settings package and the `candidates`, `openings`, and `hiring` apps, each with a `tests/` folder
    - `LoginRequiredMiddleware`, and only the `accounts/login/` and `accounts/logout/` routes
    - a placeholder workspace at `/` in `hiring`
    - a project-level `templates/` folder with `base.html` (DaisyUI header, username, POST logout form, CSRF header for HTMX) and `registration/login.html`
    - a pinned HTMX 2.0.4 at `static/js/htmx.min.js`
    - DaisyUI via `TAILWIND_CLI_USE_DAISY_UI = True`, with no Node.js
    - the built `static/css/tailwind.css` ignored by Git, with build steps in `README.md`
  - **TDD results:**
    - **Test 1** (anonymous visitor redirected to login): RED with `assert 200 == 302`. Adding `LoginRequiredMiddleware` made it GREEN.
    - **Test 2** (an active, admin-created employee logs in, sees the workspace with their username and a logout form, and logs out): RED with `assert 'jsmith' in 'Hiring workspace'`. The base template, username display, and POST logout form made it GREEN. The test also asserts `is_active=True`, `is_staff=False`, and `is_superuser=False`.
    - **Test 3** (a deactivated employee can't log in, and deactivating an already logged-in employee ends their access): both checks **passed straight away, with no RED**. Django already provides this: `ModelBackend` and `AuthenticationForm` both reject inactive users, and the backend drops inactive users from existing sessions. No code was added to force a RED; both checks are kept as regression tests.
    - **Temporary backend experiment:** a throwaway settings file in the scratchpad (no project files changed) switched to `AllowAllUsersModelBackend`. The existing-session test then **failed** (`assert 200 == 302`), proving it catches a regression. The login test still passed, because `AuthenticationForm` has its own inactive-user check.
  - **Other Phase 1 checks:** tests that `/signup/`, `/register/`, `/accounts/signup/`, and `/accounts/register/` return 404, that the login page has no sign-up or register text, and that the base template links the Tailwind CSS and HTMX. A real-server smoke test got 302 for `/`, 200 for login, 404 for sign-up, and 200 for both the CSS and HTMX files.
  - **Ruff cleanup:** `ruff check --fix` removed 8 unused imports from Django's starter files, and `ruff format` reformatted 17 files (quote style and line wrapping; no test assertions changed).
  - **Final checks:** 10 tests passed; Ruff check and format check clean; `manage.py check` clean; `makemigrations --check` reports no changes.
  - **Manual browser tests (user):** all six acceptance criteria confirmed, including `jdoe` being denied Django admin and deactivation followed by reactivation.
  - Phase 1 is not yet committed or pushed.
- **Deviations:**
  - **Login/logout-only URLs:** I made this decision without asking first (so password-reset and password-change pages weren't exposed, since email is out of scope). I flagged it right away, and the user approved it and asked for the URL list to be checked, which I did.
  - **"Staff account" wording:** my Test 2 proposal said "a staff account," but the test used a non-staff user on purpose. I flagged the mismatch; the user confirmed non-staff employees and asked for the account properties to be asserted.
  - **Project-level `templates/` folder:** a small decision I made to get Test 2 running; the user approved it afterward.
  - **Test 3 has no RED:** the TDD cycle wasn't completed for it. Following the tdd skill (a behavior an existing, tested pattern already settles isn't a TDD candidate) and the user's instruction, the checks became regression tests backed by the backend experiment.
  - **Ruff cleanup kept separate:** at the user's request it was held back from the Test 1 and Test 2 GREEN steps and done at the end of the phase.
  - **Built CSS excluded from Git:** the user agreed on condition that the build is documented and reproducible; it's documented in `README.md`.
  - **Commit message:** the user's literal `git commit -m` command was run as typed, so `99cf8d3` has no Co-Authored-By line.
- **Sideways:**
  - **uv workspace:** the first `uv init` and `uv add` found an existing workspace at `C:\Users\deana\pyproject.toml` and added this repo to it, editing that file and the home `uv.lock`. I stopped and asked. After the user chose a standalone project, I removed the one added members line, re-ran `uv lock` in the home folder (only the ATS-added packages were dropped), and ran `uv sync` in the repo to create its own `uv.lock` and `.venv`.
  - **Test 2's first run** hit `TemplateDoesNotExist: registration/login.html`, which is an error, not a RED. I added a minimal login template and the `templates/` folder, re-ran, and got a real assertion failure.
  - **Ruff on Django's generated files** failed (8 unused imports, 8 files to reformat) when first checked after Test 1. This was reported and deferred to the agreed cleanup step rather than fixed during GREEN.
  - **Browser automation:** I didn't automate a browser login, to avoid creating users in the local database without asking. I gave a manual checklist instead; the user's `jdoe` and admin accounts live in the ignored local `db.sqlite3`.
  - **Shared browser sessions:** according to the user, deactivation testing was at first confused by sharing one browser session between the admin and the employee. Using a regular window and an InPrivate window as separate sessions fixed it and confirmed `jdoe` lost access.
  - **Earlier commit made outside this session:** between the plan work and the `CLAUDE.md` commit, the user committed the PRD, plan, prototypes, and logs as `20c8c2c`; `git status` showed them already committed when `CLAUDE.md` was staged.

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
