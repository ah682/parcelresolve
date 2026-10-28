# Contributing

Read the [demo](docs/DEMO.md), [architecture](docs/ARCHITECTURE.md), and [API contracts](docs/API_CONTRACTS.md). The browser desk is a local synthetic simulator. A useful bug report supplies a small synthetic order, request, approval, fault or interruption point, source revision, and expected versus actual durable state. Remove customer data and credentials from reports.

Reproduce the failure before editing and add a regression that fails at the relevant boundary. Fix the cause in the existing engine, storage or UI path, then run the affected checks. Seek a fresh independent review after substantive behavior or workflow changes pass. When available, use Ponytail and the relevant Superpowers skills for diagnosis, tests, verification and review; do not add approval gates to work the user has already authorized.

The standard offline commands are:

```sh
make setup
make verify
npm test -- --browser-only
```

`npm test` also runs `make verify`. This includes formatting, lint, types, frontend build, the Python suite and recovery evaluation at seeds 7, 19 and 41. During a focused fix, run the relevant test file first. Browser-only verification uses installed Chrome, a fresh temporary simulator and its own demo credentials; `CHROME_BIN` selects a different executable. The runner stops the server and removes its temporary databases. These commands are configured in [CI](.github/workflows/verify.yml).

For UI changes, retain the controlled response-order tests and inspect screenshots when layout changes. For workflow changes, run actionlint as well as the affected command. For documentation-only changes, check links, commands and evidence claims; do not retrain a model or repeat the recovery matrix just to edit prose.

Preserve the recovery contract: approval binds the exact amount, action and version; a lost response requires receipt reconciliation before retry; label creation does not prove dispatch or warehouse hold; and resolution requires verified read-back. Customer messages remain drafts. The zero-value path must not invent refunds. Seed repair must preserve existing orders, approvals, cases and effects. Reset is for disposable data and must refuse an active server.

Real adapters remain read-only, and approvals cannot enable unsupported live execution. Keep hosted/model modes explicit, retain rejected-model failures, and separate synthetic evaluations from evidence about real services. Record new results in a new output location with the command and environment, following [DATA.md](docs/DATA.md) and [EVALUATION.md](docs/EVALUATION.md).

This repository currently has no project `LICENSE` file. Do not add or imply a license as part of an unrelated change; preserve existing third-party terms and data permissions.

Install ShellCheck alongside actionlint when checking workflow edits, so embedded shell commands are validated as they are on the GitHub runner.
