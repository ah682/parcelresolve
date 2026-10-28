"""Synthetic HTTP contracts for the separate merchant review profile.

These do not establish an authenticated merchant/carrier/warehouse integration.
Every handler rejects a provider mutation, including with all approvals present.
"""

import json
import sqlite3
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from parcelresolve.guarded_live import (
    LiveAccess,
    LiveProposal,
    LiveReaders,
    LiveReview,
    LiveReviewError,
    capabilities,
    main,
)
from parcelresolve.integrations import (
    CapabilityError,
    IdentityBinding,
    ProviderContractError,
    ProviderUnavailable,
    ShipStationV1Adapter,
    ShipStationV2Adapter,
    WooCommerceAdapter,
    WooShippingAddress,
)

OWNER = "synthetic-owner-token-with-more-than-32-characters"
OPERATOR = "synthetic-operator-token-with-more-than-32-characters"


def postal() -> dict[str, str]:
    return {
        "first_name": "Ada Marie",
        "last_name": "Lovelace",
        "address_1": "1 Example Road",
        "address_2": "",
        "city": "London",
        "state": "",
        "postcode": "SW1A 1AA",
        "country": "GB",
    }


def binding() -> IdentityBinding:
    return IdentityBinding.model_validate(
        {
            "store_id": "merchant-1",
            "woo_order_id": "1042",
            "woo_order_key": "wc_order_alpha",
            "shipstation_order_id": "8001",
            "shipstation_order_key": "import-1042",
            "shipstation_store_id": "7",
            "provenance": "synthetic fixture mapping; not a merchant validation",
            "lines": [
                {"woo_line_id": "311", "shipstation_item_id": "901", "shipstation_line_key": "woo-line-311"}
            ],
            "labels": [{"label_id": "se-111", "shipment_id": "se-222"}],
        }
    )


class ProviderFixture:
    def __init__(self) -> None:
        self.order: dict[str, Any] = {
            "id": 1042,
            "order_key": "wc_order_alpha",
            "status": "processing",
            "currency": "GBP",
            "total": "24.00",
            "date_modified_gmt": "2026-10-14T12:00:00",
            "date_paid_gmt": "2026-10-14T11:00:00",
            "refunds": [],
            "line_items": [{"id": 311, "sku": "MUG", "quantity": 2, "total": "20.00", "total_tax": "4.00"}],
            "shipping": postal(),
        }
        self.shipping: dict[str, Any] = {
            "orderId": 8001,
            "orderNumber": "1042",
            "orderKey": "import-1042",
            "orderStatus": "shipped",
            "modifyDate": "2026-10-14T12:00:00",
            "advancedOptions": {"storeId": 7},
            "items": [
                {
                    "orderItemId": 901,
                    "lineItemKey": "woo-line-311",
                    "sku": "MUG",
                    "quantity": 2,
                    "adjustment": False,
                }
            ],
        }
        self.label: dict[str, Any] = {
            "label_id": "se-111",
            "shipment_id": "se-222",
            "status": "completed",
            "voided": False,
            "tracking_number": "TRACK-1",
            "tracking_status": "unknown",
        }
        self.preview: dict[str, Any] = {
            "breakdown": {
                "products": {
                    "items": [
                        {"id": 311, "quantity": 2, "subtotal": "20.00", "tax": "4.00", "total": "24.00"}
                    ],
                    "subtotal": "20.00",
                    "tax": "4.00",
                    "total": "24.00",
                },
                "shipping": {"items": [], "subtotal": "0.00", "tax": "0.00", "total": "0.00"},
                "fees": {"items": [], "subtotal": "0.00", "tax": "0.00", "total": "0.00"},
            },
            "subtotal": "20.00",
            "tax": "4.00",
            "total": "24.00",
            "max_refundable": "24.00",
        }
        self.refunds: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.computed_refunds = True
        self.status = 200

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST":
            assert path == "/wp-json/wc/v3/orders/1042/refunds/preview", "Provider mutation attempted"
            assert json.loads(request.content) == {"line_items": [{"line_item_id": 311, "quantity": 2}]}
            data = self.preview
        elif request.method == "OPTIONS":
            assert path == "/wp-json/wc/v3/orders/1042/refunds"
            data = {
                "endpoints": [
                    {"methods": ["POST"], "args": {"compute_totals": {}} if self.computed_refunds else {}}
                ]
            }
        else:
            assert request.method == "GET", "Provider mutation attempted"
            assert not request.content
            paths: dict[str, Any] = {
                "/wp-json/wc/v3/orders/1042": self.order,
                "/wp-json/wc/v3/orders/1042/refunds": self.refunds,
                "/orders/8001": self.shipping,
                "/v2/labels/se-111": self.label,
            }
            assert path in paths
            data = paths[path]
        return httpx.Response(self.status, json=data, headers={"X-WP-TotalPages": "1"})

    def readers(self) -> LiveReaders:
        transport = httpx.MockTransport(self.handle)
        return LiveReaders(
            WooCommerceAdapter(
                "https://merchant.example",
                "fake-key",
                "fake-secret",
                store_id="merchant-1",
                transport=transport,
                sleep=lambda _: None,
            ),
            ShipStationV1Adapter("fake-key", "fake-secret", transport=transport, sleep=lambda _: None),
            ShipStationV2Adapter("fake-key", transport=transport, sleep=lambda _: None),
            provenance="mock_http",
        )


