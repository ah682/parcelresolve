# ParcelResolve build state

## Scope and plan

### Publication pass — 28 October 2026

- Isolated release copy; original project remains untouched. Publication plan: `docs/superpowers/plans/2026-10-28-publication.md`.
- Fresh locked setup installed 26 Python packages and npm dependencies, built and started the documented demo; authenticated metadata returned HTTP 200. Server stopped and `make reset` restored six cases.
- Fixed malformed non-ASCII bearer authentication producing HTTP 500. Regression observed RED with the original `compare_digest` TypeError, then GREEN with byte comparison and HTTP 401.
- Final `npm test`: **307 passed in 13.13 s**, one upstream Starlette test-client deprecation warning; Ruff, mypy, TypeScript and production build passed. Default evaluation: **336/336 trials**, 40 scenarios, seeds 7/19/41, 35.65 s.
- Isolated browser acceptance: **15 workflow/contrast and eight presentation checks passed**, five viewport widths without document overflow. Desktop/mobile/partial-failure captures inspected. Fresh reports retain honest synthetic/mode labels.
- README shortened around local setup, operator workflows and limits. Fresh report, per-trial checks, schedules and source hashes retained at `evaluation/results/verified-2026-10-28`; raw current traces/databases remain generated ignored artifacts. Historical compressed safety/model failure evidence and licenses remain intact; weights/runtime caches are excluded.
- Offline contract/review capability reports executed; authenticated reads remain `not_run`, live execution `unsupported`. No paid inference, merchant write, customer message or deployment performed.
- Parent release controller owns independent review, root license/metadata decision, repository audit and GitHub publication. These are publication steps, not claims of production validation.


### Requirement-completion pass — 14 October 2026 (local gates complete)

The user requested all requirements after a literal audit identified incomplete AI comparison and warehouse-hold crash coverage. The earlier passing offline suite remains historical evidence, not proof of these missing requirements.

1. Journal warehouse hold intent, receipts, permission and fresh read-back; test real process termination and ambiguous outcomes around this write.
2. Add and execute a credential-free CPU model comparison using pinned open weights, independent intake data, raw inference/usage evidence and the existing deterministic baseline. Retain deterministic defaults unless measured benefit supports another choice.
3. Add a runnable live review/proposal/approval/dry-run profile for documented contracts; keep unverified external guarantees explicit and block unsupported execution.
4. Close keyboard, loading/error and mode-label UI gaps; rerun the complete local acceptance workflow and update the requirement matrix with exact remaining external gates.

Delegation follows operating rule 12 in the original user prompt: separate evaluation/intake, integration-contract, and frontend work; the primary agent owns warehouse recovery and final integration. No merchant writes, paid model calls, customer messages or deployment are authorized.

Completed:

- Journalled warehouse holds now persist actor, intent, version, receipt and fresh read-back, survive six real SIGKILL windows, and reconcile lost responses without a second request. Additive schema migration preserves existing data. Fifteen regression variants reject unreliable/expired warehouse evidence even before label creation.
- All **305 automated tests passed in 21.30 s**, together with Ruff, mypy (15 source files), TypeScript checking and production asset build. The suite includes **30 actual external-write SIGKILL windows and two interrupted planning transitions**.
- Both default profiles passed **336/336 trials over 40 scenarios and seeds 7/19/41**. Neither produced false resolutions, duplicate effects, end-state stale tracking or new invariant violations. Retained compressed traces/state databases and source hashes were independently verified.
- Actual pinned Qwen CPU inference ran on a separate frozen 36-request corpus: **51/108 correct versus rules 57/108**, across three seeds. Its optional workflow profile failed **45/168 trials**, including **42 false resolutions** when the scripted driver approved misinterpreted requests. All failures are retained. The API now rejects this local model; it remains available only for explicit evaluation. The deterministic parser also has documented classification errors. Hosted AI remains unperformed.
- A distinct labelled development fixture provider and bounded per-case intake provenance/usage receipts are implemented. No raw model runtime logs appear in the operator timeline.
- The separate live review CLI now persists proposals, exact request artifacts, independent owner/product approvals, freshness checks, dry-runs and read-only handoff reconciliation. All **119 integration/review tests passed using mocks**. Credential-free capability reports ran; authenticated live calls and live writes remain unperformed/unsupported respectively.
- Browser acceptance passed **15 workflow/contrast checks plus eight separately disclosed presentation checks**, with no errors or overflow at five widths. Measured contrast passed 1,016 text observations across ten views. Desktop, mobile and partial-failure screenshots were inspected. Final evidence: `frontend/qa/2026-10-14T035836492Z/`.
- `npm run dev` successfully installed locked dependencies, built, preserved/seeded demo data and served the authenticated API; the task-owned server was stopped cleanly. `npm test -- --browser-only` independently started a fresh disposable demo and removed only its own data.
- README, architecture, evaluation/data/model/license, live-contract, UI/walkthrough, limitation and verification records describe the delivered implementation and actual results. Historical evidence remains intact.

