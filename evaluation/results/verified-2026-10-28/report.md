# ParcelResolve offline synthetic evaluation

Run: 2026-10-28T07:00:26.993115+00:00. Seeds: 7, 19, 41.

Observed **336/336 passing trials** across **40 distinct scenarios**. Crash matrix expansions and seeded schedules are repeated trials, not additional independent scenarios.

All profiles use the local provider simulator. The operator SOP uses explicit operator-selected intent; deterministic intake uses the shipped rules without evaluation labels. When selected, local-model runs the pinned Qwen CPU model with measured inference receipts. Hosted AI comparison was **not performed**. These acceptance fixtures are visible during implementation; the separate frozen intake benchmark measures model classification. Neither evaluation estimates merchant handling time, customer outcomes, or adoption.

| Profile | Pass / trials | False resolutions | Duplicate effects | End-state stale tracking | New invariant violations | Restart resolved / exercised | Counted operator steps | Model calls / USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| operator-sop | 168 / 168 | 0 | 0 | 0 | 0 | 84 / 87 | 924 | 0 / 0.00 |
| deterministic-intake | 168 / 168 | 0 | 0 | 0 | 0 | 84 / 87 | 762 | 0 / 0.00 |

Operator steps count invoked desk interactions plus explicit SOP intent selection. They are not timed human interactions; a smaller count does not establish a handling-time gain. Restart-exercised includes deliberately unknowable outcomes, whose correct result is escalation, so restart-resolved is not a safety success rate. Initial malformed business states are separately recorded; unchanged pre-existing findings are not labeled newly introduced violations.

## Scenario results

| Scenario | Result | Observed states |
|---|---:|---|
| cancel_two_lines | 6 / 6 | resolved |
| cancel_usd | 6 / 6 | resolved |
| cancel_eur | 6 / 6 | resolved |
| cancel_printed_with_hold | 6 / 6 | resolved |
| printed_unknown_dispatch | 6 / 6 | needs-information |
| address_label_recreation | 6 / 6 | resolved |
| address_before_label | 6 / 6 | resolved |
| already_dispatched | 6 / 6 | escalated |
| partially_dispatched | 6 / 6 | escalated |
| refund_lost_response | 6 / 6 | resolved |
| refund_failure_partial | 6 / 6 | resolved |
| refund_service_recovery | 6 / 6 | resolved |
| refund_rate_limit | 6 / 6 | resolved |
| cancel_before_write | 6 / 6 | resolved |
| carrier_void_rejected | 6 / 6 | escalated |
| replacement_failure_partial | 6 / 6 | resolved |
| address_failure_after_void | 6 / 6 | resolved |
| void_lost_response | 6 / 6 | resolved |
| replacement_lost_response | 6 / 6 | resolved |
| changed_after_approval | 6 / 6 | needs-information |
| dispatch_after_approval | 6 / 6 | escalated |
| dispatch_at_write_boundary | 6 / 6 | escalated |
| hold_expired | 6 / 6 | needs-information |
| warehouse_unreliable | 6 / 6 | needs-information |
| duplicate_active_labels | 6 / 6 | escalated |
| shipment_quantity_mismatch | 6 / 6 | escalated |
| cancel_stale_tracking | 6 / 6 | resolved |
| duplicate_out_of_order_events | 6 / 6 | resolved |
| two_operators | 6 / 6 | resolved |
| viewer_cannot_mutate | 6 / 6 | rejected |
| other_store_order | 6 / 6 | rejected |
| customer_prompt_injection | 6 / 6 | awaiting-approval, needs-information |
| unsupported_currency | 6 / 6 | rejected |
| fractional_quantity | 6 / 6 | rejected |
| ambiguous_customer_request | 6 / 6 | needs-information |
| address_missing_details | 6 / 6 | needs-information |
| cancel_restart_boundaries | 54 / 54 | resolved |
| address_restart_boundaries | 54 / 54 | resolved |
| stale_refund_read | 6 / 6 | resolved |
| refund_outcome_unknown | 6 / 6 | escalated |

## Reproduction and limits

- `results.json` contains every check and measured count; `traces.jsonl` contains inputs, interpretation, event schedules, API results, failure checkpoints, boundaries, provider truth and final audit records.
- `seeds.json` records the exact schedules. Each trial retains separate `states/…/ledger.sqlite` and `providers.sqlite` databases, preventing a shared database transaction from concealing uncertain external effects.
- Abrupt-boundary evaluation raises a `BaseException` after durable intent, provider effect, or recorded receipt. Real subprocess termination is covered by the core acceptance tests, when run; this evaluator does not claim to perform an OS kill.
- No real merchant, payment gateway, carrier, warehouse, webhook, hosted model, or customer communication is contacted. Optional local-model inference executes real open-weight inference on CPU. Provider charges are USD 0.00; local hardware and electricity are not priced. Simulator receipt lookup and warehouse fencing are stronger contracts that real deployments must verify separately.
- Warehouse hold receipts are graded separately: each needs a durable request and matching operator/store permission evidence from before the write. Resolved cases also require verified warehouse receipt read-back. Raw traces retain warehouse attempts and receipts.
- Money is integer minor units. Unsupported currency/quantity scenarios must be rejected; recovery is scoped to a single parcel. A correct escalation requires the specific obstacle, durable evidence and a safe local draft; escalation alone does not pass.
