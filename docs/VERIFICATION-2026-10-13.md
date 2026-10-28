# Verification record — 13 October 2026

The local release was built and exercised in this workspace. Results below concern synthetic data and local/mocked providers. No public deployment, hosted CI, authenticated merchant/carrier call, real payment, real model call or customer message was performed.

## Environment and executed commands

Python 3.12.3, Node 24.16.0, npm 11.13.0 and uv 0.11.28. Direct dependencies are pinned in `pyproject.toml` / `package.json`, and transitive dependencies are locked in `uv.lock` / `package-lock.json`. FastAPI 0.135.1, Pydantic 2.12.5, uvicorn 0.41.0 and httpx 0.28.1 were installed and exercised. Browser acceptance used Chromium 149.0.7827.155 through playwright-core 1.64.0.

| Executed command | Observed result |
|---|---|
| `uv sync` / subsequent `uv sync --frozen` | Dependency resolution and installation succeeded; subsequent starts use the frozen lock. |
| `uv sync --frozen --directory /tmp/parcelresolve-clean-project --cache-dir /tmp/parcelresolve-uv-cache` | Created a fresh virtual environment from copies of the three dependency/runtime input files; all 26 locked Python packages installed. The first-slice and 98 provider/intake checks then passed in that fresh environment: **99 passed in 0.26 s**. |
| `npm run dev` | Installed npm lock, built assets, seeded six synthetic cases, started FastAPI successfully on `127.0.0.1:8873`. First chosen port 8765 was occupied by an unrelated service; it was left untouched and the demo default changed. |
| `make reset` / `.venv/bin/python -m parcelresolve.cli reset` after stopping the server | Restored six cases and unused order 1048. The API test also verified reset refusal while serving and preservation of unrelated files. |
| `npm test -- browser` | Runs the actual documented lint/type/build, unit/API/recovery tests, evaluation and browser sequence. Final measured tests: **184 passed in 8.77 s**, with one Starlette httpx test-client deprecation warning. |
| Ruff check and format check | Passed across application and tests. |
| mypy | Passed: 11 source files. |
| `npm run typecheck` and `npm run build` | Passed. Final assets compile from TypeScript/CSS into `frontend/dist`. |
| `.venv/bin/python -m parcelresolve.evaluation --output evaluation/results/verified-2026-10-13 --seeds 7 19 41` | **336/336 trials passed** across 40 distinct scenarios and two offline profiles, 32.53 s. Retained source hashes identify the exact tested implementation. |
| `.venv/bin/python -m parcelresolve.cli contracts` | Ran in offline capability-report mode. WooCommerce/V1/V2 and identity checks report `not_run`; warehouse/live mutations report `unsupported`. This is not a successful live contract test. |
| API-connected browser acceptance | **13 checks passed**, including the three flows, incomplete/refused outcomes, lost-response retry, clarification and viewer permissions. Final rerun verifies the ready-to-execute queue state. |

The generic `npm test` command writes fresh timestamped evaluation evidence; it never silently overwrites an earlier report. A GitHub Actions workflow is supplied to run the offline checks, but a hosted run was not performed.

## Capability-to-evidence matrix

The complete test suite is run by `make test` / `npm test`. Named tests below are in `tests/test_recovery.py` unless another file is specified. The evaluation scenario IDs live in `evaluation/catalog.json` and are listed in `docs/EVALUATION.md`.

