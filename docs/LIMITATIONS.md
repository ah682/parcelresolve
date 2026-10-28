# Release limits and remaining gates

## What the evidence establishes

The delivered local simulator executes the three recovery flows, persists approvals and external-write intent (including warehouse holds), survives tested process deaths, reconciles lost responses, prevents tested conflicting writes, and presents incomplete outcomes in a functional browser desk. The default 40-scenario evaluation is synthetic acceptance evidence against visible fixtures. A separate frozen 36-request comparison runs actual local AI and retains its errors. Neither establishes merchant accuracy, demand or handling-time gains.

## Model decision from measured results

- The pinned Qwen CPU model scored 51/108 classifications versus 57/108 for deterministic rules on 36 new requests repeated across three seeds. It made more false actionable and wrong-intent predictions. All errors and raw inference receipts are retained; no model selection or prompt tuning used these results.
- Its experimental full workflow profile passed 123/168 trials and made 42 false resolution claims when the synthetic operator driver approved its misinterpreted address requests. Those failures are not part of the passing default release. `create_app()` now refuses `local-model` intake; this model is retained only for explicit evaluation/reproduction.
- The deterministic parser also made classification errors on the frozen corpus. Operator review of the original request and exact approval remain necessary. Neither interpreter is claimed to understand arbitrary customer language reliably.
- The OpenAI adapter is separately configurable and transport/schema tested; no paid hosted call or hosted quality comparison was performed. Local model provider charges were USD 0.00; electricity and hardware costs were not priced. Counted scripted steps are not observed human handling time.

## Live integration gates

- No merchant credentials were supplied. Real WooCommerce, ShipStation, gateway, carrier and warehouse contract checks were **not run**. Current official documentation was reviewed; transport/schema behavior was exercised with mocks. See `API_CONTRACTS.md` for exact supported GETs and report status.
- Real mutations are unsupported. `guarded_live.py` supplies a durable observation/proposal/owner-authorization/product-approval/dry-run workflow, plus read-only reconciliation of operator-reported external actions. It still rejects execution even with all gates satisfied. Supported Woo capability discovery/refund preview is explicitly non-mutating. A live writer requires verified per-operation contracts, inventory completeness, gateway settlement, physical fencing and uncertain-outcome semantics; a documented URL alone is insufficient.
- WooCommerce refund records do not independently prove gateway settlement. A carrier's label-void acceptance does not establish a payment refund, physical stop or warehouse acknowledgment.
- Simulator idempotency receipts, definitive absence of an operation and atomic dispatch/hold fencing are stronger guarantees than have been verified from live services. There is no claim of exactly-once live side effects.
- No real warehouse provides this demo's reliable five-minute hold acknowledgment. A live post-label case remains operator-controlled until such a contract is verified. Simulated physical dispatch is not carrier evidence. Address recovery leaves the parcel held; an operator must validate current evidence before physical release.
- The ShipStation API sandbox does not reproduce live carrier/warehouse operations; its lack of simulated tracking/webhooks prevents using it as recovery validation. Platform V1/V2 products and standalone API accounts are not interchangeable.

## Product and data limits

- One store and one warehouse; whole-order recovery only. Partial/split shipments are monitored and escalated. No subscriptions, chargebacks, cross-border tax changes, interception, returns logistics or arbitrary 3PL integration.
- GBP/USD/EUR with integral minor units and integral quantities only. Captured total must equal complete line totals. Shipping charges, taxes, discount allocation, multiple captures and more complex refund accounting need additional contracts and review.
- Address validation rejects blank/incomplete structural data but does not prove deliverability. No postal/carrier certification was run.
- All orders, people, addresses, events and evaluation scenarios are synthetic. No authentic merchant adoption, handling-time savings, customer satisfaction or competitive superiority has been measured.
- Customer copy is a local draft. There is no send feature, tracking email integration or messaging automation. Resolved statements describe dated verification; they do not prove later physical conditions.

## Deployment limits

- Single-machine SQLite WAL and POSIX file locks; no distributed worker orchestration, PostgreSQL deployment, high-availability design, backup/restore validation or production migrations.
- Fixed demo bearer tokens are for local synthetic use. They are not production login, credential rotation or tenant isolation infrastructure. Server-side store/role checks are tested, but the demo must remain on loopback.
- The event endpoint is an internal simulator method, not an authenticated live webhook ingestion service. The ledger is append-only through application methods but not cryptographically tamper-evident against a filesystem administrator.
- The local API's read/write work is synchronous and intentionally small. No load, throughput, recovery SLA or reliability threshold has been established. One current Starlette test-client deprecation warning for httpx is documented; all API tests pass on the pinned environment.
- CI configuration is supplied; no hosted CI run, public deployment, external repository push, paid hosted model call or live mutation was performed. Actual local CPU inference was run and failed to justify product adoption.

## Next real-world validation

Use a consenting test merchant and explicit owner authorization to verify GET mappings first. Establish gateway and warehouse contracts, then add guarded mutations with uncertain-outcome probes and carrier-specific limits. Evaluate actual anonymized cases with provenance and a held-out split. Measure human handling time and error outcomes in a supervised pilot before making adoption or productivity claims.
