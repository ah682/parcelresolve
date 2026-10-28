"""HTTP mock contract tests, not merchant/carrier integration validation."""

import copy
import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from parcelresolve.integrations import (
    CapabilityError,
    CommerceAdapter,
    IdentityBinding,
    LabelBinding,
    LineBinding,
    PaymentAdapter,
    ProviderContractError,
    ProviderUnavailable,
    ShippingAdapter,
    ShipStationV1Adapter,
    ShipStationV2Adapter,
    UnsupportedWarehouseAdapter,
    WooCommerceAdapter,
    WooShippingAddress,
    contract_checks,
    minor_units,
    verify_identity_binding,
)


def woo_order() -> dict[str, Any]:
    return {
        "id": 1042,
        "order_key": "wc_order_alpha",
        "status": "processing",
        "currency": "GBP",
        "total": "24.00",
        "date_modified_gmt": "2026-10-13T12:00:00",
        "date_paid_gmt": "2026-10-13T11:00:00",
        "refunds": [],
        "line_items": [{"id": 311, "sku": "MUG", "quantity": 2, "total": "20.00", "total_tax": "4.00"}],
    }


def ss_order() -> dict[str, Any]:
    return {
        "orderId": 8001,
        "orderNumber": "1042",
        "orderKey": "store-import-1042",
        "orderStatus": "shipped",
        "modifyDate": "2026-10-13T12:00:00",
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


def label_record() -> dict[str, Any]:
    return {
        "label_id": "se-111",
        "shipment_id": "se-222",
        "status": "completed",
        "voided": False,
        "tracking_number": "TRACK-1",
        "tracking_status": "unknown",
    }


def woo_client(data: dict[str, Any] | None = None) -> WooCommerceAdapter:
    return WooCommerceAdapter(
        "https://store.example",
        "test-key",
        "test-secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data or woo_order())),
    )


def refund_preview() -> dict[str, Any]:
    return {
        "breakdown": {
            "products": {
                "items": [{"id": 311, "quantity": 2, "subtotal": "20.00", "tax": "4.00", "total": "24.00"}],
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


def test_refund_preview_discovers_store_support_and_uses_preview_line_key() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "OPTIONS":
            assert request.url.path == "/wp-json/wc/v3/orders/1042/refunds"
            return httpx.Response(
                200,
                json={"endpoints": [{"methods": ["POST"], "args": {"compute_totals": {"type": "boolean"}}}]},
            )
        assert request.method == "POST" and request.url.path.endswith("/refunds/preview")
        assert json.loads(request.content) == {"line_items": [{"line_item_id": 311, "quantity": 2}]}
        return httpx.Response(200, json=refund_preview())

    adapter = WooCommerceAdapter(
        "https://store.example", "key", "secret", transport=httpx.MockTransport(handler)
    )
    result = adapter.preview_refund("1042", "GBP", {"311": 2})
    assert result.total_minor == result.max_refundable_minor == 2400
    assert result.line_quantities == {"311": 2} and result.compute_totals_supported is True
    assert [request.method for request in requests] == ["OPTIONS", "POST"]


@pytest.mark.parametrize(
    "methods,args",
    [
        (["GET"], {"compute_totals": {}}),
        (["POST"], {}),
        (None, {"compute_totals": {}}),
        ("POST", {"compute_totals": {}}),
    ],
)
def test_older_or_unadvertised_compute_totals_never_gets_preview(methods: Any, args: Any) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"endpoints": [{"methods": methods, "args": args}]})

    adapter = WooCommerceAdapter(
        "https://store.example", "key", "secret", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(CapabilityError, match="advertise"):
        adapter.preview_refund("1042", "GBP", {"311": 2})
    assert [request.method for request in requests] == ["OPTIONS"]


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-line",
        "quantity",
        "quantity-decimal",
        "duplicate",
        "zero",
        "over-remaining",
        "fraction",
        "line-sum",
        "grand-sum",
        "shipping",
    ],
)
def test_refund_preview_rejects_unsupported_or_inconsistent_data(mutation: str) -> None:
    data = refund_preview()
    items = data["breakdown"]["products"]["items"]
    if mutation == "wrong-line":
        items[0]["id"] = 777
    elif mutation == "quantity":
        items[0]["quantity"] = 1
    elif mutation == "quantity-decimal":
        items[0]["quantity"] = 2.0
    elif mutation == "duplicate":
        items.append(copy.deepcopy(items[0]))
    elif mutation == "zero":
        data["total"] = "0.00"
    elif mutation == "over-remaining":
        data["max_refundable"] = "12.00"
    elif mutation == "fraction":
        data["total"] = "24.001"
    elif mutation == "line-sum":
        items[0]["tax"] = "1.00"
    elif mutation == "grand-sum":
        data["tax"] = "1.00"
    else:
        data["breakdown"]["shipping"]["total"] = "1.00"

    adapter = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"endpoints": [{"methods": ["POST"], "args": {"compute_totals": {}}}]}
                if request.method == "OPTIONS"
                else data,
            )
        ),
    )
    with pytest.raises((CapabilityError, ProviderContractError)):
        adapter.preview_refund("1042", "GBP", {"311": 2})