### Original implementation plan — 13 October 2026

Build the credential-free, one-store/one-warehouse desk described in `02_Shipping_Recovery_Agent_Prompt.txt`. No deployment, customer messages, or live mutations are authorized.

1. Establish typed domain, durable SQLite ledgers, first pre-label cancellation fixture and acceptance test.
2. Add approval-bound recovery, warehouse hold fencing, uncertain-write reconciliation and fault simulation.
3. Build the operator queue, evidence timeline, approvals, recovery controls and local customer drafts.
4. Add documented read-only live adapters and optional structured model intake; keep unsupported capabilities explicit.
5. Run 30+ synthetic evaluation scenarios across seeded schedules, crash/concurrency tests, type/lint checks and browser QA. Record actual results and limitations.

## Decisions

- Python 3.12, FastAPI/Pydantic, a small TypeScript interface and a persisted state machine.
- SQLite WAL with transactional writes and per-order process locks for the single-machine demo. A separate simulator database prevents a local transaction from disguising an external side-effect failure. PostgreSQL/distributed workers are a later deployment gate; no Docker dependency for this local scope.
- Integer minor units; only explicit supported currencies and integral quantities. Complete order cancellation only; split shipments require review.
- Product permissions, exact action hashes, resource versions and current warehouse acknowledgments control actions. The optional model only interprets text.

## Historical milestones — 13 October 2026

- Read the complete build prompt; workspace contains no prior application code.
- Runtime observed: Python 3.12.3, Node 24.16.0, npm 11.13.0, uv 0.11.28.
- Official ShipStation status documentation confirms that label creation can set Shipped without physical dispatch.
- WordPress plugin changelog checked: 5.0.0 (2026-04-13) added returns/refunds; 5.3.9 is listed for 2026-10-07. Do not assume older plugin defects.
- First vertical slice passed: pre-label cancellation from intake through approval, durable effects and terminal read-back.
- All three local flows implemented through working commerce/payment/shipping/warehouse adapter interfaces; two independent SQLite stores, process locks, approval binding, fault injection and restart recovery.
- Operator interface implemented and connected to the API. Queue, current evidence, approval/execute/reconcile, read-only role, ambiguity clarification, warehouse hold, simulation lab and local drafts are working.
- Current official contracts reviewed; real read-only WooCommerce and ShipStation adapters and optional structured model adapter implemented. All live writes fail explicitly; no merchant/carrier/model calls performed.
- Independent safety review found and fixed historical/current-hold wording, missing recovery controls after a known non-write, dispatch omitted from partial-failure copy, blank address acceptance, validation error formatting, and zero-value returned-quantity address recovery. Regression tests cover them.
- Final `npm test -- browser` passed: **184 Python tests in 8.77 s**, Python lint/format/type checking, TypeScript typecheck/build, **336/336 evaluation trials** over 40 scenarios with seeds 7/19/41, and **13 browser checks**. Actual SIGKILL tests cover 24 mutating boundaries; evaluation adds 108 simulated boundary trials.
- Desktop/mobile/partial-failure screenshots inspected. Five viewport widths have no document overflow; no browser page/network errors in the acceptance run. Final run also verifies queue approval state.
- Retained evaluation artifact and source hashes independently verified. No false resolutions, duplicate effects, end-state stale tracking or newly introduced invariants in either offline profile. Real AI comparison remains unperformed.
- Fresh locked Python installation independently succeeded under `/tmp/parcelresolve-clean-project`; its first-slice and integration/intake checks passed **99/99**. `npm ci` and the documented one-command startup were exercised repeatedly from reset demo state.
- README, architecture/data/evaluation/limitations/API-contract/verification docs, walkthrough, CI configuration and raw replay evidence delivered.

## Release state and later gates

The scoped local release and the additional requirement-completion gates above passed on 14 October. The failed model experiment was preserved and its model excluded from the desk. Start the local desk with `npm run dev`, then open `http://127.0.0.1:8873`. Reproduce local acceptance with `npm test` and `npm test -- --browser-only`.

Remaining external gates require authentic merchant data and authorization: payment settlement, carrier void/replacement limits, live identity mappings, reliable warehouse stop acknowledgment, production storage/security, hosted model quality/cost and measured human/customer outcomes. No merchant credentials or reliable live warehouse mutation contract were supplied. Real recovery writes remain unsupported rather than pretending approvals supply those guarantees. These are the prompt's explicitly deferred real-world gates; the default local demo is runnable and verified. See `docs/LIMITATIONS.md` and `docs/VERIFICATION.md`.