@pytest.fixture
def desk(tmp_path: Path) -> Any:
    fixture = ProviderFixture()
    review = LiveReview(
        tmp_path / "review",
        fixture.readers(),
        LiveAccess("merchant-1", "merchant-owner", "desk-operator", OWNER, OPERATOR, allow_reads=True),
    )
    yield review, fixture
    assert review.readers is not None
    review.readers.close()


def prepared(review: LiveReview, flow: str = "cancel") -> dict[str, Any]:
    if flow == "address":
        return review.prepare(
            "case-a", binding(), "address", WooShippingAddress(**{**postal(), "address_1": "2 Example Road"})
        )["proposal"]
    return review.prepare("case-a", binding(), "cancel")["proposal"]


def approve_both(review: LiveReview, proposal: dict[str, Any]) -> None:
    review.approve(proposal["id"], proposal["proposal_hash"], "owner", OWNER)
    review.approve(proposal["id"], proposal["proposal_hash"], "operator", OPERATOR)


def action(proposal: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(item for item in proposal["actions"] if item["kind"] == kind)


def test_cancel_review_builds_exact_documented_requests_without_effects(desk: Any) -> None:
    review, fixture = desk
    proposal = prepared(review)
    assert proposal["snapshot"]["provenance"] == "mock_http"
    assert proposal["snapshot"]["shipping"]["status"] == "shipped"
    assert proposal["snapshot"]["shipping"]["physical_dispatch"] == "unknown"
    assert proposal["snapshot"]["payment"]["settlement_verified"] is False
    assert action(proposal, "void_label")["path"] == "/v2/labels/se-111/void"
    assert action(proposal, "cancel_order")["body"] == {"status": "cancelled"}
    refund = action(proposal, "refund")
    assert refund["amount_minor"] == 2400 and refund["currency"] == "GBP"
    assert refund["body"]["amount"] == "24.00"
    assert refund["body"]["compute_totals"] is True
    assert refund["body"]["api_restock"] is False
    assert refund["body"]["line_items"] == [{"id": 311, "quantity": 2}]
    assert all(item["executable"] is False for item in proposal["actions"])
    assert action(proposal, "shipping_status_review")["method"] is None
    assert action(proposal, "physical_stop_review")["method"] is None
    assert review.inspect(proposal["id"])["recovery_verified"] is False
    assert not any(request.method in {"PUT", "DELETE"} for request in fixture.requests)


def test_approvals_bind_case_actions_resource_hash_version_and_exact_money(desk: Any) -> None:
    review, _ = desk
    proposal = prepared(review)
    approve_both(review, proposal)
    inspected = review.inspect(proposal["id"])
    assert inspected["state"] == "approved"
    assert {row["role"] for row in inspected["approvals"]} == {"owner", "operator"}
    for approval in inspected["approvals"]:
        assert approval["case_id"] == "case-a"
        assert approval["proposal_hash"] == proposal["proposal_hash"]
        assert approval["resource_version"] == proposal["resource_version"]
        approved_refund = next(
            row for row in approval["actions"] if row["id"] == action(proposal, "refund")["id"]
        )
        assert approved_refund["amount_minor"] == 2400 and approved_refund["currency"] == "GBP"
        assert len(approved_refund["action_hash"]) == 64
    report = review.dry_run(proposal["id"], OPERATOR)
    assert report["owner_and_product_approved"] is True
    assert report["execution_supported"] is False and report["provider_writes"] == 0
    serialized = json.dumps(inspected)
    assert OWNER not in serialized and OPERATOR not in serialized and "fake-secret" not in serialized


@pytest.mark.parametrize(
    "role,token,expected_hash",
    [("owner", OPERATOR, "correct"), ("operator", OWNER, "correct"), ("owner", OWNER, "wrong")],
)
def test_bad_approval_cannot_trigger_reads_or_write_approval(
    desk: Any, role: Any, token: str, expected_hash: str
) -> None:
    review, fixture = desk
    proposal = prepared(review)
    before = len(fixture.requests)
    with pytest.raises(LiveReviewError):
        review.approve(
            proposal["id"], proposal["proposal_hash"] if expected_hash == "correct" else "bad", role, token
        )
    assert len(fixture.requests) == before
    assert review.inspect(proposal["id"])["approvals"] == []


@pytest.mark.parametrize("field", ["order", "shipping", "label", "preview"])
def test_external_edits_invalidate_bound_approval(desk: Any, field: str) -> None:
    review, fixture = desk
    proposal = prepared(review)
    approve_both(review, proposal)
    if field == "order":
        fixture.order["shipping"]["address_1"] = "Elsewhere"
    elif field == "shipping":
        fixture.shipping["orderStatus"] = "cancelled"
    elif field == "label":
        fixture.label["voided"] = True
    else:
        fixture.preview["max_refundable"] = "25.00"
    with pytest.raises(LiveReviewError, match="changed"):
        review.dry_run(proposal["id"], OPERATOR)
    assert review.inspect(proposal["id"])["state"] == "stale"


def test_mutation_configuration_gate_precedes_network_and_cannot_enable_unsupported_execution(
    desk: Any,
) -> None:
    review, fixture = desk
    proposal = prepared(review)
    before = len(fixture.requests)
    with pytest.raises(CapabilityError, match="disabled"):
        review.execute(proposal["id"], OPERATOR)
    assert len(fixture.requests) == before
    review.access = replace(review.access, allow_mutations=True)
    with pytest.raises(LiveReviewError, match="authorization"):
        review.execute(proposal["id"], OPERATOR)
    assert len(fixture.requests) == before
    approve_both(review, proposal)
    with pytest.raises(CapabilityError, match="unsupported"):
        review.execute(proposal["id"], OPERATOR)
    inspected = review.inspect(proposal["id"])
    assert inspected["state"] == "blocked" and inspected["provider_writes"] == 0
    assert inspected["events"][-1]["kind"] == "execution_blocked"


def test_invalidated_proposal_cannot_reactivate_when_provider_state_returns(desk: Any) -> None:
    review, fixture = desk
    proposal = prepared(review)
    approve_both(review, proposal)
    fixture.label["voided"] = True
    with pytest.raises(LiveReviewError, match="changed"):
        review.dry_run(proposal["id"], OPERATOR)
    fixture.label["voided"] = False
    before = len(fixture.requests)
    with pytest.raises(LiveReviewError, match="stale"):
        review.approve(proposal["id"], proposal["proposal_hash"], "owner", OWNER)
    assert len(fixture.requests) == before


def test_disabled_reads_wrong_merchant_and_invalid_flow_fail_before_transport(desk: Any) -> None:
    review, fixture = desk
    with pytest.raises(LiveReviewError, match="merchant"):
        review.prepare("case-a", binding().model_copy(update={"store_id": "other"}), "cancel")
    with pytest.raises(LiveReviewError, match="Only cancellation"):
        review.prepare("case-a", binding(), "ship")
    review.access = replace(review.access, allow_reads=False)
    with pytest.raises(CapabilityError, match="disabled"):
        prepared(review)
    assert fixture.requests == []


def test_identity_mismatch_does_not_make_a_proposal(desk: Any) -> None:
    review, fixture = desk
    fixture.shipping["orderKey"] = "wrong-store-import"
    with pytest.raises(ProviderContractError, match="identity"):
        prepared(review)
    with sqlite3.connect(review.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM review_proposals").fetchone()[0] == 0


@pytest.mark.parametrize("provider", ["woocommerce", "shipstation"])
def test_edits_between_joined_reads_are_detected_before_persisting_proposal(
    tmp_path: Path, provider: str
) -> None:
    fixture = ProviderFixture()
    original = fixture.handle
    reads = 0

    def changing(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        selected = "/wp-json/wc/v3/orders/1042" if provider == "woocommerce" else "/orders/8001"
        if request.method == "GET" and request.url.path == selected:
            reads += 1
            if reads == 2:
                if provider == "woocommerce":
                    fixture.order["date_modified_gmt"] = "2026-10-14T12:01:00"
                else:
                    fixture.shipping["orderStatus"] = "cancelled"
        return original(request)

    fixture.handle = changing
    review = LiveReview(
        tmp_path,
        fixture.readers(),
        LiveAccess("merchant-1", "owner", "operator", OWNER, OPERATOR, allow_reads=True),
    )
    try:
        with pytest.raises(ProviderContractError, match="changed during observation"):
            prepared(review)
        with sqlite3.connect(review.path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM review_proposals").fetchone()[0] == 0
    finally:
        assert review.readers is not None
        review.readers.close()


def test_whole_order_refund_preview_must_match_observed_commerce_money(desk: Any) -> None:
    review, fixture = desk
    fixture.preview["total"] = "12.00"
    fixture.preview["subtotal"] = "10.00"
    fixture.preview["tax"] = "2.00"
    fixture.preview["breakdown"]["products"].update({"subtotal": "10.00", "tax": "2.00", "total": "12.00"})
    fixture.preview["breakdown"]["products"]["items"][0].update(
        {"subtotal": "10.00", "tax": "2.00", "total": "12.00"}
    )
    with pytest.raises(ProviderContractError, match="observed order total"):
        prepared(review)


def test_live_service_failure_has_no_success_shaped_review(desk: Any) -> None:
    review, fixture = desk
    fixture.status = 401
    with pytest.raises(ProviderUnavailable):
        prepared(review)
    assert len(fixture.requests) == 1


def test_older_woo_gets_manual_refund_review_without_zero_amount_payload(desk: Any) -> None:
    review, fixture = desk
    fixture.computed_refunds = False
    proposal = prepared(review)
    assert action(proposal, "refund_review")["body"] is None
    assert not any(row["kind"] == "refund" for row in proposal["actions"])
    assert not any(request.method == "POST" for request in fixture.requests)


def test_fee_allocation_stays_manual_instead_of_inventing_refund_totals(desk: Any) -> None:
    review, fixture = desk
    fixture.order["total"] = "29.00"
    proposal = prepared(review)
    assert action(proposal, "refund_review")["amount_minor"] is None
    assert not any(request.method == "POST" for request in fixture.requests)


def test_address_review_is_woo_postal_fields_only_with_manual_replacement(desk: Any) -> None:
    review, fixture = desk
    proposal = prepared(review, "address")
    assert action(proposal, "update_address")["body"] == {
        "shipping": {**postal(), "address_1": "2 Example Road"}
    }
    assert action(proposal, "replacement_label_review")["method"] is None
    assert not any(request.method == "POST" for request in fixture.requests)
    assert not any(row["kind"] == "refund" for row in proposal["actions"])


def test_cross_border_address_is_explicitly_unsupported(desk: Any) -> None:
    review, _ = desk
    with pytest.raises(CapabilityError, match="Cross-border"):
        review.prepare("case-a", binding(), "address", WooShippingAddress(**{**postal(), "country": "US"}))


def test_external_handoff_is_durable_uncertain_and_cannot_be_reset_or_replayed(desk: Any) -> None:
    review, fixture = desk
    proposal = prepared(review)
    approve_both(review, proposal)
    cancel = action(proposal, "cancel_order")
    review.record_external_handoff(proposal["id"], cancel["id"], OPERATOR)
    restarted = LiveReview(review.directory, review.readers, replace(review.access, allow_mutations=True))
    assert restarted.inspect(proposal["id"])["state"] == "uncertain"
    before = len(fixture.requests)
    with pytest.raises(LiveReviewError, match="uncertain"):
        restarted.execute(proposal["id"], OPERATOR)
    with pytest.raises(LiveReviewError, match="uncertain"):
        prepared(restarted)
    with pytest.raises(LiveReviewError, match="cannot reset"):
        restarted.approve(proposal["id"], proposal["proposal_hash"], "owner", OWNER)
    with pytest.raises(LiveReviewError, match="durable record"):
        restarted.record_external_handoff(proposal["id"], cancel["id"], OPERATOR)
    assert len(fixture.requests) == before
    unresolved = restarted.reconcile(proposal["id"], OPERATOR)
    assert unresolved["state"] == "uncertain"
    assert unresolved["handoffs"][0]["retry_authorized"] is False
    fixture.order["status"] = "cancelled"
    observed = restarted.reconcile(proposal["id"], OPERATOR)
    assert observed["state"] == "operator-review" and observed["recovery_verified"] is False
    assert observed["handoffs"][0]["status"] == "provider_state_observed"
    assert observed["events"][-1]["observation"]["commerce"]["status"] == "cancelled"
    assert len(observed["handoffs"][0]["observed_resource_version"]) == 64
    for field in (
        "retry_authorized",
        "attribution_verified",
        "warehouse_stop_verified",
        "settlement_verified",
    ):
        assert observed["handoffs"][0][field] is False
    assert restarted.reconcile(proposal["id"], OPERATOR)["provider_writes"] == 0


def test_uncertain_handoff_blocks_new_proposals_even_if_summary_state_was_lost(desk: Any) -> None:
    review, _ = desk
    proposal = prepared(review)
    approve_both(review, proposal)
    review.record_external_handoff(proposal["id"], action(proposal, "cancel_order")["id"], OPERATOR)
    with sqlite3.connect(review.path) as conn:
        conn.execute("UPDATE review_proposals SET state='approved'")
    with pytest.raises(LiveReviewError, match="uncertain"):
        prepared(review)


def test_readback_evidence_and_handoff_state_commit_together(desk: Any) -> None:
    review, fixture = desk
    proposal = prepared(review)
    approve_both(review, proposal)
    review.record_external_handoff(proposal["id"], action(proposal, "cancel_order")["id"], OPERATOR)
    fixture.order["status"] = "cancelled"
    with sqlite3.connect(review.path) as conn:
        conn.execute("""CREATE TRIGGER fail_reconciliation_evidence BEFORE INSERT ON review_events
            WHEN NEW.data LIKE '%read_only_reconciliation%'
            BEGIN SELECT RAISE(ABORT, 'synthetic ledger failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic ledger failure"):
        review.reconcile(proposal["id"], OPERATOR)
    restarted = LiveReview(review.directory, review.readers, review.access)
    result = restarted.inspect(proposal["id"])
    assert result["state"] == result["handoffs"][0]["status"] == "uncertain"
    with pytest.raises(LiveReviewError, match="uncertain"):
        prepared(restarted)


@pytest.mark.parametrize(
    "provider_id,amount,quantity,paid,expected",
    [
        (None, "24.00", -2, True, "uncertain"),
        ("725", "24.00", -2, True, "uncertain"),
        ("724", "12.00", -2, True, "uncertain"),
        ("724", "24.00", -1, True, "uncertain"),
        ("724", "24.00", -2, False, "uncertain"),
        ("724", "24.00", -2, True, "provider_state_observed"),
    ],
)
def test_refund_handoff_requires_provider_id_money_lines_and_payment_record(
    desk: Any, provider_id: str | None, amount: str, quantity: int, paid: bool, expected: str
) -> None:
    review, fixture = desk
    proposal = prepared(review)
    approve_both(review, proposal)
    review.record_external_handoff(proposal["id"], action(proposal, "refund")["id"], OPERATOR, provider_id)
    fixture.order["refunds"] = [{"id": 724}]
    fixture.refunds = [
        {
            "id": 724,
            "amount": amount,
            "refunded_payment": paid,
            "line_items": [
                {"id": 999, "quantity": quantity, "meta_data": [{"key": "_refunded_item_id", "value": "311"}]}
            ],
        }
    ]
    observed = review.reconcile(proposal["id"], OPERATOR)
    handoff = observed["handoffs"][0]
    assert handoff["status"] == expected
    assert handoff["settlement_verified"] is False and handoff["retry_authorized"] is False
    assert observed["provider_writes"] == 0 and observed["recovery_verified"] is False


@pytest.mark.parametrize("kind", ["void_label", "update_address"])
def test_label_and_address_readback_do_not_claim_parcel_recovery(desk: Any, kind: str) -> None:
    review, fixture = desk
    proposal = prepared(review, "address")
    approve_both(review, proposal)
    review.record_external_handoff(proposal["id"], action(proposal, kind)["id"], OPERATOR)
    if kind == "void_label":
        fixture.label["voided"] = True
    else:
        fixture.order["shipping"]["address_1"] = "2 Example Road"
    result = review.reconcile(proposal["id"], OPERATOR)
    assert result["handoffs"][0]["status"] == "provider_state_observed"
    assert result["recovery_verified"] is False


def test_persisted_proposal_tampering_cannot_change_approved_money(desk: Any) -> None:
    review, _ = desk
    proposal = prepared(review)
    action(proposal, "refund")["amount_minor"] = 1
    with sqlite3.connect(review.path) as conn:
        conn.execute("UPDATE review_proposals SET data=?", (json.dumps(proposal),))
    with pytest.raises(LiveReviewError, match="integrity"):
        review.approve(proposal["id"], proposal["proposal_hash"], "owner", OWNER)


def test_approval_expiry_cannot_be_bypassed_by_unchanged_resource(desk: Any) -> None:
    review, fixture = desk
    proposal = LiveProposal.model_validate(prepared(review))
    proposal = proposal.model_copy(
        update={"expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
    )
    proposal = proposal.model_copy(update={"proposal_hash": proposal.calculated_hash()})
    with sqlite3.connect(review.path) as conn:
        conn.execute("UPDATE review_proposals SET data=?", (proposal.model_dump_json(),))
    before = len(fixture.requests)
    with pytest.raises(LiveReviewError, match="expired"):
        review.approve(proposal.id, proposal.proposal_hash, "owner", OWNER)
    assert len(fixture.requests) == before
    assert review.inspect(proposal.id)["state"] == "stale"


def test_per_resource_review_lock_prevents_conflicting_operators(desk: Any) -> None:
    review, _ = desk
    with review._lock("merchant-1/1042"), pytest.raises(LiveReviewError, match="Another operator"):
        prepared(review)


def test_capability_cli_is_offline_and_does_not_construct_provider_clients(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setattr(sys, "argv", ["guarded_live", "capabilities"])
    monkeypatch.setattr(LiveReview, "from_env", lambda _: pytest.fail("Offline report constructed a client"))
    main()
    report = json.loads(capsys.readouterr().out)
    assert report == capabilities()
    assert report["live_validation"] == "not_run" and report["live_recovery_execution"] == "unsupported"


def test_persisted_inspection_is_available_offline_without_credentials(
    desk: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    review, fixture = desk
    proposal = prepared(review)
    monkeypatch.setattr(
        sys,
        "argv",
        ["guarded_live", "inspect", "--directory", str(review.directory), "--proposal-id", proposal["id"]],
    )
    monkeypatch.setattr(
        LiveReview, "from_env", lambda _: pytest.fail("Offline inspection constructed a client")
    )
    before = len(fixture.requests)
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["proposal"]["proposal_hash"] == proposal["proposal_hash"]
    assert len(fixture.requests) == before
    assert review.path.stat().st_mode & 0o777 == 0o600


def test_live_factory_requires_explicit_read_gate_before_client_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PARCELRESOLVE_CONTRACT_READS", raising=False)
    monkeypatch.setattr(
        WooCommerceAdapter, "from_env", lambda: pytest.fail("Disabled live reads constructed a client")
    )
    with pytest.raises(CapabilityError, match="CONTRACT_READS"):
        LiveReview.from_env(tmp_path)
