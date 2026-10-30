---
name: implement
description: Implement one approved phase from a PRD and plan using feedback loops.
argument-hint: "@prd/<feature>.md @plans/<feature>.md implement phase <N>"
disable-model-invocation: true
---

# Implement

## 1. Understand the Phase

Read the referenced PRD and plan. Explore the codebase to understand the relevant files,
patterns, and conventions. If the request does not identify a phase, ask which one.

Implement only that phase. Do not begin the next one.

## 2. Implement the Phase

Run the tdd skill for the current phase and follow its instructions, including approval checkpoints; if no behaviors qualify, report that TDD was skipped.
Implement all remaining phase requirements using the project's normal development and testing conventions.

## 3. Run Feedback Loops

Run the full test suite, linter, formatter checks, and any additional checks required by the project.
Fix any failures and rerun the affected checks until they pass, reporting any unresolved issues.

## 4. Manual Verification

Explain how I can verify this phase or feature manually in the browser, using its acceptance criteria.
Stop and wait for my confirmation; do not finish the phase until I confirm the manual checks passed.

## 5. Finish the Phase

After manual verification is approved, update PROMPTS.md using its specified format.
Commit only the completed phase's intended files and push the commit to GitHub, then report the result.
