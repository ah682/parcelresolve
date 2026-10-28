What this repo does: ParcelResolve joins order, payment, label and warehouse evidence, proposes recovery actions, binds them to approval, and verifies durable effects. This audit assumes a single local operator using the synthetic simulator, including overlapping browser requests and process interruption; optional real-provider reads do not enable live recovery writes.

**Audit date:** 28 October 2026. **Method:** Ponytail 5.3.2 and relevant Superpowers 7.0.1 skills. Main flows were traced end to end, concrete failures were reproduced, regressions failed before each repair, and the existing verification paths were rerun. Final integration review and hosted checks passed for the recorded revision.

## Must fix — resolved

1. **A recovery read displays the previously selected order** ([app.ts](../frontend/src/app.ts)).
   - **What this is:** After a mutation error, the desk reads the case again because a lost response does not prove that the write failed.
   - **Reproduced problem:** Delay the read for order 1042, select 1043, then release it: the queue selects 1043 while the evidence panel displays 1042.
   - **Small fix and outcome:** Recheck selection after the awaited read, using the existing selection sequence. [The presentation regression](../frontend/scripts/presentation-checks.mjs) now preserves the selected order.
   - **If it regresses:** The operator reviews evidence for a different order than the queue indicates.

2. **An older dialog request destroys a newer draft** ([app.ts](../frontend/src/app.ts)).
   - **What this is:** New request loads order choices asynchronously; submissions also finish after the dialog can close.
   - **Reproduced problem:** Close and reopen New request while the first load waits, type in the newer form, then release the older response. The draft is replaced by an error; a late submission can also close a replacement dialog.
   - **Small fix and outcome:** Bind updates to the actual connected dialog instance. [Controlled delayed responses](../frontend/scripts/presentation-checks.mjs) now preserve the new form and draft.
   - **If it regresses:** A slow response discards current operator work.

3. **A successful zero-total cancellation cannot finish** ([engine.py](../parcelresolve/engine.py)).
   - **What this is:** Valid orders may have zero-priced lines, so cancellation can require no refund.
   - **Reproduced problem:** A £0 order is cancelled, then final verification demands refunded quantities and leaves it escalated with no recovery controls.
   - **Small fix and outcome:** Treat zero-captured cancellations as owing no refund while retaining cancellation, label and dispatch checks. [Labelled and pre-label regressions](../tests/test_recovery.py) verify restart durability, no refund effect, and accurate customer draft wording.
   - **If it regresses:** A supported monetary boundary becomes permanently incomplete or encourages an invented refund.

4. **An interrupted first seed never resumes** ([seed.py](../parcelresolve/seed.py)).
   - **What this is:** Startup creates six demo cases and seven orders.
   - **Reproduced problem:** Stop after the first order is stored but before its case exists. Restart sees that order and returns, leaving one order and zero cases.
   - **Small fix and outcome:** Create missing demo records individually without replacing retained work. [Seed regressions](../tests/test_seed.py) cover interrupted boundaries and preservation of modified and resolved cases.
   - **If it regresses:** A normal first-launch interruption requires a destructive reset to obtain the documented demo.

## Verification and process changes

| Evidence | Baseline | After repairs |
| --- | --- | --- |
| Python suite | 307 passed | 313 passed |
| `npm test` | Existing offline verification | Lint, formatting, Python/TypeScript types, build, tests and evaluation passed |
| Offline recovery evaluation | 336 trials at seeds 7, 19 and 41 | 336/336 expected outcomes across 40 scenarios |
| `npm test -- --browser-only` | 15 workflow checks and 8 presentation checks | 15 workflow checks and 11 presentation checks, including three delayed-response regressions |

The runtime plan contains the [red/green execution record](superpowers/plans/2026-10-28-runtime-audit.md). Earlier 307-test publication evidence remains dated in [VERIFICATION.md](VERIFICATION.md) and [its machine-readable record](verification-results-2026-10-28.json); it is not the repaired 313-test result.

Reproduce the same commands used by [CI](../.github/workflows/verify.yml):

```sh
make setup
make verify
npm test -- --browser-only
```

The browser runner builds the frontend, starts an isolated temporary simulator, and removes that disposable state after stopping it. Chrome must be installed; `CHROME_BIN` can select its executable. Set `EVAL_OUTPUT` or `PARCELRESOLVE_BROWSER_OUTPUT` to retain new evidence separately from older runs.

Verification jobs use pinned action commits, read-only repository permissions, time limits, cancellation of superseded runs, browser regressions and actionlint. [Dependency auditing](../.github/workflows/dependencies.yml) runs on pushes, pull requests and weekly schedules, with [Dependabot](../.github/dependabot.yml) proposals for Actions and npm. The revised workflows passed for the recorded revision.

Verdict: The four reproduced state-management defects are fixed within the existing simulator architecture. Approval amount/version binding, uncertain-effect reconciliation, and the distinction between printed labels and dispatch remain intact.

Not checked: Authenticated merchant, payment, carrier or warehouse behavior; live writes; paid hosted models; distributed deployment; or customer handling time. The rejected CPU model's dated 51/108 classification result and 42 false resolutions remain in [EVALUATION.md](EVALUATION.md), without a new quality claim. An existing Starlette/httpx warning remains. No project license was added.

## Hosted verification — 28 October 2026

Reviewed implementation and workflow revision: `272385848cdbe6740af881bd75ea88ea22617554`.
[Verification](https://github.com/ah682/parcelresolve/actions/runs/40669297574) and
[dependency auditing](https://github.com/ah682/parcelresolve/actions/runs/40669297584) both passed.
The run artifacts retain the generated test/browser evidence for 14 days.
Subsequent documentation-only commits do not change this tested implementation.
