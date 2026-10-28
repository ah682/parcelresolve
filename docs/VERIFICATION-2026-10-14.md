# Verification record — 14 October 2026

The local release was built and exercised in this workspace. Results concern synthetic business data and local/mocked commerce, payment, shipping and warehouse providers. **Actual CPU model inference was performed and its measured failures were retained; that model is excluded from the operator API.** No public deployment, hosted CI, authenticated merchant/carrier call, real payment, paid hosted model call or customer message was performed. The previous record is preserved as `VERIFICATION-2026-10-13.md`; machine-readable current results are in `verification-results.json`.

## Environment and executed commands

Python 3.12.3, Node 24.16.0, npm 11.13.0 and uv 0.11.28. Direct dependencies are pinned in `pyproject.toml` / `package.json`, and transitive dependencies are locked in `uv.lock` / `package-lock.json`. FastAPI 0.135.1, Pydantic 2.12.5, uvicorn 0.41.0 and httpx 0.28.1 were installed and exercised. Browser acceptance used Chromium 149.0.7827.155 through playwright-core 1.64.0.

| Executed command | Observed result |
|---|---|
| `uv sync --frozen` / `npm ci --ignore-scripts` through `npm run dev` | Reinstalled/verified all 26 locked Python packages and the npm lock, then built successfully. The fresh isolated Python installation on 13 October is separately retained in the historical record; it is not presented as a fresh run of today's 305 tests. |
| `npm run dev` | Built assets, preserved/seeded six synthetic cases and started FastAPI successfully on `127.0.0.1:8873`; authenticated `/api/meta` returned HTTP 200 and honest simulator/deterministic labels. The task-owned server then shut down cleanly. |
| `make reset` / `.venv/bin/python -m parcelresolve.cli reset` | Documented reset was executed on 13 October. Current API tests again passed reset refusal while serving and preservation of unrelated files. The final browser run used its own fresh temporary database, without resetting the user's main demo data. |
| `npm test` | Runs documented lint/type/build, unit/API/recovery tests and evaluation. Final result: **305 passed in 21.30 s**, with one Starlette httpx test-client deprecation warning. |
| Ruff check and format check | Passed across application and tests; 24 formatted files checked. |
| mypy | Passed: 15 source files. |
| `npm run typecheck` and `npm run build` | Passed. Final assets compile from TypeScript/CSS into `frontend/dist`. |
| `.venv/bin/python -m parcelresolve.evaluation --output evaluation/runs/run-20261014T035657561908247 --seeds 7 19 41` (inside final `npm test`) | **336/336 trials passed** across 40 distinct scenarios and two offline profiles, 47.07 s. The preceding matching-source run is retained losslessly in `evaluation/results/verified-2026-10-14/` (336/336, 54.97 s). |
| `.venv/bin/python -m parcelresolve.local_model setup --download` / `setup` | Public pinned model/runtime downloaded explicitly and their hashes verified. The primary agent separately re-ran cached verification and an actual single-inference engine smoke check. |
| `PARCELRESOLVE_ENABLE_LOCAL_MODEL=1 .venv/bin/python -m parcelresolve.model_evaluation --output evaluation/results/local-ai-2026-10-14` | Actual frozen CPU comparison: 216 classification rows, 36 unique requests, three seeds, two profiles; model **51/108** correct, rules **57/108**. No provider charges. |
| `PARCELRESOLVE_ENABLE_LOCAL_MODEL=1 .venv/bin/python -m parcelresolve.evaluation --profiles local-model --output evaluation/results/local-ai-workflow-2026-10-14 --seeds 7 19 41` | **Failed, exit 1:** 123/168 passed, 45 failed, including 42 false resolution claims. Failure evidence preserved; local-model startup is now rejected by the operator API. |
| `.venv/bin/python -m parcelresolve.cli contracts` and `.venv/bin/python -m parcelresolve.guarded_live capabilities` | Credential-free capability reports ran. Authenticated provider/identity checks report `not_run`; warehouse/live mutations report `unsupported`. These are not successful live contract tests. The review workflow's 119 integration tests used mocks. |
| `npm test -- --browser-only` | Started an isolated fresh simulator, ran **15 workflow/contrast checks plus eight separately disclosed presentation checks**, and removed only its own server/data. No console/page/network errors. Evidence: `frontend/qa/2026-10-14T035836492Z/`. |

The generic `npm test` command writes fresh timestamped evaluation evidence; it never silently overwrites an earlier report. A GitHub Actions workflow is supplied to run the offline checks, but a hosted run was not performed.

## Capability-to-evidence matrix

The complete test suite is run by `make test` / `npm test`. Named tests below are in `tests/test_recovery.py` unless another file is specified. The evaluation scenario IDs live in `evaluation/catalog.json` and are listed in `docs/EVALUATION.md`.

