# Working on ParcelResolve

Read [CONTRIBUTING.md](CONTRIBUTING.md), [ARCHITECTURE.md](docs/ARCHITECTURE.md), and [API_CONTRACTS.md](docs/API_CONTRACTS.md). The current findings and verification are in [QUALITY_AUDIT.md](docs/QUALITY_AUDIT.md).

- When available, apply Ponytail and relevant Superpowers skills. Follow observed reproduction → small failing test → minimal fix → relevant checks → fresh independent review for substantive changes. Use existing authorization and review arrangements; require neither extra approval gates nor a fixed number of agents.
- Trace callers, receipts, approval versions and final read-back before changing recovery logic. Keep money exact and nonnegative; a zero amount does not imply a refund operation.
- Preserve uncertain outcomes. Reconcile a lost external response before replay; never claim a stopped shipment from a printed label alone. Keep physical dispatch and warehouse fencing separate.
- The default is a local synthetic simulator. Real-provider reads do not authorize live writes, and customer explanations stay unsent drafts. Do not expose credentials or contact external providers without task authorization.
- Bind asynchronous UI updates to the current selection and actual dialog instance. Keep delayed-response checks on the normal browser test path.
- Run the relevant Python tests first, then `make verify` for runtime changes. Run `npm test -- --browser-only` for UI changes; it owns disposable simulator state. Workflow edits also need actionlint.
- Docs-only changes need checked links, commands and factual claims, not heavy model or browser runs. Preserve dated failed-model evidence and distinguish synthetic tests from real-service guarantees.
- Do not reset retained data or change licensing incidentally. There is no project `LICENSE` file; preserve existing notices and data permissions.
