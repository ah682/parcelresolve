"""Warehouse requests cross an independent durable provider boundary too."""

from __future__ import annotations

import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from parcelresolve.domain import DeskError, PreconditionFailed, WarehouseAcknowledgment
from parcelresolve.engine import VIEWER, Engine
from parcelresolve.seed import make_order


def awaiting_hold(directory, flow="post"):
    engine = Engine(directory)
    order = make_order(labelled=True)
    engine.sim.put_order(order)
    target = order.address.model_copy(update={"line1": "52 Birch Terrace"}) if flow == "address" else None
    case = engine.create_case(
        order.id, "Change address" if target else "Cancel order", "address" if target else "cancel", target
    )
    case = engine.investigate(case["id"])
    assert case["status"] == "needs-information"
    return engine, case


@pytest.mark.parametrize("flow", ["post", "address"])
@pytest.mark.parametrize("boundary", ["after_intent", "after_effect", "after_record"])
def test_real_sigkill_warehouse_boundaries_reconcile_without_second_hold(tmp_path, flow, boundary):
    engine, case = awaiting_hold(tmp_path, flow)
    script = """
import os, signal, sys
from pathlib import Path
from parcelresolve.engine import Engine
def hook(boundary, action):
    if boundary == sys.argv[3] and action.kind.value == "warehouse_hold":
        os.kill(os.getpid(), signal.SIGKILL)
Engine(Path(sys.argv[1]), crash_hook=hook).hold(sys.argv[2])
"""
    killed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), case["id"], boundary], capture_output=True, timeout=15
    )
    assert killed.returncode == -signal.SIGKILL, killed.stderr.decode()
    before = engine.sim.hold_effects("1042")
    assert len(before) == (0 if boundary == "after_intent" else 1)
    persisted = engine.store.hold_attempts(case["id"])
    assert len(persisted) == 1 and persisted[0]["operator_id"]
    restarted = Engine(tmp_path)
    result = restarted.recover_pending()[0]
    assert result["status"] == "awaiting-approval"
    assert not result["approved"]
    assert not restarted.sim.effects("1042")
    receipt = restarted.sim.hold_effects("1042")
    assert len(receipt) == 1
    assert not before or receipt == before
    attempt = result["warehouse_attempts"][0]
    assert attempt["status"] == "succeeded" and attempt["readback_status"] == "verified"
    assert attempt["provider_id"] == result["order"]["warehouse"]["ack_id"]
    assert receipt[0]["operation_key"] == attempt["idempotency_key"]
    approved = restarted.approve(result["id"], result["plan"]["hash"], result["plan"]["resource_version"])
    assert restarted.execute(approved["id"])["status"] == "resolved"
    assert len(restarted.sim.hold_effects("1042")) == 1


def test_lost_hold_response_queries_before_retry_and_keeps_original_ack(tmp_path):
    engine, case = awaiting_hold(tmp_path)
    engine.sim.inject("1042", "warehouse_hold", "lost_response")
    uncertain = engine.hold(case["id"])
    assert uncertain["warehouse_attempts"][0]["status"] == "uncertain"
    assert uncertain["plan"] is None
    assert uncertain["permitted"]["retry"] and not uncertain["permitted"]["investigate"]
    assert "not yet confirmed" in uncertain["draft"]
    receipt = engine.sim.hold_effects("1042")[0]
    recovered = Engine(tmp_path).recover_pending()[0]
    assert recovered["status"] == "awaiting-approval"
    assert recovered["order"]["warehouse"]["ack_id"] == receipt["provider_id"]
    assert engine.sim.hold_effects("1042") == [receipt]
    assert any(e["kind"] == "warehouse_reconciliation" for e in recovered["evidence"])


def test_unknown_hold_outcome_escalates_and_never_reissues(tmp_path):
    engine, case = awaiting_hold(tmp_path)
    engine.sim.inject("1042", "warehouse_hold", "unknown_outcome")
    engine.hold(case["id"])
    for _ in range(2):
        result = Engine(tmp_path).retry(case["id"])
        assert result["status"] == "escalated" and result["plan"] is None
        assert len(engine.sim.hold_effects("1042")) == 1
    with pytest.raises(DeskError, match="persisted"):
        engine.investigate(case["id"])
    with pytest.raises(DeskError, match="persisted"):
        engine.clarify(case["id"], "address", make_order().address)
    assert engine.view(case["id"])["intent"] == "cancel"
    assert not engine.sim.effects("1042")