| Required capability | Implementation | Executed evidence / observed outcome | Remaining limit |
|---|---|---|---|
| Pre-label cancellation | `Engine._propose`, `_run`, terminal verifier | `tests/test_first_slice.py`; `test_three_supported_flows_have_verified_readback[pre]`; UI order 1042 resolved with one £68 refund; 15 warehouse-evidence regression variants cover every validation stage | Synthetic provider only; reliable positive physical evidence still required |
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
| Crash at every external write boundary | Persisted intent/effect receipt + restart | **30 actual SIGKILL variants**: 24 financial/label action boundaries plus six warehouse-hold boundaries; two further planning-transition SIGKILL tests. `test_recovery.py` and `test_warehouse_recovery.py` verify independent durable stores and safe restart. Evaluator separately exercises 108 simulated action-boundary trials. | Local provider guarantees only; no live stop request made |
| Durable warehouse hold | Typed `WarehouseHoldAttempt`, actor/version/key intent, separate provider receipt and fresh read-back | `test_warehouse_recovery.py`: lost response, unknown outcome, failure/rate limit/outage, stale read, expired/changed acknowledgment, concurrent recovery and key rebinding. Browser reconciles a lost hold response without a second request. | Physical warehouse contract absent |
| Preserve existing data | Additive schema version 2 in ledger/provider stores | `test_additive_warehouse_migration_preserves_version_one_case_and_approval`; successful normal restart with existing demo data | Single-machine migration; no production backup/restore study |
| Unknowable write | No blind replay | `test_unestablished_outcome_escalates_without_blind_replay`; six evaluator trials correctly escalate on restart | Requires operator/provider reconciliation |
| Stale reads/outages/rate limits | Freshness checks, visible failure, bounded retry semantics | Parameterized failure tests, stale-read test, provider mocked timeout/rate tests | Simulator service schedule only |
| Money and quantities | Strict minor-unit/currency/quantity records | Float/bool/sub-cent/currency/fractional-line tests; independent evaluator rejection scenarios | Restricted currency and allocation scope |
| Identity normalization | Separate namespaces and merchant-verified binding model | Mock V1/V2/Woo mappings/refund-line tests in `test_integrations.py` | No merchant registry supplied |
| Working local adapter interfaces | Commerce/payment/shipping perform ports; journalled warehouse hold/query | `test_local_provider_ports_match_the_documented_adapter_interfaces`; all flows use these ports; warehouse tests exercise durable intent and query | Live observations/refund preview are non-mutating; real writes unsupported |
| Approval binds exact actions | Case, plan hash, resource version, action hash, amount | Tampered refund test, same-key/different-payload test, API approval test, evaluator independent approval checks | No live writer exists |
| Supported lifecycle only | `domain.TRANSITIONS`, audited `_transition` | Outcome/crash/state tests; cases never resolve from an unverified receipt | No operator override that bypasses evidence |
| Recovery after known non-write | Query establishes absence; replan control restored | `test_interrupted_unwritten_operation_can_replan_after_external_change` | Simulator can establish absence authoritatively |
| Necessary communication | State-based unsent draft, historical hold wording | Dispatch-plus-missing-refund regression, expired-hold draft regression, evaluator communication negative controls | Real customer receipt/delivery not tested; no sending implemented |
| Functional product experience | TypeScript queue/details, API actions, evidence, drafts/lab | 15 browser workflow/contrast checks plus eight controlled-response presentation checks; five widths, roving keyboard tabs, focus preservation, loading/invalid/empty/offline/reconnect states and literal untrusted markup; no page/network/console errors | Manual assistive-technology audit not performed |
| Actual model and deterministic comparison | `intake.py`, `local_model.py`, `model_evaluation.py`, `evaluation.py` | Frozen actual inference comparison and optional full workflow run above; model performs worse and is rejected from API, covered by `tests/test_api.py` | Synthetic corpus; no hosted model or human handling-time evidence |
| Honest fixture/model provenance | `fixture_model.py`, bounded intake receipt and UI mode labels | Recorded fixture exact-match/schema tests; `test_case_intake_evidence.py`; browser distinguishes configured mode from actual result mode | Fixture responses are never counted as inference |
| Documented real adapters | `integrations.py`, `docs/API_CONTRACTS.md` | Current official documentation reviewed; 119 integration/review mock tests include separate V1/V2 identities, Woo OPTIONS/refund-preview discovery and payload validation | No authenticated merchant/provider checks were run |
| Guarded live proposal/approval/dry-run | `guarded_live.py`, separate review ledger | `tests/test_guarded_live.py`: owner and operator scope, exact plan/action/amount binding, expiry, changed-state invalidation, dry-run and rejected execution | No verified live write transport; both gates alone cannot establish missing guarantees |
| Read-only reconciliation of external handoff | Durable uncertain handoff, joined re-read, atomic audit/readback storage | Guarded-live tests cover mismatched/ambiguous observations and no replay | No attribution, gateway settlement or physical stop claim |
| Reproducible deliverables | Locked Python/npm, `.env.example`, `Makefile`, CI, demo seeds, documentation | Tested startup/acceptance commands above; CI in `.github/workflows/verify.yml`; walkthrough in `docs/DEMO.md`; separate development/evaluation provenance in `docs/DATA.md` | No hosted CI run or public deployment |

