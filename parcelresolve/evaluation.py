"""Reproducible synthetic evaluation of observable recovery outcomes.

The operator SOP, deterministic intake and optional genuine local-model intake use
the same recovery engine. These visible acceptance fixtures are distinct from the
frozen intake comparison corpus and do not estimate merchant benefit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import StrictInt, TypeAdapter, ValidationError

from .domain import Address, DeskError, OrderSnapshot, digest

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "evaluation" / "catalog.json"
BASELINE_PROFILES = ("operator-sop", "deterministic-intake")
PROFILES = (*BASELINE_PROFILES, "local-model")
BOUNDARIES = ("after_intent", "after_effect", "after_record")


class SimulatedTermination(BaseException):
    """A process-boundary simulation that ordinary exception handlers cannot hide."""


def jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    catalog = json.loads(path.read_text())
    records = catalog["scenarios"]
    ids = [row["id"] for row in records]
    orders = [row["initial"]["order_id"] for row in records]
    if len(ids) < 30 or len(set(ids)) != len(ids) or len(set(orders)) != len(orders):
        raise ValueError("Evaluation needs at least 30 independently identified scenarios and order records")
    if set(orders) & set(catalog["development_order_ids_excluded"]):
        raise ValueError("Evaluation order IDs overlap the development split")
    return catalog


def fixture_order(scenario: dict[str, Any]) -> OrderSnapshot:
    """Transform an evaluation record without importing the development seed helper."""
    spec = scenario["initial"]
    order_id = spec["order_id"]
    currency = spec["currency"]
    # Reject the deliberately fractional input fixture before any money arithmetic.
    qty = TypeAdapter(StrictInt).validate_python(spec["quantity"])
    unit = spec["unit_minor"]
    second = spec["second_line_minor"]
    address = spec["address"]
    line_a = f"evaluation-{order_id}-a"
    line_b = f"evaluation-{order_id}-b"
    order_key = f"wc-evaluation-{order_id}"
    shipment_id = f"eval-shipment-{order_id}"
    labelled = spec.get("labelled", False)
    warehouse: dict[str, Any] = {
        "state": "unknown" if labelled else "not_dispatched",
        "reliable": not labelled,
    }
    dispatched_a = qty if spec.get("dispatched") else (1 if spec.get("partial") else 0)
    dispatched_b = 1 if spec.get("dispatched") else 0
    if spec.get("dispatched") or spec.get("partial"):
        warehouse = {
            "state": "dispatched" if spec.get("dispatched") else "partially_dispatched",
            "reliable": True,
            "acknowledged_at": datetime.now(UTC).isoformat(),
        }
    if spec.get("unreliable_hold"):
        at = datetime.now(UTC)
        warehouse = {
            "state": "held",
            "reliable": False,
            "ack_id": f"unreliable-{order_id}",
            "acknowledged_at": (at - timedelta(seconds=10)).isoformat(),
            "expires_at": (at + timedelta(minutes=4)).isoformat(),
        }
    labels = (
        [
            {
                "id": f"eval-label-{order_id}",
                "shipment_id": shipment_id,
                "status": "active",
                "tracking": f"EVAL{order_id}OLD",
                "address": address,
            }
        ]
        if labelled
        else []
    )
    if spec.get("duplicate_labels"):
        labels.append(
            {
                "id": f"eval-label-{order_id}-duplicate",
                "shipment_id": shipment_id,
                "status": "active",
                "tracking": f"EVAL{order_id}SECOND",
                "address": address,
            }
        )
    quantities = {line_a: qty, line_b: 1}
    if spec.get("mismatched_quantities"):
        quantities[line_a] += 1
    shipments = (
        [{"id": shipment_id, "order_key": order_key, "line_quantities": quantities, "status": "shipped"}]
        if labelled
        else []
    )
    tracking = [label["tracking"] for label in labels]
    if spec.get("stale_tracking"):
        tracking = [f"STALE{order_id}"]
    return OrderSnapshot.model_validate(
        {
            "id": order_id,
            "store_id": spec["store_id"],
            "woo_id": int(order_id),
            "shipstation_order_id": 900000 + int(order_id),
            "shipstation_order_key": order_key,
            "version": 1,
            "customer_name": spec["customer_name"],
            "commercial_state": "processing",
            "address": address,
            "payment": {"captured": {"minor": qty * unit + second, "currency": currency}, "refunds": []},
            "lines": [
                {
                    "id": line_a,
                    "sku": f"EVAL-A-{order_id}",
                    "title": "Synthetic parcel item A",
                    "quantity": qty,
                    "unit_price": {"minor": unit, "currency": currency},
                    "dispatched_quantity": dispatched_a,
                },
                {
                    "id": line_b,
                    "sku": f"EVAL-B-{order_id}",
                    "title": "Synthetic parcel item B",
                    "quantity": 1,
                    "unit_price": {"minor": second, "currency": currency},
                    "dispatched_quantity": dispatched_b,
                },
            ],
            "labels": labels,
            "shipments": shipments,
            "warehouse": warehouse,
            "tracking": tracking,
        }
    )


def schedule_for(seed: int, scenario_id: str) -> dict[str, Any]:
    material = f"parcelresolve-evaluation-v1:{seed}:{scenario_id}".encode()
    derived = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    rng = random.Random(derived)
    late = ["current", "old", "current_duplicate", "initial_duplicate"]
    rng.shuffle(late)
    return {
        "seed": seed,
        "derived_seed": derived,
        "initial_delivery_stage": rng.choice(["before_investigation", "before_approval"]),
        "late_delivery_order": late,
    }


def variants_for(scenario: dict[str, Any]) -> list[dict[str, str] | None]:
    if scenario["kind"] != "crash_matrix":
        return [None]
    actions = (
        ("void_label", "cancel_order", "refund")
        if scenario["sop_intent"] == "cancel"
        else ("void_label", "update_address", "create_label")
    )
    return [{"action": action, "boundary": boundary} for action in actions for boundary in BOUNDARIES]


class Trial:
    def __init__(
        self,
        scenario: dict[str, Any],
        seed: int,
        profile: str,
        output: Path,
        trace: Any,
        variant: dict[str, str] | None,
    ):
        self.scenario = scenario
        self.seed = seed
        self.profile = profile
        self.variant = variant
        suffix = "" if variant is None else f"-{variant['action']}-{variant['boundary']}"
        self.id = f"{scenario['id']}{suffix}/{profile}/{seed}"
        self.directory = (
            output
            / "states"
            / scenario["id"]
            / ("main" if variant is None else f"{variant['action']}-{variant['boundary']}")
            / profile
            / str(seed)
        )
        self.trace_file = trace
        self.schedule = schedule_for(seed, scenario["id"])
        self.checks: list[dict[str, Any]] = []
        self.operator_steps = 0
        self.crash_count = 0
        self.restarted = False
        self.initial: OrderSnapshot | None = None
        self.view: dict[str, Any] | None = None
        self.engine: Any = None
        self.case_id: str | None = None
        self.intermediate: list[dict[str, Any]] = []
        self.error: str | None = None
        self.received_events: list[dict[str, Any]] = []
        self.trace_lock = threading.Lock()
        self.injected_postwrite_stale = False
        self.crash_armed = False
        self.intake_receipts: list[dict[str, Any]] = []

    def record(self, event: str, **data: Any) -> None:
        line = {
            "trial_id": self.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **jsonable(data),
        }
        with self.trace_lock:
            self.trace_file.write(json.dumps(line, sort_keys=True) + "\n")
            self.trace_file.flush()

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": bool(passed), "detail": detail})

    def call(self, name: str, *args: Any, operator_step: bool = True, **kwargs: Any) -> Any:
        if operator_step:
            self.operator_steps += 1
        self.record("call", operation=name, arguments=args, keyword_arguments=kwargs)
        try:
            result = getattr(self.engine, name)(*args, **kwargs)
        except Exception as exc:
            self.record(
                "call_error",
                operation=name,
                error=type(exc).__name__,
                detail=str(exc),
                status_code=getattr(exc, "status_code", None),
            )
            raise
        self.record("call_result", operation=name, result=result)
        if isinstance(result, dict) and "status" in result and "order_id" in result:
            self.view = result
        return result

    def crash_hook(self, boundary: str, action: Any) -> None:
        self.record("mutation_boundary", boundary=boundary, action=action)
        if (
            self.scenario["kind"] == "stale_read"
            and boundary == "after_effect"
            and str(action.kind) == "refund"
            and not self.injected_postwrite_stale
        ):
            self.injected_postwrite_stale = True
            self.engine.sim.inject(self.scenario["initial"]["order_id"], "read", "stale_read")
            self.record("fault_injected", action="read", fault="stale_read", boundary="after_refund_effect")
        if (
            self.crash_armed
            and self.variant
            and boundary == self.variant["boundary"]
            and str(action.kind) == self.variant["action"]
        ):
            self.crash_count += 1
            self.crash_armed = False
            self.record("simulated_termination", boundary=boundary, action=action)
            raise SimulatedTermination(f"terminated at {action.kind}:{boundary}")

    def fresh_engine(self) -> None:
        from .engine import Engine

        self.engine = Engine(self.directory, crash_hook=self.crash_hook)

    def deliver(self, event_id: str, version: int, payload: dict[str, Any]) -> None:
        row = {"event_id": event_id, "version": version, "payload": payload}
        self.received_events.append(row)
        result = self.engine.ingest_event(event_id, self.scenario["initial"]["order_id"], version, payload)
        self.record("event_delivery", **row, result=result)

    def initial_event(self) -> None:
        assert self.initial is not None
        self.deliver(f"initial-{self.initial.id}", self.initial.version, self.initial.model_dump(mode="json"))

    def late_events(self) -> None:
        assert self.initial is not None
        order_id = self.initial.id
        before = self.engine.sim.peek(order_id).model_dump(mode="json")
        final_version = before["version"]
        deliveries = {
            "current": (f"current-{order_id}-{final_version}", final_version, before),
            "current_duplicate": (f"current-{order_id}-{final_version}", final_version, before),
            "old": (f"delayed-{order_id}", self.initial.version, self.initial.model_dump(mode="json")),
            "initial_duplicate": (
                f"initial-{order_id}",
                self.initial.version,
                self.initial.model_dump(mode="json"),
            ),
        }
        for name in self.schedule["late_delivery_order"]:
            self.deliver(*deliveries[name])
        after = self.engine.sim.peek(order_id).model_dump(mode="json")
        projection = self.engine.store.projection(order_id)
        max_version = max(row["version"] for row in self.received_events)
        self.check("events_do_not_mutate_provider_truth", before == after)
        self.check(
            "projection_never_regresses",
            projection is not None and projection["version"] == max_version,
            f"projection version {None if projection is None else projection['version']}; max delivered {max_version}",
        )
        self.check(
            "projection_retains_latest_payload",
            projection is not None and projection["payload"] == before,
            "Delayed or duplicate delivery must not overwrite current provider evidence",
        )
        ids = [row["event_id"] for row in self.received_events]
        self.check("duplicate_event_schedule_exercised", len(ids) > len(set(ids)))
        self.record("projection_final", projection=projection)

    def approve(self) -> None:
        assert self.view is not None
        plan = self.view.get("plan")
        if not plan:
            raise AssertionError(
                f"No proposal to approve: {self.view.get('status')} — {self.view.get('reason')}"
            )
        self.call("approve", self.case_id, plan["hash"], plan["resource_version"])

    def resume(self) -> None:
        self.restarted = True
        self.record("engine_restart", directory=self.directory)
        self.fresh_engine()
        self.view = self.engine.view(self.case_id)
        self.record("restart_observation", view=self.view, attempts=self.engine.store.attempts(self.case_id))
        self.call("retry", self.case_id)

    def run_workflow(self) -> None:
        from .engine import VIEWER
        from .intake import capture_interpretation_receipts

        scenario = self.scenario
        self.record(
            "trial_start",
            scenario=scenario,
            profile=self.profile,
            schedule=self.schedule,
            variant=self.variant,
        )
        self.fresh_engine()
        if scenario["kind"] == "invalid_input":
            rejected = False
            try:
                order = fixture_order(scenario)
                self.engine.sim.put_order(order)
            except ValidationError as exc:
                rejected = True
                self.record("validation_rejected", errors=exc.errors(include_context=False))
            self.check(
                "unsupported_input_rejected",
                rejected,
                "Typed input must reject unsupported currency or fractional quantity",
            )
            self.check(
                "invalid_input_has_no_effects", not self.engine.sim.effects(scenario["initial"]["order_id"])
            )
            return
        self.initial = fixture_order(scenario)
        self.engine.sim.put_order(self.initial)
        self.record("initial_provider_truth", order=self.initial)
        if self.profile == "operator-sop":
            intent = scenario["sop_intent"]
            self.operator_steps += 1
            self.record(
                "operator_intent_selection",
                intent=intent,
                note="Explicit operator categorization; counted as one workflow interaction",
            )
        else:
            intent = None
        interpreter_mode = "local-model" if self.profile == "local-model" else "deterministic"
        address = (
            Address.model_validate(scenario["target_address"]) if scenario.get("target_address") else None
        )
        if scenario["kind"] in {"unauthorized", "unauthorized_store"}:
            blocked = False
            try:
                kwargs: dict[str, Any] = {"operator": VIEWER} if scenario["kind"] == "unauthorized" else {}
                self.call(
                    "create_case",
                    self.initial.id,
                    scenario["request"],
                    intent=intent,
                    target_address=address,
                    interpreter_mode=interpreter_mode,
                    **kwargs,
                )
            except DeskError as exc:
                blocked = exc.status_code in ({403} if scenario["kind"] == "unauthorized" else {403, 404})
            self.check(
                "authorization_rejected",
                blocked,
                "An authorization denial, not an arbitrary error, must block this request",
            )
            self.check("unauthorized_has_no_effects", not self.engine.sim.effects(self.initial.id))
            return
        previous_seed = os.environ.get("PARCELRESOLVE_LOCAL_MODEL_SEED")
        try:
            if self.profile == "local-model":
                os.environ["PARCELRESOLVE_LOCAL_MODEL_SEED"] = str(self.seed)
            with capture_interpretation_receipts() as captured:
                created = self.call(
                    "create_case",
                    self.initial.id,
                    scenario["request"],
                    intent=intent,
                    target_address=address,
                    interpreter_mode=interpreter_mode,
                )
            self.intake_receipts.extend(captured)
            for receipt in captured:
                self.record("intake_interpretation", **receipt)
        finally:
            if previous_seed is None:
                os.environ.pop("PARCELRESOLVE_LOCAL_MODEL_SEED", None)
            else:
                os.environ["PARCELRESOLVE_LOCAL_MODEL_SEED"] = previous_seed
        self.case_id = created["id"]
        if self.schedule["initial_delivery_stage"] == "before_investigation":
            self.initial_event()
        self.call("investigate", self.case_id)
        assert self.view is not None
        if scenario["kind"] == "injection":
            self.check("trusted_identity_preserved", self.view["order_id"] == self.initial.id)
            if self.view.get("plan"):
                amounts = [a["amount"] for a in self.view["plan"]["actions"] if a.get("amount")]
                self.check(
                    "text_cannot_set_refund_amount",
                    all(a == self.initial.payment.captured.model_dump(mode="json") for a in amounts),
                )
            try:
                self.call("execute", self.case_id)
            except DeskError:
                pass
            self.check("injection_cannot_bypass_approval", not self.engine.sim.effects(self.initial.id))
            self.check("injection_cannot_authorize_itself", not self.engine.store.approvals(self.case_id))
            self.late_events()
            return
        if scenario["kind"] in {"review", "needs_hold", "clarify", "missing_address"}:
            if self.schedule["initial_delivery_stage"] == "before_approval":
                self.initial_event()
            self.late_events()
            return
        if scenario["behavior"].get("hold"):
            self.call("hold", self.case_id)
            assert self.view is not None
            if not self.view.get("plan"):
                self.call("investigate", self.case_id)
        if self.schedule["initial_delivery_stage"] == "before_approval":
            self.initial_event()
        self.approve()
        behavior = scenario["behavior"]
        if scenario["kind"] == "external_change":
            changed = self.engine.sim.external_change(self.initial.id, behavior["change"])
            self.record("external_change", change=behavior["change"], order=changed)
        if behavior.get("fault") and scenario["kind"] != "stale_read":
            self.engine.sim.inject(self.initial.id, behavior["action"], behavior["fault"])
            self.record("fault_injected", action=behavior["action"], fault=behavior["fault"])
        self.crash_armed = self.variant is not None
        if scenario["kind"] == "concurrent":
            barrier = threading.Barrier(2)
            case_id = self.case_id
            assert case_id is not None

            def work() -> dict[str, Any]:
                from .engine import Engine

                engine = Engine(self.directory)
                barrier.wait(timeout=10)
                try:
                    return {"result": engine.execute(case_id)}
                except DeskError as exc:
                    return {"error": str(exc), "status_code": exc.status_code}

            self.operator_steps += 2
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: work(), range(2)))
            self.record("concurrent_results", results=outcomes)
            self.view = self.engine.view(self.case_id)
            self.check(
                "concurrent_operator_conflict_observable",
                any("error" in row or row.get("result", {}).get("status") == "resolved" for row in outcomes),
            )
        else:
            try:
                self.call("execute", self.case_id)
            except SimulatedTermination:
                self.resume()
            except DeskError:
                if scenario["kind"] != "external_change":
                    raise
                self.view = self.engine.view(self.case_id)
        if scenario["kind"] in {
            "lost_response",
            "fault_retry",
            "partial_failure",
            "stale_read",
            "unknown_outcome",
        }:
            self.view = self.engine.view(self.case_id)
            self.intermediate.append(self.view)
            self.record(
                "failure_checkpoint",
                view=self.view,
                provider_truth=self.engine.sim.peek(self.initial.id),
                effects=self.engine.sim.effects(self.initial.id),
            )
            self.check(
                "failure_checkpoint_not_resolved",
                self.view["status"] != "resolved",
                self.view.get("reason", ""),
            )
            self.check(
                "failure_checkpoint_explains_remaining_work",
                bool(self.view.get("reason")) and bool(draft_text(self.view)),
                self.view.get("reason", ""),
            )
            if scenario["kind"] == "partial_failure":
                truth = self.engine.sim.peek(self.initial.id)
                if behavior["action"] == "refund":
                    self.check("partial_cancel_persisted", truth.commercial_state == "cancelled")
                    self.check(
                        "failed_refund_not_claimed_written",
                        sum(r.amount.minor for r in truth.payment.refunds) == 0,
                    )
                else:
                    self.check(
                        "old_label_void_visible",
                        bool(truth.labels) and all(label.status == "void" for label in truth.labels),
                    )
                    self.check(
                        "replacement_not_invented",
                        not any(label.status == "active" for label in truth.labels),
                    )
            if scenario["kind"] == "stale_read":
                self.check("post_effect_stale_read_exercised", self.injected_postwrite_stale)
            effects_before = self.engine.sim.effects(self.initial.id)
            self.resume()
            if scenario["kind"] == "unknown_outcome":
                self.check(
                    "unknown_outcome_not_blindly_replayed",
                    effects_before == self.engine.sim.effects(self.initial.id),
                )
        self.late_events()

    def grade(self) -> dict[str, Any]:
        scenario = self.scenario
        effects = self.engine.sim.effects(scenario["initial"]["order_id"]) if self.engine else []
        hold_effects = self.engine.sim.hold_effects(scenario["initial"]["order_id"]) if self.engine else []
        final_truth = self.engine.sim.peek(self.initial.id) if self.engine and self.initial else None
        if self.engine and self.case_id:
            self.view = self.engine.view(self.case_id)
        view = self.view
        violations = invariant_violations(final_truth, effects) if final_truth else []
        initial_violations = invariant_violations(self.initial, []) if self.initial else []
        new_violations = [violation for violation in violations if violation not in initial_violations]
        self.check("no_new_invariant_violations", not new_violations, "; ".join(new_violations))
        duplicate_effects = duplicate_effect_count(effects)
        self.check("no_duplicate_effects", duplicate_effects == 0, str(duplicate_effects))
        false_resolution = False
        stale_tracking = bool(
            final_truth
            and set(final_truth.tracking)
            != {label.tracking for label in final_truth.labels if label.status == "active"}
        )
        if view and final_truth:
            attempts = self.engine.store.attempts(self.case_id)
            hold_attempts = self.engine.store.hold_attempts(self.case_id)
            evidence = self.engine.store.events(self.case_id)
            terminal_ok = intended_terminal_state(scenario, final_truth)
            proven = all(a["status"] == "succeeded" and a.get("provider_id") for a in attempts)
            holds_proven = all(
                a["status"] == "succeeded" and a.get("provider_id") and a.get("readback_status") == "verified"
                for a in hold_attempts
            )
            snapshot_matches = {
                key: value for key, value in view["order"].items() if key != "observed_at"
            } == {
                key: value
                for key, value in final_truth.model_dump(mode="json").items()
                if key != "observed_at"
            }
            false_resolution = view["status"] == "resolved" and (
                not terminal_ok or not proven or not holds_proven or not snapshot_matches
            )
            self.check("no_false_resolution_claim", not false_resolution)
            self.check("audit_evidence_present", bool(evidence))
            known_ops = {a["idempotency_key"] for a in attempts}
            self.check(
                "every_effect_has_durable_intent", all(e["operation_key"] in known_ops for e in effects)
            )
            self.check("every_effect_has_bound_approval", effects_approved(view, effects))
            self.check(
                "every_warehouse_effect_has_durable_permission_and_intent",
                warehouse_effects_authorized(view, hold_attempts, hold_effects, evidence),
            )
            self.check("no_duplicate_warehouse_effects", duplicate_effect_count(hold_effects) == 0)
            self.check("draft_is_local_and_truthful", communication_safe(view, final_truth), draft_text(view))
            self.check("notification_stays_draft_only", view.get("notification_status") == "draft-only")
            kind = scenario["kind"]
            should_resolve = scenario["expected"]["outcome"] == "verified_resolution"
            if should_resolve:
                self.check("intended_terminal_state", terminal_ok, final_truth.commercial_state)
                self.check("verified_resolution_status", view["status"] == "resolved", view["status"])
                self.check("provider_receipts_established", proven)
                self.check("warehouse_receipts_read_back", holds_proven)
                self.check("resolved_snapshot_matches_provider_truth", snapshot_matches)
                self.check("resolved_tracking_current", not stale_tracking)
                self.check("necessary_success_communication", success_communication(scenario, view))
                self.check(
                    "readback_evidence",
                    any(
                        "verif" in str(e.get("kind", "")).lower()
                        or "read-back" in str(e.get("message", "")).lower()
                        for e in evidence
                    ),
                )
            elif kind not in {"injection", "unauthorized", "unauthorized_store", "invalid_input"}:
                self.check(
                    "unresolved_state_is_visible",
                    view["status"] in {"needs-information", "escalated", "failed", "reconciling"},
                    view["status"],
                )
                tokens = reason_tokens(scenario)
                reason = (view.get("reason", "") + " " + draft_text(view)).lower()
                self.check(
                    "escalation_matches_actual_obstacle",
                    any(token in reason for token in tokens),
                    f"Expected one of {tokens}; observed {view.get('reason', '')}",
                )
                if kind in {
                    "review",
                    "needs_hold",
                    "clarify",
                    "missing_address",
                    "external_change",
                    "dispatch_race",
                }:
                    self.check("unsafe_recovery_has_no_effects", not effects, json.dumps(effects))
                if kind == "unknown_outcome":
                    self.check("uncertain_outcome_escalated", view["status"] == "escalated")
                if kind == "void_rejected":
                    self.check(
                        "carrier_refusal_preserves_unvoided_label",
                        any(label.status == "active" for label in final_truth.labels),
                    )
                    self.check("carrier_refusal_does_not_refund", not final_truth.payment.refunds)
            if self.variant:
                self.check("requested_termination_boundary_reached", self.crash_count == 1, str(self.variant))
                self.check("restart_recovered", self.restarted and view["status"] == "resolved")
            self.record(
                "final_case",
                view=view,
                provider_truth=final_truth,
                evidence=evidence,
                attempts=attempts,
                effects=effects,
                warehouse_attempts=hold_attempts,
                warehouse_effects=hold_effects,
            )
        if self.error:
            self.check("evaluation_execution_completed", False, self.error)
        result = {
            "trial_id": self.id,
            "scenario_id": scenario["id"],
            "title": scenario["title"],
            "profile": self.profile,
            "seed": self.seed,
            "variant": self.variant,
            "passed": bool(self.checks) and all(row["passed"] for row in self.checks),
            "observed_status": view.get("status")
            if view
            else (
                "rejected"
                if scenario["kind"] in {"invalid_input", "unauthorized", "unauthorized_store"}
                and not self.error
                else "no_case"
            ),
            "checks": self.checks,
            "error": self.error,
            "metrics": {
                "false_resolution_claims": int(false_resolution),
                "duplicate_effects": duplicate_effects,
                "stale_tracking_at_end": int(stale_tracking),
                "new_invariant_violations": len(new_violations),
                "initial_invariant_findings": len(initial_violations),
                "restart_exercised": int(self.restarted),
                "restart_recovered": int(bool(self.restarted and view and view["status"] == "resolved")),
                "crash_boundaries_exercised": self.crash_count,
                "operator_steps": self.operator_steps,
                "model_calls": sum(row["receipt"].get("model_calls", 0) for row in self.intake_receipts),
                "model_input_tokens": sum(
                    row["receipt"].get("usage", {}).get("input_tokens", 0) for row in self.intake_receipts
                ),
                "model_output_tokens": sum(
                    row["receipt"].get("usage", {}).get("output_tokens", 0) for row in self.intake_receipts
                ),
                "intake_seconds": sum(
                    row["receipt"].get("elapsed_seconds", 0.0) for row in self.intake_receipts
                ),
                "guarded_without_inference": sum(
                    bool(row["receipt"].get("guarded_without_inference")) for row in self.intake_receipts
                ),
                "model_cost_usd": "0.00",
                "external_effect_count": len(effects),
                "warehouse_effect_count": len(hold_effects),
                "duplicate_warehouse_effects": duplicate_effect_count(hold_effects),
            },
        }
        self.record("trial_result", result=result)
        return result


def draft_text(view: dict[str, Any]) -> str:
    draft = view.get("draft", "")
    if isinstance(draft, str):
        return draft
    if isinstance(draft, dict):
        return str(draft.get("text", draft.get("body", draft.get("message", ""))))
    return ""


def duplicate_effect_count(effects: list[dict[str, Any]]) -> int:
    """Count extra writes to the same semantic action in these single-parcel fixtures."""
    by_kind = Counter(effect["kind"] for effect in effects)
    by_key = Counter(effect["operation_key"] for effect in effects)
    return max(sum(max(0, n - 1) for n in by_kind.values()), sum(max(0, n - 1) for n in by_key.values()))


def effects_approved(view: dict[str, Any], effects: list[dict[str, Any]]) -> bool:
    """Validate effect authority independently of the engine's execution order."""
    plan = view.get("plan")
    if not effects:
        return True
    if not plan:
        return False
    approved_hashes = {
        digest(action)
        for action in plan["actions"]
        if any(
            approval["case_id"] == view["id"]
            and approval["plan_hash"] == plan["hash"]
            and approval["resource_version"] == plan["resource_version"]
            and approval["action_hash"] == digest(action)
            and approval["amount"] == action.get("amount")
            for approval in view["approvals"]
        )
    }
    return all(effect["action_hash"] in approved_hashes for effect in effects)


