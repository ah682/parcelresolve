"""Policy-owned, persisted recovery state machine. A model can never execute an action."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .domain import (
    TRANSITIONS,
    ActionKind,
    Address,
    Approval,
    CustomerRequest,
    DeskError,
    Money,
    OperationAttempt,
    Operator,
    OrderSnapshot,
    Plan,
    PreconditionFailed,
    ProposedAction,
    ProviderFailure,
    RecoveryCase,
    Status,
    WarehouseHoldAttempt,
    digest,
    disagreements,
    now,
)
from .simulator import (
    LocalCommerceAdapter,
    LocalPaymentAdapter,
    LocalShippingAdapter,
    LocalWarehouseAdapter,
    Simulator,
)
from .storage import Storage

OPERATOR = Operator(id="operator-ava", name="Alex Morgan", role="operator", store_ids=["store-1"])
VIEWER = Operator(id="viewer-demo", name="Demo viewer", role="viewer", store_ids=["store-1"])


class Engine:
    def __init__(self, directory: Path, *, crash_hook: Callable[[str, ProposedAction], None] | None = None):
        self.store = Storage(directory)
        self.sim = Simulator(directory)
        self.commerce = LocalCommerceAdapter(self.sim)
        self.payments = LocalPaymentAdapter(self.sim)
        self.shipping = LocalShippingAdapter(self.sim)
        self.warehouse = LocalWarehouseAdapter(self.sim)
        self.crash_hook = crash_hook

    def _authorize(self, operator: Operator, store_id: str, *, write: bool = False) -> None:
        if store_id not in operator.store_ids:
            raise DeskError("Resource not found", 404)
        if write and operator.role not in {"operator", "owner"}:
            raise DeskError("Your role cannot modify recovery cases", 403)

    def _case(self, case_id: str, operator: Operator, *, write: bool = False) -> RecoveryCase:
        case = self.store.get_case(case_id)
        self._authorize(operator, case.store_id, write=write)
        return case

    def _transition(self, case: RecoveryCase, status: Status, reason: str) -> None:
        if status != case.status and status not in TRANSITIONS[case.status]:
            raise DeskError(f"Cannot transition from {case.status} to {status}")
        previous = case.status
        case.status = status
        case.reason = reason
        self.store.save_case(case, message=reason, data={"from": previous, "to": status})

    def _fresh(self, snapshot: OrderSnapshot) -> bool:
        try:
            age = (datetime.now(UTC) - datetime.fromisoformat(snapshot.observed_at)).total_seconds()
            return 0 <= age <= 30
        except (TypeError, ValueError):
            return False

    def create_case(
        self,
        order_id: str,
        text: str,
        intent: str | None = "cancel",
        target_address: Address | dict[str, Any] | None = None,
        operator: Operator = OPERATOR,
        *,
        interpreter_mode: str = "deterministic",
    ) -> dict[str, Any]:
        snapshot = self.sim.peek(order_id)
        self._authorize(operator, snapshot.store_id, write=True)
        with self.store.order_lock(order_id):
            if any(c["order_id"] == order_id and c["status"] != "resolved" for c in self.store.list_cases()):
                raise DeskError("This order already has an open recovery case. Continue that case.")
            intake_receipt: dict[str, Any] = {}
            if intent is None:
                from .intake import interpret_request_with_receipt

                interpreted, full_receipt = interpret_request_with_receipt(text, mode=interpreter_mode)
                intent = "unknown" if interpreted.needs_clarification else interpreted.intent
                interpreter_mode = interpreted.mode
                # Persist bounded provenance and measured usage; runtime logs/raw model output
                # belong in opt-in evaluation artifacts, not the operator's normal timeline.
                receipt_fields = {
                    "requested_mode",
                    "effective_mode",
                    "model_calls",
                    "model",
                    "model_revision",
                    "model_sha256",
                    "runtime",
                    "runtime_commit",
                    "device",
                    "threads",
                    "seed",
                    "temperature",
                    "provider_cost_usd",
                    "usage",
                    "elapsed_seconds",
                    "prompt_sha256",
                }
                intake_receipt = {key: value for key, value in full_receipt.items() if key in receipt_fields}
            else:
                interpreter_mode = "operator-selected"
            request = CustomerRequest.model_validate(
                {"text": text, "intent": intent, "target_address": target_address}
            )
            case = RecoveryCase(
                id="case-" + uuid4().hex[:10],
                order_id=order_id,
                store_id=snapshot.store_id,
                request=request,
                snapshot=snapshot,
                interpreter_mode=interpreter_mode,
            )
            self.store.save_case(
                case,
                message="Customer request received in trusted order context. No external action taken.",
                kind="intake",
                data={
                    "operator_id": operator.id,
                    "interpreter_mode": interpreter_mode,
                    "interpretation": intake_receipt,
                },
            )
        return self.view(case.id, operator)

    def investigate(self, case_id: str, operator: Operator = OPERATOR) -> dict[str, Any]:
        case = self._case(case_id, operator, write=True)
        with self.store.order_lock(case.order_id):
            case = self._case(case_id, operator, write=True)
            if case.status == "resolved":
                return self.view(case_id, operator)
            if self._pending_hold(case_id):
                raise DeskError("Reconcile the persisted warehouse request before preparing a recovery plan.")
            if any(a["status"] in {"succeeded", "intent", "uncertain"} for a in self.store.attempts(case_id)):
                raise DeskError(
                    "This case has persisted operations. Reconcile the existing plan; do not replace it."
                )
            self._transition(
                case, "investigating", "Reading order, payment, labels, shipments and warehouse evidence."
            )
            try:
                snapshot = self.sim.read(case.order_id)
            except ProviderFailure as exc:
                self._transition(case, "needs-information", str(exc))
                return self.view(case_id, operator)
            case.snapshot = snapshot
            self._record_snapshot(case, snapshot)
            if not self._fresh(snapshot):
                self._transition(
                    case,
                    "needs-information",
                    "Provider returned a stale snapshot. Refresh current evidence before planning.",
                )
            elif case.request.intent == "unknown":
                self._transition(
                    case,
                    "needs-information",
                    "Request is ambiguous. Confirm cancellation or supply a complete domestic address through operator intake.",
                )
            else:
                self._propose(case)
        return self.view(case_id, operator)

    def _record_snapshot(self, case: RecoveryCase, snapshot: OrderSnapshot) -> None:
        self.store.save_case(case)
        observations: list[tuple[str, dict[str, Any], str]] = [
            (
                "WooCommerce · simulator",
                {
                    "order_id": snapshot.woo_id,
                    "version": snapshot.version,
                    "commercial_state": snapshot.commercial_state,
                    "tracking": snapshot.tracking,
                },
                f"Order #{snapshot.id}: {snapshot.commercial_state}; resource version {snapshot.version}.",
            ),
            (
                "Payments · simulator",
                {
                    "captured": snapshot.payment.captured.model_dump(),
                    "refunds": [r.model_dump() for r in snapshot.payment.refunds],
                },
                f"Captured {self._money(snapshot.payment.captured)}; {len(snapshot.payment.refunds)} refund record(s).",
            ),
            (
                "ShipStation · simulator",
                {
                    "order_key": snapshot.shipstation_order_key,
                    "shipments": [s.model_dump() for s in snapshot.shipments],
                    "labels": [item.model_dump() for item in snapshot.labels],
                },
                f"{sum(item.status == 'active' for item in snapshot.labels)} active label(s). Label status does not establish physical dispatch.",
            ),
            (
                "Warehouse · simulator",
                snapshot.warehouse.model_dump(),
                f"Warehouse evidence: {snapshot.warehouse.state.replace('_', ' ')}.",
            ),
        ]
        for source, data, message in observations:
            self.store.event(case.id, source, "observation", message, data)

    def _propose(self, case: RecoveryCase) -> None:
        order = case.snapshot
        issues = disagreements(order)
        blocked = {
            "identity_mismatch",
            "quantity_mismatch",
            "refund_quantity_mismatch",
            "duplicate_active_labels",
            "split_shipment",
            "partial_dispatch",
        }
        if any(i["code"] in blocked for i in issues):
            messages = " ".join(i["message"] for i in issues if i["code"] in blocked)
            self._transition(
                case,
                "escalated",
                messages
                + " Review parcel and line evidence with the warehouse; no automated whole-order recovery.",
            )
            return
        if order.warehouse.state in {"dispatched", "partially_dispatched"} or any(
            item.dispatched_quantity for item in order.lines
        ):
            self._transition(
                case,
                "escalated",
                "Physical dispatch is confirmed. Contact the warehouse and customer; this desk cannot intercept a parcel.",
            )
            return
        if order.commercial_state == "completed":
            self._transition(
                case, "escalated", "Completed commercial state requires operator review before recovery."
            )
            return
        refunded = sum(r.amount.minor for r in order.payment.refunds)
        returned_quantity = sum(line.refunded_quantity for line in order.lines)
        if 0 < refunded < order.payment.captured.minor or 0 < returned_quantity < sum(
            line.quantity for line in order.lines
        ):
            self._transition(
                case,
                "escalated",
                "A partial refund exists. Review refund quantities and remaining shipment allocation manually.",
            )
            return
        if case.request.intent == "address":
            address = case.request.target_address
            if address is None:
                self._transition(
                    case,
                    "needs-information",
                    "A complete recipient name, street, city, postcode and country are required.",
                )
                return
            if address.country != order.address.country:
                self._transition(
                    case,
                    "escalated",
                    "Cross-border address changes are outside this release. Review tax and carrier implications manually.",
                )
                return
            if (
                order.commercial_state != "processing"
                or order.payment.refunds
                or any(line.refunded_quantity or line.cancelled_quantity for line in order.lines)
            ):
                self._transition(
                    case, "escalated", "A cancelled or refunded order cannot receive a replacement label."
                )
                return
        if (order.labels or case.request.intent == "address") and not order.warehouse.current_hold():
            self._transition(
                case,
                "needs-information",
                "Label recovery — awaiting a current, positively acknowledged warehouse hold. Missing dispatch data is not a safe stop.",
            )
            return
        if not order.labels and not order.warehouse.prelabel_safe():
            self._transition(
                case,
                "needs-information",
                "Current warehouse evidence is missing. Confirm a reliable hold before planning.",
            )
            return
        if self.terminal_verified(case, order):
            self._transition(
                case,
                "resolved",
                "Read-back verified the requested terminal state; no additional actions are necessary.",
            )
            return
        actions: list[ProposedAction] = []
        plan_id = "plan-" + uuid4().hex[:12]

        def add(kind: ActionKind, title: str, **kwargs: Any) -> None:
            actions.append(
                ProposedAction(id=f"{plan_id}-{len(actions) + 1}", kind=kind, title=title, **kwargs)
            )

        for label in order.labels:
            if label.status == "active":
                add(ActionKind.VOID, f"Void label {label.id}", label_id=label.id)
        if case.request.intent == "cancel":
            if (
                order.commercial_state != "cancelled"
                or any(s.status != "cancelled" for s in order.shipments)
                or any(item.cancelled_quantity != item.quantity for item in order.lines)
                or order.tracking
            ):
                add(ActionKind.CANCEL, "Cancel the order and its shipment allocation")
            remaining = order.payment.captured.minor - refunded
            if remaining > 0:
                amount = Money(minor=remaining, currency=order.payment.captured.currency)
                add(ActionKind.REFUND, f"Refund {self._money(amount)} to the original payment", amount=amount)
        else:
            add(ActionKind.ADDRESS, "Update the shipping address", address=case.request.target_address)
            add(
                ActionKind.CREATE_LABEL,
                "Create and verify a replacement label",
                address=case.request.target_address,
            )
        plan = Plan(
            id=plan_id,
            hash="",
            resource_version=order.version,
            actions=actions,
            hold_ack_id=order.warehouse.ack_id,
        )
        plan.hash = plan.calculated_hash()
        case.plan = plan
        self._transition(
            case, "proposal-ready", "Recovery plan prepared from verified resource identities and quantities."
        )
        self._transition(
            case,
            "awaiting-approval",
            "Review the exact actions and amounts. Explicit approval is required before execution.",
        )

    def _pending_hold(self, case_id: str) -> WarehouseHoldAttempt | None:
        for raw in reversed(self.store.hold_attempts(case_id)):
            attempt = WarehouseHoldAttempt.model_validate(raw)
            if (
                attempt.status in {"intent", "uncertain"}
                or (attempt.status == "succeeded" and attempt.readback_status == "pending")
                or (attempt.status == "failed" and attempt.retryable)
            ):
                return attempt
        return None

    def hold(self, case_id: str, operator: Operator = OPERATOR) -> dict[str, Any]:
        """Prepare a physical hold with durable permission, intent, receipt and read-back."""
        case = self._case(case_id, operator, write=True)
        with self.store.order_lock(case.order_id):
            case = self._case(case_id, operator, write=True)
            if (
                any(a["status"] in {"succeeded", "intent", "uncertain"} for a in self.store.attempts(case_id))
                or case.status == "resolved"
            ):
                raise DeskError(
                    "A warehouse acknowledgment cannot replace the hold bound to existing operations. Escalate to the operator."
                )
            attempt = self._pending_hold(case_id)
            self._transition(
                case, "investigating", "Checking warehouse evidence and any persisted hold request."
            )
            case.plan = None
            self.store.save_case(case)
            if attempt and attempt.status in {"intent", "uncertain"}:
                receipt = self.warehouse.query_hold(attempt.idempotency_key)
                self.store.event(
                    case_id,
                    "warehouse receipt query",
                    "warehouse_reconciliation",
                    "Queried the existing hold request before considering another write.",
                    {"operation_key": attempt.idempotency_key, "outcome": receipt["status"]},
                )
                if receipt["status"] == "unknown":
                    attempt.status = "uncertain"
                    attempt.error = "Warehouse request outcome cannot be established. Contact the warehouse; do not repeat the request."
                    self.store.save_hold_attempt(attempt)
                    self._transition(case, "escalated", attempt.error)
                    return self.view(case_id, operator)
                if receipt["status"] == "succeeded":
                    attempt.status = "succeeded"
                    attempt.provider_id = receipt["provider_id"]
                    attempt.result_version = receipt["result_version"]
                    attempt.error = None
                else:
                    attempt.status = "failed"
                    attempt.retryable = True
                    attempt.error = "Warehouse established that the request was not written."
                self.store.save_hold_attempt(attempt)
            try:
                snapshot = self.sim.read(case.order_id)
            except ProviderFailure as exc:
                self._transition(case, "needs-information", str(exc))
                return self.view(case_id, operator)
            case.snapshot = snapshot
            if not self._fresh(snapshot):
                self._transition(
                    case,
                    "needs-information",
                    "Fresh warehouse evidence is unavailable; no new hold was requested.",
                )
                return self.view(case_id, operator)
            if attempt is None:
                attempt_id = str(uuid4())
                attempt = WarehouseHoldAttempt(
                    id=attempt_id,
                    case_id=case_id,
                    action_id="hold-" + attempt_id,
                    idempotency_key=digest({"case": case_id, "hold_request": attempt_id}),
                    resource_version=snapshot.version,
                    operator_id=operator.id,
                )
            if attempt.status != "succeeded":
                if snapshot.version != attempt.resource_version:
                    attempt.status = "failed"
                    attempt.retryable = False
                    attempt.error = "State changed before a proven unwritten hold could be retried. Review current evidence and request a new hold."
                    self.store.save_hold_attempt(attempt)
                    self._transition(case, "needs-information", attempt.error)
                    return self.view(case_id, operator)
                action = ProposedAction(
                    id=attempt.action_id, kind=ActionKind.HOLD, title="Request warehouse stop/hold"
                )
                attempt.status = "intent"
                attempt.error = None
                self.store.save_hold_attempt(attempt)
                self.store.event(
                    case_id,
                    "recovery desk",
                    "warehouse_intent",
                    "Authenticated operator requested a warehouse hold; confirmation is pending.",
                    {
                        "operator_id": attempt.operator_id,
                        "operation_key": attempt.idempotency_key,
                        "expected_version": attempt.resource_version,
                    },
                )
                self._boundary("after_intent", action)
                try:
                    receipt = self.warehouse.perform_hold(
                        case.order_id,
                        idempotency_key=attempt.idempotency_key,
                        expected_version=attempt.resource_version,
                    )
                    self._boundary("after_effect", action)
                except ProviderFailure as exc:
                    attempt.status = "uncertain" if exc.uncertain else "failed"
                    attempt.retryable = exc.retryable
                    attempt.error = str(exc)
                    self.store.save_hold_attempt(attempt)
                    if isinstance(exc, PreconditionFailed):
                        case.snapshot = self.sim.peek(case.order_id)
                    self._transition(
                        case,
                        "escalated" if isinstance(exc, PreconditionFailed) else "needs-information",
                        str(exc),
                    )
                    return self.view(case_id, operator)
                attempt.status = "succeeded"
                attempt.provider_id = receipt["provider_id"]
                attempt.result_version = receipt["result_version"]
                attempt.retryable = False
                self.store.save_hold_attempt(attempt)
                self.store.event(
                    case_id,
                    "warehouse provider receipt",
                    "warehouse_result",
                    "Warehouse receipt recorded; fresh read-back is still required.",
                    receipt,
                )
                self._boundary("after_record", action)
                try:
                    snapshot = self.sim.read(case.order_id)
                except ProviderFailure as exc:
                    self._transition(case, "needs-information", str(exc))
                    return self.view(case_id, operator)
                case.snapshot = snapshot
            if not self._fresh(snapshot):
                self._transition(
                    case,
                    "needs-information",
                    "Warehouse receipt exists, but read-back is stale. Reconcile before planning.",
                )
                return self.view(case_id, operator)
            if (
                snapshot.version != attempt.result_version
                or snapshot.warehouse.ack_id != attempt.provider_id
                or not snapshot.warehouse.current_hold()
                or any(line.dispatched_quantity for line in snapshot.lines)
            ):
                attempt.readback_status = "failed"
                attempt.error = "The warehouse receipt no longer proves a current hold. Contact the warehouse and review current physical state."
                self.store.save_hold_attempt(attempt)
                self._transition(case, "escalated", attempt.error)
                return self.view(case_id, operator)
            attempt.readback_status = "verified"
            attempt.verified_at = now()
            self.store.save_hold_attempt(attempt)
            self.store.save_case(
                case,
                message="Fresh read-back verified the simulated warehouse's five-minute stop/hold.",
                kind="warehouse_hold",
                data={**snapshot.warehouse.model_dump(), "operation_key": attempt.idempotency_key},
            )
        return self.investigate(case_id, operator)

    def clarify(
        self, case_id: str, intent: str, target_address: Address | None = None, operator: Operator = OPERATOR
    ) -> dict[str, Any]:
        case = self._case(case_id, operator, write=True)
        with self.store.order_lock(case.order_id):
            case = self._case(case_id, operator, write=True)
            if (
                case.status
                not in {
                    "received",
                    "needs-information",
                    "awaiting-approval",
                    "escalated",
                }
                or self._pending_hold(case_id)
                or any(
                    a["status"] in {"succeeded", "intent", "uncertain"} for a in self.store.attempts(case_id)
                )
            ):
                raise DeskError(
                    "A request with persisted operations cannot be changed; reconcile its existing plan."
                )
            case.request = CustomerRequest.model_validate(
                {"text": case.request.text, "intent": intent, "target_address": target_address}
            )
            case.plan = None
            case.interpreter_mode = "operator-clarified"
            self.store.save_case(
                case,
                message="Operator clarified the request. All prior plan approvals are invalid for this request.",
                kind="clarification",
                data={"operator_id": operator.id},
            )
        return self.investigate(case_id, operator)

    def _approved(self, case: RecoveryCase) -> bool:
        plan = case.plan
        if not plan or plan.hash != plan.calculated_hash():
            return False
        approvals = self.store.approvals(case.id)
        return all(
            any(
                a["plan_hash"] == plan.hash
                and a["resource_version"] == plan.resource_version
                and a["action_hash"] == digest(action)
                and a["amount"] == (action.amount.model_dump() if action.amount else None)
                for a in approvals
            )
            for action in plan.actions
        )

    def approve(
        self, case_id: str, plan_hash: str, resource_version: int, operator: Operator = OPERATOR
    ) -> dict[str, Any]:
        case = self._case(case_id, operator, write=True)
        with self.store.order_lock(case.order_id):
            case = self._case(case_id, operator, write=True)
            plan = case.plan
            if (
                case.status != "awaiting-approval"
                or not plan
                or plan.hash != plan_hash
                or plan.resource_version != resource_version
                or plan.hash != plan.calculated_hash()
            ):
                raise DeskError("This approval does not match the current plan. Refresh and review it.")
            snapshot = self.sim.read(case.order_id)
            case.snapshot = snapshot
            if (
                snapshot.version != resource_version
                or not self._fresh(snapshot)
                or (not snapshot.labels and not snapshot.warehouse.prelabel_safe())
                or (
                    (snapshot.labels or case.request.intent == "address")
                    and (
                        not snapshot.warehouse.current_hold() or snapshot.warehouse.ack_id != plan.hold_ack_id
                    )
                )
            ):
                self._transition(
                    case,
                    "needs-information",
                    "State or warehouse hold changed before approval. Re-investigate and approve the new plan.",
                )
                return self.view(case_id, operator)
            if not self._approved(case):
                self.store.save_approvals(
                    [
                        Approval(
                            id=str(uuid4()),
                            case_id=case.id,
                            plan_hash=plan.hash,
                            action_hash=digest(action),
                            resource_version=resource_version,
                            operator_id=operator.id,
                            amount=action.amount,
                        )
                        for action in plan.actions
                    ]
                )
            self.store.save_case(
                case,
                message="Operator approved the exact plan, actions, resource version and refund amount.",
                kind="approval",
                data={
                    "operator_id": operator.id,
                    "plan_hash": plan.hash,
                    "resource_version": resource_version,
                },
            )
            case.reason = (
                "Approved. Execution will recheck resource state and warehouse evidence at every action."
            )
            self.store.save_case(case)
        return self.view(case_id, operator)

    def _boundary(self, boundary: str, action: ProposedAction) -> None:
        if self.crash_hook:
            self.crash_hook(boundary, action)

    def execute(self, case_id: str, operator: Operator = OPERATOR) -> dict[str, Any]:
        return self._run(case_id, operator, resume=False)

    def retry(self, case_id: str, operator: Operator = OPERATOR) -> dict[str, Any]:
        self._case(case_id, operator, write=True)
        if self._pending_hold(case_id):
            return self.hold(case_id, operator)
        return self._run(case_id, operator, resume=True)

    def _run(self, case_id: str, operator: Operator, *, resume: bool) -> dict[str, Any]:
        case = self._case(case_id, operator, write=True)
        with self.store.order_lock(case.order_id):
            case = self._case(case_id, operator, write=True)
            if case.status == "resolved":
                return self.view(case_id, operator)
            allowed = (
                {"failed", "reconciling", "executing", "awaiting-approval"}
                if resume
                else {"awaiting-approval"}
            )
            if case.status not in allowed or not self._approved(case):
                raise DeskError(
                    "Current action-bound approval is required; reconcile only an existing approved plan."
                )
            assert case.plan is not None
            plan = case.plan
            if case.status in {"failed", "executing"}:
                self._transition(
                    case, "reconciling", "Checking persisted operation outcomes before any further writes."
                )
            attempts = {
                a["action_id"]: OperationAttempt.model_validate(a) for a in self.store.attempts(case_id)
            }
            for action in plan.actions:
                attempt = attempts.get(action.id)
                if attempt and attempt.status in {"intent", "uncertain"}:
                    receipt = self.sim.query_effect(attempt.idempotency_key)
                    self.store.event(
                        case_id,
                        "provider receipt query",
                        "reconciliation",
                        "Queried operation identity before considering a retry.",
                        {"action_id": action.id, "outcome": receipt["status"]},
                    )
                    if receipt["status"] == "unknown":
                        self._transition(
                            case,
                            "escalated",
                            "The external write outcome cannot be established. Do not retry; reconcile the provider record manually.",
                        )
                        return self.view(case_id, operator)
                    if receipt["status"] == "succeeded":
                        attempt.status = "succeeded"
                        attempt.provider_id = receipt["provider_id"]
                        attempt.result_version = receipt["result_version"]
                        attempt.error = None
                    else:
                        attempt.status = "failed"
                        attempt.retryable = True
                        attempt.error = "Provider established that the operation was not written."
                    self.store.save_attempt(attempt)
            try:
                snapshot = self.sim.read(case.order_id)
            except ProviderFailure as exc:
                if case.status == "awaiting-approval":
                    self._transition(case, "executing", "Approved execution started.")
                self._transition(case, "reconciling", str(exc))
                return self.view(case_id, operator)
            case.snapshot = snapshot
            expected = plan.resource_version
            for action in plan.actions:
                attempt = attempts.get(action.id)
                if attempt and attempt.status == "succeeded":
                    assert attempt.result_version is not None
                    expected = attempt.result_version
            completed = any(a.status == "succeeded" for a in attempts.values())
            if not self._fresh(snapshot) or snapshot.version != expected:
                status: Status = (
                    "escalated"
                    if completed or snapshot.warehouse.state in {"dispatched", "partially_dispatched"}
                    else "needs-information"
                )
                self._transition(
                    case,
                    status,
                    "Approved state is stale or changed outside the desk. Recovery is incomplete; review current evidence and request a new approval where safe.",
                )
                return self.view(case_id, operator)
            if (
                snapshot.warehouse.state in {"dispatched", "partially_dispatched"}
                or any(item.dispatched_quantity for item in snapshot.lines)
                or (not snapshot.labels and not snapshot.warehouse.prelabel_safe())
                or (
                    (snapshot.labels or case.request.intent == "address")
                    and (
                        not snapshot.warehouse.current_hold() or snapshot.warehouse.ack_id != plan.hold_ack_id
                    )
                )
            ):
                self._transition(
                    case,
                    "escalated",
                    "Physical dispatch or an expired warehouse hold prevents safe completion. Contact the warehouse; no stopped-parcel claim is supported.",
                )
                return self.view(case_id, operator)
            self._transition(
                case,
                "executing",
                "Executing the approved recovery; each action has a durable intent and an independent read-back.",
            )
            for action in plan.actions:
                attempt = attempts.get(action.id)
                if attempt and attempt.status == "succeeded":
                    continue
                if attempt and not attempt.retryable:
                    self._transition(
                        case,
                        "escalated",
                        "This operation cannot safely be retried. Review its provider evidence manually.",
                    )
                    return self.view(case_id, operator)
                if attempt and attempt.error and "rate limit" in attempt.error.lower():
                    age = (datetime.now(UTC) - datetime.fromisoformat(attempt.updated_at)).total_seconds()
                    if age < 1:
                        time.sleep(1 - age)
                if attempt is None:
                    attempt = OperationAttempt(
                        id=str(uuid4()),
                        case_id=case.id,
                        action_id=action.id,
                        kind=action.kind,
                        idempotency_key=digest({"case": case.id, "plan": plan.hash, "action": action.id}),
                        resource_version=expected,
                    )
                attempt.status = "intent"
                attempt.error = None
                self.store.save_attempt(attempt)
                self.store.event(
                    case_id,
                    "recovery desk",
                    "operation_intent",
                    action.title,
                    {
                        "action_id": action.id,
                        "operation_key": attempt.idempotency_key,
                        "expected_version": expected,
                    },
                )
                self._boundary("after_intent", action)
                try:
                    adapter = (
                        self.payments
                        if action.kind == ActionKind.REFUND
                        else self.shipping
                        if action.kind in {ActionKind.VOID, ActionKind.CREATE_LABEL}
                        else self.commerce
                    )
                    receipt = adapter.perform(
                        case.order_id,
                        action,
                        idempotency_key=attempt.idempotency_key,
                        expected_version=expected,
                        hold_ack_id=plan.hold_ack_id,
                    )
                    self._boundary("after_effect", action)
                except ProviderFailure as exc:
                    attempt.status = "uncertain" if exc.uncertain else "failed"
                    attempt.error = str(exc)
                    attempt.retryable = exc.retryable
                    self.store.save_attempt(attempt)
                    case.snapshot = self.sim.peek(case.order_id)
                    if isinstance(exc, PreconditionFailed):
                        self._transition(
                            case,
                            "escalated",
                            str(exc) + " Partial completion, if any, is preserved; contact the warehouse.",
                        )
                    elif exc.uncertain:
                        self._transition(case, "reconciling", str(exc))
                    elif exc.retryable:
                        self._transition(
                            case,
                            "failed",
                            str(exc)
                            + " The case is incomplete; reconcile and resume the remaining approved actions.",
                        )
                    else:
                        self._transition(case, "escalated", str(exc))
                    return self.view(case_id, operator)
                attempt.status = "succeeded"
                attempt.provider_id = receipt["provider_id"]
                attempt.result_version = receipt["result_version"]
                attempt.error = None
                self.store.save_attempt(attempt)
                attempts[action.id] = attempt
                expected = receipt["result_version"]
                self.store.event(
                    case_id,
                    "provider receipt",
                    "operation_result",
                    action.title + " — provider receipt recorded.",
                    receipt,
                )
                self._boundary("after_record", action)
                try:
                    snapshot = self.sim.read(case.order_id)
                except ProviderFailure as exc:
                    self._transition(case, "reconciling", str(exc))
                    return self.view(case_id, operator)
                case.snapshot = snapshot
                if (
                    not self._fresh(snapshot)
                    or snapshot.version != expected
                    or not self._action_verified(action, snapshot)
                ):
                    self._transition(
                        case,
                        "reconciling",
                        "An action receipt exists, but current read-back has not verified it. Reconcile before continuing.",
                    )
                    return self.view(case_id, operator)
                self.store.save_case(
                    case,
                    message="Fresh read-back verified: " + action.title,
                    kind="read_back",
                    data={"action_id": action.id, "version": snapshot.version},
                )
            self._transition(
                case, "reconciling", "Verifying the requested terminal state across all providers."
            )
            try:
                snapshot = self.sim.read(case.order_id)
            except ProviderFailure as exc:
                self._transition(case, "reconciling", str(exc))
                return self.view(case_id, operator)
            case.snapshot = snapshot
            self._record_snapshot(case, snapshot)
            if (
                self._fresh(snapshot)
                and snapshot.version == expected
                and self.terminal_verified(case, snapshot)
            ):
                self._transition(
                    case,
                    "resolved",
                    "Verified recovery: all requested final-state checks passed. Customer explanation is drafted locally; nothing was sent.",
                )
            else:
                self._transition(
                    case,
                    "escalated",
                    "Final read-back did not establish the intended state. Recovery remains incomplete; review warehouse, label and payment evidence.",
                )
        return self.view(case_id, operator)

    def _action_verified(self, action: ProposedAction, order: OrderSnapshot) -> bool:
        if action.kind == ActionKind.CANCEL:
            return order.commercial_state == "cancelled" and all(
                item.cancelled_quantity == item.quantity for item in order.lines
            )
        if action.kind == ActionKind.REFUND:
            return sum(r.amount.minor for r in order.payment.refunds) == order.payment.captured.minor
        if action.kind == ActionKind.VOID:
            return any(item.id == action.label_id and item.status == "void" for item in order.labels) and all(
                item.tracking not in order.tracking for item in order.labels if item.status == "void"
            )
        if action.kind == ActionKind.ADDRESS:
            return order.address == action.address
        return (
            len([item for item in order.labels if item.status == "active" and item.address == action.address])
            == 1
        )

    def terminal_verified(self, case: RecoveryCase, order: OrderSnapshot) -> bool:
        if order.warehouse.state in {"dispatched", "partially_dispatched"} or any(
            item.dispatched_quantity for item in order.lines
        ):
            return False
        if order.labels and not order.warehouse.current_hold():
            return False
        if not order.labels and not order.warehouse.prelabel_safe():
            return False
        issues = disagreements(order)
        if any(i["severity"] == "danger" for i in issues):
            return False
        active = [item for item in order.labels if item.status == "active"]
        if case.request.intent == "cancel":
            return (
                order.commercial_state == "cancelled"
                and sum(r.amount.minor for r in order.payment.refunds) == order.payment.captured.minor
                and all(
                    item.refunded_quantity == item.quantity and item.cancelled_quantity == item.quantity
                    for item in order.lines
                )
                and not active
                and not order.tracking
                and all(s.status == "cancelled" for s in order.shipments)
            )
        if case.request.intent == "address":
            return (
                order.commercial_state == "processing"
                and order.address == case.request.target_address
                and len(active) == 1
                and active[0].address == case.request.target_address
                and order.tracking == [active[0].tracking]
                and not order.payment.refunds
            )
        return False

    def ingest_event(self, event_id: str, order_id: str, version: int, payload: dict[str, Any]) -> str:
        result = self.store.ingest(event_id, order_id, version, payload)
        for raw in self.store.list_cases():
            if raw["order_id"] == order_id:
                self.store.event(
                    raw["id"],
                    "provider event",
                    "delivery",
                    f"Event {result}; events are monitoring evidence and cannot authorize actions.",
                    {"event_id": event_id, "version": version, "disposition": result},
                )
        return result

    def recover_pending(self) -> list[dict[str, Any]]:
        """Reconcile persisted operator requests; financial/label actions still require approval."""
        recovered = []
        for raw in self.store.list_cases():
            if raw["status"] in {"executing", "reconciling"} or (
                raw["status"] not in {"resolved", "escalated"} and self._pending_hold(raw["id"])
            ):
                try:
                    recovered.append(self.retry(raw["id"]))
                except DeskError:
                    # A concurrent process holds the resource; leave its durable state intact.
                    continue
        return recovered

    @staticmethod
    def _money(money: Money) -> str:
        prefix = {"GBP": "£", "USD": "$", "EUR": "€"}[money.currency]
        return f"{prefix}{money.minor // 100:,}.{money.minor % 100:02d}"

    def _draft(self, case: RecoveryCase) -> str:
        order = case.snapshot
        verified_at = datetime.fromisoformat(case.updated_at).strftime("%d %b %Y at %H:%M UTC")
        if case.status == "resolved" and case.request.intent == "cancel":
            return (
                f"On {verified_at}, we verified that order #{order.id} was cancelled and a refund of {self._money(order.payment.captured)} was recorded against the original payment. "
                + (
                    "The warehouse hold was acknowledged and valid at that verification. "
                    if order.labels
                    else "No active shipping label remained at verification. "
                )
                + "Your bank's processing time may vary."
            )
        if case.status == "resolved" and case.request.intent == "address":
            return f"On {verified_at}, we verified the corrected delivery address and replacement label for order #{order.id}. The warehouse hold was valid at verification. An operator must confirm current warehouse state before releasing the parcel."
        if order.warehouse.state in {"dispatched", "partially_dispatched"}:
            payment_note = (
                " The storefront order is cancelled, but the refund is not yet confirmed."
                if order.commercial_state == "cancelled"
                and sum(r.amount.minor for r in order.payment.refunds) < order.payment.captured.minor
                else ""
            )
            return f"Your request for order #{order.id} is under review. Warehouse evidence indicates at least some items have dispatched, so we cannot confirm that the parcel has been stopped.{payment_note} An operator will review the available options."
        if (
            order.commercial_state == "cancelled"
            and sum(r.amount.minor for r in order.payment.refunds) < order.payment.captured.minor
        ):
            return f"The storefront order #{order.id} is cancelled, but the refund is not yet confirmed. We are checking the remaining recovery steps and will update you when verified."
        return f"We have received your request for order #{order.id}. We are checking payment, shipping and warehouse records. We have not yet confirmed that the recovery is complete or that the parcel is stopped."

    def view(self, case_id: str, operator: Operator = OPERATOR) -> dict[str, Any]:
        case = self._case(case_id, operator)
        order = case.snapshot
        issues = disagreements(order)
        attempts = self.store.attempts(case.id)
        pending_hold = self._pending_hold(case.id)
        can_replan = not pending_hold and not any(
            a["status"] in {"succeeded", "intent", "uncertain"} for a in attempts
        )
        write = operator.role in {"operator", "owner"}
        return {
            "id": case.id,
            "order_id": case.order_id,
            "customer_name": order.customer_name,
            "intent": case.request.intent,
            "status": case.status,
            "reason": case.reason,
            "created_at": case.created_at,
            "updated_at": case.updated_at,
            "revision": case.revision,
            "amount": order.payment.captured.model_dump(),
            "issue_count": len(issues),
            "approved": self._approved(case),
            "request": case.request.model_dump(),
            "order": order.model_dump(mode="json"),
            "plan": case.plan.model_dump(mode="json") if case.plan else None,
            "approvals": self.store.approvals(case.id),
            "attempts": attempts,
            "warehouse_attempts": self.store.hold_attempts(case.id),
            "evidence": self.store.events(case.id),
            "disagreements": issues,
            "draft": self._draft(case),
            "interpreter_mode": case.interpreter_mode,
            "notification_status": "draft-only",
            "permitted": {
                "investigate": write
                and case.status
                in {
                    "received",
                    "investigating",
                    "proposal-ready",
                    "needs-information",
                    "awaiting-approval",
                    "failed",
                    "escalated",
                }
                and can_replan,
                "approve": write and case.status == "awaiting-approval" and not self._approved(case),
                "execute": write and case.status == "awaiting-approval" and self._approved(case),
                "hold": write
                and case.status not in {"resolved", "executing", "reconciling"}
                and can_replan
                and order.warehouse.state not in {"dispatched", "partially_dispatched"},
                "retry": write
                and (bool(pending_hold) or case.status in {"failed", "reconciling", "executing"}),
            },
        }

    def list_cases(self, operator: Operator = OPERATOR) -> list[dict[str, Any]]:
        return [
            self.view(c["id"], operator)
            for c in self.store.list_cases()
            if c["store_id"] in operator.store_ids
        ]
