# ParcelResolve offline synthetic evaluation

Run: 2026-10-14T03:52:37.687907+00:00. Seeds: 7, 19, 41.

Observed **123/168 passing trials** across **40 distinct scenarios**. Crash matrix expansions and seeded schedules are repeated trials, not additional independent scenarios.

All profiles use the local provider simulator. The operator SOP uses explicit operator-selected intent; deterministic intake uses the shipped rules without evaluation labels. When selected, local-model runs the pinned Qwen CPU model with measured inference receipts. Hosted AI comparison was **not performed**. These acceptance fixtures are visible during implementation; the separate frozen intake benchmark measures model classification. Neither evaluation estimates merchant handling time, customer outcomes, or adoption.

| Profile | Pass / trials | False resolutions | Duplicate effects | End-state stale tracking | New invariant violations | Restart resolved / exercised | Counted operator steps | Model calls / USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| local-model | 123 / 168 | 42 | 0 | 0 | 0 | 66 / 69 | 744 | 153 / 0.00 |

Operator steps count invoked desk interactions plus explicit SOP intent selection. They are not timed human interactions; a smaller count does not establish a handling-time gain. Restart-exercised includes deliberately unknowable outcomes, whose correct result is escalation, so restart-resolved is not a safety success rate. Initial malformed business states are separately recorded; unchanged pre-existing findings are not labeled newly introduced violations.

## Scenario results

| Scenario | Result | Observed states |
|---|---:|---|
| cancel_two_lines | 3 / 3 | resolved |
| cancel_usd | 3 / 3 | resolved |
| cancel_eur | 3 / 3 | resolved |
| cancel_printed_with_hold | 3 / 3 | resolved |
| printed_unknown_dispatch | 3 / 3 | needs-information |
| address_label_recreation | 0 / 3 | resolved |
| address_before_label | 0 / 3 | resolved |
| already_dispatched | 3 / 3 | escalated |
| partially_dispatched | 3 / 3 | escalated |
| refund_lost_response | 3 / 3 | resolved |
| refund_failure_partial | 3 / 3 | resolved |
| refund_service_recovery | 3 / 3 | resolved |
| refund_rate_limit | 3 / 3 | resolved |
| cancel_before_write | 3 / 3 | resolved |
| carrier_void_rejected | 3 / 3 | escalated |
| replacement_failure_partial | 0 / 3 | resolved |
| address_failure_after_void | 0 / 3 | resolved |
| void_lost_response | 3 / 3 | resolved |
| replacement_lost_response | 0 / 3 | resolved |
| changed_after_approval | 3 / 3 | needs-information |
| dispatch_after_approval | 3 / 3 | escalated |
| dispatch_at_write_boundary | 3 / 3 | escalated |
| hold_expired | 3 / 3 | needs-information |
| warehouse_unreliable | 3 / 3 | needs-information |
| duplicate_active_labels | 3 / 3 | escalated |
| shipment_quantity_mismatch | 3 / 3 | escalated |
| cancel_stale_tracking | 3 / 3 | resolved |
| duplicate_out_of_order_events | 3 / 3 | resolved |
| two_operators | 3 / 3 | resolved |
| viewer_cannot_mutate | 3 / 3 | rejected |
| other_store_order | 3 / 3 | rejected |
| customer_prompt_injection | 3 / 3 | needs-information |
| unsupported_currency | 3 / 3 | rejected |
| fractional_quantity | 3 / 3 | rejected |
| ambiguous_customer_request | 3 / 3 | needs-information |
| address_missing_details | 0 / 3 | needs-information |
| cancel_restart_boundaries | 27 / 27 | resolved |
| address_restart_boundaries | 0 / 27 | resolved |
| stale_refund_read | 3 / 3 | resolved |
| refund_outcome_unknown | 3 / 3 | escalated |

## Failures requiring attention

