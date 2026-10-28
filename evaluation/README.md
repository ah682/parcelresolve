# Synthetic recovery evaluation

`catalog.json` contains 40 independent synthetic scenarios and expected outcomes. `manifest.json` records their provenance, split policy and limits. No real merchant or customer data is included.

```bash
.venv/bin/python -m parcelresolve.evaluation --output /tmp/parcelresolve-evaluation-new --seeds 7 19 41
```

The default two profiles are operator-selected SOP and deterministic text intake. Neither is live AI. Read [the methodology](../docs/EVALUATION.md) and [data provenance](../docs/DATA.md) before interpreting counts.

The current delivered safety run is under [results/verified-2026-10-14/](results/verified-2026-10-14/report.md): 336/336 trials passed, including durable warehouse-request grading. The 13 October run remains historical evidence. Raw JSONL and separate SQLite states are losslessly compressed to keep the repository small. Recreate the raw files inside the chosen result directory with:

```bash
gzip -dk traces.jsonl.gz
tar -xzf states.tar.gz
```

The ordinary evaluation command writes uncompressed raw files directly. `ARTIFACTS.json` identifies the delivered compressed artifacts and hashes. These acceptance results do not establish production reliability, model accuracy, handling-time gains or merchant validation.

The separate [frozen intake comparison](results/local-ai-2026-10-14/report.md) performed actual pinned CPU inference on 36 new requests and three seeds. The model scored 51/108 correct versus rules 57/108. Its [experimental recovery run](results/local-ai-workflow-2026-10-14/report.md) failed 45/168 trials, including 42 false resolutions under scripted approval. All failures and raw evidence remain intact; the model is rejected from the desk API and retained only for explicit evaluation. Reproduction, provenance and the later exclusion decision are explained in the methodology.
