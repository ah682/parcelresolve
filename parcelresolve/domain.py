"""Validated domain records. Provider status is never physical dispatch evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


Quantity = Annotated[StrictInt, Field(ge=0, le=10000)]


class Money(Record):
    minor: Annotated[StrictInt, Field(ge=0, le=1_000_000_000)]
    currency: Literal["GBP", "USD", "EUR"]


class Address(Record):
    name: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    postcode: str = Field(min_length=1, max_length=20)
    country: str = Field(pattern=r"^[A-Z]{2}$")


class LineItem(Record):
    id: str
    sku: str
    title: str
    quantity: Annotated[StrictInt, Field(ge=1, le=10000)]
    unit_price: Money
    refunded_quantity: Quantity = 0
    dispatched_quantity: Quantity = 0
    cancelled_quantity: Quantity = 0

    @model_validator(mode="after")
    def quantities_fit(self) -> LineItem:
        if max(self.refunded_quantity, self.dispatched_quantity, self.cancelled_quantity) > self.quantity:
            raise ValueError("Recorded line quantities cannot exceed ordered quantity")
        return self


class Refund(Record):
    id: str
    amount: Money
    line_quantities: dict[str, Quantity]
    operation_key: str
    created_at: str = Field(default_factory=now)


class Payment(Record):
    captured: Money
    refunds: list[Refund] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_refunds(self) -> Payment:
        if any(r.amount.currency != self.captured.currency for r in self.refunds):
            raise ValueError("Cross-currency refunds are unsupported")
        if sum(r.amount.minor for r in self.refunds) > self.captured.minor:
            raise ValueError("Refunds exceed captured payment")
        if len({r.id for r in self.refunds}) != len(self.refunds):
            raise ValueError("Duplicate refund identifier")
        return self


class Label(Record):
    id: str
    shipment_id: str
    status: Literal["active", "void"]
    tracking: str
    address: Address


class Shipment(Record):
    id: str
    order_key: str
    line_quantities: dict[str, Quantity]
    status: Literal["awaiting_shipment", "shipped", "cancelled"] = "awaiting_shipment"


class WarehouseAcknowledgment(Record):
    state: Literal["not_dispatched", "unknown", "held", "dispatched", "partially_dispatched"]
    ack_id: str | None = None
    acknowledged_at: str | None = None
    expires_at: str | None = None
    reliable: bool = False

    def prelabel_safe(self) -> bool:
        """A fresh authoritative unshipped read or a current positive hold is required."""
        return (self.state == "not_dispatched" and self.reliable) or self.current_hold()

    def current_hold(self, at: datetime | None = None) -> bool:
        at = at or datetime.now(UTC)
        if not (
            self.state == "held"
            and self.reliable
            and self.ack_id
            and self.expires_at
            and self.acknowledged_at
        ):
            return False
        try:
            issued = datetime.fromisoformat(self.acknowledged_at)
            expires = datetime.fromisoformat(self.expires_at)
            return issued <= at < expires and (at - issued).total_seconds() <= 300
        except (ValueError, TypeError):
            return False


class OrderSnapshot(Record):
    id: str
    store_id: str = "store-1"
    woo_id: int
    shipstation_order_id: int
    shipstation_order_key: str
    version: int = Field(ge=1, default=1)
    customer_name: str
    commercial_state: Literal["processing", "cancelled", "completed"] = "processing"
    address: Address
    payment: Payment
    lines: list[LineItem] = Field(min_length=1)
    labels: list[Label] = Field(default_factory=list)
    shipments: list[Shipment] = Field(default_factory=list)
    warehouse: WarehouseAcknowledgment
    tracking: list[str] = Field(default_factory=list)
    observed_at: str = Field(default_factory=now)

    @model_validator(mode="after")
    def valid_money_and_identities(self) -> OrderSnapshot:
        currency = self.payment.captured.currency
        if any(line.unit_price.currency != currency for line in self.lines):
            raise ValueError("Mixed-currency lines are unsupported")
        if sum(line.quantity * line.unit_price.minor for line in self.lines) != self.payment.captured.minor:
            raise ValueError(
                "Only fully captured integral line totals are supported; fees/discount allocations require review"
            )
        for values in (
            [line.id for line in self.lines],
            [s.id for s in self.shipments],
            [item.id for item in self.labels],
        ):
            if len(set(values)) != len(values):
                raise ValueError("Duplicate resource identity")
        return self


class CustomerRequest(Record):
    text: str = Field(min_length=1, max_length=4000)
    intent: Literal["cancel", "address", "unknown"]
    target_address: Address | None = None


class ActionKind(StrEnum):
    HOLD = "warehouse_hold"
    CANCEL = "cancel_order"
    REFUND = "refund"
    VOID = "void_label"
    ADDRESS = "update_address"
    CREATE_LABEL = "create_label"


class ProposedAction(Record):
    id: str
    kind: ActionKind
    title: str
    amount: Money | None = None
    label_id: str | None = None
    address: Address | None = None


class Plan(Record):
    id: str
    hash: str
    resource_version: int
    actions: list[ProposedAction]
    created_at: str = Field(default_factory=now)
    hold_ack_id: str | None = None

    def calculated_hash(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"hash"}))


class Approval(Record):
    id: str
    case_id: str
    plan_hash: str
    action_hash: str
    resource_version: int
    operator_id: str
    amount: Money | None = None
    created_at: str = Field(default_factory=now)


class OperationAttempt(Record):
    id: str
    case_id: str
    action_id: str
    kind: ActionKind
    status: Literal["intent", "uncertain", "succeeded", "failed"] = "intent"
    idempotency_key: str
    provider_id: str | None = None
    resource_version: int
    result_version: int | None = None
    error: str | None = None
    retryable: bool = False
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)


class WarehouseHoldAttempt(OperationAttempt):
    """A preparatory stop request authorized by an authenticated operator."""

    kind: Literal[ActionKind.HOLD] = ActionKind.HOLD
    operator_id: str
    readback_status: Literal["pending", "verified", "failed"] = "pending"
    verified_at: str | None = None


class EvidenceEvent(Record):
    id: str
    source: str
    kind: str
    message: str
    created_at: str = Field(default_factory=now)
    data: dict[str, Any] = Field(default_factory=dict)


Status = Literal[
    "received",
    "investigating",
    "needs-information",
    "proposal-ready",
    "awaiting-approval",
    "executing",
    "reconciling",
    "resolved",
    "escalated",
    "failed",
]

TRANSITIONS: dict[str, set[str]] = {
    "received": {"investigating", "needs-information"},
    "investigating": {"needs-information", "proposal-ready", "escalated", "resolved"},
    "needs-information": {"investigating", "escalated"},
    "proposal-ready": {"awaiting-approval", "investigating", "needs-information", "escalated"},
    "awaiting-approval": {"executing", "investigating", "needs-information", "escalated"},
    "executing": {"reconciling", "failed", "escalated", "needs-information"},
    "reconciling": {"executing", "resolved", "failed", "escalated", "needs-information"},
    "failed": {"reconciling", "investigating", "escalated"},
    "resolved": {"escalated"},
    "escalated": {"investigating"},
}


class RecoveryCase(Record):
    id: str
    order_id: str
    store_id: str
    status: Status = "received"
    request: CustomerRequest
    reason: str = "Ready to investigate the request."
    plan: Plan | None = None
    snapshot: OrderSnapshot
    interpreter_mode: str = "deterministic"
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    revision: int = 1


class Operator(Record):
    id: str
    name: str
    role: Literal["operator", "viewer", "owner"]
    store_ids: list[str]


class DeskError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class ProviderFailure(Exception):
    def __init__(self, message: str, *, uncertain: bool = False, retryable: bool = False):
        super().__init__(message)
        self.uncertain = uncertain
        self.retryable = retryable


class PreconditionFailed(ProviderFailure):
    pass


def disagreements(order: OrderSnapshot) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def add(code: str, message: str, severity: str = "warning") -> None:
        found.append({"code": code, "severity": severity, "message": message})

    active = [label for label in order.labels if label.status == "active"]
    if (
        active
        and not order.warehouse.current_hold()
        and order.warehouse.state not in {"dispatched", "partially_dispatched"}
    ):
        add(
            "dispatch_unknown",
            "Label printed. Physical dispatch is not confirmed; a current warehouse hold is required.",
        )
    if any(s.status == "shipped" for s in order.shipments) and order.warehouse.state not in {
        "dispatched",
        "partially_dispatched",
    }:
        add(
            "printed_not_dispatched",
            "ShipStation says Shipped, which can mean a label was created. This is not handoff evidence.",
            "info",
        )
    if len(active) > 1:
        add("duplicate_active_labels", "Multiple active labels require operator review.", "danger")
    if set(order.tracking) != {label.tracking for label in active}:
        add("stale_tracking", "Storefront tracking does not match the active label set.", "danger")
    if order.commercial_state == "cancelled" or any(
        line.refunded_quantity or line.cancelled_quantity for line in order.lines
    ):
        if active or any(
            s.status != "cancelled" and any(s.line_quantities.values()) for s in order.shipments
        ):
            add(
                "cancelled_refunded_active",
                "Cancelled or refunded items are still assigned to an active shipment.",
                "danger",
            )
    if order.warehouse.state == "partially_dispatched" or any(
        0 < item.dispatched_quantity < item.quantity for item in order.lines
    ):
        add(
            "partial_dispatch",
            "Some items have physically dispatched. Whole-order recovery is blocked.",
            "danger",
        )
    if len(order.shipments) > 1:
        add("split_shipment", "Split shipments require an operator to review each parcel.", "danger")
    quantities: dict[str, int] = {}
    for shipment in order.shipments:
        if shipment.order_key != order.shipstation_order_key:
            add("identity_mismatch", "Shipment mapping does not match the verified order key.", "danger")
        for line_id, qty in shipment.line_quantities.items():
            quantities[line_id] = quantities.get(line_id, 0) + qty
    if order.shipments and quantities != {line.id: line.quantity for line in order.lines}:
        add("quantity_mismatch", "Shipment quantities do not match order lines.", "danger")
    if any(label.shipment_id not in {s.id for s in order.shipments} for label in order.labels):
        add("identity_mismatch", "A label is not bound to a known shipment.", "danger")
    refund_quantities: dict[str, int] = {}
    for refund in order.payment.refunds:
        for line_id, qty in refund.line_quantities.items():
            refund_quantities[line_id] = refund_quantities.get(line_id, 0) + qty
    if any(refund_quantities.get(item.id, 0) != item.refunded_quantity for item in order.lines) or set(
        refund_quantities
    ) - {item.id for item in order.lines}:
        add("refund_quantity_mismatch", "Refund quantities disagree with order lines.", "danger")
    return found
