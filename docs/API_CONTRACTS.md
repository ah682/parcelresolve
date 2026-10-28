# Provider contracts and validation record

Reviewed **14 October 2026**. The local recovery workflow uses its own durable simulator. Real provider observations and the new guarded review CLI are separate from the simulator API/UI. The CLI produces durable request artifacts, approvals, dry-runs and read-only reconciliation. It does **not execute provider mutations**, even with every approval and configuration gate enabled.

## What was checked

Official documentation was opened for WooCommerce WP REST v3, ShipStation V1 orders, ShipStation V2 labels, ShipStation status/sandbox semantics and OpenAI Responses structured outputs. On 14 October, the current individual WooCommerce order/refund pages and ShipStation create/update, label creation and void contracts were rechecked. WooCommerce's older combined documentation exceeded the browsing renderer's size limit; its official HTML was also fetched with `curl -fL`. No credentials were supplied and no authenticated provider, carrier, warehouse or hosted-model request was made.

The [WooCommerce ShipStation plugin changelog](https://en-gb.wordpress.org/plugins/woocommerce-shipstation-integration/#developers) lists 5.0.0 on 13 April 2026 adding refund/return data to order responses and 5.3.9 on 7 October 2026 as its latest listed release. ParcelResolve does not assume the older plugin lacks refund support, and its synthetic disagreement cases are not claims about an existing plugin bug. A merchant's installed version and settings remain unverified.

Executed on this environment:

```sh
.venv/bin/python -m pytest -q tests/test_integrations.py tests/test_guarded_live.py
.venv/bin/ruff check parcelresolve/integrations.py parcelresolve/guarded_live.py tests/test_integrations.py tests/test_guarded_live.py
.venv/bin/mypy parcelresolve/integrations.py parcelresolve/guarded_live.py
.venv/bin/python -m parcelresolve.guarded_live capabilities
```

Observed: **119 tests passed**, Ruff passed, mypy passed. The capability CLI returned `live_validation: not_run`, `live_recovery_execution: unsupported`, `provider_writes: 0`. Tests use `httpx.MockTransport`, synthetic payloads and fake credentials. They cover parsing and quantity/money rejection, capability discovery, edits during joined reads, stale/expired approvals, restart, per-resource contention, an uncertain external handoff, and truthful read-back limits. They do not establish account access or live integration compatibility. The earlier 13 October combined integration/intake check passed 98 tests; current intake/model evaluation is documented separately in [EVALUATION.md](EVALUATION.md).

## Implemented contracts

| Adapter | Documented request | Authentication | Normalized observations |
| --- | --- | --- | --- |
| `WooCommerceAdapter.read_commerce` | `GET /wp-json/wc/v3/orders/{id}` | HTTPS Basic, consumer key/secret | Order identity, commercial status, currency, line IDs/quantities/totals, refund IDs |
| `WooCommerceAdapter.read_payment` | Order read plus `GET /wp-json/wc/v3/orders/{id}/refunds` | Same as above | Complete paginated refund records, refund line mapping, payment-record timestamps |
| `WooCommerceAdapter.preview_refund` | `OPTIONS /wp-json/wc/v3/orders/{id}/refunds`, then documented non-mutating `POST .../refunds/preview` | Same; merchant must grant preview permission | Capability-checked whole-line quantities and exact server-computed totals, with no refund creation |
| `ShipStationV1Adapter.read_shipping` | `GET https://ssapi.shipstation.com/orders/{orderId}` | Basic, API key/secret | V1 order ID/key/store, item identities/quantities, provider status |
| `ShipStationV2Adapter.read_label` | `GET https://api.shipstation.com/v2/labels/{label_id}` | `API-Key` header | V2 label/shipment IDs, provider label state, tracking reference |
| `UnsupportedWarehouseAdapter` | No live contract implemented | None | Raises `CapabilityError`; never invents a hold or dispatch acknowledgment |

The WooCommerce product is **WP REST `wc/v3`**, distinct from the older `wc-api/v3` path. Its order `id`, `order_key`, line IDs, decimal money strings and refund records are documented in the [official REST reference](https://woocommerce.github.io/woocommerce-rest-api-docs/#orders). Refund examples identify the original order line through `_refunded_item_id` metadata; the refund's own line ID is a different resource. The adapter preserves both and refuses incomplete mappings.

ShipStation V1's system `orderId`, user/import `orderKey` and display `orderNumber` are distinct, as documented in the [order model](https://www.shipstation.com/docs/api/models/order/) and [get-order endpoint](https://www.shipstation.com/docs/api/orders/get-order/). V1's [requirements](https://www.shipstation.com/docs/api/requirements/) specify its host, Basic authentication and `X-Rate-Limit-Reset`. The adapter retains the raw provider modification timestamp; V1's documented PST/PDT timestamps are not silently relabeled UTC.

V2 [label reads](https://docs.shipstation.com/list-labels) use string `label_id` and `shipment_id` resources and the [V2 authentication contract](https://docs.shipstation.com/authentication). A V1 numeric shipment/order ID is not converted into a V2 ID. Neither adapter automatically discovers or asserts a cross-product mapping.

## Identity, money and evidence limits

`IdentityBinding` represents a server-owned, merchant-verified mapping with provenance. `verify_identity_binding` checks each provider namespace, store ID, line key and whole-item quantity independently. It never joins by a display number or SKU. V2 label/shipment bindings are explicit. The verification checks consistency with the supplied registry; it cannot prove that the registry was originally established correctly. Split/merged mappings require operator review.

Money is parsed into exact integer minor units for GBP, USD and EUR. Fractional item quantities, other currencies, non-finite values, binary floating-point input, sub-cent amounts and amounts outside the supported range fail explicitly. Decimal conversion does not round. Line totals and tax totals remain separate; no unit price is guessed by dividing a discounted total. Refund pagination is bounded to 100 pages and detects inconsistent/duplicate IDs, unknown line mappings, excessive refund amounts and excessive returned quantities.

Observed revisions are content hashes, **not provider conditional-write guarantees**. Independent reads can still race with merchant edits. WooCommerce refund records, including `refunded_payment`, are surfaced as records with `settlement_verified=false`; no payment-gateway settlement API is configured.

ShipStation explains that [label creation/printing can move an order into Shipped](https://help.shipstation.com/hc/en-us/articles/360025869712-Understanding-Order-Statuses). Consequently both real shipping read models retain `physical_dispatch="unknown"`. An application `on_hold` status does not establish a current physical warehouse hold. These observations cannot authorize a stopped-parcel claim.

All live adapter `perform(...)` calls raise `CapabilityError`, including refunds, cancellation, address edits, label voids and replacements. **There is no live-write enabling switch in this release.** Configuration, owner authorization and local approval cannot bypass this unsupported capability. Implementing a future live writer requires all three gates, the ledger/reconciliation workflow and merchant/provider validation before enabling it.

## Guarded live review profile

`parcelresolve/guarded_live.py` implements a separate local review ledger. It accepts an operator-established `IdentityBinding`, reads the mapped resources, detects edits during its joined reads, and creates a 15-minute proposal with a content hash. Owner authorization and product approval bind the case, proposal hash, observed resource version, every action hash, amount and currency. Each approval and dry-run rereads the resources. A detected change permanently stales that proposal; returning to an earlier provider value cannot reactivate it. Read hashes are still not atomic external-write preconditions.

The current [WooCommerce refund contract](https://developer.woocommerce.com/docs/apis/rest-api/v3/order-refunds) documents `compute_totals` and preview since 11.1. Older stores can ignore that flag, so the adapter checks the deployed `OPTIONS` arguments first. The preview endpoint uses `line_item_id`; creation uses `id`. Preview requires refund permissions despite not creating a refund. This profile validates whole-line money and quantity agreement and declines existing-refund, shipping/fee and unsupported-currency allocation. A failed capability check produces a manual refund-review artifact, never a zero-amount substitute.

| Proposed artifact | Exact documented boundary | Execution in this release |
| --- | --- | --- |
| Woo cancellation | `PUT /wp-json/wc/v3/orders/{id}` with `status: cancelled`, per [orders reference](https://developer.woocommerce.com/docs/apis/rest-api/v3/orders) | Unsupported; status would not prove a physical stop |
| Woo address | Same endpoint with explicitly entered `shipping` postal/name fields; same-country only | Unsupported; does not modify a ShipStation address or a label |
| Woo refund | `POST .../orders/{id}/refunds`, exact previewed amount and whole-line quantities; `compute_totals: true`, `api_refund: true`, `api_restock: false` | Unsupported; gateway, inventory policy and settlement unverified |
| V2 label void | `PUT /v2/labels/{label_id}/void`, per [void reference](https://docs.shipstation.com/void-labels) | Unsupported; eligibility is carrier-dependent, irreversible, and not refund settlement |
| V1 order update | [Create/update](https://www.shipstation.com/docs/api/orders/create-update-order/) requires the entire resource and permits only awaiting-payment, awaiting-shipment or on-hold updates | Manual review; no invented partial update of a shipped order |
| Replacement label | [Creation](https://docs.shipstation.com/create-labels) needs verified shipment/rate or carrier/service/address/package inputs | Manual review; no invented purchase request or price |
| Warehouse stop | No configured real acknowledgment contract | Manual review; no fabricated hold |

Every action has `executable: false`. Request artifacts are not an execution sequence. Correlation metadata in the refund artifact is not a provider idempotency key. `execute` checks the operator, configuration, owner/product approvals and current observations, then raises `CapabilityError` for the unsupported recovery contract. Enabling `PARCELRESOLVE_ALLOW_LIVE_MUTATIONS=1` only exercises those rejection gates; it cannot issue a write. Notification/plugin side effects, complete label inventory, reliable warehouse fencing and atomic conditional writes remain unresolved.

The ledger uses a per-resource process lock and SQLite transactions with `synchronous=FULL`. It stores proposal/approval/event and operator-reported handoff records in `.parcelresolve-live-review/live-review.sqlite`; the default directory is ignored by version control. The database is mode 0600 and a newly created directory is mode 0700. Artifacts contain merchant postal data: keep the directory within the authorized local operator environment. Tokens and provider credentials are never saved in the ledger. This local role-token workflow is not a deployed merchant identity service.

An operator can record an action they attempted outside ParcelResolve. This report is durable and initially `uncertain`; it does not assert permission, success or attribution. Restart cannot replay it, a new proposal for that resource is blocked while it is uncertain, and approvals cannot reset the handoff. `reconcile` makes reads only. A matching provider state is labeled `provider_state_observed`, with attribution, settlement, warehouse stop and retry authorization all false. A refund also needs the reported provider refund ID and matching money/line quantities. Absence or disagreement remains uncertain for operator escalation. This is handoff reconciliation, not an implemented live mutation backend.

### Commands and reproducible fixtures

No credentials or network are needed for the capability report or mock tests:

```sh
uv run python -m parcelresolve.guarded_live capabilities
uv run pytest -q tests/test_integrations.py tests/test_guarded_live.py
```

The synthetic `ProviderFixture` in `tests/test_guarded_live.py` supplies Woo order 1042, ShipStation V1 order 8001, label `se-111`/shipment `se-222`, and GBP 24.00 for two units. Its transport rejects all mutation requests. Example mapping for that fixture only (replace every mapping with verified merchant data before real reads):

```json
{
  "store_id": "merchant-1",
  "woo_order_id": "1042",
  "woo_order_key": "wc_order_alpha",
  "shipstation_order_id": "8001",
  "shipstation_order_key": "import-1042",
  "shipstation_store_id": "7",
  "provenance": "synthetic fixture mapping; not a merchant validation",
  "lines": [{"woo_line_id": "311", "shipstation_item_id": "901", "shipstation_line_key": "woo-line-311"}],
  "labels": [{"label_id": "se-111", "shipment_id": "se-222"}]
}
```

With explicit read authorization, configure the provider variables below and the live-review role variables in `.env.example`. Supply a trusted mapping file; customer text cannot supply it. The CLI does not automatically load `.env`. Read/preview commands require `PARCELRESOLVE_CONTRACT_READS=1`. `WOO_STORE_ID` must match the binding. Optional V2 credentials are required whenever the binding contains labels.

```sh
uv run python -m parcelresolve.guarded_live prepare --case-id CASE_ID --flow cancel --binding verified-binding.json
uv run python -m parcelresolve.guarded_live inspect --proposal-id PROPOSAL_ID
# Run each approval in its authorized role's process; submit the role token via the named environment variable.
uv run python -m parcelresolve.guarded_live owner-authorize --proposal-id PROPOSAL_ID --proposal-hash EXACT_HASH
uv run python -m parcelresolve.guarded_live approve --proposal-id PROPOSAL_ID --proposal-hash EXACT_HASH
uv run python -m parcelresolve.guarded_live dry-run --proposal-id PROPOSAL_ID
```

The default submitted-token variable is `PARCELRESOLVE_REVIEW_SUBMITTED_TOKEN`; `--token-env` selects another environment variable without exposing its value in arguments. Owner/operator secrets must each have at least 32 characters and configured actor IDs. Inspection remains available offline without those credentials. `--directory` selects a separate ledger.

For address review, use `--flow address --address verified-address.json`. Its exact postal shape is:

```json
{"first_name":"Ada Marie","last_name":"Lovelace","address_1":"2 Example Road","address_2":"","city":"London","state":"","postcode":"SW1A 1AA","country":"GB"}
```

If an operator has already acted in the provider's own interface, report the reviewed action ID and the refund provider ID when applicable, then reconcile without retrying:

```sh
uv run python -m parcelresolve.guarded_live record-handoff --proposal-id PROPOSAL_ID --action-id ACTION_ID --provider-id PROVIDER_REFUND_ID
uv run python -m parcelresolve.guarded_live reconcile --proposal-id PROPOSAL_ID
```

## Configuration and reproducible contract report

The report command is safe without configuration:

```sh
uv run python -m parcelresolve.cli contracts
```

Its default mode is `offline capability report`: provider checks are `not_run`, not success. The report does not print credentials or provider response bodies. A separate, deliberately enabled read probe uses:

| Purpose | Server-side environment variables |
| --- | --- |
| Explicit read-probe gate | `PARCELRESOLVE_CONTRACT_READS=1` |
| WooCommerce | `WOO_STORE_URL`, `WOO_CONSUMER_KEY`, `WOO_CONSUMER_SECRET`, `WOO_ORDER_ID`; optional `WOO_STORE_ID` |
| ShipStation V1 | `SHIPSTATION_V1_KEY`, `SHIPSTATION_V1_SECRET`, `SHIPSTATION_ORDER_ID` |
| ShipStation V2 | `SHIPSTATION_V2_KEY`, `SHIPSTATION_LABEL_ID` |

Only fully configured providers run, and only for the explicitly selected resource. Use authorized merchant read credentials. These probes issue GET requests only and do not send notifications, buy labels or modify orders/payments. Cross-provider identity remains `not_run` until separately checked against a trusted merchant registry. A test-injected transport is labeled `mock_http`, never `live_read`.

Read clients use timeouts, disable redirects and environment proxies, keep credentials out of URLs and make at most three attempts for transient read failures. A provider cooldown longer than two seconds is surfaced with `retry_after_seconds`; it is not retried early. Unsupported operations, authentication errors, malformed responses and unresolved pagination do not return success-shaped data.

## Request interpretation

`interpret_request(text)` uses the deterministic interpreter without constructing a network client. It classifies clear whole-order cancellations and address corrections, and requests clarification for unsupported scope, conflicts, conditions and obvious injected instructions. This is a conservative English-language rules baseline, not a trained model or a comprehensive injection detector. Its output has only intent, clarification, explanation and mode. Authentication, order identity, monetary values, verified target address and action permissions come from trusted application context and backend rules.

The optional `OpenAIInterpreter` uses the [Responses structured-output contract](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses): `text.format` with a strict JSON schema, all fields required and `additionalProperties=false`. It has no tools or order database access, receives only the submitted customer message, validates the returned object, and never displays model-written prose as authorization or warehouse evidence. Refusals, malformed/extra fields and incomplete responses require operator clarification.

Hosted model interpretation requires `mode="openai"`, `PARCELRESOLVE_ALLOW_MODEL_NETWORK=1`, `OPENAI_API_KEY` and an explicit `OPENAI_MODEL` that supports the contract. No model is silently selected. The adapter sets `store=false`, records returned token usage in `last_usage` and does not automatically retry a potentially billable timeout. The application default remains deterministic even when credentials exist. A locally rejected request remains labeled deterministic because no model was called. Hosted model accuracy, account/model availability, latency and cost were **not measured**. Actual local CPU model results and its exclusion from the desk are documented separately in [EVALUATION.md](EVALUATION.md).

## Remaining real validation gates

Before merchant use, establish the installed plugin/settings, read-key access, actual identity and line mappings, payment gateway settlement/refund behavior, supported conditional writes/idempotency, void/replacement carrier rules, merchant event delivery and a reliable warehouse stop/dispatch contract. Test action races with authentic data under explicit owner authorization and product approval. No current real mutation adapter claims these guarantees.

Sandbox availability depends on the ShipStation product/account. Current [authentication guidance](https://docs.shipstation.com/authentication) distinguishes standalone API sandbox keys from ShipStation platform accounts, which have no sandbox environment. The supplied [sandbox documentation](https://docs.shipstation.com/apis/shipengine/docs/getting-started/sandbox) states that it does not simulate tracking events and does not support webhooks. Local fault simulation therefore remains essential, and sandbox success would not establish a live carrier stop or warehouse recovery.
