# Verification record — 28 October 2026

This publication pass used a fresh checkout without the original virtual environment, npm modules, built frontend, model weights or ignored evaluation runs. The default product remains a synthetic local simulator. No merchant writes, customer messages, paid model calls or deployment were performed.

Machine-readable results are in [verification-results-2026-10-28.json](verification-results-2026-10-28.json). The detailed [14 October capability matrix](VERIFICATION-2026-10-14.md) and [13 October record](VERIFICATION-2026-10-13.md) remain historical evidence; their run dates and source hashes should not be read as current results.

## Fresh commands and outcomes

Environment: Linux, Python 3.12.3, Node 24.16.0, npm 11.13.0, uv 0.11.28; browser Chromium 155.0.8059.79 through Playwright Core 1.64.0.

| Command | Observed outcome |
|---|---|
| `make setup` | Created a fresh virtual environment, installed all 26 locked Python packages and the npm lock, then built the frontend. Initial sandbox DNS failure was resolved by rerunning the same setup with network permission. |
| `npm test` | Ruff lint/format, mypy (15 source files), TypeScript and build passed; **307 tests passed in 13.13 s**, with one upstream Starlette httpx test-client deprecation warning. |
| Evaluation inside `npm test` | **336/336 trials passed** across 40 scenarios, two profiles and seeds 7/19/41, in 35.65 s. Both profiles recorded zero false resolutions, duplicate effects, end-state stale tracking and newly introduced invariant violations. |
| `npm test -- --browser-only` | **15 workflow/layout/contrast checks and eight controlled presentation checks passed**, using a fresh disposable simulator. No unexpected page, console or network errors; no document overflow at 320, 390, 768, 1024 and 1440 pixels. |
| `npm run dev` | Rechecked locked dependencies, built, seeded six cases and served the desk on loopback. Authenticated `/api/meta` returned HTTP 200 and simulator/deterministic labels. The owned server shut down cleanly. |
| `make reset` | After shutdown, reset restored six cases. Automated tests also verify refusal while serving and preservation of unrelated files. |
| `.venv/bin/python -m parcelresolve.cli contracts` | Executed the offline capability report. Authenticated provider/identity checks: `not_run`; warehouse/live writes: `unsupported`. |
| `.venv/bin/python -m parcelresolve.guarded_live capabilities` | Executed the offline review capability report; live validation `not_run`, writes zero, execution `unsupported`. |

The baseline also passed 305 tests and 336/336 trials before the publication fix. A malformed authentication probe then reproduced an HTTP 500: Python's constant-time string comparison rejects non-ASCII characters. A regression failed with that exact `TypeError` before the fix and passed afterward. Comparisons now use bytes, preserving constant-time comparison while rejecting the malformed token with HTTP 401. The full suite above includes the regression.

## Capability coverage

All named tests below ran in the fresh suite. Detailed implementation/test mappings and historical experimental results remain in the 14 October record.

| Capability | Implementation and executed evidence | Limit |
|---|---|---|
| Three recovery flows and verified final states | `engine.py`, simulator ports; `test_first_slice.py` and three-flow cases in `test_recovery.py`; browser completes orders 1042–1044 | Synthetic providers |
| Printed label, positive current hold and dispatch races | Typed warehouse evidence and atomic simulator fences; `test_warehouse_recovery.py` plus hold expiry/dispatch cases | No physical warehouse contract |
| Lost/unknown writes, partial failures and safe restart | Intent/receipt/read-back journal in separate SQLite stores; recovery tests and 30 real SIGKILL write windows, plus two planning transitions | Real provider idempotency/lookup unverified |
| Approval, permissions, concurrency and changed state | Exact hash/version/amount binding, per-order locking; API, recovery and guarded-live tests | Single-machine POSIX demo, no production SSO |
| Money, quantities, split shipments, stale/duplicate events | Strict typed records and policy; domain/recovery tests and independent evaluation checks | Restricted currency/allocation scope |
| Intent boundaries and provenance | `intake.py`, fixture/model ports; `test_intake.py`, `test_case_intake_evidence.py`, API injection and model-exclusion tests | Rules have documented classification errors; hosted quality unverified |
| Read-only adapters and guarded review | `integrations.py`, `guarded_live.py`; mock contract, proposal/approval/dry-run and uncertain handoff tests | Authenticated provider checks unperformed; live execution unsupported |
| Operator interface | Actual local UI/API workflow tests, keyboard checks, mobile layouts and separately disclosed controlled-response presentation checks | Computed contrast checks are bounded; manual assistive-technology audit unperformed |

## Retained evidence

The [fresh report](../evaluation/results/verified-2026-10-28/report.md) and [per-trial results](../evaluation/results/verified-2026-10-28/results.json) retain source hashes, checks, provenance and schedules. [ARTIFACTS.json](../evaluation/results/verified-2026-10-28/ARTIFACTS.json) records their hashes and sizes. Fresh raw traces and state databases are generated under ignored `evaluation/runs/` and are not included in this publication snapshot. They can be recreated by running the documented evaluation command. Complete losslessly compressed raw evidence from 14 October remains in the repository.

Fresh browser reports and screenshots are indexed in [browser evidence](../frontend/qa/README.md). Desktop, mobile and partial-failure screenshots were opened and inspected: controls and recovery evidence are legible, the mobile queue scrolls horizontally within its panel, and partial completion retains its remaining refund action. Contrast measurement uses computed solid backgrounds and does not certify overall accessibility.

The CPU model was not rerun during publication. Its authentic frozen inference and failed workflow evidence remain unchanged: **51/108** classifications versus rules **57/108**, and **42 false resolutions** under scripted workflow approval. It remains rejected by the operator API. No model benefit or human handling-time saving is claimed.

Authenticated merchant/carrier/gateway/warehouse behavior, supported live write guarantees, production storage/security, hosted model quality/cost and human/customer outcomes remain external gates. See [limitations](LIMITATIONS.md).

## Final review and dependency audit

Independent review found no major blocker. A malformed `Origin` header produced
a server error before route handling; a regression reproduced HTTP 500, then
verified HTTP 403 and no case creation after the fix. The complete suite and
evaluation above were rerun on the final source.

The publication audit updated certifi to 2026.10.19 and pytest to 9.0.3, resolving
[the certifi advisory](https://github.com/advisories/GHSA-6q48-6c7w-9gw2) and
[the pytest advisory](https://github.com/advisories/GHSA-6w46-j5rx-g56g).
`uvx pip-audit --path .venv/lib/python3.12/site-packages` reported no known
vulnerabilities; `npm audit` also reported zero. These are dated advisory checks,
not a guarantee against undiscovered issues.