@pytest.mark.parametrize(
    "currency,lines",
    [
        ("JPY", {"311": 2}),
        ("GBP", {}),
        ("GBP", {"../311": 2}),
        ("GBP", {"311": True}),
        ("GBP", {"311": 0}),
        ("GBP", {"311": 2.0}),
        ("GBP", {"311": Decimal("2")}),
        ("GBP", {311: 1, "311": 2}),
    ],
)
def test_bad_refund_preview_inputs_fail_before_network(currency: str, lines: Any) -> None:
    adapter = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(lambda _: pytest.fail("Invalid preview input reached transport")),
    )
    with pytest.raises((CapabilityError, ProviderContractError)):
        adapter.preview_refund("1042", currency, lines)


@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", "orders/1042"),
        ("DELETE", "orders/1042/refunds/9"),
        ("POST", "orders/1042/refunds"),
        ("POST", "orders/1042/refunds/preview/../"),
    ],
)
def test_read_transport_cannot_send_mutation_endpoints(method: str, path: str) -> None:
    adapter = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(lambda _: pytest.fail("Mutation reached read transport")),
    )
    with pytest.raises(CapabilityError, match="cannot issue"):
        adapter._read_request(method, path, body={})


def test_shipping_address_preserves_explicit_names_and_rejects_incomplete_postal_data() -> None:
    data = woo_order()
    data["shipping"] = {
        "first_name": "Ada Marie",
        "last_name": "Lovelace",
        "address_1": " 1 Example Road ",
        "address_2": "",
        "city": "London",
        "state": "",
        "postcode": "SW1A 1AA",
        "country": "GB",
        "phone": "ignored",
    }
    result = woo_client(data).read_commerce("1042").shipping_address
    assert result == WooShippingAddress(
        **{key: value for key, value in data["shipping"].items() if key != "phone"}
    )
    assert result.address_1 == "1 Example Road"
    data["shipping"]["address_1"] = "   "
    with pytest.raises(ProviderContractError, match="shipping address"):
        woo_client(data).read_commerce("1042")


def test_woo_uses_current_wp_rest_path_and_header_auth() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/shop/wp-json/wc/v3/orders/1042"
        assert request.method == "GET"
        assert request.headers["authorization"].startswith("Basic ")
        assert not request.url.query
        return httpx.Response(200, json=woo_order())

    adapter = WooCommerceAdapter(
        "https://store.example/shop/", "key", "secret", transport=httpx.MockTransport(handler)
    )
    order = adapter.read_commerce("1042")
    assert order.order_id == "1042" and order.order_key == "wc_order_alpha"
    assert order.total_minor == 2400 and order.lines[0].total_minor == 2000
    assert order.lines[0].tax_minor == 400 and order.lines[0].quantity == 2
    assert len(order.revision) == 64 and len(requests) == 1
    assert isinstance(adapter, CommerceAdapter)
    assert isinstance(adapter, PaymentAdapter)


@pytest.mark.parametrize("amount,expected", [("0.00", 0), ("12.10", 1210), (Decimal("0.01"), 1), (7, 700)])
def test_exact_minor_units(amount: Any, expected: int) -> None:
    assert minor_units(amount, "GBP") == expected


@pytest.mark.parametrize(
    "amount",
    [
        "0.001",
        "-1.00",
        "NaN",
        "Infinity",
        0.1,
        True,
        None,
        "x",
        "1e999999999",
        "0.00000000000000000000000000001",
        "92233720368547758.08",
    ],
)
def test_invalid_money_is_rejected_without_rounding(amount: Any) -> None:
    with pytest.raises(ProviderContractError):
        minor_units(amount, "GBP")


