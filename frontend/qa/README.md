# Browser evidence

Latest audited passing run: [2026-10-14T035836492Z/report.json](2026-10-14T035836492Z/report.json).

- 15 checks cover real local API/UI workflows, responsive layout, absence of unexpected browser/network errors and measured text contrast.
- Eight separately labeled presentation checks use controlled browser responses for loading, empty/invalid/unavailable states, focus behavior, interpretation provenance and escaped text. They do not validate a model, provider or backend recovery.
- [contrast.json](2026-10-14T035836492Z/contrast.json) and [presentation-report.json](2026-10-14T035836492Z/presentation-report.json) record 1,016 visible text observations across ten views, with zero applicable threshold failures. The minimum ratio is 3.84 for large text, where 3:1 applies; normal text is checked at 4.5:1. Measurement is limited to computed solid backgrounds and is not a full accessibility certification.
- [Desktop](2026-10-14T035836492Z/desktop.png), [mobile](2026-10-14T035836492Z/mobile.png) and [partial failure](2026-10-14T035836492Z/partial-failure.png) screenshots were inspected visually. Five viewport widths, 320–1440 pixels, passed document-overflow checks.

The run used a fresh, temporary local simulator and deterministic intake. All provider effects are synthetic. No real carrier, merchant, warehouse or model verification is claimed by this browser report. Actual optional local model evaluation and guarded provider profiles have their own reports outside this directory.

Earlier artifacts are preserved. The original `report.json` and screenshots document the earlier acceptance pass. Timestamped runs at `2026-10-14T033850746Z`, `2026-10-14T034033704Z` and `2026-10-14T034131491Z` exposed contrast failures during this audit; the final passing run follows the resulting text-color fixes. They are historical results, not current acceptance claims.

Reproduce with `npm test -- --browser-only`. The runner starts and stops its own temporary server, leaves `.parcelresolve` untouched and writes a new timestamped directory.
