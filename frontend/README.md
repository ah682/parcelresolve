# Recovery desk interface

The browser is a small typed TypeScript application bundled with esbuild. FastAPI serves the generated `frontend/dist/index.html` and `/assets` files. No remote fonts, analytics or image services are used.

From the repository root:

```sh
npm run dev
```

This delegates to the repository's `make demo` setup and local server. `npm run build` produces the static files; `npm run typecheck` checks the browser code. Build tool versions are pinned in `package-lock.json`.

The default interface uses the known local simulator tokens `demo-operator` and `demo-viewer`, selected by the role menu. These are demonstration identities, not production login credentials. Amounts, permissions, approvals and warehouse truth are controlled by the backend. Every approval submits the exact displayed plan hash and order revision. Browser timeouts trigger case read-back rather than an automatic repeat of a mutation. Customer text and external evidence are escaped before rendering. No customer messages are sent.

The guarded real-provider profile is a separate CLI that produces read, preview, proposal and dry-run review artifacts. It is not routed through this simulator desk and cannot authorize live writes from the browser.

The queue supports search and status filters. Selected cases show separate commerce, payment, label and physical warehouse states, exact proposed actions, execution attempts, evidence/audit records and a local customer draft. Warehouse hold operations have their own receipt/read-back history, separate from approved recovery actions. An uncertain hold never appears verified, and a historical acknowledgment does not extend an expired hold. Operators can investigate, acknowledge a simulated hold, approve, execute, reconcile, clarify ambiguous requests and queue simulator faults, including warehouse faults.

The footer reports the configured intake mode; each request reports its actual interpretation provenance. Deterministic rules, deterministic safety checks, operator selections/clarifications, local CPU inference and recorded fixtures have distinct labels. A fixture is never presented as real inference or integration verification. Model interpretation does not supply amounts, permissions or warehouse evidence.

Responsive mobile layouts use a horizontally scrolling queue and full-width case details. Dialogs use native focus containment and Escape behavior. Tabs use roving keyboard focus with arrow keys, Home and End; the search shortcut is `/`. Loading progress is announced, errors retain form input, invalid fields get explicit messages and focus, and unavailable evidence disables stale actions until a successful reconnect. Empty queues, searches and order catalogs have dedicated states.

## Reproducible browser acceptance

After installing the project dependencies, use the isolated runner:

```sh
npm test -- --browser-only
```

This builds the frontend, starts an owned temporary simulator on an available loopback port, tests it, and removes that temporary data directory. It does not reset `.parcelresolve` or stop an existing demo. Reports and screenshots go to a new timestamped directory under `frontend/qa`. `npm test` without this flag continues to run the repository's `make verify` target.

`playwright-core` uses an installed Chromium browser (Chrome, Chromium or Brave), or set `CHROME_BIN` to the executable. For a machine without one, install a supported Chromium browser first. To test an already-running **fresh simulator**, use `npm run browser:check`; it mutates the seeded cases, defaults to `http://127.0.0.1:8873`, and accepts `PARCELRESOLVE_BROWSER_URL`. Both runners accept `PARCELRESOLVE_BROWSER_OUTPUT` to choose the evidence directory.

The script verifies actual API-connected UI interactions for the three supported flows, warehouse/refund lost-response reconciliation, carrier rejection, partial dispatch, role restrictions, request creation/clarification, fault injection, incomplete recovery and safe retry. It checks widths 320/390/768/1024/1440, evidence and draft tabs, JS/network errors, and saves desktop/mobile/partial-failure screenshots and a machine-readable report. A separate browser context uses explicitly identified controlled responses to check loading, empty/invalid/unavailable states, keyboard focus, provenance labels and escaped untrusted text. Those presentation checks do not establish backend recovery, model quality or provider behavior.

The [2026-10-14 passing report](qa/2026-10-14T034158716Z/report.json) records 15 workflow/layout/contrast checks and eight controlled presentation checks. All 1,016 computed solid-background text observations across ten views passed their applicable normal/large text thresholds. Screenshots were visually inspected. This is not a full accessibility certification or live integration validation; see the [evidence index](qa/README.md) for scope and earlier runs.