def test_unsupported_currency_fails_even_with_two_decimal_amount() -> None:
    with pytest.raises(CapabilityError, match="GBP"):
        minor_units("12.00", "JPY")


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, "2"])
def test_unsupported_quantities_are_not_coerced(quantity: Any) -> None:
    data = woo_order()
    data["line_items"][0]["quantity"] = quantity
    with pytest.raises(ProviderContractError, match="quantities"):
        woo_client(data).read_commerce("1042")


def test_refund_line_identity_uses_original_item_metadata_and_does_not_claim_settlement() -> None:
    order = woo_order()
    order["refunds"] = [{"id": 724, "total": "-12.00"}]
    refund = {
        "id": 724,
        "amount": "12.00",
        "refunded_payment": True,
        "line_items": [
            {"id": 999, "quantity": -1, "meta_data": [{"key": "_refunded_item_id", "value": "311"}]}
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/refunds"):
            assert request.url.params["per_page"] == "100"
            return httpx.Response(200, json=[refund], headers={"X-WP-TotalPages": "1"})
        return httpx.Response(200, json=order)

    payment = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(handler),
    ).read_payment("1042")
    assert payment.refunds[0].amount_minor == 1200
    line = payment.refunds[0].lines[0]
    assert line.refund_line_id == "999" and line.order_line_id == "311" and line.quantity == 1
    assert payment.refunds[0].refunded_payment is True
    assert payment.settlement_verified is False and payment.refunds[0].settlement_verified is False


def test_refunds_are_paginated_completely() -> None:
    order = woo_order()
    order["refunds"] = [{"id": n} for n in range(1, 102)]
    seen_pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/refunds"):
            return httpx.Response(200, json=order)
        page = int(request.url.params["page"])
        seen_pages.append(page)
        rows = [
            {"id": n, "amount": "0.01", "refunded_payment": False, "line_items": []}
            for n in (range(1, 101) if page == 1 else range(101, 102))
        ]
        return httpx.Response(200, json=rows, headers={"X-WP-TotalPages": "2"})

    payment = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(handler),
    ).read_payment("1042")
    assert seen_pages == [1, 2] and len(payment.refunds) == 101


def test_refund_mapping_missing_does_not_guess_by_sku_or_refund_line_id() -> None:
    order = woo_order()
    order["refunds"] = [{"id": 724}]
    refund = {
        "id": 724,
        "amount": "1.00",
        "refunded_payment": False,
        "line_items": [{"id": 311, "sku": "MUG", "quantity": -1, "meta_data": []}],
    }
    adapter = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=[refund] if r.url.path.endswith("refunds") else order)
        ),
    )
    with pytest.raises(CapabilityError, match="mapping"):
        adapter.read_payment("1042")


def test_inconsistent_refund_reads_require_reread() -> None:
    adapter = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json=[{"id": 724, "amount": "1.00", "refunded_payment": False, "line_items": []}]
                if r.url.path.endswith("refunds")
                else woo_order(),
            )
        ),
    )
    with pytest.raises(ProviderContractError, match="disagree"):
        adapter.read_payment("1042")


def test_shipstation_v1_identity_and_shipped_status_are_not_physical_dispatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://ssapi.shipstation.com/orders/8001"
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, json=ss_order())

    adapter = ShipStationV1Adapter("key", "secret", transport=httpx.MockTransport(handler))
    order = adapter.read_shipping("8001")
    assert order.order_id == "8001" and order.order_key == "store-import-1042" and order.store_id == "7"
    assert order.status == "shipped" and order.physical_dispatch == "unknown"
    assert order.warehouse_hold_verified is False
    assert isinstance(adapter, ShippingAdapter)


def test_shipstation_v2_uses_own_ids_endpoint_and_key_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.shipstation.com/v2/labels/se-111"
        assert request.headers["api-key"] == "test-v2-key"
        assert "authorization" not in request.headers
        return httpx.Response(200, json=label_record())

    label = ShipStationV2Adapter("test-v2-key", transport=httpx.MockTransport(handler)).read_label("se-111")
    assert label.label_id == "se-111" and label.shipment_id == "se-222"
    assert label.status == "completed" and label.voided is False
    assert label.physical_dispatch == "unknown"


