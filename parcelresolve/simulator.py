"""Independent provider simulator with durable idempotency receipts and real fault windows.

The strong receipt query and atomic warehouse fence are simulator contracts, not claims
about WooCommerce, ShipStation, payment gateways, or physical warehouses.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .domain import (
    ActionKind,
    DeskError,
    Label,
    OrderSnapshot,
    Payment,
    PreconditionFailed,
    ProposedAction,
    ProviderFailure,
    Refund,
    Shipment,
    WarehouseAcknowledgment,
    digest,
    now,
)

FAULTS = {
    "before_write",
    "lost_response",
    "unavailable",
    "rate_limit",
    "void_rejected",
    "stale_read",
    "dispatch_race",
    "unknown_outcome",
}


class Simulator:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "providers.sqlite"
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (seq INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS effects (operation_key TEXT PRIMARY KEY, order_id TEXT NOT NULL, action_hash TEXT NOT NULL, data TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS hold_effects (operation_key TEXT PRIMARY KEY, order_id TEXT NOT NULL, expected_version INTEGER NOT NULL, data TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS faults (seq INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL, kind TEXT NOT NULL, fault TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO schema_migrations VALUES (1);
                INSERT OR IGNORE INTO schema_migrations VALUES (2);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=FULL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _get(self, conn: sqlite3.Connection, order_id: str) -> OrderSnapshot:
        row = conn.execute("SELECT data FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise DeskError("Order not found", 404)
        return OrderSnapshot.model_validate_json(row[0])

    def _put(self, conn: sqlite3.Connection, order: OrderSnapshot) -> None:
        # Revalidate nested model mutations before persistence.
        order = OrderSnapshot.model_validate(order.model_dump(mode="json"))
        conn.execute(
            "INSERT INTO orders VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (order.id, order.model_dump_json()),
        )
        conn.execute("INSERT INTO history(order_id,data) VALUES (?,?)", (order.id, order.model_dump_json()))

    def put_order(self, order: OrderSnapshot) -> None:
        with self.connect() as conn:
            self._put(conn, order)

    def list_orders(self) -> list[OrderSnapshot]:
        with self.connect() as conn:
            return [
                OrderSnapshot.model_validate_json(r[0])
                for r in conn.execute("SELECT data FROM orders ORDER BY id")
            ]

    def peek(self, order_id: str) -> OrderSnapshot:
        """Read simulator truth for inspection only. Workflow execution must use read()."""
        with self.connect() as conn:
            return self._get(conn, order_id)

    def read(self, order_id: str) -> OrderSnapshot:
        failure: str | None = None
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            order = self._get(conn, order_id)
            row = conn.execute(
                "SELECT seq,fault FROM faults WHERE order_id=? AND consumed=0 AND (fault='stale_read' OR kind='read') ORDER BY seq LIMIT 1",
                (order_id,),
            ).fetchone()
            if row:
                conn.execute("UPDATE faults SET consumed=1 WHERE seq=?", (row[0],))
                if row[1] == "stale_read":
                    old = conn.execute(
                        "SELECT data FROM history WHERE order_id=? ORDER BY seq LIMIT 1", (order_id,)
                    ).fetchone()
                    order = OrderSnapshot.model_validate_json(old[0])
                    order.observed_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
                    return order
                failure = row[1]
            order.observed_at = now()
        if failure:
            raise ProviderFailure(
                "Provider read is unavailable; current state could not be established.", retryable=True
            )
        return order

    def inject(self, order_id: str, action_kind: str, fault: str) -> None:
        if fault not in FAULTS or action_kind not in {k.value for k in ActionKind} | {"read"}:
            raise DeskError("Unsupported simulation fault or action", 422)
        with self.connect() as conn:
            self._get(conn, order_id)
            conn.execute(
                "INSERT INTO faults(order_id,kind,fault) VALUES (?,?,?)", (order_id, action_kind, fault)
            )

    def confirm_hold(self, order_id: str, *, operation_key: str, expected_version: int) -> dict[str, Any]:
        """Idempotent provider write with a durable, independently queryable receipt."""
        failure: ProviderFailure | None = None
        receipt: dict[str, Any] = {}
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT order_id,expected_version,data FROM hold_effects WHERE operation_key=?",
                (operation_key,),
            ).fetchone()
            if existing:
                if existing[0] != order_id or existing[1] != expected_version:
                    raise PreconditionFailed(
                        "Warehouse operation key was already used for a different request"
                    )
                return json.loads(existing[2])
            order = self._get(conn, order_id)
            fault_row = conn.execute(
                "SELECT seq,fault FROM faults WHERE order_id=? AND kind='warehouse_hold' AND consumed=0 ORDER BY seq LIMIT 1",
                (order_id,),
            ).fetchone()
            fault = fault_row[1] if fault_row else None
            if fault_row:
                conn.execute("UPDATE faults SET consumed=1 WHERE seq=?", (fault_row[0],))
            if fault == "dispatch_race":
                self._external_change(order, "dispatch")
                self._put(conn, order)
            if order.version != expected_version:
                failure = PreconditionFailed(
                    "Warehouse state changed before the hold; refresh current evidence."
                )
            elif order.warehouse.state in {"dispatched", "partially_dispatched"} or any(
                item.dispatched_quantity for item in order.lines
            ):
                failure = PreconditionFailed(
                    "Warehouse cannot confirm a stop: items have already dispatched."
                )
            elif fault in {"before_write", "unavailable", "rate_limit", "void_rejected"}:
                failure = ProviderFailure(
                    "Warehouse did not accept the hold request; no stop is confirmed.", retryable=True
                )
            else:
                at = datetime.now(UTC)
                order.warehouse = WarehouseAcknowledgment(
                    state="held",
                    ack_id="hold-" + uuid4().hex[:12],
                    acknowledged_at=at.isoformat(),
                    expires_at=(at + timedelta(minutes=5)).isoformat(),
                    reliable=True,
                )
                order.version += 1
                order.observed_at = now()
                self._put(conn, order)
                receipt = {
                    "operation_key": operation_key,
                    "kind": "warehouse_hold",
                    "provider_id": order.warehouse.ack_id,
                    "result_version": order.version,
                    "warehouse": order.warehouse.model_dump(mode="json"),
                    "created_at": now(),
                }
                conn.execute(
                    "INSERT INTO hold_effects VALUES (?,?,?,?,?)",
                    (
                        operation_key,
                        order_id,
                        expected_version,
                        json.dumps(receipt),
                        int(fault == "unknown_outcome"),
                    ),
                )
                if fault in {"lost_response", "unknown_outcome"}:
                    failure = ProviderFailure(
                        "Warehouse hold response was lost; reconcile before any further hold request.",
                        uncertain=True,
                    )
        if failure:
            raise failure
        return receipt

    def query_hold(self, operation_key: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT data,hidden FROM hold_effects WHERE operation_key=?", (operation_key,)
            ).fetchone()
        if row is None:
            return {"status": "not_written"}
        if row[1]:
            return {"status": "unknown"}
        return {"status": "succeeded", **json.loads(row[0])}

    def hold_effects(self, order_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT data FROM hold_effects WHERE order_id=? ORDER BY rowid", (order_id,)
                )
            ]

    def _external_change(self, order: OrderSnapshot, change: str) -> None:
        if change == "address":
            order.address.line1 = "44 Customer Changed Street"
        elif change in {"dispatch", "partial_dispatch"}:
            for i, line in enumerate(order.lines):
                line.dispatched_quantity = line.quantity if change == "dispatch" else (1 if i == 0 else 0)
            order.warehouse = WarehouseAcknowledgment(
                state="dispatched" if change == "dispatch" else "partially_dispatched",
                reliable=True,
                acknowledged_at=now(),
            )
        elif change == "expire_hold":
            order.warehouse.expires_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        else:
            raise DeskError("Unknown external simulator change", 422)
        order.version += 1
        order.observed_at = now()

    def external_change(self, order_id: str, change: str) -> OrderSnapshot:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            order = self._get(conn, order_id)
            self._external_change(order, change)
            self._put(conn, order)
        return order

    def query_effect(self, operation_key: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT data,hidden FROM effects WHERE operation_key=?", (operation_key,)
            ).fetchone()
        if not row:
            return {"status": "not_written"}
        if row[1]:
            return {"status": "unknown"}
        return {"status": "succeeded", **json.loads(row[0])}

    def effects(self, order_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute("SELECT data FROM effects WHERE order_id=? ORDER BY rowid", (order_id,))
            ]

    def apply(
        self,
        order_id: str,
        action: ProposedAction,
        operation_key: str,
        expected_version: int,
        hold_ack_id: str | None,
    ) -> dict[str, Any]:
        if action.kind == ActionKind.HOLD:
            raise PreconditionFailed("Warehouse holds require the journaled warehouse adapter")
        failure: ProviderFailure | None = None
        receipt: dict[str, Any] = {}
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT action_hash,data FROM effects WHERE operation_key=?", (operation_key,)
            ).fetchone()
            if existing:
                if existing[0] != digest(action):
                    raise PreconditionFailed("Idempotency key was already used with a different action")
                return json.loads(existing[1])
            order = self._get(conn, order_id)
            fault_row = conn.execute(
                "SELECT seq,fault FROM faults WHERE order_id=? AND kind=? AND consumed=0 ORDER BY seq LIMIT 1",
                (order_id, action.kind.value),
            ).fetchone()
            fault = fault_row[1] if fault_row else None
            if fault_row:
                conn.execute("UPDATE faults SET consumed=1 WHERE seq=?", (fault_row[0],))
            if fault == "dispatch_race":
                self._external_change(order, "dispatch")
                self._put(conn, order)
            if order.version != expected_version:
                failure = PreconditionFailed(
                    "Order changed at the action boundary; the approved plan is stale."
                )
            elif order.warehouse.state in {"dispatched", "partially_dispatched"} or any(
                item.dispatched_quantity for item in order.lines
            ):
                failure = PreconditionFailed("Physical dispatch evidence prevents a safe recovery.")
            elif (order.labels or action.kind == ActionKind.CREATE_LABEL) and (
                not order.warehouse.current_hold() or order.warehouse.ack_id != hold_ack_id
            ):
                failure = PreconditionFailed(
                    "The warehouse hold is missing, stale, or changed; recovery stopped."
                )
            elif not order.labels and not order.warehouse.prelabel_safe():
                failure = PreconditionFailed(
                    "Reliable current warehouse evidence is required before unlabelled recovery."
                )
            elif fault in {"before_write", "unavailable", "rate_limit"}:
                messages = {
                    "before_write": "Provider rejected the request before writing. Safe reconciliation is available.",
                    "unavailable": "Provider unavailable before accepting the operation.",
                    "rate_limit": "Provider rate limit reached. Retry after 1 second.",
                }
                failure = ProviderFailure(messages[fault], retryable=True)
            elif fault == "void_rejected":
                failure = ProviderFailure(
                    "Carrier rejected the label void. Contact the carrier and warehouse; no stop or refund is confirmed."
                )
            else:
                self._mutate(order, action, operation_key)
                order.version += 1
                order.observed_at = now()
                self._put(conn, order)
                receipt = {
                    "operation_key": operation_key,
                    "kind": action.kind.value,
                    "provider_id": "sim-" + uuid4().hex[:14],
                    "result_version": order.version,
                    "created_at": now(),
                    "action_hash": digest(action),
                }
                conn.execute(
                    "INSERT INTO effects VALUES (?,?,?,?,?)",
                    (
                        operation_key,
                        order_id,
                        digest(action),
                        json.dumps(receipt),
                        int(fault == "unknown_outcome"),
                    ),
                )
                if fault in {"lost_response", "unknown_outcome"}:
                    failure = ProviderFailure(
                        "The provider response was lost after a possible write. Reconcile before retrying.",
                        uncertain=True,
                    )
        if failure:
            raise failure
        return receipt

    def _mutate(self, order: OrderSnapshot, action: ProposedAction, operation_key: str) -> None:
        if action.kind == ActionKind.VOID:
            label = next((item for item in order.labels if item.id == action.label_id), None)
            if not label or label.status != "active":
                raise PreconditionFailed("Label no longer matches the proposed void")
            label.status = "void"
            order.tracking = [item.tracking for item in order.labels if item.status == "active"]
        elif action.kind == ActionKind.CANCEL:
            if any(item.status == "active" for item in order.labels):
                raise PreconditionFailed("Active labels must be voided before cancellation")
            order.commercial_state = "cancelled"
            for line in order.lines:
                line.cancelled_quantity = line.quantity
            for shipment in order.shipments:
                shipment.status = "cancelled"
            order.tracking = []
        elif action.kind == ActionKind.REFUND:
            remaining = order.payment.captured.minor - sum(r.amount.minor for r in order.payment.refunds)
            if (
                order.commercial_state != "cancelled"
                or action.amount is None
                or action.amount.currency != order.payment.captured.currency
                or action.amount.minor != remaining
                or remaining <= 0
            ):
                raise PreconditionFailed("Refund amount/state does not match the approved remaining capture")
            quantities = {line.id: line.quantity - line.refunded_quantity for line in order.lines}
            refund = Refund(
                id="refund-" + uuid4().hex[:12],
                amount=action.amount,
                line_quantities=quantities,
                operation_key=operation_key,
            )
            order.payment.refunds.append(refund)
            for line in order.lines:
                line.refunded_quantity = line.quantity
        elif action.kind == ActionKind.ADDRESS:
            if (
                not action.address
                or action.address.country != order.address.country
                or any(item.status == "active" for item in order.labels)
            ):
                raise PreconditionFailed(
                    "Address change requires a supported domestic address and no active old label"
                )
            order.address = action.address.model_copy(deep=True)
        elif action.kind == ActionKind.CREATE_LABEL:
            if (
                order.commercial_state != "processing"
                or not action.address
                or order.address != action.address
                or any(item.status == "active" for item in order.labels)
            ):
                raise PreconditionFailed("Replacement label preconditions failed")
            if not order.shipments:
                order.shipments.append(
                    Shipment(
                        id="shipment-" + order.id,
                        order_key=order.shipstation_order_key,
                        line_quantities={item.id: item.quantity for item in order.lines},
                    )
                )
            shipment = order.shipments[0]
            shipment.status = "shipped"
            label = Label(
                id="label-" + uuid4().hex[:12],
                shipment_id=shipment.id,
                status="active",
                tracking="PR" + uuid4().hex[:12].upper(),
                address=action.address,
            )
            order.labels.append(label)
            order.tracking = [label.tracking]


class LocalCommerceAdapter:
    kinds = {ActionKind.CANCEL, ActionKind.ADDRESS}

    def __init__(self, simulator: Simulator):
        self.sim = simulator

    def read_commerce(self, order_id: str) -> OrderSnapshot:
        return self.sim.read(order_id)

    def perform(
        self,
        order_id: str,
        action: ProposedAction,
        *,
        idempotency_key: str,
        expected_version: int,
        hold_ack_id: str | None = None,
    ) -> dict[str, Any]:
        if action.kind not in self.kinds:
            raise PreconditionFailed("This adapter does not support the proposed action kind")
        return self.sim.apply(order_id, action, idempotency_key, expected_version, hold_ack_id)


class LocalPaymentAdapter(LocalCommerceAdapter):
    kinds = {ActionKind.REFUND}

    def read_payment(self, order_id: str) -> Payment:
        return self.sim.read(order_id).payment


class LocalShippingAdapter(LocalCommerceAdapter):
    kinds = {ActionKind.VOID, ActionKind.CREATE_LABEL}

    def read_shipping(self, order_id: str) -> dict[str, Any]:
        order = self.sim.read(order_id)
        return {"labels": order.labels, "shipments": order.shipments, "tracking": order.tracking}


class LocalWarehouseAdapter(LocalCommerceAdapter):
    kinds: set[ActionKind] = set()

    def read_warehouse(self, order_id: str) -> WarehouseAcknowledgment:
        return self.sim.read(order_id).warehouse

    def confirm_hold(
        self, order_id: str, *, idempotency_key: str | None = None, expected_version: int | None = None
    ) -> WarehouseAcknowledgment:
        if idempotency_key is None or expected_version is None:
            raise PreconditionFailed("Warehouse holds require a durable operation key and expected version")
        receipt = self.perform_hold(
            order_id, idempotency_key=idempotency_key, expected_version=expected_version
        )
        return WarehouseAcknowledgment.model_validate(receipt["warehouse"])

    def perform_hold(self, order_id: str, *, idempotency_key: str, expected_version: int) -> dict[str, Any]:
        return self.sim.confirm_hold(
            order_id, operation_key=idempotency_key, expected_version=expected_version
        )

    def query_hold(self, operation_key: str) -> dict[str, Any]:
        return self.sim.query_hold(operation_key)
