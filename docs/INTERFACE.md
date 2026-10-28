# Shared implementation contract

Backend owned by root: `parcelresolve/domain.py`, `storage.py`, `simulator.py`, `engine.py`, `api.py`, `seed.py`, `cli.py`, core tests, dependency files, README and release docs. UI agent owns `frontend/`, `package.json`, `package-lock.json`, `tsconfig.json`, frontend tests/build config. Integrations agent owns `parcelresolve/integrations.py`, `parcelresolve/intake.py`, `tests/test_integrations.py`, `tests/test_intake.py`, `docs/API_CONTRACTS.md`. Evaluation agent owns `parcelresolve/evaluation.py`, `evaluation/`, `tests/test_evaluation.py`, `docs/EVALUATION.md`, `docs/DATA.md`. Do not edit another owner's files without coordination.

## HTTP contract

Same-origin `/api`; default local auth `Authorization: Bearer demo-operator` (simulation-only known credential). Viewer token `demo-viewer` cannot mutate. No real browser credentials. FastAPI serves `frontend/dist` on port 8873 (configurable with `PORT`). All error bodies `{detail: string}`. Mutating responses are full case views. All times ISO UTC.

- GET `/api/meta`: `{mode:'local simulator',interpreter_mode,operator:{id,name,role},capabilities:{live_mutations:false}}`; configured interpreter mode defaults to `deterministic`. The result on each case may have different provenance, such as an operator clarification or deterministic safety check.
- GET `/api/cases`: `{cases:[CaseSummary],stats:{open,needs_attention,awaiting_approval,resolved}}`
- GET `/api/cases/{id}`: CaseView
- GET `/api/orders`: `{orders:[{id,customer_name,commercial_state}]}`
- POST `/api/cases`: `{order_id,text,intent?:'cancel'|'address'|'unknown',target_address?:Address}`
- POST `/api/cases/{id}/investigate`: `{}`
- POST `/api/cases/{id}/hold`: `{}`; journals an operation to confirm a simulated reliable warehouse hold; a lost response remains uncertain until receipt/read-back reconciliation. Never a real warehouse acknowledgment.
- POST `/api/cases/{id}/approve`: `{plan_hash,resource_version}` approves exactly the actions and amounts visible in plan.
- POST `/api/cases/{id}/execute`: `{}`
- POST `/api/cases/{id}/retry`: `{}` durable reconcile/resume; no blind uncertain retries.
- POST `/api/cases/{id}/clarify`: `{intent:'cancel'|'address',target_address?:Address}`; invalidates old plans and requires fresh approval.
- POST `/api/cases/{id}/fault`: `{action_kind,fault}` for local simulation. Kinds `warehouse_hold`, `cancel_order`, `refund`, `void_label`, `update_address`, `create_label`. Faults `before_write`, `lost_response`, `unavailable`, `rate_limit`, `void_rejected`, `stale_read`, `dispatch_race`, `unknown_outcome`. `void_rejected` applies only to `void_label`.

CaseSummary: `{id,order_id,customer_name,intent,status,reason,updated_at,amount:{minor,currency},issue_count,approved}`. An approved plan in `awaiting-approval` is presented as ready to execute; the internal status changes to executing only when execution starts.
CaseView extends CaseSummary with `{request,order,plan,approvals,attempts,warehouse_attempts,evidence,disagreements,draft,interpreter_mode,permitted}`.
Status strings: `received`, `investigating`, `needs-information`, `proposal-ready`, `awaiting-approval`, `executing`, `reconciling`, `resolved`, `escalated`, `failed`.
Address: `{name,line1,city,postcode,country}`. Money: `{minor: integer,currency:'GBP'|'USD'|'EUR'}`.
Request: `{text,intent,target_address}`.
Order: `{id,store_id,woo_id,shipstation_order_id,shipstation_order_key,version,customer_name,commercial_state,address,payment:{captured,refunds},lines:[{id,sku,title,quantity,unit_price,refunded_quantity,dispatched_quantity}],labels:[{id,shipment_id,status,tracking,address}],shipments:[{id,order_key,line_quantities,status}],warehouse:{state,ack_id,acknowledged_at,expires_at,reliable},tracking,observed_at}`.
Plan: `{id,hash,resource_version,actions:[{id,kind,title,amount,label_id,address}],created_at,hold_ack_id}` or null.
Approval: `{id,case_id,plan_hash,resource_version,operator_id,created_at,action_hash,amount}`.
Attempt: `{id,case_id,action_id,kind,status,idempotency_key,provider_id,error,created_at,updated_at}`; status `intent`, `uncertain`, `succeeded`, `failed`.
WarehouseAttempt: `{id,case_id,action_id,kind:'warehouse_hold',status,idempotency_key,provider_id,resource_version,result_version,error,retryable,operator_id,verified_at,readback_status,created_at,updated_at}`. The UI displays this separately from approved-plan actions. A successful receipt requires successful read-back before the hold operation is shown as verified. Current warehouse state and hold expiry remain authoritative; a historical receipt cannot extend a hold. Retry reconciles a pending warehouse operation before resuming ordinary recovery; an unknown, unrecoverable outcome stays escalated.
Evidence: `{id,source,kind,message,created_at,data}`. Disagreement: `{code,severity,message}`. `permitted` boolean keys `investigate`, `approve`, `execute`, `hold`, `retry`.

The UI labels `deterministic`, deterministic safety checks, `operator-selected`, `operator-clarified`, and `local-model` distinctly. Recorded/fixture provenance is explicitly identified as recorded. The configured mode in `/api/meta` does not override the actual mode attached to a request result. Mobile views retain this result label.

## Python engine/evaluation contract

`Storage(directory: pathlib.Path)` owns ledger.sqlite; `Simulator(directory)` owns providers.sqlite. `Engine(directory, *, crash_hook=None)` initializes both and exposes `.store`, `.sim`.
`seed_demo(engine)` populates development fixtures only.
`make_order(order_id='1042', *, labelled=False, dispatched=False, partial=False) -> OrderSnapshot` fixture helper.
`engine.sim.put_order(order)`; `.read(order_id)`; `.external_change(order_id, change: str)` where change `address`, `dispatch`, `expire_hold`, `partial_dispatch`; `.inject(order_id, action_kind, fault)`; `.confirm_hold(order_id)`.
`engine.create_case(order_id, text, intent='cancel', target_address=None, operator=OPERATOR) -> dict`; `.investigate(case_id, operator=OPERATOR)`, `.hold(...)`, `.approve(case_id, plan_hash, resource_version, operator=OPERATOR)`, `.execute(...)`, `.retry(...)`, `.view(...)` each returns CaseView dict. OPERATOR, VIEWER from engine. `engine.store.list_cases()` yields raw case dicts; `.events(case_id)`, `.attempts(case_id)` expose ledger records. `.sim.effects(order_id)` lists successful effects.
`crash_hook(boundary: str, action: ProposedAction)` called `after_intent`, `after_effect`, `after_record` for each action; raising a `BaseException` simulates abrupt process exit. Real SIGKILL/subprocess coverage also required.
`engine.ingest_event(event_id, order_id, version, payload)` deduplicates and prevents projection regressions; events never authorize actions.

Intake module exports `interpret_request(text: str, *, mode='deterministic') -> Interpretation` with `.intent` cancel/address/unknown, `.needs_clarification` bool, `.explanation` str, `.mode` str. No identity, amount or authorization from model output. Real adapter opt-in via environment; offline default performs no network calls.