@pytest.mark.parametrize("fault", ["before_write", "unavailable", "rate_limit"])
def test_known_unwritten_hold_is_retryable_without_duplicating_intent(tmp_path, fault):
    engine, case = awaiting_hold(tmp_path)
    engine.sim.inject("1042", "warehouse_hold", fault)
    result = engine.hold(case["id"])
    assert result["status"] == "needs-information"
    assert not engine.sim.hold_effects("1042")
    key = result["warehouse_attempts"][0]["idempotency_key"]
    result = Engine(tmp_path).retry(case["id"])
    assert result["status"] == "awaiting-approval"
    assert len(result["warehouse_attempts"]) == 1
    assert engine.sim.hold_effects("1042")[0]["operation_key"] == key


def test_dispatch_at_hold_boundary_cannot_claim_a_stop(tmp_path):
    engine, case = awaiting_hold(tmp_path)
    engine.sim.inject("1042", "warehouse_hold", "dispatch_race")
    result = engine.hold(case["id"])
    assert result["status"] == "escalated"
    assert result["plan"] is None and not engine.sim.hold_effects("1042")
    assert "cannot confirm" in result["draft"]
    assert result["warehouse_attempts"][0]["status"] == "failed"


@pytest.mark.parametrize("change", ["expire_hold", "dispatch", "address"])
def test_changed_or_expired_hold_is_not_renewed_during_restart(tmp_path, change):
    engine, case = awaiting_hold(tmp_path)
    engine.sim.inject("1042", "warehouse_hold", "lost_response")
    engine.hold(case["id"])
    engine.sim.external_change("1042", change)
    result = Engine(tmp_path).recover_pending()[0]
    assert result["status"] == "escalated" and result["plan"] is None
    assert len(engine.sim.hold_effects("1042")) == 1
    assert result["warehouse_attempts"][0]["readback_status"] == "failed"
    assert not result["permitted"]["approve"]


@pytest.mark.parametrize("fault", ["stale_read", "unavailable"])
def test_hold_receipt_requires_fresh_readback(tmp_path, fault):
    engine, case = awaiting_hold(tmp_path)

    def hook(boundary, action):
        if boundary == "after_record":
            engine.sim.inject("1042", "read", fault)

    engine.crash_hook = hook
    result = engine.hold(case["id"])
    assert result["status"] == "needs-information" and result["plan"] is None
    assert result["warehouse_attempts"][0]["readback_status"] == "pending"
    result = Engine(tmp_path).recover_pending()[0]
    assert result["status"] == "awaiting-approval"
    assert len(engine.sim.hold_effects("1042")) == 1


def test_unwritten_hold_external_change_requires_fresh_operator_request(tmp_path):
    engine, case = awaiting_hold(tmp_path)
    engine.sim.inject("1042", "warehouse_hold", "before_write")
    engine.hold(case["id"])
    engine.sim.external_change("1042", "address")
    result = Engine(tmp_path).retry(case["id"])
    assert result["status"] == "needs-information"
    assert not result["permitted"]["retry"] and not engine.sim.hold_effects("1042")
    assert engine.hold(case["id"])["status"] == "awaiting-approval"
    assert len(engine.sim.hold_effects("1042")) == 1


def test_concurrent_hold_recovery_and_unauthorized_retry(tmp_path):
    engine, case = awaiting_hold(tmp_path)
    engine.sim.inject("1042", "warehouse_hold", "lost_response")
    engine.hold(case["id"])
    with pytest.raises(DeskError) as error:
        engine.retry(case["id"], VIEWER)
    assert error.value.status_code == 403

    def retry(_):
        try:
            return Engine(tmp_path).retry(case["id"])["status"]
        except DeskError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(retry, range(2)))
    assert "awaiting-approval" in states
    assert len(engine.sim.hold_effects("1042")) == 1
    assert not engine.sim.effects("1042")


def test_hold_idempotency_cannot_be_rebound_to_another_version(tmp_path):
    engine, case = awaiting_hold(tmp_path)
    result = engine.hold(case["id"])
    attempt = result["warehouse_attempts"][0]
    with pytest.raises(PreconditionFailed):
        engine.sim.confirm_hold("1042", operation_key=attempt["idempotency_key"], expected_version=999)
    assert len(engine.sim.hold_effects("1042")) == 1