@pytest.mark.parametrize("label_id", ["8001", "../labels/se-1", "se-1?secret", "se-1/void"])
def test_v1_numeric_and_unsafe_ids_cannot_be_used_as_v2_label_ids(label_id: str) -> None:
    calls = []
    adapter = ShipStationV2Adapter("key", transport=httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(ProviderContractError):
        adapter.read_label(label_id)
    assert calls == []


def test_trusted_mapping_separates_all_id_namespaces_and_detects_quantities() -> None:
    woo = woo_client().read_commerce("1042")
    shipping = ShipStationV1Adapter(
        "key",
        "secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=ss_order())),
    ).read_shipping("8001")
    label = ShipStationV2Adapter(
        "key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=label_record())),
    ).read_label("se-111")
    binding = IdentityBinding(
        store_id="primary",
        woo_order_id="1042",
        woo_order_key="wc_order_alpha",
        shipstation_order_id="8001",
        shipstation_order_key="store-import-1042",
        shipstation_store_id="7",
        provenance="synthetic server-owned test registry",
        lines=(
            LineBinding(woo_line_id="311", shipstation_item_id="901", shipstation_line_key="woo-line-311"),
        ),
        labels=(LabelBinding(label_id="se-111", shipment_id="se-222"),),
    )
    verify_identity_binding(binding, woo, shipping, (label,))
    with pytest.raises(ProviderContractError, match="identity"):
        verify_identity_binding(
            binding.model_copy(update={"shipstation_order_key": "wc_order_alpha"}), woo, shipping, (label,)
        )
    with pytest.raises(ProviderContractError, match="shipment mapping"):
        verify_identity_binding(binding, woo, shipping)
    changed = shipping.model_copy(update={"lines": (shipping.lines[0].model_copy(update={"quantity": 1}),)})
    with pytest.raises(ProviderContractError, match="quantity"):
        verify_identity_binding(binding, woo, changed, (label,))


@pytest.mark.parametrize("mutated", ["id", "line"])
def test_wrong_or_duplicate_provider_identity_is_rejected(mutated: str) -> None:
    data = woo_order()
    if mutated == "id":
        data["id"] = 9999
    else:
        data["line_items"].append(copy.deepcopy(data["line_items"][0]))
    with pytest.raises(ProviderContractError):
        woo_client(data).read_commerce("1042")


def test_read_retries_rate_limit_but_returns_actual_final_data() -> None:
    calls, sleeps = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json=woo_order())

    adapter = WooCommerceAdapter(
        "https://store.example", "key", "secret", transport=httpx.MockTransport(handler), sleep=sleeps.append
    )
    assert adapter.read_commerce("1042").total_minor == 2400
    assert len(calls) == 3 and sleeps == [1.0, 1.0]
    assert all(r.method == "GET" for r in calls)


@pytest.mark.parametrize("header", ["Retry-After", "X-Rate-Limit-Reset"])
def test_declared_long_rate_limit_is_not_retried_early(header: str) -> None:
    calls, sleeps = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={header: "60"})

    adapter = WooCommerceAdapter(
        "https://store.example", "key", "secret", transport=httpx.MockTransport(handler), sleep=sleeps.append
    )
    with pytest.raises(ProviderUnavailable) as error:
        adapter.read_commerce("1042")
    assert error.value.retry_after_seconds == 60
    assert len(calls) == 1 and sleeps == []


@pytest.mark.parametrize("status,attempts", [(401, 1), (404, 1), (429, 3), (503, 3), (302, 1)])
def test_read_failure_is_explicit_and_never_leaks_provider_body(status: int, attempts: int) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status, text="SECRET PRIVATE CUSTOMER BODY", headers={"Location": "https://evil.example"}
        )

    adapter = WooCommerceAdapter(
        "https://store.example", "key", "secret", transport=httpx.MockTransport(handler), sleep=lambda _: None
    )
    with pytest.raises(ProviderUnavailable) as error:
        adapter.read_commerce("1042")
    assert len(calls) == attempts and "SECRET" not in str(error.value)


def test_malformed_payload_and_fractional_json_quantity_fail_closed() -> None:
    adapter = WooCommerceAdapter(
        "https://store.example",
        "key",
        "secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="this is not json")),
    )
    with pytest.raises(ProviderContractError, match="JSON"):
        adapter.read_commerce("1042")
    data = woo_order()
    data["line_items"][0]["quantity"] = 2.0
    with pytest.raises(ProviderContractError, match="quantities"):
        woo_client(data).read_commerce("1042")


