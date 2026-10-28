"""Documented, read-only provider adapters; no simulated success in live mode.

These records are observations, not a live execution backend. In particular a
Woo refund record is not proof of payment settlement, and a ShipStation status
or label is not a physical warehouse acknowledgment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, Literal, NoReturn, Protocol, TypeVar, runtime_checkable
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SUPPORTED_CURRENCIES = frozenset({"GBP", "USD", "EUR"})
T_co = TypeVar("T_co", covariant=True)


class CapabilityError(RuntimeError):
    """An operation has no supported contract in this release."""


class ProviderContractError(RuntimeError):
    """Provider data cannot be safely interpreted; contains no response body."""


class ProviderUnavailable(RuntimeError):
    def __init__(
        self,
        provider: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ):
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        suffix = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"{provider} read unavailable{suffix}; no mutation was attempted")


@runtime_checkable
class MutationPort(Protocol):
    def perform(
        self,
        order_id: str,
        action: Any,
        *,
        idempotency_key: str,
        expected_version: int,
        hold_ack_id: str | None = None,
    ) -> Any: ...


@runtime_checkable
class CommerceAdapter(MutationPort, Protocol[T_co]):
    def read_commerce(self, order_id: str) -> T_co: ...


@runtime_checkable
class PaymentAdapter(MutationPort, Protocol[T_co]):
    def read_payment(self, order_id: str) -> T_co: ...


@runtime_checkable
class ShippingAdapter(MutationPort, Protocol[T_co]):
    def read_shipping(self, order_id: str) -> T_co: ...


@runtime_checkable
class WarehouseAdapter(Protocol[T_co]):
    def read_warehouse(self, order_id: str) -> T_co: ...

    def confirm_hold(self, order_id: str) -> T_co: ...


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CommerceLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    line_id: str
    sku: str
    quantity: int
    total_minor: int
    tax_minor: int


class WooShippingAddress(BaseModel):
    """WooCommerce's postal fields; names are entered explicitly, never split by a model."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    address_1: str = Field(min_length=1, max_length=200)
    address_2: str = Field(default="", max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(default="", max_length=100)
    postcode: str = Field(min_length=1, max_length=20)
    country: str = Field(pattern=r"^[A-Z]{2}$")

    @model_validator(mode="after")
    def named_recipient(self) -> WooShippingAddress:
        if not self.first_name and not self.last_name:
            raise ValueError("A named recipient is required")
        return self


class CommerceObservation(Observation):
    source: Literal["woocommerce-wp-rest-v3"] = "woocommerce-wp-rest-v3"
    store_id: str
    order_id: str
    order_key: str
    status: str
    currency: str
    total_minor: int
    lines: tuple[CommerceLine, ...]
    refund_ids: tuple[str, ...]
    modified_at_gmt: str
    revision: str
    shipping_address: WooShippingAddress | None = None
    # This is an observed content digest, NOT a provider conditional-write token.


class RefundLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    refund_line_id: str
    order_line_id: str | None
    quantity: int


class RefundObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    refund_id: str
    amount_minor: int
    currency: str
    refunded_payment: bool
    lines: tuple[RefundLine, ...]
    settlement_verified: Literal[False] = False


class RefundPreview(Observation):
    source: Literal["woocommerce-refund-preview"] = "woocommerce-refund-preview"
    order_id: str
    currency: str
    total_minor: int
    max_refundable_minor: int
    line_quantities: dict[str, int]
    compute_totals_supported: Literal[True] = True


class PaymentObservation(Observation):
    source: Literal["woocommerce-refund-records"] = "woocommerce-refund-records"
    order_id: str
    currency: str
    order_total_minor: int
    paid_recorded_at_gmt: str | None
    refunds: tuple[RefundObservation, ...]
    settlement_verified: Literal[False] = False


class ShippingLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_id: str
    line_key: str | None
    sku: str
    quantity: int
    adjustment: bool


class ShippingObservation(Observation):
    source: Literal["shipstation-v1"] = "shipstation-v1"
    order_id: str
    order_key: str
    order_number: str
    store_id: str
    status: str
    lines: tuple[ShippingLine, ...]
    modified_at: str
    revision: str
    physical_dispatch: Literal["unknown"] = "unknown"
    warehouse_hold_verified: Literal[False] = False


class LabelObservation(Observation):
    source: Literal["shipstation-v2"] = "shipstation-v2"
    label_id: str
    shipment_id: str
    status: str
    voided: bool
    tracking_number: str | None
    tracking_status: str | None
    physical_dispatch: Literal["unknown"] = "unknown"


class LineBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    woo_line_id: str
    shipstation_item_id: str
    shipstation_line_key: str | None


class LabelBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    label_id: str
    shipment_id: str


class IdentityBinding(BaseModel):
    """A server-owned registry entry; never construct this from customer text.

    Validation checks the pinned mapping, not its merchant provenance. An
    operator must establish that provenance before onboarding a real store.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    store_id: str
    woo_order_id: str
    woo_order_key: str
    shipstation_order_id: str
    shipstation_order_key: str
    shipstation_store_id: str
    provenance: str = Field(min_length=1)
    lines: tuple[LineBinding, ...]
    labels: tuple[LabelBinding, ...] = ()


def verify_identity_binding(
    binding: IdentityBinding,
    commerce: CommerceObservation,
    shipping: ShippingObservation,
    labels: tuple[LabelObservation, ...] = (),
) -> None:
    """Check every namespace independently; never join on display number/SKU."""
    observed = (
        commerce.store_id,
        commerce.order_id,
        commerce.order_key,
        shipping.order_id,
        shipping.order_key,
        shipping.store_id,
    )
    expected = (
        binding.store_id,
        binding.woo_order_id,
        binding.woo_order_key,
        binding.shipstation_order_id,
        binding.shipstation_order_key,
        binding.shipstation_store_id,
    )
    if observed != expected:
        raise ProviderContractError("Trusted order identity mapping does not match provider observations")
    woo_lines = {x.line_id: x for x in commerce.lines}
    ss_lines = {x.item_id: x for x in shipping.lines if not x.adjustment}
    if len({x.woo_line_id for x in binding.lines}) != len(binding.lines):
        raise CapabilityError("Split line mappings require operator review")
    if len({x.shipstation_item_id for x in binding.lines}) != len(binding.lines):
        raise ProviderContractError("Duplicate mapped shipping item")
    if set(woo_lines) != {x.woo_line_id for x in binding.lines}:
        raise ProviderContractError("Unmapped commerce line quantities")
    if set(ss_lines) != {x.shipstation_item_id for x in binding.lines}:
        raise ProviderContractError("Unmapped shipping line quantities")
    for line in binding.lines:
        woo_line, ss_line = woo_lines[line.woo_line_id], ss_lines[line.shipstation_item_id]
        if ss_line.line_key != line.shipstation_line_key or woo_line.quantity != ss_line.quantity:
            raise ProviderContractError("Mapped line identity or quantity mismatch")
    observed_labels = {(x.label_id, x.shipment_id) for x in labels}
    expected_labels = {(x.label_id, x.shipment_id) for x in binding.labels}
    if len(observed_labels) != len(labels) or len(expected_labels) != len(binding.labels):
        raise ProviderContractError("Duplicate label identities")
    if observed_labels != expected_labels:
        raise ProviderContractError("V2 labels require an explicit, matching shipment mapping")


def minor_units(value: Any, currency: str) -> int:
    """Convert only exact two-decimal supported currencies; never round floats."""
    if currency not in SUPPORTED_CURRENCIES:
        raise CapabilityError("Only GBP, USD and EUR minor units are supported in this release")
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise ProviderContractError("Money must use a decimal string or exact decimal value")
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ProviderContractError("Invalid money value") from None
    if not decimal.is_finite():
        raise ProviderContractError("Money must be finite")
    sign, digits, exponent = decimal.as_tuple()
    if not any(digits):
        return 0
    if sign or not isinstance(exponent, int):
        raise ProviderContractError("Money outside supported non-negative minor-unit range")
    # Work on decimal digits directly so the global Decimal context cannot
    # silently round a very long coefficient during multiplication by 100.
    cut = -exponent - 2
    if cut > 0:
        if any(digits[-cut:]):
            raise ProviderContractError("Money has unsupported fractional precision")
        cents_digits = digits[:-cut]
    else:
        if len(digits) - cut > 19:
            raise ProviderContractError("Money outside supported non-negative minor-unit range")
        cents_digits = digits + (0,) * (-cut)
    if len(cents_digits) > 19:
        raise ProviderContractError("Money outside supported non-negative minor-unit range")
    amount = int("".join(str(digit) for digit in cents_digits) or "0")
    if amount > 9_223_372_036_854_775_807:
        raise ProviderContractError("Money outside supported non-negative minor-unit range")
    return amount


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderContractError("Expected a provider object")
    return value


def _array(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ProviderContractError("Expected a provider list")
    return value


def _string(value: Any, *, optional: bool = False) -> str:
    if not isinstance(value, str) or (not value and not optional):
        raise ProviderContractError("Missing or invalid provider text field")
    return value


def _positive_id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ProviderContractError("Expected a positive integer provider ID")
    result = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,18}", result):
        raise ProviderContractError("Expected a positive integer provider ID")
    return result


def _quantity(value: Any, *, refund: bool = False) -> int:
    if type(value) is not int or (value > 0 if refund else value <= 0):
        raise ProviderContractError("Only supported whole-item quantities may be read")
    return abs(value)


def _boolean(value: Any) -> bool:
    if type(value) is not bool:
        raise ProviderContractError("Expected a provider boolean")
    return value


def _revision(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _base_url(value: str, *, expected_host: str | None = None) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Provider base URL must be HTTPS without embedded credentials")
    if parsed.query or parsed.fragment or (expected_host and parsed.hostname != expected_host):
        raise ValueError("Unexpected provider base URL")
    return value.rstrip("/") + "/"


class ReadOnlyProvider:
    provider: str = "provider"

    def __init__(
        self,
        base_url: str,
        *,
        auth: httpx.Auth | None = None,
        headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if timeout <= 0:
            raise ValueError("Provider timeout must be positive")
        self._client = httpx.Client(
            base_url=base_url,
            auth=auth,
            headers=headers,
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: Mapping[str, str | int] | None = None) -> tuple[Any, httpx.Headers]:
        return self._read_request("GET", path, params=params)

    def _read_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[Any, httpx.Headers]:
        # POST is allowed only for the documented non-mutating Woo refund preview.
        if method not in {"GET", "OPTIONS"} and not (
            self.provider == "WooCommerce WP REST v3"
            and method == "POST"
            and re.fullmatch(r"orders/[1-9][0-9]*/refunds/preview", path)
        ):
            raise CapabilityError("The read adapter cannot issue a provider mutation")
        for attempt in range(3):
            try:
                response = self._client.request(method, path, params=params, json=body)
            except httpx.TransportError:
                if attempt < 2:
                    self._sleep(0.1 * (2**attempt))
                    continue
                raise ProviderUnavailable(self.provider, retryable=True) from None
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < 2:
                delay = response.headers.get("Retry-After", response.headers.get("X-Rate-Limit-Reset", ""))
                retry_after: float | None = None
                if delay.isdigit():
                    retry_after = float(delay)
                elif delay:
                    try:
                        retry_after = max(
                            0.0, (parsedate_to_datetime(delay) - datetime.now(UTC)).total_seconds()
                        )
                    except (ValueError, TypeError, OverflowError):
                        pass
                if retry_after is not None and retry_after > 2:
                    # Surface a long provider cooldown; never retry before its
                    # declared window or block the operator desk for a minute.
                    raise ProviderUnavailable(
                        self.provider,
                        status_code=response.status_code,
                        retryable=True,
                        retry_after_seconds=retry_after,
                    )
                self._sleep(retry_after if retry_after is not None else 0.1 * (2**attempt))
                continue
            if response.status_code < 200 or response.status_code >= 300:
                raise ProviderUnavailable(
                    self.provider, status_code=response.status_code, retryable=retryable
                )
            if len(response.content) > 5_000_000:
                raise ProviderContractError("Provider response exceeds the supported size")
            try:
                return json.loads(response.content, parse_float=Decimal), response.headers
            except (ValueError, UnicodeDecodeError):
                raise ProviderContractError("Provider returned invalid JSON") from None
        raise AssertionError("unreachable")

    def perform(
        self,
        order_id: str,
        action: Any,
        *,
        idempotency_key: str,
        expected_version: int,
        hold_ack_id: str | None = None,
    ) -> NoReturn:
        # No configuration/owner/approval combination can enable a live write
        # until a supported mutation backend is implemented and contract-tested.
        raise CapabilityError(
            f"{self.provider} live mutations are unsupported in this release; "
            "configuration, owner authorization and product approval cannot bypass this limit"
        )


class WooCommerceAdapter(ReadOnlyProvider):
    """WP REST /wp-json/wc/v3, not the obsolete /wc-api/v3 API."""

    provider = "WooCommerce WP REST v3"

    def __init__(
        self,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        *,
        store_id: str = "primary",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not consumer_key or not consumer_secret or not store_id:
            raise ValueError("WooCommerce server-side credentials and store identity are required")
        root = _base_url(base_url)
        if "/wp-json/" in urlsplit(root).path:
            raise ValueError("Supply the WooCommerce store URL, without its REST API path")
        self.store_id = store_id
        super().__init__(
            root + "wp-json/wc/v3/",
            auth=httpx.BasicAuth(consumer_key, consumer_secret),
            transport=transport,
            sleep=sleep,
        )

    @classmethod
    def from_env(cls) -> WooCommerceAdapter:
        return cls(
            os.environ.get("WOO_STORE_URL", ""),
            os.environ.get("WOO_CONSUMER_KEY", ""),
            os.environ.get("WOO_CONSUMER_SECRET", ""),
            store_id=os.environ.get("WOO_STORE_ID", "primary"),
        )

    def _order_data(self, order_id: str) -> dict[str, Any]:
        requested = _positive_id(order_id)
        data = _object(self._get(f"orders/{requested}")[0])
        if _positive_id(data.get("id")) != requested:
            raise ProviderContractError("WooCommerce returned a different order identity")
        return data

    def read_commerce(self, order_id: str) -> CommerceObservation:
        data = self._order_data(order_id)
        currency = _string(data.get("currency"))
        lines = tuple(
            CommerceLine(
                line_id=_positive_id(line.get("id")),
                sku=_string(line.get("sku", ""), optional=True),
                quantity=_quantity(line.get("quantity")),
                total_minor=minor_units(line.get("total"), currency),
                tax_minor=minor_units(line.get("total_tax"), currency),
            )
            for line in map(_object, _array(data.get("line_items")))
        )
        if len({x.line_id for x in lines}) != len(lines):
            raise ProviderContractError("Duplicate WooCommerce order line identities")
        refunds = tuple(_positive_id(_object(x).get("id")) for x in _array(data.get("refunds")))
        if len(set(refunds)) != len(refunds):
            raise ProviderContractError("Duplicate WooCommerce refund identities")
        return CommerceObservation(
            store_id=self.store_id,
            order_id=_positive_id(data.get("id")),
            order_key=_string(data.get("order_key")),
            status=_string(data.get("status")),
            currency=currency,
            total_minor=minor_units(data.get("total"), currency),
            lines=lines,
            refund_ids=refunds,
            modified_at_gmt=_string(data.get("date_modified_gmt")),
            revision=_revision(data),
            shipping_address=self._shipping_address(data.get("shipping")),
        )

    @staticmethod
    def _shipping_address(value: Any) -> WooShippingAddress | None:
        if value is None:
            return None
        data = _object(value)
        try:
            return WooShippingAddress.model_validate(
                {key: data[key] for key in WooShippingAddress.model_fields if key in data}
            )
        except ValidationError:
            raise ProviderContractError("WooCommerce shipping address is incomplete or unsupported") from None

    def preview_refund(
        self, order_id: str, currency: str, line_quantities: Mapping[str, int]
    ) -> RefundPreview:
        """Verify deployed support before the documented non-mutating preview POST.

        WooCommerce before 11.1 can silently ignore compute_totals on creation;
        a version string or documentation example is not a capability check.
        """
        requested = _positive_id(order_id)
        minor_units("0.00", currency)  # Reject unsupported precision before any request.
        if not line_quantities:
            raise CapabilityError("A refund preview needs explicit supported order-line quantities")
        normalized = {_positive_id(key): _quantity(quantity) for key, quantity in line_quantities.items()}
        if len(normalized) != len(line_quantities):
            raise ProviderContractError("Refund preview contains duplicate normalized line identities")
        options = _object(self._read_request("OPTIONS", f"orders/{requested}/refunds")[0])
        supported = any(
            isinstance(endpoint, dict)
            and isinstance(endpoint.get("methods"), list)
            and "POST" in endpoint.get("methods", [])
            and isinstance(endpoint.get("args"), dict)
            and "compute_totals" in endpoint["args"]
            for endpoint in _array(options.get("endpoints"))
        )
        if not supported:
            raise CapabilityError(
                "Store did not advertise compute_totals; computed refunds require WooCommerce 11.1 support"
            )
        body = {
            "line_items": [
                {"line_item_id": int(key), "quantity": quantity} for key, quantity in normalized.items()
            ]
        }
        result = _object(self._read_request("POST", f"orders/{requested}/refunds/preview", body=body)[0])
        total = minor_units(result.get("total"), currency)
        maximum = minor_units(result.get("max_refundable"), currency)
        if not 0 < total <= maximum:
            raise ProviderContractError("Refund preview does not fit the remaining refundable amount")
        breakdown = _object(result.get("breakdown"))
        returned: dict[str, int] = {}
        products = _object(breakdown.get("products"))
        line_total = 0
        for row in _array(products.get("items")):
            item = _object(row)
            key = _positive_id(item.get("id"))
            if key in returned:
                raise ProviderContractError("Refund preview returned duplicate lines")
            returned[key] = _quantity(item.get("quantity"))
            amount = minor_units(item.get("total"), currency)
            if minor_units(item.get("subtotal"), currency) + minor_units(item.get("tax"), currency) != amount:
                raise ProviderContractError("Refund preview line totals disagree")
            line_total += amount
        if returned != normalized:
            raise ProviderContractError(
                "Refund preview line identities or quantities differ from the request"
            )
        if (
            line_total != total
            or minor_units(products.get("total"), currency) != total
            or minor_units(products.get("subtotal"), currency) + minor_units(products.get("tax"), currency)
            != total
            or minor_units(result.get("subtotal"), currency) + minor_units(result.get("tax"), currency)
            != total
        ):
            raise ProviderContractError("Refund preview totals disagree")
        for category in ("shipping", "fees"):
            section = _object(breakdown.get(category))
            if _array(section.get("items")) or any(
                minor_units(section.get(key), currency) for key in ("subtotal", "tax", "total")
            ):
                raise CapabilityError("Shipping/fee refund allocation requires merchant review")
        return RefundPreview(
            order_id=requested,
            currency=currency,
            total_minor=total,
            max_refundable_minor=maximum,
            line_quantities=normalized,
        )

    def read_payment(self, order_id: str) -> PaymentObservation:
        data = self._order_data(order_id)
        currency = _string(data.get("currency"))
        # Pagination prevents falsely reporting complete refunds after page 1.
        refunds: list[RefundObservation] = []
        for page in range(1, 101):
            raw, headers = self._get(
                f"orders/{_positive_id(order_id)}/refunds", {"per_page": 100, "page": page}
            )
            rows = _array(raw)
            refunds.extend(self._refund(_object(row), currency) for row in rows)
            total_pages = headers.get("X-WP-TotalPages")
            if total_pages is not None:
                if not total_pages.isdigit() or int(total_pages) > 100:
                    raise ProviderContractError(
                        "Refund pagination cannot be established within the read limit"
                    )
                if page >= int(total_pages):
                    break
            elif len(rows) < 100:
                break
        else:
            raise ProviderContractError("Refund pagination exceeds supported read limit")
        if len({x.refund_id for x in refunds}) != len(refunds):
            raise ProviderContractError(
                "Refund collection changed or returned duplicate identities; reread required"
            )
        summary_ids = {_positive_id(_object(x).get("id")) for x in _array(data.get("refunds"))}
        if summary_ids != {x.refund_id for x in refunds}:
            raise ProviderContractError("Order and refund reads disagree; reread required")
        line_ids = {_positive_id(_object(x).get("id")) for x in _array(data.get("line_items"))}
        if any(line.order_line_id not in line_ids for refund in refunds for line in refund.lines):
            raise CapabilityError("Refund line mapping is incomplete; operator review is required")
        order_total = minor_units(data.get("total"), currency)
        if sum(x.amount_minor for x in refunds) > order_total:
            raise ProviderContractError("Recorded refunds exceed the observed order total")
        for raw_line in _array(data.get("line_items")):
            order_line = _object(raw_line)
            line_id = _positive_id(order_line.get("id"))
            returned_quantity = sum(
                line.quantity for refund in refunds for line in refund.lines if line.order_line_id == line_id
            )
            if returned_quantity > _quantity(order_line.get("quantity")):
                raise ProviderContractError("Refund quantities exceed the observed ordered quantity")
        paid = data.get("date_paid_gmt")
        if paid is not None:
            paid = _string(paid)
        return PaymentObservation(
            order_id=_positive_id(order_id),
            currency=currency,
            order_total_minor=order_total,
            paid_recorded_at_gmt=paid,
            refunds=tuple(refunds),
        )

    @staticmethod
    def _refund(row: dict[str, Any], currency: str) -> RefundObservation:
        lines: list[RefundLine] = []
        for raw in _array(row.get("line_items")):
            line = _object(raw)
            original_ids = [
                _positive_id(item.get("value"))
                for item in map(_object, _array(line.get("meta_data")))
                if item.get("key") == "_refunded_item_id"
            ]
            if len(original_ids) > 1:
                raise ProviderContractError("Ambiguous refund line mapping")
            lines.append(
                RefundLine(
                    refund_line_id=_positive_id(line.get("id")),
                    order_line_id=original_ids[0] if original_ids else None,
                    quantity=_quantity(line.get("quantity"), refund=True),
                )
            )
        return RefundObservation(
            refund_id=_positive_id(row.get("id")),
            amount_minor=minor_units(row.get("amount"), currency),
            currency=currency,
            refunded_payment=_boolean(row.get("refunded_payment")),
            lines=tuple(lines),
        )


class ShipStationV1Adapter(ReadOnlyProvider):
    provider = "ShipStation V1"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        base_url: str = "https://ssapi.shipstation.com/",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key or not api_secret:
            raise ValueError("ShipStation V1 server-side key and secret are required")
        super().__init__(
            _base_url(base_url, expected_host="ssapi.shipstation.com"),
            auth=httpx.BasicAuth(api_key, api_secret),
            transport=transport,
            sleep=sleep,
        )

    @classmethod
    def from_env(cls) -> ShipStationV1Adapter:
        return cls(os.environ.get("SHIPSTATION_V1_KEY", ""), os.environ.get("SHIPSTATION_V1_SECRET", ""))

    def read_shipping(self, order_id: str) -> ShippingObservation:
        requested = _positive_id(order_id)
        data = _object(self._get(f"orders/{requested}")[0])
        if _positive_id(data.get("orderId")) != requested:
            raise ProviderContractError("ShipStation returned a different order identity")
        lines = tuple(
            ShippingLine(
                item_id=_positive_id(line.get("orderItemId")),
                line_key=(_string(line["lineItemKey"]) if line.get("lineItemKey") is not None else None),
                sku=_string(line.get("sku", ""), optional=True),
                quantity=_quantity(line.get("quantity")),
                adjustment=_boolean(line.get("adjustment", False)),
            )
            for line in map(_object, _array(data.get("items")))
        )
        if len({x.item_id for x in lines}) != len(lines):
            raise ProviderContractError("Duplicate ShipStation item identities")
        return ShippingObservation(
            order_id=requested,
            order_key=_string(data.get("orderKey")),
            order_number=_string(data.get("orderNumber")),
            store_id=_positive_id(_object(data.get("advancedOptions")).get("storeId")),
            status=_string(data.get("orderStatus")),
            lines=lines,
            modified_at=_string(data.get("modifyDate")),
            revision=_revision(data),
        )


class ShipStationV2Adapter(ReadOnlyProvider):
    provider = "ShipStation V2"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.shipstation.com/v2/",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise ValueError("ShipStation V2 server-side API key is required")
        root = _base_url(base_url, expected_host="api.shipstation.com")
        if urlsplit(root).path != "/v2/":
            raise ValueError("ShipStation V2 requires the /v2/ base path")
        super().__init__(root, headers={"API-Key": api_key}, transport=transport, sleep=sleep)

    @classmethod
    def from_env(cls) -> ShipStationV2Adapter:
        return cls(os.environ.get("SHIPSTATION_V2_KEY", ""))

    def read_label(self, label_id: str) -> LabelObservation:
        if not re.fullmatch(r"se-[A-Za-z0-9][A-Za-z0-9_-]*", label_id):
            raise ProviderContractError("A V2 label ID is required; V1 shipment IDs are not interchangeable")
        data = _object(self._get(f"labels/{label_id}")[0])
        if data.get("label_id") != label_id:
            raise ProviderContractError("ShipStation returned a different label identity")
        shipment_id = _string(data.get("shipment_id"))
        if not re.fullmatch(r"se-[A-Za-z0-9][A-Za-z0-9_-]*", shipment_id):
            raise ProviderContractError("Invalid V2 shipment identity")
        tracking_number, tracking_status = data.get("tracking_number"), data.get("tracking_status")
        return LabelObservation(
            label_id=label_id,
            shipment_id=shipment_id,
            status=_string(data.get("status")),
            voided=_boolean(data.get("voided")),
            tracking_number=_string(tracking_number, optional=True) if tracking_number is not None else None,
            tracking_status=_string(tracking_status, optional=True) if tracking_status is not None else None,
        )


class UnsupportedWarehouseAdapter:
    """No generic 3PL or physical dispatch API is claimed."""

    def read_warehouse(self, order_id: str) -> NoReturn:
        raise CapabilityError("A merchant-specific reliable warehouse read contract is not configured")

    def confirm_hold(self, order_id: str) -> NoReturn:
        raise CapabilityError("ShipStation on_hold is not a physical warehouse hold acknowledgment")


def contract_checks(
    *,
    environ: Mapping[str, str] | None = None,
    transports: Mapping[str, httpx.BaseTransport] | None = None,
) -> dict[str, Any]:
    """Run only explicitly enabled reads of explicitly selected resources.

    Without the environment gate this is an offline capability report, not a
    successful live check. ``transports`` is for isolated HTTP contract tests;
    their results are labeled mocked and must never be published as live reads.
    """
    env = os.environ if environ is None else environ
    enabled = env.get("PARCELRESOLVE_CONTRACT_READS") == "1"
    mocks = transports or {}
    checks: dict[str, dict[str, Any]] = {}
    required = {
        "woocommerce": ("WOO_STORE_URL", "WOO_CONSUMER_KEY", "WOO_CONSUMER_SECRET", "WOO_ORDER_ID"),
        "shipstation_v1": ("SHIPSTATION_V1_KEY", "SHIPSTATION_V1_SECRET", "SHIPSTATION_ORDER_ID"),
        "shipstation_v2": ("SHIPSTATION_V2_KEY", "SHIPSTATION_LABEL_ID"),
    }
    for provider, keys in required.items():
        missing = [name for name in keys if not env.get(name)]
        if not enabled or missing:
            checks[provider] = {
                "status": "not_run",
                "missing_configuration": missing,
                "reason": "Explicit live read gate is disabled"
                if not enabled
                else "Required configuration is missing",
            }
            continue
        adapter: ReadOnlyProvider | None = None
        try:
            if provider == "woocommerce":
                woo = WooCommerceAdapter(
                    env["WOO_STORE_URL"],
                    env["WOO_CONSUMER_KEY"],
                    env["WOO_CONSUMER_SECRET"],
                    store_id=env.get("WOO_STORE_ID", "primary"),
                    transport=mocks.get(provider),
                )
                adapter = woo
                commerce = woo.read_commerce(env["WOO_ORDER_ID"])
                payment = woo.read_payment(env["WOO_ORDER_ID"])
                observed: dict[str, Any] = {
                    "order_identity_matched": True,
                    "currency": commerce.currency,
                    "line_count": len(commerce.lines),
                    "refund_count": len(payment.refunds),
                    "payment_settlement_verified": False,
                }
            elif provider == "shipstation_v1":
                v1 = ShipStationV1Adapter(
                    env["SHIPSTATION_V1_KEY"],
                    env["SHIPSTATION_V1_SECRET"],
                    transport=mocks.get(provider),
                )
                adapter = v1
                shipping = v1.read_shipping(env["SHIPSTATION_ORDER_ID"])
                observed = {
                    "order_identity_matched": True,
                    "line_count": len(shipping.lines),
                    "provider_status": shipping.status,
                    "physical_dispatch": "unknown",
                }
            else:
                v2 = ShipStationV2Adapter(env["SHIPSTATION_V2_KEY"], transport=mocks.get(provider))
                adapter = v2
                label = v2.read_label(env["SHIPSTATION_LABEL_ID"])
                observed = {
                    "label_identity_matched": True,
                    "provider_status": label.status,
                    "voided": label.voided,
                    "physical_dispatch": "unknown",
                }
            checks[provider] = {
                "status": "passed",
                "validation": "mock_http" if provider in mocks else "live_read",
                "observed": observed,
            }
        except (CapabilityError, ProviderContractError, ProviderUnavailable, ValueError) as exc:
            checks[provider] = {
                "status": "failed",
                "validation": "mock_http" if provider in mocks else "live_read",
                "reason": str(exc),
            }
        finally:
            if adapter is not None:
                adapter.close()
    checks["cross_provider_identity"] = {
        "status": "not_run",
        "reason": "Requires a trusted merchant-specific identity registry; resource numbers are not joined automatically",
    }
    checks["warehouse"] = {
        "status": "unsupported",
        "reason": "No real warehouse hold/dispatch contract is configured",
    }
    checks["live_mutations"] = {
        "status": "unsupported",
        "reason": "No live mutation backend is enabled in this release",
    }
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "documentation_reviewed_on": "2026-10-14",
        "mode": "explicit read checks" if enabled else "offline capability report",
        "live_mutations": False,
        "checks": checks,
    }