## Measured evaluation results

Each offline profile passed 168 trials: 111 resolutions, 24 escalations, 12 access/validation rejections, and the remaining cases correctly held for clarification/approval. Across both profiles there were **zero false resolution claims, duplicate effects, end-state stale tracking or new invariant violations**. Of 174 restart trials, 168 resolved and six deliberately unknowable outcomes escalated correctly. Existing malformed fixture states are reported separately from newly introduced violations.

The retained report includes counted interactions (924 operator SOP; 762 deterministic intake). These are scripted operation counts, not measured human handling-time savings. Both profiles made zero model calls and incurred USD 0.00 model charges. No AI superiority claim follows from this comparison.

Each profile also recorded 93 warehouse hold effects with zero duplicates; the independent evaluator requires matching durable intent, operator/store permission evidence and read-back. These are simulator effects, not real warehouse stops.

Retained default evidence: `evaluation/results/verified-2026-10-14/` has machine-readable results, seeds, source/catalog hashes, a readable report, **9,390 losslessly compressed raw trace records and all 336 separate provider/ledger database pairs**. Artifact hashes, decompressed traces, every archived state file and recorded source hashes were independently checked against the delivered files. The 13 October artifacts remain intact. See `ARTIFACTS.json` and `docs/EVALUATION.md` for extraction and reproduction.

## Actual AI comparison and exclusion decision

The independent intake corpus contains 36 original synthetic requests (12 cancellation, 12 address and 12 ambiguous/unsupported), disjoint from three development probes. Corpus, prompt and runtime configuration were frozen before its first full run; annotations are openly visible, so this is not a concealed external benchmark. No tuning or model selection followed the measured failures. Seeds 7, 19 and 41 repeat requests; they do not create 108 unique cases.

| Frozen comparison | Deterministic rules | Pinned local CPU model |
|---|---:|---:|
| Correct / 108 repeated classifications | 57 | 51 |
| Correct / 36 for each seed | 19 | 17 |
| False actionable interpretations | 9 | 21 |
| Wrong actionable intent | 0 | 27 |
| Unnecessary clarification | 42 | 9 |
| Actual inference calls | 0 | 102 |
| Input / output tokens | 0 / 0 | 12,108 / 231 |
| Total measured intake time | 0.004 s | 77.968 s |

Six model-profile rows were blocked by the shared preflight guard without inference. The local model made no correct address classifications. Its separate workflow profile performed **153 actual calls, 17,607 input and 312 output tokens**, and passed only **123/168 trials**. The scripted driver approved the returned plans, producing **42 false resolution claims** against intended address outcomes; three further failures gave the wrong obstacle. This is a failed experiment, not a passing release profile, and zero duplicate effects does not make those wrong recoveries acceptable.

The desk API now refuses this model at startup. The direct engine/evaluator retains it for explicit reproduction of failures; the earlier generated classification report's opt-in wording describes that experiment before the later workflow exclusion decision. The default parser also has documented errors, so operators must review the request and exact proposal. The hosted OpenAI adapter remains separately opt-in and unvalidated for quality. USD 0.00 here means no model provider charge, not free electricity/hardware. Scripted step counts do not establish human time savings.

`evaluation/results/local-ai-2026-10-14/` retains every input, output, usage record and raw runtime log from the frozen comparison. `evaluation/results/local-ai-workflow-2026-10-14/` retains all 45 failures, **4,620 raw trace records and 168 provider/ledger pairs**. All artifact and recorded source hashes were independently verified; all compressed state files match their original run bytes. Model/runtime revisions, hashes and licenses are in `model_assets/`.

## Visual review and environment issues

The final browser suite checked 320, 390, 768, 1024 and 1440 px layouts without document overflow, actual operator actions, viewer restrictions, search/empty state and keyboard tab navigation. Desktop, mobile and partial-failure screenshots were opened and visually inspected. They show readable hierarchy, clear printed/warehouse distinctions, preserved incomplete work and usable responsive controls. The eight presentation tests explicitly use controlled responses; they do not prove real inference or provider recovery. Measured contrast passed **1,016 visible-text observations across ten views** (903 workflow and 113 presentation), with no failures under the script's normal/large-text thresholds. This is a bounded computed-style check, not complete accessibility certification.

The connected Playwright extension did not attach and CUA reported no available browser. Verification used the installed headless browser through the project's Playwright test script instead. Initial direct sandbox execution could not bind the server or wake asynchronous test-client threads; the documented `npm run dev` and `npm test` paths executed successfully in this environment. These failed initial probes are not counted as passing UI checks.

Outstanding external gates are explicitly listed in `LIMITATIONS.md`: authenticated merchant/carrier/gateway/warehouse behavior, supported live write contracts, hosted AI quality/cost, production security/storage and human/customer validation remain unperformed. The prompt permits these later authentic gates; the complete default credential-free demonstration and its local acceptance workflow have been executed. No local result is substituted for those external checks.
