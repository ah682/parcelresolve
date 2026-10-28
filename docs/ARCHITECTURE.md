# Implementation architecture

## Boundary and ownership

`api.py` exposes an authenticated same-origin FastAPI API. `frontend/src/app.ts` renders the queue, evidence, approval plan, execution history and unsent customer explanation. The default server binds only to loopback; TrustedHost and origin checks protect browser request boundaries. Every case read and write checks the authenticated operator's store scope; viewers cannot mutate. Synthetic demo tokens are fixed by default and intentionally selectable in the UI. Production identity federation, revocation and tenant administration are not implemented.

`domain.py` contains Pydantic records for order snapshots, money, lines, refunds, shipments, labels, warehouse acknowledgment, requests, recovery cases, plans/actions, approvals, operation attempts and evidence. Money is a strict integer in GBP/USD/EUR minor units. Fractional quantities, floats/bools as money, negative balances, over-refunds, unsupported currencies and inconsistent captured line totals are rejected. Address strings are stripped and must remain nonblank; this is structural validation, not carrier address certification.

Commercial status, captured/refunded payment, line cancellation/refund/dispatch quantities, label state, shipment status, physical warehouse state and draft-only notification status remain separate. The UI explicitly distinguishes a printed label from an acknowledged hold and from physical dispatch.

## Persistence and resource serialization

`storage.py` applies additive schema versions 1 and 2 in `ledger.sqlite`: cases, append-only evidence, action attempts, approvals, delivery deduplication, monitored projections and warehouse hold attempts. `simulator.py` separately initializes `providers.sqlite`: authoritative synthetic order records, history, fault queue, action receipts and warehouse hold receipts. Both use WAL, full synchronous commits and bounded busy timeouts. Keeping them separate exposes the write/acknowledgment gap instead of hiding it in a shared transaction. Existing version-1 data remains readable; the migration adds tables without discarding records.

A hashed per-order `flock` file prevents concurrent operators, cases and processes from writing the same resource. Lock acquisition fails with a recoverable conflict; a process death releases the lock. SQLite commits persist intent, receipts and case transitions. These are single-machine guarantees; shared network filesystems and distributed workers are unsupported. A server-lifetime shared lock makes demo reset refuse while that directory is serving requests.

SQLite replaces the suggested PostgreSQL solely for the credential-free single-machine release. Moving to multiple hosts requires transactional resource leases/fencing in PostgreSQL, migration and backup procedures, not merely pointing this program at a shared disk. The persisted state machine avoids an unnecessary workflow framework for these bounded flows.

## Lifecycle and actions

The allowed transition table is executable in `domain.TRANSITIONS`. Cases begin `received`, enter `investigating`, then request information, escalate, or move through `proposal-ready` and `awaiting-approval`. Explicit approval leaves the plan ready to execute. Execution enters `executing`, then `reconciling`, and only a fresh verified terminal state can reach `resolved`. Known failures remain `failed`; unsupported or unknowable outcomes are `escalated`. Consequential transitions and reasons are persisted together.

`Engine._propose` derives actions from backend policy and a fresh provider read. Plans store the exact action list, resource version and warehouse acknowledgment identity. Each approval stores case, plan hash, action hash, resource version, operator, timestamp and amount. Replanning always produces a new hash; an old approval cannot authorize it. Customer text cannot set these values.

Cancellation actions void any active label, cancel the commerce/shipment allocation, then refund the remaining captured money. Address actions void the old label, update the domestic address, then create one replacement. A current acknowledged hold is mandatory for labelled recovery and for address/label creation. Pre-label cancellation requires reliable positive not-dispatched evidence or a current reliable hold; absent, unreliable or expired evidence fails at planning, approval, execution, the provider boundary and final verification. Split shipments, partial dispatch, mismapped quantities, duplicate active labels and complex return/refund states require review.

Before each effect:

1. Persist an intent with a stable operation key.
2. Revalidate the approved resource version and hold at the provider write boundary.
3. Apply the effect through the local commerce/payment/shipping interface.
4. Persist the provider receipt and resulting resource version.
5. Read back current state before continuing.

The simulator atomically enforces resource version, warehouse fence, idempotency key and action hash. A forced dispatch race changes warehouse truth before these checks and blocks the pending effect. This strong simulator contract is deliberately **not** advertised as an existing live provider capability.

## Recovery and incomplete work

