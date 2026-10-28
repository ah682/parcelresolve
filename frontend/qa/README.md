# Browser evidence

## Publication verification — 28 October 2026

Latest passing run: [report.json](2026-10-28T070211764Z/report.json), with [presentation report](2026-10-28T070211764Z/presentation-report.json) and [contrast checks](2026-10-28T070211764Z/contrast.json). Chromium 155.0.8059.79 exercised a fresh disposable simulator after the publication authentication fix.

- 15 workflow/layout/contrast checks passed, including the three recovery flows, warehouse/refund reconciliation, partial failure and viewer restrictions.
- Eight controlled-response presentation checks passed; these check loading/errors, keyboard focus, escaping and provenance rather than real provider/model behavior.
- Five widths (320, 390, 768, 1024 and 1440 px) passed document-overflow checks. [Desktop](2026-10-28T070211764Z/desktop.png), [mobile](2026-10-28T070211764Z/mobile.png) and [partial failure](2026-10-28T070211764Z/partial-failure.png) captures were opened and visually inspected.
- No unexpected browser/page/network errors. Contrast checks use computed solid backgrounds and are not a full accessibility audit.

Reproduce with `npm test -- --browser-only`; the runner owns its temporary server/data and preserves `.parcelresolve`.

The evidence below is historical, retained with its original dates.

## Historical verification — 14 October 2026

Passing run: [2026-10-14T035836492Z/report.json](2026-10-14T035836492Z/report.json).

- 15 checks cover real local API/UI workflows, responsive layout, absence of unexpected browser/network errors and measured text contrast.
- Eight separately labeled presentation checks use controlled browser responses for loading, empty/invalid/unavailable states, focus behavior, interpretation provenance and escaped text. They do not validate a model, provider or backend recovery.
- [contrast.json](2026-10-14T035836492Z/contrast.json) and [presentation-report.json](2026-10-14T035836492Z/presentation-report.json) record 1,016 visible text observations across ten views, with zero applicable threshold failures. The minimum ratio is 3.84 for large text, where 3:1 applies; normal text is checked at 4.5:1. Measurement is limited to computed solid backgrounds and is not a full accessibility certification.
- [Desktop](2026-10-14T035836492Z/desktop.png), [mobile](2026-10-14T035836492Z/mobile.png) and [partial failure](2026-10-14T035836492Z/partial-failure.png) screenshots were inspected visually. Five viewport widths, 320–1440 pixels, passed document-overflow checks.

The run used a fresh, temporary local simulator and deterministic intake. All provider effects are synthetic. No real carrier, merchant, warehouse or model verification is claimed by this browser report. Actual optional local model evaluation and guarded provider profiles have their own reports outside this directory.

Earlier artifacts are preserved. The original `report.json` and screenshots document the earlier acceptance pass. Timestamped runs at `2026-10-14T033850746Z`, `2026-10-14T034033704Z` and `2026-10-14T034131491Z` exposed contrast failures during this audit; the final passing run follows the resulting text-color fixes. They are historical results, not current acceptance claims.

Reproduce with `npm test -- --browser-only`. The runner starts and stops its own temporary server, leaves `.parcelresolve` untouched and writes a new timestamped directory.
