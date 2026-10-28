"""Outcome grader tests include negative controls, not just happy-path scores."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from parcelresolve.evaluation import (
    Trial,
    communication_safe,
    duplicate_effect_count,
    effects_approved,
    fixture_order,
    intended_terminal_state,
    load_catalog,
    run_evaluation,
    schedule_for,
    variants_for,
    warehouse_effects_authorized,
)


def scenario(scenario_id: str) -> dict:
    return next(row for row in load_catalog()["scenarios"] if row["id"] == scenario_id)


def test_independent_evaluation_records_and_validation_cases() -> None:
    catalog = load_catalog()
    orders = [row["initial"]["order_id"] for row in catalog["scenarios"]]
    assert len(catalog["scenarios"]) >= 30
    assert len(set(orders)) == len(orders)
    assert not set(orders).intersection(catalog["development_order_ids_excluded"])
    for row in catalog["scenarios"]:
        if row["kind"] == "invalid_input":
            with pytest.raises(ValidationError):
                fixture_order(row)
        else:
            order = fixture_order(row)
            assert order.id == row["initial"]["order_id"]
            assert order.payment.captured.minor == sum(
                line.quantity * line.unit_price.minor for line in order.lines
            )


def test_seeded_schedules_are_reproducible_and_have_real_delivery_variation() -> None:
    schedules = [schedule_for(seed, "refund_lost_response") for seed in [7, 19, 41]]
    assert schedules == [schedule_for(seed, "refund_lost_response") for seed in [7, 19, 41]]
    assert len({tuple(row["late_delivery_order"]) for row in schedules}) > 1
    assert all(
        set(row["late_delivery_order"]) == {"current", "old", "current_duplicate", "initial_duplicate"}
        for row in schedules
    )
    assert schedule_for(7, "refund_lost_response") != schedule_for(7, "dispatch_after_approval")


def test_crash_matrix_covers_every_mutating_boundary_in_both_flows() -> None:
    cancel = variants_for(scenario("cancel_restart_boundaries"))
    address = variants_for(scenario("address_restart_boundaries"))
    for action in {"void_label", "cancel_order", "refund", "update_address", "create_label"}:
        present = [row for row in cancel + address if row and row["action"] == action]
        assert {row["boundary"] for row in present} == {"after_intent", "after_effect", "after_record"}


def test_duplicate_grader_rejects_semantic_duplicate_under_different_key() -> None:
    effects = [{"kind": "refund", "operation_key": "first"}, {"kind": "refund", "operation_key": "second"}]
    assert duplicate_effect_count(effects) == 1
    assert duplicate_effect_count(effects[:1]) == 0


def test_communication_grader_rejects_unsupported_stopped_or_refunded_claim() -> None:
    order = fixture_order(scenario("printed_unknown_dispatch"))
    assert not communication_safe({"draft": "Your parcel is stopped."}, order)
    assert not communication_safe({"draft": "Your order has been refunded."}, order)
    assert communication_safe({"draft": "We have not yet confirmed that the parcel is stopped."}, order)
    assert not communication_safe({"draft": {"text": "We are checking your request.", "sent": True}}, order)


def test_false_resolution_negative_control_uses_provider_truth(tmp_path: Path) -> None:
    row = scenario("cancel_two_lines")
    trial = Trial(row, 7, "operator-sop", tmp_path, io.StringIO(), None)
    trial.run_workflow()
    assert trial.view and trial.view["status"] == "resolved"
    # Corrupt the provider truth after a plausible desk success. The grader must
    # not count the desk's status or its own expected label as evidence of success.
    initial = fixture_order(row)
    trial.engine.sim.put_order(initial)
    result = trial.grade()
    assert not result["passed"]
    assert result["metrics"]["false_resolution_claims"] == 1
    assert not intended_terminal_state(row, initial)


def test_arbitrary_escalation_cannot_pass_a_supported_success(tmp_path: Path) -> None:
    row = scenario("cancel_two_lines")
    trial = Trial(row, 19, "operator-sop", tmp_path, io.StringIO(), None)
    trial.run_workflow()
    case = trial.engine.store.get_case(trial.case_id)
    case.status = "escalated"
    case.reason = "Manual review."
    trial.engine.store.save_case(case)
    result = trial.grade()
    assert not result["passed"]
    assert any(
        check["name"] == "verified_resolution_status" and not check["passed"] for check in result["checks"]
    )


def test_address_grade_requires_a_real_label_and_current_hold(tmp_path: Path) -> None:
    row = scenario("address_before_label")
    trial = Trial(row, 7, "operator-sop", tmp_path, io.StringIO(), None)
    trial.run_workflow()
    order = trial.engine.sim.peek(row["initial"]["order_id"])
    assert intended_terminal_state(row, order)
    no_label = order.model_copy(deep=True)
    no_label.labels = []
    no_label.tracking = []
    assert not intended_terminal_state(row, no_label)
    unreliable_hold = order.model_copy(deep=True)
    unreliable_hold.warehouse.reliable = False
    assert not intended_terminal_state(row, unreliable_hold)


def test_prelabel_grader_rejects_unreliable_or_expired_warehouse_claim(tmp_path: Path) -> None:
    row = scenario("cancel_two_lines")
    trial = Trial(row, 7, "operator-sop", tmp_path, io.StringIO(), None)
    trial.run_workflow()
    order = trial.engine.sim.peek(row["initial"]["order_id"])
    assert intended_terminal_state(row, order)
    order.warehouse.reliable = False
    assert not intended_terminal_state(row, order)
    order.warehouse.reliable = True
    order.warehouse.state = "held"
    order.warehouse.ack_id = "expired-ack"
    order.warehouse.acknowledged_at = "2020-01-01T00:00:00+00:00"
    order.warehouse.expires_at = "2020-01-01T00:05:00+00:00"
    assert not intended_terminal_state(row, order)


def test_effect_authorization_grade_rejects_approval_for_a_different_amount(tmp_path: Path) -> None:
    row = scenario("cancel_two_lines")
    trial = Trial(row, 7, "operator-sop", tmp_path, io.StringIO(), None)
    trial.run_workflow()
    view = trial.engine.view(trial.case_id)
    effects = trial.engine.sim.effects(row["initial"]["order_id"])
    assert effects_approved(view, effects)
    for approval in view["approvals"]:
        if approval["amount"]:
            approval["amount"]["minor"] -= 1
    assert not effects_approved(view, effects)


def test_warehouse_grade_rejects_missing_or_postdated_intent_or_wrong_operator(tmp_path: Path) -> None:
    import copy

    row = scenario("address_before_label")
    trial = Trial(row, 7, "operator-sop", tmp_path, io.StringIO(), None)
    trial.run_workflow()
    view = trial.engine.view(trial.case_id)
    attempts = trial.engine.store.hold_attempts(trial.case_id)
    effects = trial.engine.sim.hold_effects(row["initial"]["order_id"])
    evidence = trial.engine.store.events(trial.case_id)
    assert effects and attempts
    assert warehouse_effects_authorized(view, attempts, effects, evidence)
    assert not warehouse_effects_authorized(view, [], effects, evidence)
    assert not warehouse_effects_authorized(view, attempts, effects, [])
    changed = copy.deepcopy(evidence)
    for event in changed:
        if event["kind"] == "warehouse_intent":
            event["created_at"] = "9999-01-01"
    assert not warehouse_effects_authorized(view, attempts, effects, changed)
    changed_attempts = copy.deepcopy(attempts)
    changed_attempts[0]["operator_id"] = "viewer-demo"
    assert not warehouse_effects_authorized(view, changed_attempts, effects, evidence)


def test_frozen_model_split_and_grade_have_no_inference_or_target_padding() -> None:
    from parcelresolve.model_evaluation import grade_interpretation, validate_freeze

    freeze, corpus = validate_freeze()
    records = corpus["records"]
    assert len(records) == 36 and freeze["no_fine_tuning"] is True
    record = next(row for row in records if row["expected_intent"] == "unknown")
    wrong = grade_interpretation(record, {"intent": "cancel", "needs_clarification": False})
    assert not wrong["correct"] and wrong["false_actionable_interpretation"]
    assert not grade_interpretation(record, None)["correct"]
    assert grade_interpretation(record, {"intent": "unknown", "needs_clarification": True})["correct"]


def test_offline_profiles_emit_replayable_evidence_without_model_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline evaluation must not instantiate a live model client")

    monkeypatch.setattr("parcelresolve.intake.OpenAIInterpreter.from_env", forbidden)
    selected = [
        "cancel_two_lines",
        "refund_lost_response",
        "replacement_failure_partial",
        "dispatch_at_write_boundary",
        "duplicate_out_of_order_events",
        "customer_prompt_injection",
        "refund_outcome_unknown",
    ]
    run = run_evaluation(tmp_path / "run", [7], selected)
    assert run["summary"]["failed"] == 0
    assert run["summary"]["trials"] == len(selected) * 2
    assert run["live_ai_comparison"] == "not performed"
    assert all(
        row["metrics"]["model_calls"] == 0 and row["metrics"]["model_cost_usd"] == "0.00"
        for row in run["results"]
    )
    trace = [json.loads(line) for line in (tmp_path / "run" / "traces.jsonl").read_text().splitlines()]
    assert any(row["event"] == "failure_checkpoint" for row in trace)
    assert any(row["event"] == "engine_restart" for row in trace)
    assert any(row["event"] == "event_delivery" for row in trace)
    assert (tmp_path / "run" / "seeds.json").is_file()
    assert len(list((tmp_path / "run" / "states").rglob("providers.sqlite"))) == len(selected) * 2
    with pytest.raises(ValueError, match="not empty"):
        run_evaluation(tmp_path / "run", [7], selected)
