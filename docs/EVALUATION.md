# Evaluation

## Publication verification — 28 October 2026

The fresh [report](../evaluation/results/verified-2026-10-28/report.md) and [per-trial checks](../evaluation/results/verified-2026-10-28/results.json) passed 336/336 trials with the unchanged recovery engine and seeds 7/19/41. The publication snapshot retains report, checks, catalog/provenance and schedules, with hashes in `ARTIFACTS.json`; newly generated raw traces and databases are excluded. Run `make evaluate` to regenerate them. Historical lossless raw evidence below remains available. No CPU or hosted model experiment was rerun during publication.

## Reproduce

Run the credential-free release profile from the repository root:

```bash
.venv/bin/python -m parcelresolve.evaluation --output /tmp/parcelresolve-evaluation-new --seeds 7 19 41
```

Use a fresh output directory. The runner refuses to overwrite existing evidence and exits nonzero if any trial fails. `make evaluate` automatically chooses a unique timestamped output directory; `make evaluate EVAL_OUTPUT=/tmp/a-fresh-run` supplies an explicit destination. `--scenarios refund_lost_response dispatch_after_approval` selects a debugging subset; `--profiles operator-sop` selects a single profile. A subset is not the full release gate.

The full catalog has **40 distinct synthetic scenarios**. Two scenarios expand into nine crash checkpoints each: after durable intent, after provider effect, and after receipt recording, for each action in labelled cancellation and address recreation. This yields **56 trials per seed/profile**, or **336 trials** for three seeds and both profiles. Repetitions are never presented as 336 independent cases.

## What is compared

- **Operator SOP:** deterministic desk workflow with an explicit operator-selected intent and a confirmed target address where needed. Intent selection counts as one interaction.
- **Deterministic intake:** the shipped conservative text interpreter chooses intent or requests clarification. It receives the request text without evaluation labels. Backend policy, identities, quantities, approvals and warehouse truth remain identical to the SOP profile.

Both default profiles are offline and use the local simulator. Neither invokes a model or incurs a provider charge. The separate `local-model` workflow profile executes genuine CPU inference when explicitly enabled; it is not a fixture lookup. The recorded fixture provider in `parcelresolve/fixture_model.py` exists only for development contract tests and is excluded from all measured profiles. No model is evaluated against merchant cases. None of these results establishes handling-time gains, merchant adoption or external integration reliability.

## Actual model comparison

The [frozen intake benchmark](../evaluation/intake-benchmark.json) contains 36 new requests, balanced across cancellation, address correction and clarification. The model prompt/configuration/grammar and development/evaluation corpora were [hashed before the first full comparison](../evaluation/model-comparison-freeze.json). The runtime receives only request text, not expected labels. No fine-tuning or tuning on observed results occurred. The three seeds repeat the same 36 requests; they do not create 108 independent examples.

The real local provider runs official Qwen2.5-0.5B-Instruct Q4_K_M weights with llama.cpp b11429 on CPU, with pinned revisions, licenses and SHA-256 values. Provisioning and platform limits are documented in [model_assets/README.md](../model_assets/README.md). No hosted API, paid inference or fake model response is involved. The same existing unsupported-scope/prompt-injection guard applies to both interpreters; guard answers are explicitly labeled deterministic and do not count as model calls.

```bash
.venv/bin/python -m parcelresolve.local_model setup --download
PARCELRESOLVE_ENABLE_LOCAL_MODEL=1 .venv/bin/python -m parcelresolve.model_evaluation --output /tmp/parcelresolve-ai-comparison-new --seeds 7 19 41
```

The original one-pass run on 2026-10-14 completed from **03:49:39.645 to 03:50:57.635 UTC**, **77.990 seconds** total. It produced the following measured results, identically at all three seeds:

| Metric | Deterministic rules | Actual local CPU model |
|---|---:|---:|
| Correct interpretations | 57 / 108 (19 / 36 unique) | 51 / 108 (17 / 36 unique) |
| False actionable interpretations of unknown requests | 9 | 21 |
| Unnecessary clarification | 42 | 9 |
| Wrong actionable intent | 0 | 27 |
| Actual model calls / guarded local-profile trials | 0 / — | 102 / 6 |
| Input / output tokens | 0 / 0 | 12,108 / 231 |
| Measured intake time | 0.0039 s | 77.968 s |
| Median / p95 intake latency | 0.000033 / 0.000058 s | 0.755 / 0.846 s |
| Provider cost USD | 0.00 | 0.00 |
| Runtime errors / missing usage records | 0 / 0 | 0 / 0 |