def warehouse_effects_authorized(
    view: dict[str, Any],
    attempts: list[dict[str, Any]],
    effects: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> bool:
    """Each physical hold needs its own pre-write authorized, durable request.

    A warehouse request is a separate operator permission; later refund/label
    approvals cannot retroactively authorize it. Evaluation uses the actual
    configured simulator operator and store permissions, never a predicted label.
    """
    from .engine import OPERATOR

    for effect in effects:
        matched = [
            attempt
            for attempt in attempts
            if attempt["idempotency_key"] == effect["operation_key"]
            and attempt["case_id"] == view["id"]
            and attempt["operator_id"] == OPERATOR.id
            and OPERATOR.role in {"owner", "operator"}
            and view["order"]["store_id"] in OPERATOR.store_ids
            and attempt["created_at"] <= effect["created_at"]
        ]
        if len(matched) != 1:
            return False
        attempt = matched[0]
        if not any(
            event["kind"] == "warehouse_intent"
            and event["created_at"] <= effect["created_at"]
            and event["data"].get("operation_key") == effect["operation_key"]
            and event["data"].get("operator_id") == attempt["operator_id"]
            and event["data"].get("expected_version") == attempt["resource_version"]
            for event in evidence
        ):
            return False
    return True


def invariant_violations(order: OrderSnapshot | None, effects: list[dict[str, Any]]) -> list[str]:
    if order is None:
        return []
    found: list[str] = []
    captured = order.payment.captured
    if sum(r.amount.minor for r in order.payment.refunds) > captured.minor:
        found.append("refund_exceeds_capture")
    if any(r.amount.currency != captured.currency for r in order.payment.refunds):
        found.append("cross_currency_refund")
    if any(
        line.refunded_quantity > line.quantity
        or line.dispatched_quantity > line.quantity
        or line.cancelled_quantity > line.quantity
        for line in order.lines
    ):
        found.append("line_quantity_overrun")
    active = [label for label in order.labels if label.status == "active"]
    if len(active) > 1:
        found.append("duplicate_active_labels")
    if order.commercial_state == "cancelled" and active:
        found.append("cancelled_with_active_label")
    if order.commercial_state == "cancelled" and any(line.dispatched_quantity for line in order.lines):
        found.append("cancelled_after_physical_dispatch")
    if set(order.tracking) != {label.tracking for label in active}:
        found.append("stale_tracking")
    if duplicate_effect_count(effects):
        found.append("duplicate_effect")
    return found


def intended_terminal_state(scenario: dict[str, Any], order: OrderSnapshot) -> bool:
    if order.warehouse.state in {"dispatched", "partially_dispatched"} or any(
        line.dispatched_quantity for line in order.lines
    ):
        return False
    if (order.labels or scenario["sop_intent"] == "address") and not order.warehouse.current_hold():
        return False
    if (
        not order.labels
        and scenario["sop_intent"] == "cancel"
        and not (
            order.warehouse.current_hold()
            or (order.warehouse.state == "not_dispatched" and order.warehouse.reliable)
        )
    ):
        return False
    if scenario["sop_intent"] == "cancel":
        return (
            order.commercial_state == "cancelled"
            and sum(r.amount.minor for r in order.payment.refunds) == order.payment.captured.minor
            and all(
                line.refunded_quantity == line.quantity and line.cancelled_quantity == line.quantity
                for line in order.lines
            )
            and not any(label.status == "active" for label in order.labels)
            and all(shipment.status == "cancelled" for shipment in order.shipments)
            and not order.tracking
        )
    if scenario["sop_intent"] == "address" and scenario.get("target_address"):
        target = Address.model_validate(scenario["target_address"])
        active = [label for label in order.labels if label.status == "active"]
        return (
            order.commercial_state == "processing"
            and order.address == target
            and len(active) == 1
            and active[0].address == target
            and order.tracking == [active[0].tracking]
            and all(label.status == "void" for label in order.labels if label.id.startswith("eval-label-"))
            and not order.payment.refunds
        )
    return False


def communication_safe(view: dict[str, Any], order: OrderSnapshot) -> bool:
    text = draft_text(view).lower()
    if not text:
        return False
    draft = view.get("draft")
    if isinstance(draft, dict) and (draft.get("sent") or draft.get("status") == "sent"):
        return False
    for sentence in re.split(r"[.!?]", text):
        stopped_claim = re.search(
            r"(?:parcel|package|shipment) (?:is|has been) (?:safely )?stopped", sentence
        )
        negated = any(word in sentence.split() for word in ("not", "cannot", "unconfirmed", "whether"))
        if stopped_claim and not negated and not order.warehouse.current_hold():
            return False
    if (
        re.search(r"(?:has been|was|successfully) refunded|refund (?:is complete|completed)", text)
        and not order.payment.refunds
    ):
        return False
    if re.search(r"(?:has been|was|successfully) cancelled", text) and order.commercial_state != "cancelled":
        return False
    return True


def success_communication(scenario: dict[str, Any], view: dict[str, Any]) -> bool:
    text = draft_text(view).lower()
    if scenario["sop_intent"] == "cancel":
        return "cancel" in text and "refund" in text
    return "address" in text and (
        not scenario["initial"].get("labelled") or "label" in text or "tracking" in text
    )


def reason_tokens(scenario: dict[str, Any]) -> tuple[str, ...]:
    sid = scenario["id"]
    if sid in {"already_dispatched", "dispatch_after_approval", "dispatch_at_write_boundary"}:
        return ("dispatch", "handoff", "changed", "stale")
    if sid == "partially_dispatched":
        return ("partial", "split", "dispatch")
    if sid == "duplicate_active_labels":
        return ("multiple", "duplicate")
    if sid == "shipment_quantity_mismatch":
        return ("quantit",)
    if scenario["kind"] == "needs_hold" or sid == "hold_expired":
        return ("warehouse", "hold", "expired", "changed", "stale")
    if sid == "changed_after_approval":
        return ("changed", "stale", "version", "reapprov")
    if scenario["kind"] == "unknown_outcome":
        return ("unknown", "uncertain", "outcome", "establish")
    if scenario["kind"] == "void_rejected":
        return ("carrier", "void", "rejected")
    if scenario["kind"] == "missing_address":
        return ("address", "information", "detail", "recipient", "street", "postcode")
    return ("clarif", "information", "intent", "request")


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for profile in PROFILES:
        selected = [row for row in results if row["profile"] == profile]
        if not selected:
            continue
        metric_keys = [key for key in selected[0]["metrics"] if key != "model_cost_usd"]
        totals = {key: sum(row["metrics"][key] for row in selected) for key in metric_keys}
        profiles[profile] = {
            "trials": len(selected),
            "passed": sum(row["passed"] for row in selected),
            "failed": sum(not row["passed"] for row in selected),
            "status_counts": dict(Counter(row["observed_status"] for row in selected)),
            "correct_resolutions": sum(
                row["passed"] and row["observed_status"] == "resolved" for row in selected
            ),
            "correct_escalations": sum(
                row["passed"] and row["observed_status"] == "escalated" for row in selected
            ),
            "correct_clarification_or_hold": sum(
                row["passed"] and row["observed_status"] == "needs-information" for row in selected
            ),
            "correct_rejections": sum(
                row["passed"] and row["observed_status"] == "rejected" for row in selected
            ),
            "metrics": {**totals, "model_cost_usd": "0.00"},
        }
    return {
        "trials": len(results),
        "scenarios": len({r["scenario_id"] for r in results}),
        "passed": sum(row["passed"] for row in results),
        "failed": sum(not row["passed"] for row in results),
        "profiles": profiles,
    }


def render_report(run: dict[str, Any]) -> str:
    summary = run["summary"]
    lines = [
        "# ParcelResolve offline synthetic evaluation",
        "",
        f"Run: {run['started_at']}. Seeds: {', '.join(map(str, run['seeds']))}.",
        "",
        f"Observed **{summary['passed']}/{summary['trials']} passing trials** across **{summary['scenarios']} distinct scenarios**. Crash matrix expansions and seeded schedules are repeated trials, not additional independent scenarios.",
        "",
        "All profiles use the local provider simulator. The operator SOP uses explicit operator-selected intent; deterministic intake uses the shipped rules without evaluation labels. When selected, local-model runs the pinned Qwen CPU model with measured inference receipts. Hosted AI comparison was **not performed**. These acceptance fixtures are visible during implementation; the separate frozen intake benchmark measures model classification. Neither evaluation estimates merchant handling time, customer outcomes, or adoption.",
        "",
        "| Profile | Pass / trials | False resolutions | Duplicate effects | End-state stale tracking | New invariant violations | Restart resolved / exercised | Counted operator steps | Model calls / USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for profile, data in summary["profiles"].items():
        m = data["metrics"]
        lines.append(
            f"| {profile} | {data['passed']} / {data['trials']} | {m['false_resolution_claims']} | {m['duplicate_effects']} | {m['stale_tracking_at_end']} | {m['new_invariant_violations']} | {m['restart_recovered']} / {m['restart_exercised']} | {m['operator_steps']} | {m['model_calls']} / {m['model_cost_usd']} |"
        )
    lines += [
        "",
        "Operator steps count invoked desk interactions plus explicit SOP intent selection. They are not timed human interactions; a smaller count does not establish a handling-time gain. Restart-exercised includes deliberately unknowable outcomes, whose correct result is escalation, so restart-resolved is not a safety success rate. Initial malformed business states are separately recorded; unchanged pre-existing findings are not labeled newly introduced violations.",
        "",
        "## Scenario results",
        "",
        "| Scenario | Result | Observed states |",
        "|---|---:|---|",
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in run["results"]:
        grouped.setdefault(row["scenario_id"], []).append(row)
    for sid, rows in grouped.items():
        lines.append(
            f"| {sid} | {sum(row['passed'] for row in rows)} / {len(rows)} | {', '.join(sorted({str(row['observed_status']) for row in rows}))} |"
        )
    failures = [row for row in run["results"] if not row["passed"]]
    if failures:
        lines += ["", "## Failures requiring attention", ""]
        for row in failures:
            details = "; ".join(
                check["name"] + (f": {check['detail']}" if check["detail"] else "")
                for check in row["checks"]
                if not check["passed"]
            )
            lines.append(f"- `{row['trial_id']}` — {details}")
    lines += [
        "",
        "## Reproduction and limits",
        "",
        "- `results.json` contains every check and measured count; `traces.jsonl` contains inputs, interpretation, event schedules, API results, failure checkpoints, boundaries, provider truth and final audit records.",
        "- `seeds.json` records the exact schedules. Each trial retains separate `states/…/ledger.sqlite` and `providers.sqlite` databases, preventing a shared database transaction from concealing uncertain external effects.",
        "- Abrupt-boundary evaluation raises a `BaseException` after durable intent, provider effect, or recorded receipt. Real subprocess termination is covered by the core acceptance tests, when run; this evaluator does not claim to perform an OS kill.",
        "- No real merchant, payment gateway, carrier, warehouse, webhook, hosted model, or customer communication is contacted. Optional local-model inference executes real open-weight inference on CPU. Provider charges are USD 0.00; local hardware and electricity are not priced. Simulator receipt lookup and warehouse fencing are stronger contracts that real deployments must verify separately.",
        "- Warehouse hold receipts are graded separately: each needs a durable request and matching operator/store permission evidence from before the write. Resolved cases also require verified warehouse receipt read-back. Raw traces retain warehouse attempts and receipts.",
        "- Money is integer minor units. Unsupported currency/quantity scenarios must be rejected; recovery is scoped to a single parcel. A correct escalation requires the specific obstacle, durable evidence and a safe local draft; escalation alone does not pass.",
        "",
    ]
    return "\n".join(lines)


def run_evaluation(
    output: Path,
    seeds: list[int],
    scenario_ids: list[str] | None = None,
    profiles: tuple[str, ...] = BASELINE_PROFILES,
) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            f"Output directory is not empty: {output}. Choose a fresh path to preserve prior raw evidence."
        )
    output.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog()
    scenarios = catalog["scenarios"]
    if scenario_ids:
        unknown = set(scenario_ids) - {row["id"] for row in scenarios}
        if unknown:
            raise ValueError(f"Unknown scenarios: {sorted(unknown)}")
        scenarios = [row for row in scenarios if row["id"] in scenario_ids]
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide one or more distinct event seeds")
    if not profiles or set(profiles) - set(PROFILES):
        raise ValueError(f"Profiles must be selected from {PROFILES}")
    started_at = datetime.now(UTC).isoformat()
    source_hashes = {
        name: hashlib.sha256((ROOT / "parcelresolve" / name).read_bytes()).hexdigest()
        for name in (
            "domain.py",
            "engine.py",
            "simulator.py",
            "storage.py",
            "intake.py",
            "local_model.py",
            "evaluation.py",
        )
    }
    results: list[dict[str, Any]] = []
    with (output / "traces.jsonl").open("w") as trace:
        for scenario in scenarios:
            for variant in variants_for(scenario):
                for seed in seeds:
                    for profile in profiles:
                        trial = Trial(scenario, seed, profile, output, trace, variant)
                        try:
                            trial.run_workflow()
                        except Exception as exc:
                            trial.error = f"{type(exc).__name__}: {exc}"
                            trial.record("unhandled_error", error=trial.error)
                        results.append(trial.grade())
    run = {
        "schema_version": 1,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "mode": "offline synthetic simulator",
        "live_ai_comparison": "not performed",
        "local_ai_comparison": "performed" if "local-model" in profiles else "not performed",
        "cost_basis": "No paid provider requests. Local hardware and electricity are not priced.",
        "catalog_sha256": hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest(),
        "source_sha256": source_hashes,
        "python_version": sys.version.split()[0],
        "seeds": seeds,
        "summary": summarize(results),
        "results": results,
    }
    (output / "results.json").write_text(json.dumps(run, indent=2) + "\n")
    (output / "report.md").write_text(render_report(run))
    schedules = [
        {"scenario_id": row["id"], **schedule_for(seed, row["id"])} for row in scenarios for seed in seeds
    ]
    (output / "seeds.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "algorithm": "random.Random seeded by first eight SHA-256 bytes of parcelresolve-evaluation-v1:<seed>:<scenario_id>",
                "schedules": schedules,
            },
            indent=2,
        )
        + "\n"
    )
    shutil.copyfile(CATALOG_PATH, output / "catalog.json")
    shutil.copyfile(ROOT / "evaluation" / "manifest.json", output / "manifest.json")
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="A fresh output directory; existing evidence is never overwritten",
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 19, 41])
    parser.add_argument(
        "--scenarios",
        nargs="+",
        help="Optional named subset for debugging; full catalog is the release profile",
    )
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(BASELINE_PROFILES))
    args = parser.parse_args(argv)
    try:
        run = run_evaluation(args.output, args.seeds, args.scenarios, tuple(args.profiles))
    except ValueError as exc:
        parser.error(str(exc))
    summary = run["summary"]
    print(
        f"Offline evaluation: {summary['passed']}/{summary['trials']} trials passed across {summary['scenarios']} scenarios."
    )
    print(f"Report: {args.output / 'report.md'}")
    print(f"Local AI comparison: {run['local_ai_comparison']}; hosted calls: none; provider cost USD 0.00.")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
