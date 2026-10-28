# ParcelResolve

An operator desk for cancellation and address-change requests when commerce, payment, label and warehouse records disagree. It joins the evidence, proposes exact actions, requires approval, and verifies the result. A printed shipping label never counts as physical dispatch evidence.

**The default product is a working local simulator.** It uses synthetic data, drafts customer explanations without sending them, and makes no merchant, carrier or model calls. Real WooCommerce and ShipStation observations, refund previews and approved request artifacts use a separate guarded review CLI. Live recovery execution remains explicitly unsupported until merchant, provider and physical warehouse guarantees are verified.

## Start

Prerequisites: Python 3.12, Node 24, npm and uv. The verified environment is Python 3.12.3, Node 24.16.0, npm 11.13.0 and uv 0.11.28 on Linux. macOS is expected to support the file-lock mechanism but was not tested; Windows is not supported by this release.

```bash
npm run dev
```

This single command installs locked dependencies, builds the interface, seeds the local data once and starts the API at **http://127.0.0.1:8873**. First setup needs the public Python/npm registries; the installed demo works offline. `make demo` is equivalent. Use `PORT=8874 npm run dev` if that port is occupied.

To start over, stop the server with Ctrl+C and run:

```bash
make reset
npm run dev
```

Reset replaces only the two owned demonstration databases. It refuses while the server is using that directory. Data persists across ordinary restarts in `.parcelresolve/`. Do not run this desk against a production filesystem or expose it publicly.

## Try it

| Order | Request / expected behavior |
|---|---|
| **1042 — Jamie Taylor** | Pre-label cancellation. Review the £68.00 refund, approve, then execute. Order, line quantities, payment and shipment state are read back before resolution. |
| **1043 — Morgan Ellis** | Label printed, dispatch unknown. Confirm the **simulated** warehouse hold, approve the void/cancellation/refund plan, then execute. |
| **1044 — Sam Rivera** | Address correction. Confirm a hold, approve, execute. The old label is voided, the address changes and exactly one replacement label/tracking record is verified. |
| **1045 — Robin Chen** | Refund response is lost. Investigate, approve, execute. The case stays reconciling; **Reconcile & resume** finds the original refund and resolves without another refund. Restarting the server also reconciles pending approved work. |
| **1046 — Alex Brooks** | Carrier rejects the void. Confirm hold, approve, execute. The case escalates with its evidence and remaining operator action. |
| **1047 — Casey James** | Partially dispatched order. Whole-order recovery is blocked for operator review. |
| **1048 — Drew Parker** | Unused order for **New request**. Try ambiguous wording, clarify it, then use the simulation lab to inject a refund failure. |

The queue, evidence/audit tab, exact approval controls, execution receipts and customer draft all use the API. The role menu demonstrates operator versus viewer permissions on synthetic data. The lab injects before-write failure, lost response, stale reads, service outages, rate limits, dispatch races and unknowable outcomes. No customer-message send feature exists.

Warehouse holds now have durable intent, operator identity, provider receipt and fresh read-back records. To exercise a hold timeout, choose **Warehouse hold → Lost response** in the lab before confirming a hold. Reconcile finds the same acknowledgment without issuing another stop request. Expired, unreliable or unknowable evidence cannot authorize recovery, including before label creation.

## Verify

```bash
npm test
```

This runs Python lint/format/type checks, TypeScript checking and build, the automated test suite, and the 40-scenario evaluation with seeds 7, 19 and 41. Results are written to a new timestamped directory under `evaluation/runs/`; previous evidence is preserved. `make test`, `make check` and `make evaluate` run individual stages.

For isolated browser acceptance, run:

```bash
npm test -- --browser-only
```

This starts and stops a disposable simulator, preserving the main demo data. Browser checks require an installed Chrome/Chromium/Brave executable or `CHROME_BIN`. They perform real local UI actions; controlled response fixtures separately exercise loading, failure and provenance presentation. Timestamped screenshots and reports are saved in `frontend/qa/`. `npm test -- browser` still supports an already-running fresh demo. CI runs the portable offline tests and evaluation; headless browser verification was run locally.