`after_intent`, `after_effect` and `after_record` are explicit crash-test boundaries for each external mutating action, including the warehouse hold. A restart finds `executing`/`reconciling` cases and resumes only already-approved financial/label plans. Pending/uncertain operations are queried by their persisted key before any retry. A known successful receipt is recorded without replaying the action; a definitively unwritten action may retry with the same key. If the provider cannot establish the outcome, the case escalates. Ordinary failed financial/label cases remain operator-controlled until reconcile/resume is requested.

Warehouse requests have their own typed `WarehouseHoldAttempt` and provider receipt table. An authenticated operator's explicit hold request persists its actor, exact resource version and stable operation key before calling the warehouse. Startup reconciles interrupted requests and verifies the original acknowledgment, freshness and physical quantities before generating a proposal. It cannot approve or execute the resulting refund/label plan. Lost responses reuse the same receipt rather than renewing the hold; expired, changed or unknowable holds require review. An unresolved hold prevents clarification/replanning from bypassing the pending request. The API exposes warehouse attempts separately from approved plan progress. Local planning interrupted between durable transitions retains a working Investigate control.

Current resource state must equal the plan's starting version plus its recorded effect chain. External changes invalidate the plan. A conclusively unwritten interrupted case can re-investigate, but any uncertain or completed effect prevents replacing its plan. Partial operations remain visible: cancellation does not imply refund success, and label void does not imply replacement success. There is no fictional rollback. Creating a replacement is a new compensating action; an old label cannot be unvoided and a refund is not reversed.

Final checks include commercial state, refund total/quantities, shipment allocation, active-label count/address, active tracking, physical quantities and current hold evidence. Historical resolved drafts date their verification rather than claiming a short-lived hold remains current forever.

## Events and models

Incoming simulator events have stable IDs and monotonic order versions. Duplicates are ignored; older/equal versions do not regress the monitoring projection. Deliveries stay in the timeline and never authorize writes or override authoritative action-boundary reads. No live webhook listener is claimed.

`intake.py` implements deterministic rules, a separately labelled exact-match development fixture provider, an explicitly enabled OpenAI Responses adapter with a strict output schema, and a pinned local CPU language-model adapter for evaluation. It returns intent/clarification/mode only. Trusted order context, structured operator address, monetary calculations, policy and authorization stay outside the model. Remote notes and model explanations are treated as data; bounded local explanation text replaces model prose. API failures, invalid output and refusal do not produce actions. Intake evidence persists bounded mode, model and measured usage provenance from the single inference call. Raw runtime logs remain in optional evaluation artifacts, outside the operator timeline.

`local_model.py` runs pinned Qwen2.5-0.5B-Instruct GGUF weights through a pinned llama.cpp CPU executable. Setup is explicit; normal intake never downloads code or weights. Hash verification, bounded threads, a timeout, JSON-escaped customer input and a grammar restrict execution and output. Public model/runtime licenses and revisions are recorded in `model_assets/`. Evaluation separates development probes from a frozen comparison corpus and records real inference, token counts, latency, classification errors and recovery outcomes. The executed comparison found worse classification and unsafe workflow outcomes from this model. `api.create_app()` therefore rejects `local-model` before opening the desk; direct engine and evaluation entry points retain it for explicit experiments. Deterministic intake remains the default, and hosted OpenAI quality is unverified.

`integrations.py` implements documented WooCommerce v3, ShipStation V1 order and V2 label reads with explicit identity normalization, finite timeouts, bounded reads/retries, response validation and safe errors. WooCommerce OPTIONS capability discovery and a capability-checked non-mutating refund preview distinguish preview `line_item_id` from create-request `id`. Live observations remain distinct from domain simulator records. Unsupported mutations and warehouse confirmation raise capability errors, never mock results.

`guarded_live.py` provides a separate durable review CLI. Merchant-verified identity bindings and fresh joined observations produce exact documented cancellation/refund/address/label-void request artifacts. Separate store-scoped owner authorization and operator product approvals bind the case, proposal/action hashes, resource version and amounts, expire, and become unusable after observed state changes. A dry-run re-reads current state and reports unsupported actions and missing guarantees. Execution checks configuration, authority, approval and freshness, then still raises a capability error: there is no live write transport or verified physical warehouse fence. Operator-reported external handoffs can be recorded as uncertain and reconciled by reads without replay or claims of attribution, payment settlement or physical stop. `docs/API_CONTRACTS.md` documents each command and the contracts actually checked.
