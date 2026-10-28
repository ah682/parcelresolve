# ParcelResolve

ParcelResolve is a local recovery desk for WooCommerce merchants using ShipStation. It helps an operator handle cancellation and address-change requests when the order, payment, label and warehouse records disagree.

The desk gathers evidence, proposes exact actions, asks for approval and reads the resulting state back before marking a case resolved. A printed label never proves physical dispatch. Lost responses are reconciled against durable receipts before another action is attempted.

**The default demo is a simulator with synthetic orders.** It works without credentials or model calls and drafts customer explanations without sending them. Real provider reads and review artifacts use a separate CLI; live recovery writes are unsupported.

## Run locally

You need **Python 3.12, Node 24, npm, uv and make**. Linux is tested; macOS is unverified and Windows is unsupported because the demo uses POSIX file locks.

```bash
npm run dev
```

Open **http://127.0.0.1:8873**. This command installs locked dependencies, builds the interface, seeds six cases and starts the API. First setup needs access to the public Python and npm registries. Use `PORT=8874 npm run dev` to choose another port.

Data persists in `.parcelresolve/` between restarts. To reset the synthetic cases, stop the server with Ctrl+C, then run:

```bash
make reset
npm run dev
```

Reset replaces only the two demonstration databases and refuses while the server is using them. The application is intended for a local machine, not a public deployment.

## Walk through a recovery

Select a case, investigate its evidence, review the proposed actions, approve and execute. Post-label recovery first needs a current **simulated warehouse hold**. The desk shows incomplete work and remaining actions when a step fails.

| Order | What to try |
|---|---|
| **1042** | Cancel before a label exists. Approve the £68 refund and verify the final order/payment state. |
| **1043** | Cancel after label creation. Confirm a simulated hold, then approve the void, cancellation and refund. |
| **1044** | Correct an address. Confirm a hold, then void the old label and verify one replacement label. |
| **1045** | Recover a lost refund response. Use **Reconcile & resume** to find the original refund without refunding twice. |
| **1046** | See a carrier void refusal escalate with evidence and an operator action. |
| **1047** | See partial dispatch block whole-order recovery. |
| **1048** | Create a new request, clarify ambiguous text and inject a failure in the simulation lab. |

The role menu demonstrates viewer restrictions. The simulation lab can inject outages, rate limits, lost responses, stale reads and dispatch races. The [walkthrough](docs/DEMO.md) explains successful and incomplete recoveries.

## Verify

After setup:

```bash
npm test
npm test -- --browser-only
```

The first command runs Python lint/format/type checks, TypeScript checking, the frontend build, automated tests and a 40-scenario evaluation at seeds 7, 19 and 41. Evaluation runs get fresh directories under ignored `evaluation/runs/`.

The second command starts a disposable simulator and exercises real UI actions without changing the main demo data. It needs an installed Chrome, Chromium or Brave executable, or `CHROME_BIN`. Eight separately labelled presentation checks use controlled responses for loading, errors, focus and provenance. Screenshots and reports go to `frontend/qa/`.

The [publication verification](docs/VERIFICATION.md) records **306 passing tests**, **336/336 offline recovery trials**, and **15 browser workflow/contrast checks plus eight presentation checks**. Process-kill tests cover 30 external-write windows and two planning transitions. CI runs the portable offline checks; these results do not establish real carrier or warehouse behavior.

## Integration and model modes

The normal desk uses deterministic intent rules and operator clarification. An explicit request-type selection provides the model-free SOP baseline. Operators must review the request and proposal: the parser has documented classification errors.

A frozen CPU model experiment scored **51/108** classifications versus **57/108** for rules. Its recovery experiment had **42 false resolutions** under scripted approval. That model is rejected by the desk API and retained for explicit evaluation only. [Reports and failure evidence](docs/EVALUATION.md) explain the comparison; weights and runtime downloads are optional and excluded from the repository.

Optional hosted model intake, recorded development fixtures, real read-only adapters and the guarded review CLI are documented in [.env.example](.env.example), [model assets](model_assets/README.md) and [API contracts](docs/API_CONTRACTS.md). The app reads exported environment variables; it does not load `.env` automatically. Hosted model calls require explicit configuration and can incur charges; their quality has not been validated. The default browser uses intentional local demo tokens, not production credentials.

## Scope

One store, one warehouse, whole-order cancellation and domestic address/label recreation. Money uses integer minor units in GBP/USD/EUR; quantities are integral. Split shipments, complex refund/tax allocation, subscriptions, chargebacks, cross-border changes and interception require review or are outside this release.

Two SQLite databases and per-order process locks keep the demo runnable without a database service. The simulator supplies authoritative receipt lookup, idempotency and warehouse fencing. Those guarantees have not been established for real services, and approvals cannot enable unsupported live execution.

See [architecture](docs/ARCHITECTURE.md), [data provenance](docs/DATA.md), [evaluation](docs/EVALUATION.md), [limitations](docs/LIMITATIONS.md) and [build state](docs/BUILD_STATE.md). Merchant data, real payment settlement, physical stop acknowledgments, production security/storage and human handling-time studies remain external validation gates.