The model recognized all 12 unique cancellation requests but misclassified all 12 address requests (nine as cancellation, three as unknown) and seven of 12 unknown requests as cancellation. Rules correctly interpreted five cancellation, five address and nine unknown requests. The model's better cancellation recall does not offset the observed overall accuracy and safety losses. **The desk keeps deterministic intake; the API refuses local-model mode.** The rejected model remains available only for evaluation/probe and engine experiments so these real results can be reproduced. No paid OpenAI evaluation was run.

False actionable interpretation is a proposed intent, not proof that an external action occurred: the backend still requires fresh evidence, trusted identity and operator approval. The separate recovery evaluator grades final provider state and communication. An automatically approving synthetic workflow can expose wrong-intent terminal outcomes; its raw failures must be preserved rather than counted as successful model-assisted recovery.

The [report](../evaluation/results/local-ai-2026-10-14/report.md), [results](../evaluation/results/local-ai-2026-10-14/results.json) and raw `traces.jsonl` retain all 216 paired trials, including every incorrect prediction, exact stdout/stderr, token counters, prompt hashes, seeds and runtime provenance. `ARTIFACTS.json` checksums the delivered files. Token accounting includes EOS. Latency includes per-request subprocess startup/inference; initial model hash verification, provisioning and harness I/O are excluded from intake latency. Local electricity and hardware are unpriced, so zero provider cost is not a total-compute-cost estimate. Synthetic/openly visible annotations, small sample size and zero-temperature repetition prevent a claim of merchant-level accuracy or generalization.

The actual model was also run through all 40 recovery scenarios, at three event seeds, with the same frozen interpreter:

```bash
PARCELRESOLVE_ENABLE_LOCAL_MODEL=1 .venv/bin/python -m parcelresolve.evaluation --output evaluation/results/local-ai-workflow-2026-10-14 --seeds 7 19 41 --profiles local-model
```

This experiment **failed**, exiting 1 with **123/168 passing trials and 42 false resolutions**. The synthetic driver approved cancellation plans produced from misinterpreted address requests, so the resulting provider state did not satisfy the customer's intended address correction. Three additional trials gave the wrong explanation for missing address information. Some expected address-action crash boundaries were never reached because the wrong cancellation workflow ran; these were correctly recorded as failures. There were zero duplicate effects, stale tracking or new invariant violations, which does not excuse the wrong intended outcome.

The local workflow run made **153 actual inferences** plus three shared-guard answers, consumed **17,607 input / 312 output tokens**, counted **744 synthetic operator interactions**, and recorded **69 restarts, 66 resolved**. It ran from 03:52:37.688 to 03:55:51.306 UTC (193.618 s), including 165.408 s of intake time. It overlapped other acceptance checks, so its timings should not be treated as a controlled latency comparison. The [failed experiment report](../evaluation/results/local-ai-workflow-2026-10-14/report.md), [all checks](../evaluation/results/local-ai-workflow-2026-10-14/results.json), compressed 4,620-line raw trace and 168 ledger/provider pairs preserve the failures. This is the basis for rejecting this model from the operator API, not a claim of successful AI-assisted recovery. No prompts, model configuration or labels were tuned after either measured model run.

## Outcome grading

The grader checks intended final state, evidence and necessary communication; it does not require a fixed tool-call sequence. A resolved cancellation needs the exact captured currency/amount refunded, consistent line and shipment quantities, cancellation, no active labels or stale tracking, and no physical dispatch. Before label creation, warehouse evidence must independently show reliable not-dispatched state or a current hold; an expired/unreliable hold cannot pass. A resolved address correction needs the confirmed target, one current label/tracking value, old labels void, unchanged payment, and warehouse safety evidence. Successful effects must map to durable operation intents and established provider receipts. Warehouse hold receipts are checked separately against pre-write durable intent, the actual authorized operator/store and permission evidence; resolved cases require verified hold read-back. Read-back evidence and a truthful local customer draft are required.

A generic escalation cannot satisfy a supported success case. A required review must identify the actual obstacle—such as physical dispatch, duplicate labels, quantity mismatch, expired hold or unknown provider outcome—and keep the case visibly incomplete. The grader checks missing address fields rather than requiring one exact sentence. Cancellation/refund and label-recreation failures are inspected **before retry**: partial state must be durable, incomplete and explained; subsequent recovery must achieve the intended state without repeating a successful effect.

The mandatory scenarios are represented directly:

