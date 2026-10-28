"""Durable merchant review/handoff profile for real observations.

No HTTP mutation transport is exposed here. Documented request artifacts are
reviewable, but a read followed by PUT is not an atomic provider/warehouse fence.
The profile refuses that unsupported execution and can reconcile an operator's
reported external action without replaying it or claiming a recovered parcel.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, NoReturn
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .integrations import (
    CapabilityError,
    CommerceObservation,
    IdentityBinding,
    LabelObservation,
    PaymentObservation,
    ProviderContractError,
    RefundPreview,
    ShippingObservation,
    ShipStationV1Adapter,
    ShipStationV2Adapter,
    WooCommerceAdapter,
    WooShippingAddress,
    verify_identity_binding,
)

DOCUMENTATION_DATE = "2026-10-14"
BLOCKERS = (
    "No configured reliable live warehouse hold/dispatch fence.",
    "No verified atomic conditional-write contract across merchant edits and provider resources.",
    "No merchant-verified contract for notification/plugin side effects.",
    "No provider idempotency guarantee is assumed; uncertain writes must not be replayed.",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _stable(item) for key, item in value.items() if key not in {"observed_at", "captured_at"}
        }
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _money(minor: int) -> str:
    return f"{minor // 100}.{minor % 100:02d}"


class LiveReviewError(RuntimeError):
    pass


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LiveSnapshot(ReviewModel):
    binding: IdentityBinding
    commerce: CommerceObservation
    payment: PaymentObservation
    shipping: ShippingObservation
    labels: tuple[LabelObservation, ...]
    refund_preview: RefundPreview | None
    preview_limitation: str | None
    provenance: Literal["live_read", "mock_http"]
    captured_at: str = Field(default_factory=_now)

    @property
    def resource_version(self) -> str:
        return _hash(_stable(self.model_dump(mode="json")))


class LiveAction(ReviewModel):
    id: str
    kind: str
    provider: Literal["woocommerce", "shipstation_v1", "shipstation_v2", "warehouse"]
    method: Literal["PUT", "POST"] | None
    path: str | None
    body: dict[str, Any] | None
    amount_minor: int | None = None
    currency: str | None = None
    provider_resource_id: str | None = None
    limitations: tuple[str, ...]
    executable: Literal[False] = False

    @property
    def action_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


class LiveProposal(ReviewModel):
    id: str
    case_id: str = Field(min_length=1, max_length=100)
    flow: Literal["cancel", "address"]
    snapshot: LiveSnapshot
    resource_version: str
    actions: tuple[LiveAction, ...]
    target_address: WooShippingAddress | None
    blockers: tuple[str, ...]
    created_at: str
    expires_at: str
    proposal_hash: str
    recovery_verified: Literal[False] = False

    def calculated_hash(self) -> str:
        return _hash(self.model_dump(mode="json", exclude={"proposal_hash"}))


@dataclass(frozen=True)
class LiveAccess:
    store_id: str
    owner_id: str
    operator_id: str
    owner_token: str = field(repr=False)
    operator_token: str = field(repr=False)
    allow_reads: bool = False
    allow_mutations: bool = False

    def authenticate(self, token: str, role: Literal["owner", "operator"], store_id: str) -> str:
        if role not in {"owner", "operator"}:
            raise LiveReviewError("Unknown live review role")
        expected = self.owner_token if role == "owner" else self.operator_token
        actor = self.owner_id if role == "owner" else self.operator_id
        if store_id != self.store_id or not actor or len(expected) < 32:
            raise LiveReviewError("Live role/store configuration is missing or insufficient")
        if not token or not secrets.compare_digest(token.encode(), expected.encode()):
            raise LiveReviewError("Live review credential is invalid")
        return actor


@dataclass
class LiveReaders:
    commerce: WooCommerceAdapter
    shipping: ShipStationV1Adapter
    labels: ShipStationV2Adapter | None = None
    provenance: Literal["live_read", "mock_http"] = "live_read"

    def close(self) -> None:
        self.commerce.close()
        self.shipping.close()
        if self.labels is not None:
            self.labels.close()


class LiveReview:
    def __init__(self, directory: Path, readers: LiveReaders | None, access: LiveAccess):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "live-review.sqlite"
        self.readers = readers
        self.access = access
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS review_proposals (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL, resource_id TEXT NOT NULL,
                    state TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_approvals (
                    proposal_id TEXT NOT NULL, role TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY (proposal_id, role)
                );
                CREATE TABLE IF NOT EXISTS review_handoffs (
                    proposal_id TEXT NOT NULL, action_id TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY (proposal_id, action_id)
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_schema_migrations (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO review_schema_migrations VALUES (1);
            """)
        self.path.chmod(0o600)

    @classmethod
    def from_env(cls, directory: Path) -> LiveReview:
        if os.getenv("PARCELRESOLVE_CONTRACT_READS") != "1":
            raise CapabilityError("Live observation/preview reads require PARCELRESOLVE_CONTRACT_READS=1")
        store = os.getenv("WOO_STORE_ID", "")
        if not store:
            raise LiveReviewError("WOO_STORE_ID must identify the authorized merchant")
        readers = LiveReaders(
            WooCommerceAdapter.from_env(),
            ShipStationV1Adapter.from_env(),
            ShipStationV2Adapter.from_env() if os.getenv("SHIPSTATION_V2_KEY") else None,
        )
        return cls(
            directory,
            readers,
            LiveAccess(
                store,
                os.getenv("PARCELRESOLVE_LIVE_OWNER_ID", ""),
                os.getenv("PARCELRESOLVE_LIVE_OPERATOR_ID", ""),
                os.getenv("PARCELRESOLVE_LIVE_OWNER_TOKEN", ""),
                os.getenv("PARCELRESOLVE_LIVE_OPERATOR_TOKEN", ""),
                allow_reads=True,
                allow_mutations=os.getenv("PARCELRESOLVE_ALLOW_LIVE_MUTATIONS") == "1",
            ),
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=FULL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def _lock(self, resource: str) -> Iterator[None]:
        path = self.directory / ("live-" + _hash(resource) + ".lock")
        with path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LiveReviewError("Another operator is reviewing this resource") from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _event(self, proposal_id: str, kind: str, **data: Any) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO review_events(proposal_id,data) VALUES (?,?)",
                (
                    proposal_id,
                    json.dumps({"at": _now(), "kind": kind, **data}),
                ),
            )

    def _state(self, proposal_id: str, state: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE review_proposals SET state=? WHERE id=?", (state, proposal_id))

    def _proposal(self, proposal_id: str) -> LiveProposal:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM review_proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None:
            raise LiveReviewError("Live proposal not found")
        proposal = LiveProposal.model_validate_json(row[0])
        if proposal.proposal_hash != proposal.calculated_hash():
            raise LiveReviewError("Live proposal integrity check failed")
        return proposal

    def _capture(self, binding: IdentityBinding, *, refund_preview: bool) -> LiveSnapshot:
        if not self.access.allow_reads or self.readers is None:
            raise CapabilityError("Live observation reads are disabled")
        if binding.store_id != self.access.store_id:
            raise LiveReviewError("Order binding is outside the configured merchant")
        commerce = self.readers.commerce.read_commerce(binding.woo_order_id)
        payment = self.readers.commerce.read_payment(binding.woo_order_id)
        if (
            payment.order_id != commerce.order_id
            or payment.currency != commerce.currency
            or payment.order_total_minor != commerce.total_minor
        ):
            raise ProviderContractError("Commerce and payment observations disagree")
        shipping = self.readers.shipping.read_shipping(binding.shipstation_order_id)
        if binding.labels and self.readers.labels is None:
            raise CapabilityError("Mapped V2 labels require the separate V2 API credentials")
        labels = (
            tuple(self.readers.labels.read_label(item.label_id) for item in binding.labels)
            if self.readers.labels
            else ()
        )
        verify_identity_binding(binding, commerce, shipping, labels)
        preview, limitation = None, None
        if refund_preview and not payment.refunds and commerce.total_minor:
            if sum(line.total_minor + line.tax_minor for line in commerce.lines) != commerce.total_minor:
                limitation = "Shipping, fee or discount allocation is outside the whole-line preview profile."
            else:
                try:
                    preview = self.readers.commerce.preview_refund(
                        commerce.order_id,
                        commerce.currency,
                        {line.line_id: line.quantity for line in commerce.lines},
                    )
                except CapabilityError as exc:
                    limitation = str(exc)
                if preview is not None and preview.total_minor != commerce.total_minor:
                    raise ProviderContractError("Whole-order preview differs from the observed order total")
        # Detect edits during a joined read; this is not an atomic write fence.
        if self.readers.commerce.read_commerce(binding.woo_order_id).revision != commerce.revision:
            raise ProviderContractError("WooCommerce changed during observation; capture again")
        if self.readers.shipping.read_shipping(binding.shipstation_order_id).revision != shipping.revision:
            raise ProviderContractError("ShipStation changed during observation; capture again")
        return LiveSnapshot(
            binding=binding,
            commerce=commerce,
            payment=payment,
            shipping=shipping,
            labels=labels,
            refund_preview=preview,
            preview_limitation=limitation,
            provenance=self.readers.provenance,
        )

    def prepare(
        self,
        case_id: str,
        binding: IdentityBinding,
        flow: Literal["cancel", "address"],
        target_address: WooShippingAddress | None = None,
    ) -> dict[str, Any]:
        if flow not in {"cancel", "address"}:
            raise LiveReviewError("Only cancellation and address review are supported")
        resource = f"{binding.store_id}/{binding.woo_order_id}"
        with self._lock(resource):
            with self._connect() as conn:
                pending = any(
                    json.loads(row[0])["status"] == "uncertain"
                    for row in conn.execute(
                        "SELECT h.data FROM review_handoffs h JOIN review_proposals p ON p.id=h.proposal_id WHERE p.resource_id=?",
                        (resource,),
                    )
                )
            if pending:
                raise LiveReviewError(
                    "An external handoff is uncertain; reconcile it before making another proposal"
                )
            snapshot = self._capture(binding, refund_preview=flow == "cancel")
            if flow == "address":
                if target_address is None or snapshot.commerce.shipping_address is None:
                    raise LiveReviewError(
                        "Address review requires complete current and operator-confirmed target postal fields"
                    )
                if target_address.country != snapshot.commerce.shipping_address.country:
                    raise CapabilityError("Cross-border address recovery is outside this profile")
                if snapshot.payment.refunds or snapshot.commerce.status != "processing":
                    raise CapabilityError("Refunded or non-processing orders require manual address review")
            proposal_id = "live-" + uuid4().hex
            actions: list[LiveAction] = []

            def add(
                kind: str,
                provider: Any,
                method: Any = None,
                path: str | None = None,
                body: dict[str, Any] | None = None,
                **extra: Any,
            ) -> None:
                actions.append(
                    LiveAction(
                        id=f"{proposal_id}-{len(actions) + 1}",
                        kind=kind,
                        provider=provider,
                        method=method,
                        path=path,
                        body=body,
                        **extra,
                    )
                )

            for label in snapshot.labels:
                if not label.voided:
                    add(
                        "void_label",
                        "shipstation_v2",
                        "PUT",
                        f"/v2/labels/{label.label_id}/void",
                        {},
                        provider_resource_id=label.label_id,
                        limitations=(
                            "Carrier eligibility/refund settlement is unverified; void is irreversible.",
                        ),
                    )
            order_path = f"/wp-json/wc/v3/orders/{binding.woo_order_id}"
            if flow == "cancel":
                if snapshot.commerce.status != "cancelled":
                    add(
                        "cancel_order",
                        "woocommerce",
                        "PUT",
                        order_path,
                        {"status": "cancelled"},
                        provider_resource_id=binding.woo_order_id,
                        limitations=(
                            "Woo status does not establish ShipStation cancellation or a physical stop.",
                        ),
                    )
                if snapshot.refund_preview is not None:
                    preview = snapshot.refund_preview
                    add(
                        "refund",
                        "woocommerce",
                        "POST",
                        order_path + "/refunds",
                        {
                            "amount": _money(preview.total_minor),
                            "compute_totals": True,
                            "api_refund": True,
                            "api_restock": False,
                            "reason": f"ParcelResolve operator review {proposal_id}",
                            "line_items": [
                                {"id": int(key), "quantity": qty}
                                for key, qty in preview.line_quantities.items()
                            ],
                            "meta_data": [{"key": "parcelresolve_proposal", "value": proposal_id}],
                        },
                        amount_minor=preview.total_minor,
                        currency=preview.currency,
                        limitations=(
                            "Gateway capture/settlement and merchant stock policy require verification.",
                            "Metadata is a correlation reference, not a provider idempotency key.",
                        ),
                    )
                elif (
                    sum(item.amount_minor for item in snapshot.payment.refunds)
                    < snapshot.commerce.total_minor
                ):
                    add(
                        "refund_review",
                        "woocommerce",
                        limitations=(
                            snapshot.preview_limitation
                            or "Existing refund allocation requires operator review.",
                        ),
                    )
            else:
                assert target_address is not None
                add(
                    "update_address",
                    "woocommerce",
                    "PUT",
                    order_path,
                    {"shipping": target_address.model_dump()},
                    provider_resource_id=binding.woo_order_id,
                    limitations=(
                        "This changes Woo postal fields only; it does not recreate or redirect a label.",
                    ),
                )
                add(
                    "replacement_label_review",
                    "shipstation_v2",
                    limitations=(
                        "A verified V2 shipment address, carrier/service/package contract and exact approved purchase price are required.",
                        "No label-purchase payload is invented from the V1 order or old label.",
                    ),
                )
            add(
                "shipping_status_review",
                "shipstation_v1",
                limitations=(
                    "V1 createorder requires a complete resource; shipped/cancelled orders cannot be patched through it.",
                ),
            )
            add(
                "physical_stop_review",
                "warehouse",
                limitations=("No live warehouse acknowledgment contract is configured.",),
            )
            at = datetime.now(UTC)
            proposal = LiveProposal(
                id=proposal_id,
                case_id=case_id,
                flow=flow,
                snapshot=snapshot,
                resource_version=snapshot.resource_version,
                actions=tuple(actions),
                target_address=target_address,
                blockers=BLOCKERS
                + ("Label inventory completeness and gateway settlement remain unverified.",),
                created_at=at.isoformat(),
                expires_at=(at + timedelta(minutes=15)).isoformat(),
                proposal_hash="",
            )
            proposal = proposal.model_copy(update={"proposal_hash": proposal.calculated_hash()})
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO review_proposals VALUES (?,?,?,?,?)",
                    (
                        proposal.id,
                        case_id,
                        resource,
                        "prepared",
                        proposal.model_dump_json(),
                    ),
                )
            self._event(
                proposal.id,
                "proposal_prepared",
                provenance=snapshot.provenance,
                resource_version=proposal.resource_version,
                provider_writes=0,
            )
            return self.inspect(proposal.id)

    def _current(self, proposal: LiveProposal) -> LiveSnapshot:
        if self.inspect(proposal.id)["state"] == "stale":
            raise LiveReviewError("Live proposal is stale; capture and review a new proposal")
        if datetime.now(UTC) >= datetime.fromisoformat(proposal.expires_at):
            self._state(proposal.id, "stale")
            raise LiveReviewError("Live proposal expired; capture and review a new proposal")
        snapshot = self._capture(proposal.snapshot.binding, refund_preview=proposal.flow == "cancel")
        if snapshot.resource_version != proposal.resource_version:
            self._state(proposal.id, "stale")
            self._event(proposal.id, "approval_invalidated", reason="Provider resource version changed")
            raise LiveReviewError(
                "Provider state changed; prior approvals cannot authorize this resource version"
            )
        return snapshot

    def approve(
        self, proposal_id: str, expected_hash: str, role: Literal["owner", "operator"], token: str
    ) -> dict[str, Any]:
        proposal = self._proposal(proposal_id)
        actor = self.access.authenticate(token, role, proposal.snapshot.binding.store_id)
        with self._lock(f"{proposal.snapshot.binding.store_id}/{proposal.snapshot.binding.woo_order_id}"):
            if self.inspect(proposal.id)["handoffs"]:
                raise LiveReviewError("A handoff has been recorded; approvals cannot reset its outcome")
            if expected_hash != proposal.proposal_hash:
                raise LiveReviewError("Approval hash does not match the exact live proposal")
            self._current(proposal)
            approval = {
                "case_id": proposal.case_id,
                "proposal_hash": proposal.proposal_hash,
                "resource_version": proposal.resource_version,
                "actor_id": actor,
                "role": role,
                "at": _now(),
                "actions": [
                    {
                        "id": item.id,
                        "action_hash": item.action_hash,
                        "amount_minor": item.amount_minor,
                        "currency": item.currency,
                    }
                    for item in proposal.actions
                ],
                "scope": "reviewed request artifacts; unsupported live recovery stays blocked",
            }
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO review_approvals VALUES (?,?,?) ON CONFLICT(proposal_id,role) DO UPDATE SET data=excluded.data",
                    (
                        proposal.id,
                        role,
                        json.dumps(approval),
                    ),
                )
            self._event(
                proposal.id,
                "owner_authorization" if role == "owner" else "product_approval",
                actor_id=actor,
                proposal_hash=proposal.proposal_hash,
                resource_version=proposal.resource_version,
            )
            self._state(
                proposal.id,
                "approved" if len(self.inspect(proposal.id)["approvals"]) == 2 else "partially-approved",
            )
            return self.inspect(proposal.id)

    def _approved(self, proposal: LiveProposal) -> bool:
        expected_actions = [
            {
                "id": item.id,
                "action_hash": item.action_hash,
                "amount_minor": item.amount_minor,
                "currency": item.currency,
            }
            for item in proposal.actions
        ]
        approvals = self.inspect(proposal.id)["approvals"]
        return {item["role"] for item in approvals} == {"owner", "operator"} and all(
            item["case_id"] == proposal.case_id
            and item["proposal_hash"] == proposal.proposal_hash
            and item["resource_version"] == proposal.resource_version
            and item["actions"] == expected_actions
            and item["actor_id"]
            == (self.access.owner_id if item["role"] == "owner" else self.access.operator_id)
            for item in approvals
        )

    def dry_run(self, proposal_id: str, token: str) -> dict[str, Any]:
        proposal = self._proposal(proposal_id)
        self.access.authenticate(token, "operator", proposal.snapshot.binding.store_id)
        with self._lock(f"{proposal.snapshot.binding.store_id}/{proposal.snapshot.binding.woo_order_id}"):
            self._current(proposal)
            report = {
                "mode": "dry-run",
                "provenance": proposal.snapshot.provenance,
                "proposal_id": proposal.id,
                "case_id": proposal.case_id,
                "proposal_hash": proposal.proposal_hash,
                "resource_version": proposal.resource_version,
                "owner_and_product_approved": self._approved(proposal),
                "configuration_allows_mutations": self.access.allow_mutations,
                "provider_writes": 0,
                "execution_supported": False,
                "recovery_verified": False,
                "blockers": list(proposal.blockers),
                "requests": [item.model_dump(mode="json") for item in proposal.actions],
            }
            self._event(
                proposal.id,
                "dry_run",
                owner_and_product_approved=report["owner_and_product_approved"],
                provider_writes=0,
            )
            return report

    def execute(self, proposal_id: str, token: str) -> NoReturn:
        proposal = self._proposal(proposal_id)
        self.access.authenticate(token, "operator", proposal.snapshot.binding.store_id)
        with self._lock(f"{proposal.snapshot.binding.store_id}/{proposal.snapshot.binding.woo_order_id}"):
            if any(item["status"] == "uncertain" for item in self.inspect(proposal.id)["handoffs"]):
                raise LiveReviewError(
                    "An external handoff is uncertain; reconcile before considering any further action"
                )
            if not self.access.allow_mutations:
                raise CapabilityError("Live mutations are disabled by PARCELRESOLVE_ALLOW_LIVE_MUTATIONS")
            if not self._approved(proposal):
                raise LiveReviewError("Separate owner authorization and product approval are required")
            self._current(proposal)
            self._state(proposal.id, "blocked")
            self._event(proposal.id, "execution_blocked", provider_writes=0, blockers=list(proposal.blockers))
            raise CapabilityError("Live recovery execution is unsupported: " + " ".join(proposal.blockers))

    def record_external_handoff(
        self, proposal_id: str, action_id: str, token: str, provider_id: str | None = None
    ) -> dict[str, Any]:
        """Record an operator report, not permission or evidence of an external effect."""
        proposal = self._proposal(proposal_id)
        actor = self.access.authenticate(token, "operator", proposal.snapshot.binding.store_id)
        with self._lock(f"{proposal.snapshot.binding.store_id}/{proposal.snapshot.binding.woo_order_id}"):
            action = next((item for item in proposal.actions if item.id == action_id), None)
            if action is None or action.method is None:
                raise CapabilityError("Only a concrete reviewed request can have an external handoff record")
            if not self._approved(proposal):
                raise LiveReviewError(
                    "Owner authorization and product approval must precede a handoff record"
                )
            data = {
                "action_id": action.id,
                "action_hash": action.action_hash,
                "status": "uncertain",
                "reported_provider_id": provider_id,
                "reported_by": actor,
                "reported_at": _now(),
                "source": "operator report",
                "desk_provider_writes": 0,
            }
            with self._connect() as conn:
                try:
                    conn.execute(
                        "INSERT INTO review_handoffs VALUES (?,?,?)",
                        (proposal.id, action.id, json.dumps(data)),
                    )
                    conn.execute("UPDATE review_proposals SET state='uncertain' WHERE id=?", (proposal.id,))
                except sqlite3.IntegrityError:
                    raise LiveReviewError(
                        "This handoff already has a durable record; reconcile rather than replace it"
                    ) from None
            self._event(
                proposal.id,
                "external_handoff_reported",
                action_id=action.id,
                actor_id=actor,
                desk_provider_writes=0,
            )
            return self.inspect(proposal.id)

    def reconcile(self, proposal_id: str, token: str) -> dict[str, Any]:
        proposal = self._proposal(proposal_id)
        self.access.authenticate(token, "operator", proposal.snapshot.binding.store_id)
        with self._lock(f"{proposal.snapshot.binding.store_id}/{proposal.snapshot.binding.woo_order_id}"):
            snapshot = self._capture(proposal.snapshot.binding, refund_preview=False)
            handoffs = self.inspect(proposal.id)["handoffs"]
            if not handoffs:
                raise LiveReviewError("No external handoff has been reported")
            uncertain = False
            for handoff in handoffs:
                action = next(item for item in proposal.actions if item.id == handoff["action_id"])
                established = False
                if action.kind == "cancel_order":
                    established = snapshot.commerce.status == "cancelled"
                elif action.kind == "update_address":
                    established = snapshot.commerce.shipping_address == proposal.target_address
                elif action.kind == "void_label":
                    established = any(
                        item.label_id == action.provider_resource_id and item.voided
                        for item in snapshot.labels
                    )
                elif action.kind == "refund" and handoff.get("reported_provider_id"):
                    established = any(
                        item.refund_id == handoff["reported_provider_id"]
                        and item.amount_minor == action.amount_minor
                        and item.currency == action.currency
                        and item.refunded_payment
                        and {line.order_line_id: line.quantity for line in item.lines}
                        == {line.line_id: line.quantity for line in proposal.snapshot.commerce.lines}
                        for item in snapshot.payment.refunds
                    )
                handoff.update(
                    {
                        "status": "provider_state_observed" if established else "uncertain",
                        "reconciled_at": _now(),
                        "observed_resource_version": snapshot.resource_version,
                        "provider_writes": 0,
                        "retry_authorized": False,
                        "attribution_verified": False,
                        "warehouse_stop_verified": False,
                        "settlement_verified": False,
                    }
                )
                uncertain |= not established
            with self._connect() as conn:
                for handoff in handoffs:
                    conn.execute(
                        "UPDATE review_handoffs SET data=? WHERE proposal_id=? AND action_id=?",
                        (
                            json.dumps(handoff),
                            proposal.id,
                            handoff["action_id"],
                        ),
                    )
                conn.execute(
                    "UPDATE review_proposals SET state=? WHERE id=?",
                    (
                        "uncertain" if uncertain else "operator-review",
                        proposal.id,
                    ),
                )
                conn.execute(
                    "INSERT INTO review_events(proposal_id,data) VALUES (?,?)",
                    (
                        proposal.id,
                        json.dumps(
                            {
                                "at": _now(),
                                "kind": "read_only_reconciliation",
                                "unresolved": uncertain,
                                "provider_writes": 0,
                                "observation": snapshot.model_dump(mode="json"),
                                "message": "Observed resource states do not prove who caused them, settlement, or a warehouse stop. No retry authorized.",
                            }
                        ),
                    ),
                )
            return self.inspect(proposal.id)

    def inspect(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposal(proposal_id)
        with self._connect() as conn:
            state = conn.execute("SELECT state FROM review_proposals WHERE id=?", (proposal_id,)).fetchone()[
                0
            ]
            approvals = [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT data FROM review_approvals WHERE proposal_id=? ORDER BY role", (proposal_id,)
                )
            ]
            handoffs = [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT data FROM review_handoffs WHERE proposal_id=? ORDER BY action_id", (proposal_id,)
                )
            ]
            events = [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT data FROM review_events WHERE proposal_id=? ORDER BY seq", (proposal_id,)
                )
            ]
        return {
            "proposal": proposal.model_dump(mode="json"),
            "state": state,
            "approvals": approvals,
            "handoffs": handoffs,
            "events": events,
            "provider_writes": 0,
            "recovery_verified": False,
        }


