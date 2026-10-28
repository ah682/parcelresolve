# Runtime Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix four reproduced state-management gaps while keeping the local simulator and existing recovery contracts.

**Architecture:** Reuse the existing browser selection sequence and bind modal updates to their dialog instance. Keep zero-total cancellation inside current final verification, and resume seed creation one missing record at a time without replacing existing state.

**Tech Stack:** Python 3.12, SQLite, pytest, TypeScript, Playwright/Chrome, npm/make.

**Spec:** [Accepted audit findings](#accepted-audit-findings) below; authorization covers implementation without another plan approval.

## Accepted audit findings

1. A mutation-error read-back for order 1042, delayed until the user selects 1043, replaces the selected evidence with 1042.
2. Closing/reopening New request while two order-list reads overlap lets the older response destroy the newer draft. Late modal submissions can likewise close a replacement dialog.
3. A valid zero-total cancellation performs cancellation, then escalates because final verification demands refund quantities although no refund is owed.
4. Interruption after writing the first seed order leaves one order and no cases on every subsequent startup.

## Global constraints

- One local machine; offline synthetic simulator; actual live recovery writes remain unsupported.
- No new dependencies, license, speculative abstractions, or model claims.
- Preserve existing modified orders/cases, approvals, effects, and the frozen model failure evidence.
- Never invent a zero-value refund or repeat a completed seed operation.
- Root owns workflows, dependency locks, publication and aggregate audit documentation.

## Review focus

- Case selection or role can change while an error recovery GET waits: browser regression in task 1.
- A closed dialog's successful submission can finish after another dialog opens: regression in task 2.
- A reopened form has typed unsaved text: regression in task 2 verifies preservation.
- Zero-total labelled cancellation still needs a hold and void, and must survive restart: parametrized test in task 3.
- Seed restart can encounter a modified or already-resolved case: preservation assertions in task 4.

### Task 1: Keep recovery read-back attached to the current selection

**Files:** Modify `frontend/src/app.ts`, `frontend/scripts/presentation-checks.mjs`.

**Interfaces:** Keep `mutate(action: string, body: unknown): Promise<void>` and existing `checkPresentationStates(browser, baseURL, snapshots)`; no new production interface.

- [x] Add a controlled-response browser test: fail the mutation, delay its fallback GET, select a second case, release the old GET; assert both queue and detail still identify the second order.
- [x] Run the browser test against the old code and record the identity assertion failure.
- [x] Read the fallback GET into a local result; update selection only if its captured selection is still current after the await.
- [x] Rebuild and run the regression; assert no unexpected page error and no extra mutation.

### Task 2: Keep async modal results attached to their dialog

**Files:** Modify `frontend/src/app.ts`, `frontend/scripts/presentation-checks.mjs`.

**Interfaces:** `modalShell(...)` may return its created `HTMLDialogElement`; callers use `dialog.isConnected` before asynchronous UI changes.

- [x] Add delayed-response tests for two New request openings and for a completed submission after closing/reopening. Assert the replacement form retains its text and remains open.
- [x] Run both tests before implementation and record the lost-draft/closed-dialog failures.
- [x] Return/capture the existing dialog and check its identity after each relevant asynchronous boundary in new-request, clarification and simulation forms; scope error updates to the original dialog.
- [x] Rebuild and rerun browser regressions, including existing validation/focus checks.

### Task 3: Verify cancellation when no refund is due

**Files:** Modify `parcelresolve/engine.py`, `tests/test_recovery.py`.

**Interfaces:** Keep `Engine.terminal_verified(case, order) -> bool` and `Engine._draft(case) -> str`.

- [x] Add `test_zero_total_cancellation_resolves_without_refund` for labelled/unlabelled valid £0 orders. Assert approval still gates execution, final cancellation/label state is durable after restart, no refund/effect exists, and draft says no refund was required.
- [x] Run the test before implementation; expect `escalated` instead of `resolved`.
- [x] Exempt zero-captured orders from refund-quantity completion while retaining all other terminal checks. Use accurate zero-total customer copy.
- [x] Run `tests/test_recovery.py`; existing paid refund/partial-return/dispatch tests must pass.

### Task 4: Resume missing seed records without resetting existing work

**Files:** Modify `parcelresolve/seed.py`; create `tests/test_seed.py`.

**Interfaces:** Keep `seed_demo(engine: Engine) -> None` and `make_order(...)`.

- [x] Add interrupted seed tests after first order and first case persistence; restart and assert six cases and seven orders without duplicate cases or queued faults.
- [x] Add a repeat-seed preservation test that modifies an order, resolves a case, and compares persisted cases/orders/effects before and after reseeding.
- [x] Run the tests before implementation; interrupted seed must fail with an incomplete catalog.
- [x] Enumerate existing order/case identities once; create only missing demo records and perform initial investigation/fault setup only for newly created cases. Preserve existing state and avoid duplicate startup writes.
- [x] Rerun seed tests and the whole Python suite.

### Final verification and commit

- [x] Run `npm test` (format/lint/types/build, complete Python tests, 336 offline trials at seeds 7/19/41).
- [x] Run `npm test -- --browser-only` with an isolated output directory; new races run through the existing browser path.
- [x] Review the owned diff for unsupported claims or unrelated changes; commit only runtime/frontend/test/plan files.
- [x] Report commit SHA, exact fresh counts, red/green evidence and remaining validation limits to the root agent. Do not push.

## Verification record

- Baseline: 307 Python tests passed.
- RED: selected-order assertion, erased reopened form, and closed replacement dialog each failed before the corresponding browser fix.
- RED: both zero-total cancellation variants returned escalated; all three interrupted-seed variants produced incomplete records.
- GREEN: `npm test` passed lint/format/types/build, 313 tests, and 336/336 offline trials over 40 scenarios at seeds 7/19/41. The existing Starlette/httpx test-client deprecation warning remains.
- GREEN: isolated `npm test -- --browser-only` passed 15 workflow/layout/contrast checks and 11 controlled presentation checks, including the three new delayed-response cases.
- Seed restart preserves an existing case, including one whose initial investigation was interrupted; its existing Investigate control continues that read-only step. Default fault rows are installed before creating their case and checked before insertion, so restart does not lose or rearm them.
- No real provider writes, merchant validation, hosted calls or local-model inference were performed. Historical rejected-model evidence remains unchanged.
- Author diff review passed; the root agent owns independent review and publication of this commit.