| Requirement | Catalog scenarios |
|---|---|
| Pre-label cancellation; printed label needs warehouse confirmation | `cancel_two_lines`, `printed_unknown_dispatch`, `cancel_printed_with_hold` |
| Lost refund response and restart reconciliation | `refund_lost_response` |
| Cancel succeeds/refund fails | `refund_failure_partial` |
| Void succeeds/replacement fails | `replacement_failure_partial`, `address_failure_after_void` |
| Carrier refuses void | `carrier_void_rejected` |
| Competing operators | `two_operators` |
| Customer changes order after approval | `changed_after_approval` |
| Dispatch after approval or at write boundary | `dispatch_after_approval`, `dispatch_at_write_boundary` |
| Duplicate and delayed events | `duplicate_out_of_order_events`, plus seeded deliveries in ordinary workflow cases |
| Partly dispatched order | `partially_dispatched` |
| Unauthorized access and injected customer text | `viewer_cannot_mutate`, `other_store_order`, `customer_prompt_injection` |
| Every mutating restart boundary | `cancel_restart_boundaries`, `address_restart_boundaries` |
| Unknown outcome, stale read, rate limit, unavailable service | `refund_outcome_unknown`, `stale_refund_read`, `refund_rate_limit`, `refund_service_recovery` |

Crash evaluation raises a `BaseException` at a selected durable boundary, reconstructs the engine against the same separate databases, and reconciles. It does not claim to issue an OS-level kill. The core acceptance suite separately exercises actual process termination; consult `docs/VERIFICATION.md` for executed commands and results.

## Metrics and artifacts

`results.json` records every check, the initial input findings and these measured values: correct resolutions/escalations, false resolved claims, duplicate effects, end-state stale tracking, newly introduced invariant violations, restarts exercised/resolved, crash boundaries reached, operator steps, effect count, warehouse effect/duplicate counts, model calls, input/output tokens, inference time and provider cost. A duplicate effect includes the same semantic action written under a different operation key in these single-parcel cases; provider-key uniqueness alone is insufficient. Existing bad input states, such as duplicate labels, are reported separately from violations caused by recovery.

Operator steps are counted calls to the desk plus explicit SOP intent selection. They are not observed human handling time, and the comparison's interaction counts do not establish a productivity gain. Provider cost is USD 0.00 because no paid service is invoked. Default profiles have zero model calls; optional local-model receipts record actual usage. Local infrastructure costs are not priced. An unknown-outcome restart should escalate, so “restart resolved / exercised” is not itself a safety success rate.

Every output directory contains:

- `report.md`: readable measured outcomes and failure details.
- `results.json`: machine-readable checks, counts, actual run times, catalog/source hashes and Python version.
- `traces.jsonl`: input records, interpreted requests with full inference receipts when selected, API results, operation boundaries, failure checkpoints, event deliveries, final provider truth, warehouse attempts/receipts and audit records.
- `seeds.json`: the exact derived seeds and delivery schedules.
- `catalog.json`, `manifest.json`: the input/provenance snapshot used for the run.
- `states/…/ledger.sqlite` and `states/…/providers.sqlite`: persisted ledger and separate provider state for each trial.

Grader regression tests include negative controls: a desk claiming resolution against incorrect provider truth fails; arbitrary escalation on a supported recovery fails; unsupported stopped/refunded communication fails; and duplicate writes with different keys fail. Offline regression tests prohibit construction of the real model client and assert that raw traces and replay inputs are written.

## Historical release evidence (2026-10-13)

This retained run predates the durable warehouse-request journal and real local-model comparison added on 2026-10-14. It remains historical evidence; current final safety results are recorded separately below.

On 2026-10-13, the exact command below completed in **32.53 seconds**, from 17:06:49.819 to 17:07:22.352 UTC, with **336/336 passing trials across 40 distinct scenarios**:

```bash
.venv/bin/python -m parcelresolve.evaluation --output evaluation/results/verified-2026-10-13 --seeds 7 19 41
```

| Measured result | Operator SOP | Deterministic intake |
|---|---:|---:|
| Passing trials | 168 / 168 | 168 / 168 |
| Correct verified resolutions | 111 | 111 |
| Correct escalations | 24 | 24 |
| Correct clarification / hold requests | 18 | 21 |
| Correct validation / access rejections | 12 | 12 |
| Injection held behind explicit approval | 3 | 0 (clarification instead) |
| False resolutions / duplicate effects | 0 / 0 | 0 / 0 |
| End-state stale tracking / new invariant violations | 0 / 0 | 0 / 0 |
| Restart resolved / exercised | 84 / 87 | 84 / 87 |
| Crash boundaries exercised | 54 | 54 |
| Counted operator interactions | 924 | 762 |
| Model calls / model cost USD | 0 / 0.00 | 0 / 0.00 |