The [verification matrix](docs/VERIFICATION.md), [evaluation methodology](docs/EVALUATION.md) and [browser evidence index](frontend/qa/README.md) link actual results. The 14 October completion pass passed **305 automated tests** and **336/336 default recovery trials**. Real process-kill tests cover 30 external write windows, including warehouse holds, plus two interrupted planning transitions. Historical evidence remains preserved.

The new [frozen AI comparison](evaluation/results/local-ai-2026-10-14/report.md) used real CPU inference on 36 independent synthetic requests and three seeds. The pinned small model scored **51/108**, versus **57/108** for rules. Its [experimental workflow evaluation](evaluation/results/local-ai-workflow-2026-10-14/report.md) passed only **123/168**, with **42 false resolutions** when the synthetic driver approved misinterpreted requests. These are failed model results, not passing product gates. The desk API therefore rejects this local model; its code and failure traces remain available for evaluation. No model or prompt was tuned on the frozen comparison.

## Modes and configuration

`.env.example` documents supported environment variables; export selected variables in the process environment (the app does not automatically load `.env`). Default tokens `demo-operator` and `demo-viewer` are intentional local-demo identities, not production credentials. Secrets for optional provider reads or model calls stay server-side. The browser only sees its synthetic desk token.

- **Default deterministic intake:** conservative text rules classify cancellation/address/unknown. Ambiguous text needs operator clarification. An explicit request-type selection implements the model-free SOP baseline.
- **Recorded fixture provider:** a separate exact-match development provider is available for interface testing, explicitly labelled `recorded-fixture`. It is not a model and is excluded from AI comparisons. See [model assets](model_assets/README.md).
- **Optional real model intake:** set `PARCELRESOLVE_INTAKE_MODE=openai`, `PARCELRESOLVE_ALLOW_MODEL_NETWORK=1`, `OPENAI_API_KEY` and an explicit `OPENAI_MODEL` supporting Responses structured outputs. This opt-in can incur provider charges. No model is selected by default and no paid calls were run. The model only classifies intent; it cannot select identities, money, permissions or warehouse state. Supply a structured address separately.
- **Actual local AI, evaluation only:** pinned Qwen2.5-0.5B-Instruct and llama.cpp run on CPU without paid API access. Provision explicitly with `.venv/bin/python -m parcelresolve.local_model setup --download`, then run `PARCELRESOLVE_ENABLE_LOCAL_MODEL=1 .venv/bin/python -m parcelresolve.model_evaluation --output evaluation/runs/my-intake-comparison`. Choose a fresh output directory. This does not enable the model in the desk. See [model assets](model_assets/README.md) for hashes, licenses and platform requirements.
- **Real contracts and guarded review:** `.venv/bin/python -m parcelresolve.cli contracts` and `.venv/bin/python -m parcelresolve.guarded_live capabilities` report unperformed/unsupported capabilities without credentials. The configured review CLI creates documented requests, binds separate owner and product approvals to exact amounts/versions, revalidates state, produces dry-runs, and reconciles operator-reported handoffs without replay. See [API contracts](docs/API_CONTRACTS.md) for exact commands, identity bindings and configuration. Approvals cannot bypass unsupported live execution or substitute for a reliable physical stop.

## Scope and limits

One store, one warehouse, whole-order cancellation and domestic address/label recreation. Supported money is integral minor units in GBP/USD/EUR, with integral line quantities and fully captured line totals. Unsupported currency/quantity shapes and complex refund/split-shipment cases require review. Fees, discounts, tax allocation, subscriptions, chargebacks, cross-border changes, carrier interception and arbitrary 3PL contracts are outside this release.

The local state machine uses two SQLite databases and per-order process locks. This keeps the demo runnable without Docker/PostgreSQL while testing separate desk/provider commits. The simulator provides authoritative operation lookup, idempotency and atomic warehouse fencing; real services have not been shown to provide those guarantees. This is not a production deployment or a claim of exactly-once live effects.

Read [architecture](docs/ARCHITECTURE.md), [data provenance](docs/DATA.md), [evaluation](docs/EVALUATION.md), [limitations](docs/LIMITATIONS.md), [walkthrough](docs/DEMO.md) and [build state](docs/BUILD_STATE.md). Merchant cases, actual gateway settlement, carrier behavior, warehouse stop acknowledgments and human handling-time/adoption studies remain future gates.
