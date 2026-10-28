"""End-to-end domain outcomes, unsafe windows, provider effects and operator boundaries."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from parcelresolve.domain import ActionKind, Address, DeskError, Money, Operator, ProposedAction, Refund
from parcelresolve.engine import OPERATOR, VIEWER, Engine
from parcelresolve.seed import make_order


def prepare(tmp_path, flow="pre", *, fault=None, action="refund"):
    engine = Engine(tmp_path)
    order = make_order(labelled=flow != "pre")
    engine.sim.put_order(order)
    target = order.address.model_copy(update={"line1": "52 Birch Terrace"}) if flow == "address" else None
    case = engine.create_case(
        order.id,
        "Please correct my address" if target else "Cancel my order",
        "address" if target else "cancel",
        target,
    )
    case = engine.investigate(case["id"])
    if flow != "pre":
        assert case["status"] == "needs-information"
        case = engine.hold(case["id"])
    assert case["status"] == "awaiting-approval"
    case = engine.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])
    if fault:
        engine.sim.inject(order.id, action, fault)
    return engine, case


@pytest.mark.parametrize("flow", ["pre", "post", "address"])
def test_three_supported_flows_have_verified_readback(tmp_path, flow):
    engine, case = prepare(tmp_path, flow)
    result = engine.execute(case["id"])
    assert result["status"] == "resolved"
    assert engine.terminal_verified(engine.store.get_case(case["id"]), engine.sim.read("1042"))
    assert all(a["status"] == "succeeded" for a in result["attempts"])
    assert result["notification_status"] == "draft-only"


def test_printed_label_is_not_dispatch_or_stop_evidence(tmp_path):
    engine = Engine(tmp_path)
    engine.sim.put_order(make_order(labelled=True))
    case = engine.create_case("1042", "cancel")
    case = engine.investigate(case["id"])
    assert case["status"] == "needs-information"
    assert "warehouse hold" in case["reason"]
    assert case["order"]["shipments"][0]["status"] == "shipped"
    assert case["order"]["warehouse"]["state"] == "unknown"
    with pytest.raises(DeskError):
        engine.execute(case["id"])
    assert engine.sim.effects("1042") == []


def test_refund_lost_response_restarts_without_duplicate(tmp_path):
    engine, case = prepare(tmp_path, fault="lost_response")
    case = engine.execute(case["id"])
    assert case["status"] == "reconciling"
    assert len(engine.sim.read("1042").payment.refunds) == 1
    restarted = Engine(tmp_path)
    results = restarted.recover_pending()
    assert results[0]["status"] == "resolved"
    restarted.retry(case["id"])
    assert len(restarted.sim.read("1042").payment.refunds) == 1
    assert len(restarted.sim.effects("1042")) == 2


def test_unestablished_outcome_escalates_without_blind_replay(tmp_path):
    engine, case = prepare(tmp_path, fault="unknown_outcome")
    result = engine.execute(case["id"])
    assert result["status"] == "reconciling"
    result = Engine(tmp_path).retry(case["id"])
    assert result["status"] == "escalated"
    assert "Do not retry" in result["reason"]
    with pytest.raises(DeskError):
        engine.retry(case["id"])
    assert len(engine.sim.read("1042").payment.refunds) == 1


@pytest.mark.parametrize("fault", ["before_write", "unavailable", "rate_limit"])
def test_cancelled_but_refund_failed_remains_visibly_incomplete(tmp_path, fault):
    engine, case = prepare(tmp_path, fault=fault)
    result = engine.execute(case["id"])
    assert result["status"] == "failed"
    assert result["order"]["commercial_state"] == "cancelled"
    assert result["order"]["payment"]["refunds"] == []
    assert "refund is not yet confirmed" in result["draft"]
    result = Engine(tmp_path).retry(case["id"])
    assert result["status"] == "resolved"
    assert len(engine.sim.effects("1042")) == 2


def test_voided_label_failed_replacement_is_recoverable(tmp_path):
    engine, case = prepare(tmp_path, "address", fault="before_write", action="create_label")
    result = engine.execute(case["id"])
    assert result["status"] == "failed"
    assert all(label["status"] == "void" for label in result["order"]["labels"])
    assert result["order"]["tracking"] == []
    assert result["permitted"]["retry"]
    result = Engine(tmp_path).retry(case["id"])
    assert result["status"] == "resolved"
    assert len([label for label in result["order"]["labels"] if label["status"] == "active"]) == 1


def test_carrier_rejection_escalates_with_no_false_stop(tmp_path):
    engine, case = prepare(tmp_path, "post", fault="void_rejected", action="void_label")
    result = engine.execute(case["id"])
    assert result["status"] == "escalated"
    assert "Carrier rejected" in result["reason"]
    assert result["order"]["commercial_state"] == "processing"
    assert not engine.sim.effects("1042")
    assert "not yet confirmed" in result["draft"]


def test_stale_approval_is_not_reusable_for_new_customer_address(tmp_path):
    engine, case = prepare(tmp_path)
    engine.sim.external_change("1042", "address")
    result = engine.execute(case["id"])
    assert result["status"] == "needs-information"
    assert engine.sim.effects("1042") == []
    result = engine.investigate(case["id"])
    assert result["plan"]["hash"] != case["plan"]["hash"]
    assert not result["permitted"]["execute"]
    with pytest.raises(DeskError):
        engine.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])


@pytest.mark.parametrize("when", ["before_execution", "at_boundary", "between_actions"])
def test_dispatch_race_cannot_produce_a_stopped_claim(tmp_path, when):
    engine, case = prepare(tmp_path, "post")
    if when == "before_execution":
        engine.sim.external_change("1042", "dispatch")
    elif when == "at_boundary":
        engine.sim.inject("1042", "void_label", "dispatch_race")
    else:
        engine.sim.inject("1042", "cancel_order", "dispatch_race")
    result = engine.execute(case["id"])
    assert result["status"] == "escalated"
    assert result["order"]["commercial_state"] == "processing"
    assert "cannot confirm" in result["draft"]
    assert not result["order"]["payment"]["refunds"]


def test_hold_expiry_at_action_boundary_is_fenced(tmp_path):
    engine, case = prepare(tmp_path, "post")

    def boundary(name, action):
        if name == "after_intent":
            engine.sim.external_change("1042", "expire_hold")

    engine.crash_hook = boundary
    result = engine.execute(case["id"])
    assert result["status"] == "escalated"
    assert not engine.sim.effects("1042")


def test_two_operators_cannot_conflict_or_duplicate_effects(tmp_path):
    engine, case = prepare(tmp_path)
    other = OPERATOR.model_copy(update={"id": "operator-second"})

    def execute(operator):
        try:
            return Engine(tmp_path).execute(case["id"], operator)["status"]
        except DeskError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(execute, [OPERATOR, other]))
    assert "resolved" in states
    assert set(states) <= {"resolved", "conflict"}
    assert len(engine.sim.effects("1042")) == 2
    assert len(engine.sim.read("1042").payment.refunds) == 1


def test_approval_cannot_be_tampered_to_refund_another_amount(tmp_path):
    engine, case = prepare(tmp_path)
    persisted = engine.store.get_case(case["id"])
    persisted.plan.actions[-1].amount.minor += 1
    engine.store.save_case(persisted)
    with pytest.raises(DeskError):
        engine.execute(case["id"])
    assert engine.sim.effects("1042") == []


def test_same_key_different_operation_is_rejected_by_provider(tmp_path):
    engine, case = prepare(tmp_path)
    engine.execute(case["id"])
    attempt = engine.store.attempts(case["id"])[0]
    different = ProposedAction(
        id="other", kind=ActionKind.REFUND, title="Other refund", amount=Money(minor=99999, currency="GBP")
    )
    with pytest.raises(Exception, match="different action"):
        engine.sim.apply("1042", different, attempt["idempotency_key"], 1, None)
    assert len(engine.sim.effects("1042")) == 2


def test_partial_dispatch_never_uses_whole_order_cancellation(tmp_path):
    engine = Engine(tmp_path)
    engine.sim.put_order(make_order(labelled=True, partial=True))
    case = engine.create_case("1042", "Cancel everything")
    result = engine.investigate(case["id"])
    assert result["status"] == "escalated"
    assert "Whole-order recovery is blocked" in result["reason"]
    assert result["plan"] is None


def test_out_of_order_duplicate_deliveries_do_not_regress_projection(tmp_path):
    engine, case = prepare(tmp_path)
    assert engine.ingest_event("new", "1042", 10, {"state": "dispatched"}) == "accepted"
    assert engine.ingest_event("older", "1042", 2, {"state": "not_dispatched"}) == "stale"
    assert engine.ingest_event("new", "1042", 10, {"state": "not_dispatched"}) == "duplicate"
    assert engine.store.projection("1042") == {"version": 10, "payload": {"state": "dispatched"}}
    assert engine.sim.effects("1042") == []


def test_viewer_and_cross_store_operator_cannot_access_or_mutate(tmp_path):
    engine, case = prepare(tmp_path)
    outsider = Operator(id="outside", name="Other store", role="owner", store_ids=["store-2"])
    with pytest.raises(DeskError) as hidden:
        engine.view(case["id"], outsider)
    assert hidden.value.status_code == 404
    for method in [engine.execute, engine.retry, engine.hold, engine.investigate]:
        with pytest.raises(DeskError) as forbidden:
            method(case["id"], VIEWER)
        assert forbidden.value.status_code == 403
    assert engine.sim.effects("1042") == []


def test_stale_provider_reads_do_not_authorize_actions(tmp_path):
    engine, case = prepare(tmp_path)
    engine.sim.inject("1042", "read", "stale_read")
    result = engine.execute(case["id"])
    assert result["status"] == "needs-information"
    assert engine.sim.effects("1042") == []


def test_structured_operator_clarification_creates_fresh_approval_requirement(tmp_path):
    engine = Engine(tmp_path)
    engine.sim.put_order(make_order())
    case = engine.create_case("1042", "Maybe change or cancel this", "unknown")
    result = engine.investigate(case["id"])
    assert result["status"] == "needs-information"
    result = engine.clarify(case["id"], "cancel")
    assert result["status"] == "awaiting-approval"
    assert result["permitted"]["approve"]
    assert not engine.sim.effects("1042")


@pytest.mark.parametrize("bad", [1.1, "12.00", True, -1])
def test_money_never_rounds_or_accepts_floats(bad):
    with pytest.raises(ValidationError):
        Money(minor=bad, currency="GBP")


def test_unsupported_currency_and_fractional_quantity_are_rejected():
    with pytest.raises(ValidationError):
        Money(minor=100, currency="JPY")
    order = make_order().model_dump()
    order["lines"][0]["quantity"] = 0.5
    with pytest.raises(ValidationError):
        type(make_order()).model_validate(order)


CRASH_POINTS = [
    (flow, action, boundary)
    for flow, actions in [
        ("pre", ["cancel_order", "refund"]),
        ("post", ["void_label", "cancel_order", "refund"]),
        ("address", ["void_label", "update_address", "create_label"]),
    ]
    for action in actions
    for boundary in ["after_intent", "after_effect", "after_record"]
]


@pytest.mark.parametrize("flow,action,boundary", CRASH_POINTS)
def test_real_sigkill_at_every_mutating_boundary_preserves_recovery(tmp_path, flow, action, boundary):
    engine, case = prepare(tmp_path, flow)
    script = """