def test_all_live_mutations_are_blocked_before_any_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARCELRESOLVE_LIVE_MUTATIONS", "1")
    monkeypatch.setenv("PARCELRESOLVE_OWNER_AUTHORIZED", "1")
    calls = []
    transport = httpx.MockTransport(lambda r: calls.append(r))
    adapters = [
        WooCommerceAdapter("https://store.example", "key", "secret", transport=transport),
        ShipStationV1Adapter("key", "secret", transport=transport),
        ShipStationV2Adapter("key", transport=transport),
    ]
    for adapter in adapters:
        for kind in ["cancel_order", "refund", "void_label", "create_label", "update_address"]:
            with pytest.raises(CapabilityError, match="unsupported"):
                adapter.perform(
                    "1042", {"kind": kind, "approved": True}, idempotency_key="k", expected_version=1
                )
    assert calls == []


def test_generic_warehouse_adapter_does_not_invent_hold_or_dispatch() -> None:
    with pytest.raises(CapabilityError, match="not configured"):
        UnsupportedWarehouseAdapter().read_warehouse("1042")
    with pytest.raises(CapabilityError, match="physical"):
        UnsupportedWarehouseAdapter().confirm_hold("1042")


@pytest.mark.parametrize(
    "url", ["http://store.example", "https://key:secret@store.example", "https://store.example?secret=x"]
)
def test_unsafe_base_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        WooCommerceAdapter(url, "key", "secret")


def test_contract_fixture_is_json_serializable_with_exact_amounts() -> None:
    # Read models carry only fixed minor units, never provider floats.
    result = json.loads(woo_client().read_commerce("1042").model_dump_json())
    assert type(result["total_minor"]) is int


def test_offline_contract_report_never_constructs_provider_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbid(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Offline contract report constructed a network client")

    monkeypatch.setattr(httpx, "Client", forbid)
    report = contract_checks(environ={})
    assert report["mode"] == "offline capability report" and report["live_mutations"] is False
    assert report["checks"]["woocommerce"]["status"] == "not_run"
    assert report["checks"]["shipstation_v1"]["status"] == "not_run"
    assert report["checks"]["shipstation_v2"]["status"] == "not_run"
    assert report["checks"]["warehouse"]["status"] == "unsupported"


def test_enabled_contract_checks_label_mock_provenance_and_do_not_print_credentials() -> None:
    env = {
        "PARCELRESOLVE_CONTRACT_READS": "1",
        "WOO_STORE_URL": "https://store.example",
        "WOO_CONSUMER_KEY": "do-not-print-key",
        "WOO_CONSUMER_SECRET": "do-not-print-secret",
        "WOO_ORDER_ID": "1042",
        "SHIPSTATION_V1_KEY": "do-not-print-v1",
        "SHIPSTATION_V1_SECRET": "do-not-print-v1-secret",
        "SHIPSTATION_ORDER_ID": "8001",
        "SHIPSTATION_V2_KEY": "do-not-print-v2",
        "SHIPSTATION_LABEL_ID": "se-111",
    }
    mocks = {
        "woocommerce": httpx.MockTransport(
            lambda r: httpx.Response(200, json=[] if r.url.path.endswith("refunds") else woo_order())
        ),
        "shipstation_v1": httpx.MockTransport(lambda _: httpx.Response(200, json=ss_order())),
        "shipstation_v2": httpx.MockTransport(lambda _: httpx.Response(200, json=label_record())),
    }
    report = contract_checks(environ=env, transports=mocks)
    for provider in mocks:
        assert report["checks"][provider]["status"] == "passed"
        assert report["checks"][provider]["validation"] == "mock_http"
    assert report["checks"]["cross_provider_identity"]["status"] == "not_run"
    assert "do-not-print" not in json.dumps(report)


def test_failed_live_contract_is_not_success_shaped() -> None:
    env = {
        "PARCELRESOLVE_CONTRACT_READS": "1",
        "SHIPSTATION_V2_KEY": "fake",
        "SHIPSTATION_LABEL_ID": "se-111",
    }
    report = contract_checks(
        environ=env,
        transports={
            "shipstation_v2": httpx.MockTransport(lambda _: httpx.Response(401, text="secret-body")),
        },
    )
    assert report["checks"]["shipstation_v2"]["status"] == "failed"
    assert "401" in report["checks"]["shipstation_v2"]["reason"]
    assert "secret-body" not in json.dumps(report)
