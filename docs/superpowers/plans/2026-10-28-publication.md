# ParcelResolve Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Publish a reproducible, honestly documented local recovery desk with verified release evidence.

**Architecture:** Preserve the accepted FastAPI, TypeScript and durable SQLite simulator design. Audit existing behavior before changing it, reproduce defects before fixing them, and keep authenticated live execution unsupported.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic, SQLite, TypeScript, esbuild, pytest, Playwright.

**Spec:** Publication request, accepted implementation in `docs/ARCHITECTURE.md` and existing `docs/BUILD_STATE.md`. The original `02_Shipping_Recovery_Agent_Prompt.txt` is preserved locally and excluded from the public tree.

## Global Constraints

- One store, one warehouse and three flows: pre-label cancellation, post-label cancellation before confirmed dispatch, and domestic address correction with label recreation.
- No customer messages, merchant mutations, paid model calls or deployment.
- Keep synthetic/default, real read-only and experimental inference evidence distinct.
- Preserve the original project; work in this isolated release copy.
- Python `>=3.12,<3.13`; dependencies remain locked.

## Review Focus

- Fresh clone installs and runs without excluded caches, build output, weights or raw run directories.
- Invalid authentication/input produces an explicit rejection rather than a server error.
- Interrupted or ambiguous writes remain incomplete until read-back establishes their outcome.
- Browser acceptance preserves primary demo data and tests real operator actions.
- Retained reports describe actual tested source and do not imply the failed CPU model is deployable.

### Task 1: Verify release behavior and fix reproduced defects

**Files:** `parcelresolve/`, `tests/`, `Makefile`, `.github/workflows/verify.yml`, dependency locks as required by observed failures.

**Interfaces:** Consumes existing CLI/API and test runner; produces a fresh verified offline release with unchanged supported scope.

- [x] Run `make setup` from the copied checkout. Expected: locked Python/npm install and asset build succeed.
- [x] Run `npm test`. Expected: lint, formatting, types, build, Python tests and both default evaluation profiles pass.
- [x] Investigate each failure before editing. For a product defect, add a minimal regression, observe RED, implement the smallest fix, observe GREEN.
- [x] Run `npm test -- --browser-only`. Expected: all workflow/presentation checks pass against disposable data.
- [x] Run the documented `npm run dev`, request authenticated `/api/meta`, stop the owned process and run `make reset`. Expected: local simulator starts and reset succeeds after shutdown.
- [x] Commit tested fixes, if any.

### Task 2: Prepare accurate publication documentation and evidence

**Files:** `README.md`, `docs/BUILD_STATE.md`, `docs/VERIFICATION.md`, `docs/EVALUATION.md`, `evaluation/README.md`, `frontend/qa/README.md`, publication plan and new compact release evidence.

**Interfaces:** Consumes Task 1 command results and historical artifact manifests; produces public-facing setup, limitations and reproducible evidence references.

- [x] Rewrite the README around who uses the desk, startup, three recovery flows, verification and explicit integration/model limits.
- [x] Retain compact authentic historical/model evidence and fresh offline results; document any omitted local-only raw artifacts without overstating what the repository contains.
- [x] Record exact fresh command outcomes, warnings and remaining external gates in verification/build state.
- [x] Check local documentation links and `git diff --check`. Expected: no broken repository links introduced and no whitespace errors.
- [x] Commit publication documentation and report tested commit to the parent for independent review and publication.

## Execution ledger

Pre-flight: Task 2 consumes command results from Task 1; no interface conflict. Parent owns independent final review, secret/size audit and GitHub publication.


Task 1 complete: baseline 305 tests and 336/336 trials; malformed bearer regression RED→GREEN; final 306 tests, all lint/types/build checks and 336/336 trials passed. Isolated browser acceptance passed twice, including after the fix. Startup and reset exercised.

Task 2 complete: concise README, fresh verification record and compact checksummed evaluation evidence. Historical raw/model evidence retained. Local link/whitespace checks passed. Parent owns final independent review and publication.

Ruling: Retain complete historical compressed evidence but omit fresh raw databases/traces from the new snapshot; reports, per-trial checks, provenance and schedules remain, and raw artifacts regenerate through `make evaluate`. Cost if wrong: a reader must regenerate current raw state rather than inspect it directly; historical lossless raw state remains available.