The three unresolved restarts in each profile were deliberately unknowable external outcomes; all correctly escalated without blindly repeating a write. The three SOP injection cases remained behind the explicit approval boundary, whereas deterministic intake requested clarification. This is a difference in safe workflow disposition, not an AI-quality comparison.

The [readable report](../evaluation/results/verified-2026-10-13/report.md) and [machine-readable results](../evaluation/results/verified-2026-10-13/results.json) contain the full checks. Delivered raw evidence is losslessly compressed in `traces.jsonl.gz` and `states.tar.gz` with hashes in `ARTIFACTS.json`; `gzip -dk traces.jsonl.gz` and `tar -xzf states.tar.gz` restore the original paths. The default runner writes uncompressed artifacts. The final run contains 336 separate provider/ledger database pairs.

Executed grader checks: `.venv/bin/python -m pytest tests/test_evaluation.py -q` passed **10 tests**; Ruff check/format and mypy passed for the evaluator and its tests. Source hashes and the Python runtime version are embedded in the result file.

Earlier diagnostic runs are preserved under `/tmp` rather than relabeled as successful. The first run exposed a warehouse-hold requirement for pre-label address-label creation and a missing-address validation-order issue, both corrected in the engine. A subsequent run exposed a grader wording mismatch for a concrete list of address fields, corrected without changing the expected safety outcome. The final grader additionally verifies current hold, exactly one replacement label, snapshot/provider agreement, effect-bound approval and retained event payloads.

Live WooCommerce merchant behavior, ShipStation/carrier void guarantees, payment gateway refunds, real warehouse stop acknowledgments, production webhooks, model quality on authentic messages and authentic customer outcomes remain unverified. Strong simulator receipt queries and atomic warehouse fencing are local contracts, not evidence of guarantees offered by real providers.

## Current verified safety evidence (2026-10-14)

The retained backend/grader run invoked by `npm test` completed from **03:53:01.551 to 03:53:56.524 UTC (54.973 seconds)**. It passed **336/336 trials across 40 distinct scenarios**. Every recorded core source hash was independently compared with the delivered code before these artifacts were retained. The subsequent API-only change rejects the underperforming model mode; it does not change these core hashes or baseline execution. A later full-project rerun also passed; its command and results are in [VERIFICATION.md](VERIFICATION.md).

| Measured result | Operator SOP | Deterministic intake |
|---|---:|---:|
| Passing trials | 168 / 168 | 168 / 168 |
| Correct verified resolutions | 111 | 111 |
| Correct escalations | 24 | 24 |
| Correct clarification / hold requests | 18 | 21 |
| Correct validation / access rejections | 12 | 12 |
| Injection held behind approval | 3 | 0 (clarification) |
| False resolutions / duplicate recovery effects | 0 / 0 | 0 / 0 |
| End-state stale tracking / new invariant violations | 0 / 0 | 0 / 0 |
| Authorized warehouse hold receipts / duplicates | 93 / 0 | 93 / 0 |
| Restart resolved / exercised | 84 / 87 | 84 / 87 |
| Requested recovery crash boundaries reached | 54 | 54 |
| Counted operator interactions | 924 | 762 |
| Model calls / provider USD | 0 / 0.00 | 0 / 0.00 |

The [current report](../evaluation/results/verified-2026-10-14/report.md) and [results](../evaluation/results/verified-2026-10-14/results.json) retain all checks. The delivered `traces.jsonl.gz` restores **9,390 raw records**; `states.tar.gz` restores **336 separate ledger/provider pairs**. Compression was verified by hashing the decompressed trace and every archived state file against the raw originals. `ARTIFACTS.json` records hashes, sizes and restoration paths. The historical original run directory is not included in the repository; the compressed artifacts restore the raw evidence. To restore delivered compressed evidence:

```bash
cd evaluation/results/verified-2026-10-14
gzip -dk traces.jsonl.gz
tar -xzf states.tar.gz
```

Focused intake/evaluator/receipt tests passed **71 tests** in **2.66 s** using `.venv/bin/python -m pytest tests/test_intake.py tests/test_evaluation.py tests/test_case_intake_evidence.py -q`. Ruff and mypy passed the five owned Python modules. Negative controls now also reject missing/postdated warehouse intent, the wrong hold operator, and unreliable/expired pre-label warehouse claims. Actual warehouse-hold SIGKILL and full-project checks are tracked in [VERIFICATION.md](VERIFICATION.md); evaluator boundary exceptions remain distinct from OS process termination.