def capabilities() -> dict[str, Any]:
    return {
        "mode": "offline capability report",
        "documentation_reviewed_on": DOCUMENTATION_DATE,
        "live_validation": "not_run",
        "provider_writes": 0,
        "live_recovery_execution": "unsupported",
        "supported": [
            "verified-resource observations",
            "Woo 11.1 capability discovery and non-mutating refund preview",
            "durable request artifacts",
            "owner authorization",
            "bound product approvals",
            "fresh dry-run",
            "operator-reported handoff reconciliation",
        ],
        "blockers": list(BLOCKERS),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ParcelResolve guarded live review; no provider mutation transport"
    )
    parser.add_argument(
        "command",
        choices=[
            "capabilities",
            "prepare",
            "inspect",
            "owner-authorize",
            "approve",
            "dry-run",
            "execute",
            "record-handoff",
            "reconcile",
        ],
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path(os.getenv("PARCELRESOLVE_LIVE_REVIEW_DIR", ".parcelresolve-live-review")),
    )
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--address", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument("--flow", choices=["cancel", "address"], default="cancel")
    parser.add_argument("--proposal-id")
    parser.add_argument("--proposal-hash")
    parser.add_argument("--action-id")
    parser.add_argument("--provider-id")
    parser.add_argument("--token-env", default="PARCELRESOLVE_REVIEW_SUBMITTED_TOKEN")
    args = parser.parse_args()
    if args.command == "capabilities":
        print(json.dumps(capabilities(), indent=2))
        return
    review = None
    try:
        if args.command == "inspect":
            review = LiveReview(args.directory, None, LiveAccess("", "", "", "", ""))
        else:
            review = LiveReview.from_env(args.directory)
        token = os.getenv(args.token_env, "")
        if args.command == "prepare":
            if not args.binding or not args.case_id:
                raise LiveReviewError("prepare requires --binding and --case-id")
            binding = IdentityBinding.model_validate_json(args.binding.read_text())
            address = (
                WooShippingAddress.model_validate_json(args.address.read_text()) if args.address else None
            )
            result = review.prepare(args.case_id, binding, args.flow, address)
        else:
            if not args.proposal_id:
                raise LiveReviewError("This command requires --proposal-id")
            if args.command == "inspect":
                result = review.inspect(args.proposal_id)
            elif args.command in {"owner-authorize", "approve"}:
                if not args.proposal_hash:
                    raise LiveReviewError("Approval requires the exact --proposal-hash")
                result = review.approve(
                    args.proposal_id,
                    args.proposal_hash,
                    "owner" if args.command == "owner-authorize" else "operator",
                    token,
                )
            elif args.command == "record-handoff":
                if not args.action_id:
                    raise LiveReviewError("Handoff requires --action-id")
                result = review.record_external_handoff(
                    args.proposal_id, args.action_id, token, args.provider_id
                )
            else:
                result = getattr(review, args.command.replace("-", "_"))(args.proposal_id, token)
        print(json.dumps(result, indent=2))
    except sqlite3.Error:
        parser.exit(
            2,
            json.dumps(
                {"status": "blocked", "detail": "Live review ledger unavailable", "provider_writes": 0}
            )
            + "\n",
        )
    except ValidationError:
        parser.exit(
            2,
            json.dumps(
                {"status": "blocked", "detail": "Invalid live-review document fields", "provider_writes": 0}
            )
            + "\n",
        )
    except (RuntimeError, ValueError, OSError) as exc:
        # Provider errors are already bounded and do not contain credentials or raw bodies.
        parser.exit(2, json.dumps({"status": "blocked", "detail": str(exc), "provider_writes": 0}) + "\n")
    finally:
        if review is not None and review.readers is not None:
            review.readers.close()


if __name__ == "__main__":
    main()