import os, signal, sys
from pathlib import Path
from parcelresolve.engine import Engine
def hook(boundary, action):
    if boundary == sys.argv[3] and action.kind.value == sys.argv[4]:
        os.kill(os.getpid(), signal.SIGKILL)
Engine(Path(sys.argv[1]), crash_hook=hook).execute(sys.argv[2])
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), case["id"], boundary, action],
        timeout=15,
        capture_output=True,
    )
    assert result.returncode == -signal.SIGKILL, result.stderr.decode()
    restarted = Engine(tmp_path)
    result = restarted.retry(case["id"])
    assert result["status"] == "resolved"
    receipts = restarted.sim.effects("1042")
    assert len({r["operation_key"] for r in receipts}) == len(receipts)
    assert len(receipts) == (2 if flow == "pre" else 3)
    assert len(restarted.sim.read("1042").payment.refunds) == (0 if flow == "address" else 1)
    assert all(a["status"] == "succeeded" and a["provider_id"] for a in result["attempts"])


def test_durable_files_are_separate_from_provider_transaction(tmp_path):
    engine, case = prepare(tmp_path)
    assert engine.store.path != engine.sim.path
    assert os.path.exists(engine.store.path)
    assert os.path.exists(engine.sim.path)
    assert json.loads(engine.store.get_case(case["id"]).model_dump_json())["plan"]["hash"]