@pytest.mark.parametrize("status", ["investigating", "proposal-ready"])
def test_interrupted_plan_preparation_retains_an_operator_recovery_control(tmp_path, status):
    engine = Engine(tmp_path)
    engine.sim.put_order(make_order())
    case = engine.create_case("1042", "Cancel the order")
    script = """
import os, signal, sys
from pathlib import Path
from parcelresolve.engine import Engine
engine = Engine(Path(sys.argv[1]))
save = engine.store.save_case
def interrupted_save(case, **kwargs):
    save(case, **kwargs)
    if case.status == sys.argv[3]:
        os.kill(os.getpid(), signal.SIGKILL)
engine.store.save_case = interrupted_save
engine.investigate(sys.argv[2])
"""
    killed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), case["id"], status], capture_output=True, timeout=15
    )
    assert killed.returncode == -signal.SIGKILL, killed.stderr.decode()
    restarted = Engine(tmp_path)
    pending = restarted.view(case["id"])
    assert pending["status"] == status and pending["permitted"]["investigate"]
    result = restarted.investigate(case["id"])
    assert result["status"] == "awaiting-approval" and not result["approved"]
    assert not restarted.sim.effects("1042")


def test_additive_warehouse_migration_preserves_version_one_case_and_approval(tmp_path):
    engine = Engine(tmp_path)
    engine.sim.put_order(make_order())
    case = engine.create_case("1042", "Cancel the order")
    case = engine.investigate(case["id"])
    case = engine.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])
    with engine.store.connect() as conn:
        conn.execute("DROP TABLE warehouse_attempts")
        conn.execute("DELETE FROM schema_migrations WHERE version=2")
    with engine.sim.connect() as conn:
        conn.execute("DROP TABLE hold_effects")
        conn.execute("DELETE FROM schema_migrations WHERE version=2")
    restarted = Engine(tmp_path)
    upgraded = restarted.view(case["id"])
    assert upgraded["plan"] == case["plan"] and upgraded["approvals"] == case["approvals"]
    assert upgraded["warehouse_attempts"] == [] and restarted.sim.hold_effects("1042") == []
    assert restarted.execute(case["id"])["status"] == "resolved"


@pytest.mark.parametrize("evidence", ["expired_hold", "unreliable_hold", "unreliable_not_dispatched"])
@pytest.mark.parametrize("stage", ["planning", "approval", "execution", "action_boundary", "terminal"])
def test_unlabelled_recovery_never_trusts_expired_or_unreliable_warehouse_evidence(tmp_path, evidence, stage):
    at = datetime.now(UTC)
    positive = WarehouseAcknowledgment(
        state="held",
        reliable=True,
        ack_id="confirmed-hold",
        acknowledged_at=at.isoformat(),
        expires_at=(at + timedelta(minutes=5)).isoformat(),
    )
    bad = positive.model_copy(deep=True)
    if evidence == "expired_hold":
        bad.expires_at = (at - timedelta(seconds=1)).isoformat()
    elif evidence == "unreliable_hold":
        bad.reliable = False
    else:
        bad = WarehouseAcknowledgment(state="not_dispatched", reliable=False)
    engine = Engine(tmp_path)
    order = make_order()
    order.warehouse = bad if stage == "planning" else positive
    engine.sim.put_order(order)
    case = engine.create_case("1042", "Cancel the order")
    case = engine.investigate(case["id"])
    if stage == "planning":
        assert case["status"] == "needs-information" and case["plan"] is None
        return

    def lose_evidence():
        current = engine.sim.peek("1042")
        # Expiry/reliability loss must be caught even without a version increment.
        current.warehouse = bad
        engine.sim.put_order(current)

    if stage == "approval":
        lose_evidence()
    case = engine.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])
    if stage == "approval":
        assert case["status"] == "needs-information" and not case["approved"]
        assert not engine.sim.effects("1042")
        return
    if stage == "execution":
        lose_evidence()
    else:

        def hook(boundary, action):
            if (stage == "action_boundary" and boundary == "after_intent") or (
                stage == "terminal" and boundary == "after_effect" and action.kind.value == "refund"
            ):
                lose_evidence()

        engine.crash_hook = hook
    result = engine.execute(case["id"])
    assert result["status"] == "escalated"
    assert not engine.terminal_verified(engine.store.get_case(case["id"]), engine.sim.peek("1042"))
    if stage != "terminal":
        assert not engine.sim.effects("1042")
