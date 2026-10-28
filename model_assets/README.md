# Optional local model

The default desk uses deterministic intake. The frozen comparison on 2026-10-14 found no net interpretation improvement from this small model: 17/36 requests correct versus 19/36 for the rules, with more false actionable interpretations. The model is retained only in the evaluation/probe CLI and experimental engine interface for reproduction. The desk API refuses `PARCELRESOLVE_INTAKE_MODE=local-model`.

This is actual open-weight CPU inference, not a recorded-response lookup or hosted API. The weights are [Qwen2.5-0.5B-Instruct Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/9217f5db79a29953eb74d5343926648285ec7e67), revision `9217f5db79a29953eb74d5343926648285ec7e67`, under Apache-2.0. The runtime is the official Linux x86_64 [llama.cpp b11429 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11429), commit `d81235049384534c167caea52b85a694f6103d14`, under MIT. License copies are in `licenses/`; all URLs, byte counts, versions and SHA-256 values are pinned in [local-model.json](local-model.json).

Provision from the project root:

```bash
.venv/bin/python -m parcelresolve.local_model setup --download
PARCELRESOLVE_ENABLE_LOCAL_MODEL=1 .venv/bin/python -m parcelresolve.local_model probe 'I would like to cancel the entire purchase, please.'
```

Provisioning explicitly downloads approximately 509 MB of public weights/runtime archives into ignored `.models/parcelresolve-local-ai`; extracted runtime libraries add approximately 44 MB. It checks the pinned archive, model and executable hashes and writes `installation.json`. Running `setup` without `--download` only verifies or extracts already present artifacts. Ordinary intake never downloads files. The delivered runtime profile was executed on Linux x86_64; other operating systems and CPUs are unverified. There are no additional Python dependencies, GPU requirements, provider credentials or paid calls.

The setup download uses Python HTTPS. In this managed environment standalone approved `curl -fL` downloads were needed; the exact URLs are in the manifest. Those artifacts were then verified and extracted by `python -m parcelresolve.local_model setup`. Do not disable verification or substitute an unpinned file if a download fails.

For an explicit CLI experiment, set `PARCELRESOLVE_ENABLE_LOCAL_MODEL=1`. `PARCELRESOLVE_LOCAL_MODEL_DIR`, `PARCELRESOLVE_LOCAL_MODEL_THREADS` (default 4), and `PARCELRESOLVE_LOCAL_MODEL_SEED` (default 7) configure the probe runtime. The frozen comparison always uses four threads and its recorded seeds. Configuration is server-side. A missing artifact, invalid hash, subprocess timeout or invalid output fails explicitly; it is not replaced with a fabricated inference result. Setting the desk's intake mode to this rejected experimental model fails at API startup.

Every inference uses CPU, temperature 0, context 2048 and maximum eight output tokens. A grammar constrains decoding to `cancel`, `address` or `unknown`; this constrains format, not correctness. Existing input and unsupported-scope guards run before inference and are labeled deterministic when they answer. The model cannot produce identities, amounts, approval or warehouse facts. Runtime stdout/stderr, prompt hashes, token counters, seeds and timings are retained in evaluation traces; the operator timeline contains only bounded provenance and usage.

Run the frozen comparison explicitly:

```bash
PARCELRESOLVE_ENABLE_LOCAL_MODEL=1 .venv/bin/python -m parcelresolve.model_evaluation --output /tmp/parcelresolve-ai-comparison-new --seeds 7 19 41
```

The output directory must be fresh. Prompt, model configuration, grammar, development data and evaluation corpus must match the pre-run freeze. No tuning followed the measured run. Token totals are actual runtime counters; USD 0.00 means no provider charge, not free electricity or hardware. See [evaluation documentation](../docs/EVALUATION.md) for results and limits.