@pytest.mark.parametrize("field", ["name", "line1", "city", "postcode"])
def test_blank_address_fields_are_rejected_before_any_writes(field):
    address = make_order().address.model_dump()
    address[field] = "   "
    with pytest.raises(ValidationError):
        Address.model_validate(address)


def test_resolved_customer_draft_dates_warehouse_evidence(tmp_path):
    engine, case = prepare(tmp_path, "post")
    case = engine.execute(case["id"])
    assert "valid at that verification" in case["draft"]
    assert "current hold" not in case["draft"]
    engine.sim.external_change("1042", "expire_hold")
    case = engine.view(case["id"])
    assert "current hold" not in case["draft"]
    assert "parcel remains" not in case["draft"]


def test_interrupted_unwritten_operation_can_replan_after_external_change(tmp_path):
    engine, case = prepare(tmp_path)

    class Crash(BaseException):
        pass

    def hook(boundary, action):
        if boundary == "after_intent":
            raise Crash()

    engine.crash_hook = hook
    with pytest.raises(Crash):
        engine.execute(case["id"])
    restarted = Engine(tmp_path)
    restarted.sim.external_change("1042", "address")
    case = restarted.retry(case["id"])
    assert case["status"] == "needs-information"
    assert case["permitted"]["investigate"]
    case = restarted.investigate(case["id"])
    assert case["permitted"]["approve"]
    case = restarted.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])
    assert restarted.execute(case["id"])["status"] == "resolved"