- `address_label_recreation/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_label_recreation/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_label_recreation/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_before_label/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_before_label/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_before_label/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `replacement_failure_partial/local-model/7` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `replacement_failure_partial/local-model/19` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `replacement_failure_partial/local-model/41` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_failure_after_void/local-model/7` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_failure_after_void/local-model/19` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_failure_after_void/local-model/41` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `replacement_lost_response/local-model/7` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `replacement_lost_response/local-model/19` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `replacement_lost_response/local-model/41` — failure_checkpoint_not_resolved: Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.; no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_missing_details/local-model/7` — escalation_matches_actual_obstacle: Expected one of ('address', 'information', 'detail', 'recipient', 'street', 'postcode'); observed Label recovery — awaiting a current, positively acknowledged warehouse hold. Missing dispatch data is not a safe stop.
- `address_missing_details/local-model/19` — escalation_matches_actual_obstacle: Expected one of ('address', 'information', 'detail', 'recipient', 'street', 'postcode'); observed Label recovery — awaiting a current, positively acknowledged warehouse hold. Missing dispatch data is not a safe stop.
- `address_missing_details/local-model/41` — escalation_matches_actual_obstacle: Expected one of ('address', 'information', 'detail', 'recipient', 'street', 'postcode'); observed Label recovery — awaiting a current, positively acknowledged warehouse hold. Missing dispatch data is not a safe stop.
- `address_restart_boundaries-void_label-after_intent/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_intent/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_intent/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_effect/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_effect/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_effect/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_record/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_record/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-void_label-after_record/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication
- `address_restart_boundaries-update_address-after_intent/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_intent'}; restart_recovered
- `address_restart_boundaries-update_address-after_intent/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_intent'}; restart_recovered
- `address_restart_boundaries-update_address-after_intent/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_intent'}; restart_recovered
- `address_restart_boundaries-update_address-after_effect/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_effect'}; restart_recovered
- `address_restart_boundaries-update_address-after_effect/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_effect'}; restart_recovered
- `address_restart_boundaries-update_address-after_effect/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_effect'}; restart_recovered
- `address_restart_boundaries-update_address-after_record/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_record'}; restart_recovered
- `address_restart_boundaries-update_address-after_record/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_record'}; restart_recovered
- `address_restart_boundaries-update_address-after_record/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'update_address', 'boundary': 'after_record'}; restart_recovered
- `address_restart_boundaries-create_label-after_intent/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_intent'}; restart_recovered
- `address_restart_boundaries-create_label-after_intent/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_intent'}; restart_recovered
- `address_restart_boundaries-create_label-after_intent/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_intent'}; restart_recovered
- `address_restart_boundaries-create_label-after_effect/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_effect'}; restart_recovered
- `address_restart_boundaries-create_label-after_effect/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_effect'}; restart_recovered
- `address_restart_boundaries-create_label-after_effect/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_effect'}; restart_recovered
- `address_restart_boundaries-create_label-after_record/local-model/7` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_record'}; restart_recovered
- `address_restart_boundaries-create_label-after_record/local-model/19` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_record'}; restart_recovered
- `address_restart_boundaries-create_label-after_record/local-model/41` — no_false_resolution_claim; intended_terminal_state: cancelled; necessary_success_communication; requested_termination_boundary_reached: {'action': 'create_label', 'boundary': 'after_record'}; restart_recovered

## Reproduction and limits

- `results.json` contains every check and measured count; `traces.jsonl` contains inputs, interpretation, event schedules, API results, failure checkpoints, boundaries, provider truth and final audit records.
- `seeds.json` records the exact schedules. Each trial retains separate `states/…/ledger.sqlite` and `providers.sqlite` databases, preventing a shared database transaction from concealing uncertain external effects.
- Abrupt-boundary evaluation raises a `BaseException` after durable intent, provider effect, or recorded receipt. Real subprocess termination is covered by the core acceptance tests, when run; this evaluator does not claim to perform an OS kill.
- No real merchant, payment gateway, carrier, warehouse, webhook, hosted model, or customer communication is contacted. Optional local-model inference executes real open-weight inference on CPU. Provider charges are USD 0.00; local hardware and electricity are not priced. Simulator receipt lookup and warehouse fencing are stronger contracts that real deployments must verify separately.
- Warehouse hold receipts are graded separately: each needs a durable request and matching operator/store permission evidence from before the write. Resolved cases also require verified warehouse receipt read-back. Raw traces retain warehouse attempts and receipts.
- Money is integer minor units. Unsupported currency/quantity scenarios must be rejected; recovery is scoped to a single parcel. A correct escalation requires the specific obstacle, durable evidence and a safe local draft; escalation alone does not pass.