| Required capability | Implementation | Executed evidence / observed outcome | Remaining limit |
|---|---|---|---|
| Pre-label cancellation | `Engine._propose`, `_run`, terminal verifier | `tests/test_first_slice.py`; `test_three_supported_flows_have_verified_readback[pre]`; UI order 1042 resolved with one £68 refund | Synthetic provider only |
| Printed label vs dispatch | Separate shipment/label/warehouse records; joined evidence | `test_printed_label_is_not_dispatch_or_stop_evidence`; UI order 1043 withheld approval until hold | No real warehouse acknowledgment |
| Post-label cancellation | Hold-bound plan, void/cancel/refund | Three-flow post-label test; UI order 1043 resolved after current hold | Carrier-specific rules unverified |
| Address recreation | Void old label, structured domestic change, one replacement | Three-flow address test; UI order 1044; zero-value return and blank-address regressions | Structural validation is not postal certification |
| Lost refund response | Intent/receipt query, resume existing approved plan | `test_refund_lost_response_restarts_without_duplicate`; UI 1045; evaluator `refund_lost_response` | Live receipt lookup/idempotency unverified |
| Cancellation without refund | Failed attempt and partial state retained | `test_cancelled_but_refund_failed_remains_visibly_incomplete`; partial-failure screenshot and retry | Real gateway settlement not verified |
| Void without replacement | Compensation/resume, no fake rollback | `test_voided_label_failed_replacement_is_recoverable`; evaluation checks intermediate failure before retry | Real label purchase/void limits unverified |
| Carrier refuses void | Nonretryable escalation | `test_carrier_rejection_escalates_with_no_false_stop`; UI 1046 | Synthetic rejection |
| Concurrent operators | Per-order process lock plus provider version fence | `test_two_operators_cannot_conflict_or_duplicate_effects`; evaluator competing operators; no duplicate effects | Single machine/POSIX only |
| External edit after approval | Resource-version and plan/action hash checks | `test_stale_approval_is_not_reusable_for_new_customer_address`; API stale-approval test; no write before new approval | Live conditional writes unsupported |
| Dispatch race | Atomic simulator warehouse/version precondition | `test_dispatch_race_cannot_produce_a_stopped_claim`, before execution/at boundary/between actions | A real warehouse must supply the fence |
| Expired hold | Current reliable acknowledgment required at action boundary | `test_hold_expiry_at_action_boundary_is_fenced`; draft uses dated verification | No automatic physical hold renewal/release |
| Duplicate/out-of-order events | Delivery IDs and monotonic projection version | `test_out_of_order_duplicate_deliveries_do_not_regress_projection`; seeded event schedules | No live webhook adapter |
| Partial shipments | Quantities/disagreement detection, escalation | `test_partial_dispatch_never_uses_whole_order_cancellation`; UI 1047 | Recovery of split/partly dispatched orders excluded |
| Unauthorized access | API bearer/role/store checks | `tests/test_api.py` auth/viewer/cross-store/origin tests and domain role tests | Demo identities, no production SSO |
| Prompt injection | Bounded interpretation schema; trusted context and backend policy | API injection test; 98 intake/integration mock tests include injection/refusal/schema/network gates | Not a claim of comprehensive natural-language attack detection |
| Crash at every planned write boundary | Persisted intent/effect receipt + restart | **24 actual SIGKILL variants**: 2 pre-label, 3 post-label, 3 address actions × 3 boundaries. All restart to verified state without duplicate effects. Evaluator separately exercises 108 simulated crash trials. | Warehouse acknowledgment button is a local fixture control, not a live stop request |
| Unknowable write | No blind replay | `test_unestablished_outcome_escalates_without_blind_replay`; six evaluator trials correctly escalate on restart | Requires operator/provider reconciliation |
| Stale reads/outages/rate limits | Freshness checks, visible failure, bounded retry semantics | Parameterized failure tests, stale-read test, provider mocked timeout/rate tests | Simulator service schedule only |
| Money and quantities | Strict minor-unit/currency/quantity records | Float/bool/sub-cent/currency/fractional-line tests; independent evaluator rejection scenarios | Restricted currency and allocation scope |
| Identity normalization | Separate namespaces and merchant-verified binding model | Mock V1/V2/Woo mappings/refund-line tests in `test_integrations.py` | No merchant registry supplied |
| Working local adapter interfaces | Commerce/payment/shipping perform ports; warehouse read/hold | `test_local_provider_ports_match_the_documented_adapter_interfaces`; all flows use these ports | Live adapters remain read-only |
| Approval binds exact actions | Case, plan hash, resource version, action hash, amount | Tampered refund test, same-key/different-payload test, API approval test, evaluator independent approval checks | No live writer exists |
| Supported lifecycle only | `domain.TRANSITIONS`, audited `_transition` | Outcome/crash/state tests; cases never resolve from an unverified receipt | No operator override that bypasses evidence |
| Recovery after known non-write | Query establishes absence; replan control restored | `test_interrupted_unwritten_operation_can_replan_after_external_change` | Simulator can establish absence authoritatively |
| Necessary communication | State-based unsent draft, historical hold wording | Dispatch-plus-missing-refund regression, expired-hold draft regression, evaluator communication negative controls | Real customer receipt/delivery not tested; no sending implemented |
| Functional product experience | TypeScript queue/details, API actions, evidence, drafts/lab | 13 browser checks, keyboard tabs/role/search; five viewport widths; no page/network/console errors | Manual assistive-technology audit not performed |

## Measured evaluation results

Each offline profile passed 168 trials: 111 resolutions, 24 escalations, 12 access/validation rejections, and the remaining cases correctly held for clarification/approval. Across both profiles there were **zero false resolution claims, duplicate effects, end-state stale tracking or new invariant violations**. Of 174 restart trials, 168 resolved and six deliberately unknowable outcomes escalated correctly. Existing malformed fixture states are reported separately from newly introduced violations.

The retained report includes counted interactions (924 operator SOP; 762 deterministic intake). These are scripted operation counts, not measured human handling-time savings. Both profiles made zero model calls and incurred USD 0.00 model charges. No AI superiority claim follows from this comparison.

Retained evidence: `evaluation/results/verified-2026-10-13/` has machine-readable results, seeds, source/catalog hashes, a readable report, 8,838 losslessly compressed raw trace records and all 336 separate provider/ledger database pairs. Artifact hashes were independently checked against the delivered files. See `ARTIFACTS.json` and `docs/EVALUATION.md` for extraction and reproduction.

## Visual review and environment issues

The browser suite checked 320, 390, 768, 1024 and 1440 px layouts without document overflow, actual operator actions, viewer restrictions, search/empty state and keyboard tab navigation. Desktop, mobile and partial-failure screenshots were opened and visually inspected. They show readable hierarchy, clear printed/warehouse distinctions, preserved incomplete work and usable responsive controls.

The connected Playwright extension did not attach and CUA reported no available browser. Verification used the installed headless browser through the project's Playwright test script instead. Initial direct sandbox execution could not bind the server or wake asynchronous test-client threads; the documented `npm run dev` and `npm test` paths executed successfully in this environment. These failed initial probes are not counted as passing UI checks.

Outstanding release gates are explicitly listed in `LIMITATIONS.md`: authentic merchant/carrier/gateway/warehouse behavior, live AI quality/cost, production security/storage and human/customer validation remain unperformed.