def test_partial_cancellation_draft_reports_known_dispatch_and_missing_refund(tmp_path):
    engine, case = prepare(tmp_path, fault="dispatch_race")
    case = engine.execute(case["id"])
    assert case["status"] == "escalated"
    assert "dispatched" in case["draft"]
    assert "refund is not yet confirmed" in case["draft"]


def test_zero_value_return_cannot_receive_a_new_address_label(tmp_path):
    engine = Engine(tmp_path)
    order = make_order(labelled=True)
    order.payment.refunds.append(
        Refund(
            id="return-1",
            amount=Money(minor=0, currency="GBP"),
            line_quantities={"line-1": 1},
            operation_key="return-1",
        )
    )
    order.lines[0].refunded_quantity = 1
    engine.sim.put_order(order)
    target = order.address.model_copy(update={"line1": "New Road"})
    case = engine.create_case("1042", "Correct address", "address", target)
    case = engine.hold(case["id"])
    assert case["status"] == "escalated"
    assert case["plan"] is None
    assert engine.sim.effects("1042") == []


@pytest.mark.parametrize("labelled", [False, True])
def test_zero_total_cancellation_resolves_without_refund(tmp_path, labelled):
    engine = Engine(tmp_path)
    order = make_order(labelled=labelled)
    order.payment.captured.minor = 0
    for line in order.lines:
        line.unit_price.minor = 0
    engine.sim.put_order(order)
    case = engine.create_case(order.id, "Cancel my whole order", "cancel")
    case = engine.investigate(case["id"])
    if labelled:
        assert case["status"] == "needs-information"
        assert engine.sim.effects(order.id) == []
        case = engine.hold(case["id"])
    assert [action["kind"] for action in case["plan"]["actions"]] == (
        ["void_label", "cancel_order"] if labelled else ["cancel_order"]
    )
    with pytest.raises(DeskError, match="approval"):
        engine.execute(case["id"])
    engine.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])
    assert engine.execute(case["id"])["status"] == "resolved"

    restarted = Engine(tmp_path)
    result = restarted.view(case["id"])
    truth = restarted.sim.read(order.id)
    assert result["status"] == "resolved"
    assert restarted.terminal_verified(restarted.store.get_case(case["id"]), truth)
    assert truth.commercial_state == "cancelled"
    assert all(
        line.cancelled_quantity == line.quantity and line.refunded_quantity == 0 for line in truth.lines
    )
    assert all(label.status == "void" for label in truth.labels)
    assert truth.payment.refunds == []
    assert not any(effect["kind"] == "refund" for effect in restarted.sim.effects(order.id))
    assert "no refund was required" in result["draft"]
    assert "refund of" not in result["draft"]


def test_local_provider_ports_match_the_documented_adapter_interfaces(tmp_path):
    from parcelresolve.integrations import CommerceAdapter, PaymentAdapter, ShippingAdapter, WarehouseAdapter

    engine, case = prepare(tmp_path)
    assert isinstance(engine.commerce, CommerceAdapter)
    assert isinstance(engine.payments, PaymentAdapter)
    assert isinstance(engine.shipping, ShippingAdapter)
    assert isinstance(engine.warehouse, WarehouseAdapter)
    assert engine.commerce.read_commerce("1042").id == "1042"
    assert engine.payments.read_payment("1042").captured.minor == 6800
    assert len(engine.shipping.read_shipping("1042")["shipments"]) == 1
    assert engine.warehouse.read_warehouse("1042").state == "not_dispatched"
    result = engine.execute(case["id"])
    assert result["status"] == "resolved"
