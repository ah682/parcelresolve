"""One-pass comparison of the frozen intake corpus using actual local CPU inference.

Expected labels are used only after each interpreter returns. No hosted model is
called. Prompt, configuration and corpus hashes must match the pre-run freeze.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .intake import IntakeConfigurationError, interpret_request_with_receipt
from .local_model import (
    DEFAULT_DIRECTORY,
    GRAMMAR,
    LOCAL_SYSTEM,
    MANIFEST_PATH,
    ROOT,
    LocalModelInterpreter,
    sha256_file,
)

CORPUS_PATH = ROOT / "evaluation" / "intake-benchmark.json"
DEVELOPMENT_PATH = ROOT / "evaluation" / "intake-development.json"
FREEZE_PATH = ROOT / "evaluation" / "model-comparison-freeze.json"
MODES = ("deterministic", "local-model")
LABELS = ("cancel", "address", "unknown")


def validate_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    freeze = json.loads(FREEZE_PATH.read_text())
    checks = {
        "evaluation_corpus_sha256": sha256_file(CORPUS_PATH),
        "development_corpus_sha256": sha256_file(DEVELOPMENT_PATH),
        "model_manifest_sha256": sha256_file(MANIFEST_PATH),
        "system_prompt_sha256": hashlib.sha256(LOCAL_SYSTEM.encode()).hexdigest(),
        "grammar_sha256": hashlib.sha256(GRAMMAR.encode()).hexdigest(),
    }
    for key, actual in checks.items():
        if freeze[key] != actual:
            raise ValueError(f"Frozen comparison changed: {key}. Do not tune on evaluation results.")
    corpus = json.loads(CORPUS_PATH.read_text())
    development = json.loads(DEVELOPMENT_PATH.read_text())
    records = corpus["records"]
    texts = {row["text"] for row in records}
    if len(texts) != len(records) or len({row["id"] for row in records}) != len(records):
        raise ValueError("Repeated intake record or identifier")
    if texts.intersection(row["text"] for row in development["records"]):
        raise ValueError("Evaluation and development intake splits overlap")
    if any(
        row["expected_intent"] not in LABELS
        or row["expected_needs_clarification"] != (row["expected_intent"] == "unknown")
        for row in records
    ):
        raise ValueError("Invalid benchmark annotation")
    return freeze, corpus


def grade_interpretation(record: dict[str, Any], interpretation: dict[str, Any] | None) -> dict[str, Any]:
    predicted = interpretation.get("intent") if interpretation else None
    clarification = interpretation.get("needs_clarification") if interpretation else None
    return {
        "correct": predicted == record["expected_intent"]
        and clarification is record["expected_needs_clarification"],
        "expected_intent": record["expected_intent"],
        "predicted_intent": predicted,
        "false_actionable_interpretation": record["expected_intent"] == "unknown"
        and predicted in {"cancel", "address"}
        and clarification is False,
        "unnecessary_clarification": record["expected_intent"] != "unknown"
        and (predicted == "unknown" or clarification is True),
        "wrong_actionable_intent": record["expected_intent"] in {"cancel", "address"}
        and predicted in {"cancel", "address"}
        and predicted != record["expected_intent"],
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for mode in MODES:
        selected = [row for row in rows if row["mode"] == mode]
        times = [row["receipt"].get("elapsed_seconds", 0) for row in selected]
        actual = [row for row in selected if row["receipt"].get("model_calls")]
        missing_usage = sum(
            not all(key in row["receipt"].get("usage", {}) for key in ("input_tokens", "output_tokens"))
            for row in actual
        )
        profiles[mode] = {
            "trials": len(selected),
            "unique_requests": len({row["record_id"] for row in selected}),
            "correct": sum(row["grade"]["correct"] for row in selected),
            "errors": sum(row["error"] is not None for row in selected),
            "false_actionable_interpretations": sum(
                row["grade"]["false_actionable_interpretation"] for row in selected
            ),
            "unnecessary_clarifications": sum(row["grade"]["unnecessary_clarification"] for row in selected),
            "wrong_actionable_intents": sum(row["grade"]["wrong_actionable_intent"] for row in selected),
            "model_calls": sum(row["receipt"].get("model_calls", 0) for row in selected),
            "guarded_without_inference": sum(
                bool(row["receipt"].get("guarded_without_inference")) for row in selected
            ),
            "input_tokens": sum(row["receipt"].get("usage", {}).get("input_tokens", 0) for row in selected),
            "output_tokens": sum(row["receipt"].get("usage", {}).get("output_tokens", 0) for row in selected),
            "missing_usage_records": missing_usage,
            "provider_cost_usd": "0.00",
            "intake_seconds": sum(times),
            "median_intake_seconds": statistics.median(times),
            "p95_intake_seconds": sorted(times)[min(len(times) - 1, int(len(times) * 0.95))],
            "confusion_matrix": {
                expected: dict(
                    Counter(
                        str(row["grade"]["predicted_intent"])
                        for row in selected
                        if row["grade"]["expected_intent"] == expected
                    )
                )
                for expected in LABELS
            },
            "seed_results": {
                str(seed): {
                    "correct": sum(row["grade"]["correct"] for row in selected if row["seed"] == seed),
                    "trials": sum(row["seed"] == seed for row in selected),
                }
                for seed in sorted({row["seed"] for row in selected})
            },
        }
    paired: dict[str, Any] = {}
    for record_id in sorted({row["record_id"] for row in rows}):
        selected = [row for row in rows if row["record_id"] == record_id]
        paired[record_id] = {
            "expected": selected[0]["grade"]["expected_intent"],
            **{
                mode: sorted(
                    {str(row["grade"]["predicted_intent"]) for row in selected if row["mode"] == mode}
                )
                for mode in MODES
            },
        }
    return {"profiles": profiles, "paired_predictions": paired}


def render_report(run: dict[str, Any]) -> str:
    lines = [
        "# Frozen synthetic intake comparison — actual local CPU model",
        "",
        f"Run: {run['started_at']}; {run['unique_requests']} unique requests; seeds {run['seeds']}. Repeated seeds are trials, not independent samples.",
        "",
        "The local-model profile executes pinned Qwen2.5-0.5B-Instruct Q4_K_M through llama.cpp on CPU. Both profiles share the existing unsupported-scope and prompt-injection guard. Guarded requests use deterministic refusal without inference. The interpreter never receives expected labels. No fine-tuning, prompt changes or model selection was performed after the frozen comparison began.",
        "",
        "| Profile | Correct / trials | False actionable | Needless clarification | Wrong actionable | Actual model calls | Input / output tokens | Intake seconds | Provider USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, data in run["summary"]["profiles"].items():
        lines.append(
            f"| {mode} | {data['correct']} / {data['trials']} | {data['false_actionable_interpretations']} | {data['unnecessary_clarifications']} | {data['wrong_actionable_intents']} | {data['model_calls']} | {data['input_tokens']} / {data['output_tokens']} | {data['intake_seconds']:.3f} | 0.00 |"
        )
    lines += [
        "",
        "Provider charges are zero because no paid service is called; local hardware and electricity are unpriced. Token totals come from llama.cpp's runtime counters, including EOS. Latency includes per-request CLI inference startup, but provisioning/hash verification and harness I/O are excluded. Total harness time is separately recorded. Temperature is zero, so distinct seeds may yield identical predictions.",
        "",
        "False actionable means the classifier proposed cancel/address for an annotated ambiguous or unsupported request. It is not an executed write or a false resolved case: the backend still requires trusted identity, fresh evidence and operator approval. Terminal recovery safety is measured in the separate workflow evaluation.",
        "",
        "## Paired predictions",
        "",
        "| Request | Expected | Deterministic | Local model |",
        "|---|---|---|---|",
    ]
    for record_id, row in run["summary"]["paired_predictions"].items():
        lines.append(
            f"| {record_id} | {row['expected']} | {', '.join(row['deterministic'])} | {', '.join(row['local-model'])} |"
        )
    lines += [
        "",
        "## Decision and limitations",
        "",
        run["recommendation"],
        "",
        "The corpus contains original synthetic text with openly visible annotations. Its prompt/config/corpus hashes were fixed before the first full run, and development texts are disjoint, but it is not a concealed external test or a merchant sample. No real recovery rate, human handling time, demand, or financial benefit is inferred. Hosted OpenAI comparison remains unperformed and no paid calls were authorized.",
        "",
        "`traces.jsonl` retains every exact input, label, output, seed, runtime stdout/stderr, usage counter and error. `results.json` retains all grades and source hashes; the copied corpus, manifest and freeze permit reproduction. Errors are retained unchanged.",
        "",
    ]
    return "\n".join(lines)


def run_comparison(output: Path, seeds: list[int]) -> dict[str, Any]:
    freeze, corpus = validate_freeze()
    if not seeds or len(set(seeds)) != len(seeds) or set(seeds) - set(freeze["seeds"]):
        raise ValueError(f"Select distinct frozen seeds from {freeze['seeds']}")
    if os.environ.get("PARCELRESOLVE_ENABLE_LOCAL_MODEL") != "1":
        raise IntakeConfigurationError("Comparison requires explicit PARCELRESOLVE_ENABLE_LOCAL_MODEL=1")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Comparison output is not empty; preserve previous evidence and choose a fresh path")
    # Verify the frozen artifacts before recording a run as started.
    local = LocalModelInterpreter(
        enabled=True,
        directory=Path(os.environ.get("PARCELRESOLVE_LOCAL_MODEL_DIR", str(DEFAULT_DIRECTORY))),
        threads=freeze["model"]["default_threads"],
        seed=seeds[0],
    )
    output.mkdir(parents=True, exist_ok=True)
    for source in (CORPUS_PATH, DEVELOPMENT_PATH, FREEZE_PATH, MANIFEST_PATH):
        shutil.copyfile(source, output / source.name)
    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat()
    sources = {
        name: sha256_file(ROOT / "parcelresolve" / name)
        for name in ("intake.py", "local_model.py", "model_evaluation.py")
    }
    (output / "run-start.json").write_text(
        json.dumps(
            {
                "started_at": started_at,
                "source_sha256": sources,
                "freeze_sha256": sha256_file(FREEZE_PATH),
                "seeds": seeds,
            },
            indent=2,
        )
        + "\n"
    )
    rows: list[dict[str, Any]] = []
    with (output / "traces.jsonl").open("w") as trace:
        for seed in seeds:
            local.seed = seed
            for record in corpus["records"]:
                for mode in MODES:
                    interpretation = None
                    receipt: dict[str, Any] = {}
                    error = None
                    try:
                        if mode == "local-model":
                            interpreted = local.interpret(record["text"])
                            receipt = dict(local.last_receipt)
                        else:
                            interpreted, receipt = interpret_request_with_receipt(
                                record["text"], mode="deterministic"
                            )
                        interpretation = interpreted.model_dump()
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        if mode == "local-model":
                            receipt = dict(local.last_receipt)
                    row = {
                        "record_id": record["id"],
                        "seed": seed,
                        "mode": mode,
                        "text": record["text"],
                        "interpretation": interpretation,
                        "receipt": receipt,
                        "error": error,
                        "grade": grade_interpretation(record, interpretation),
                    }
                    rows.append(row)
                    trace.write(json.dumps(row, sort_keys=True) + "\n")
                    trace.flush()
    run = {
        "schema_version": 1,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "unique_requests": len(corpus["records"]),
        "seeds": seeds,
        "source_sha256": sources,
        "freeze_sha256": sha256_file(FREEZE_PATH),
        "python_version": sys.version.split()[0],
        "machine": {
            "system": platform.system(),
            "architecture": platform.machine(),
            "available_cpu_count": os.cpu_count(),
        },
        "mode": "real pinned local CPU model vs deterministic intake",
        "hosted_model_calls": 0,
        "recommendation": "Keep deterministic intake as the default. This small synthetic comparison does not establish merchant benefit or justify silently enabling a model. Local AI remains an explicit opt-in, with operator clarification and approval required by the same backend policy.",
        "summary": summarize(rows),
        "results": [
            {key: value for key, value in row.items() if key != "receipt"}
            | {
                "receipt": {
                    key: value
                    for key, value in row["receipt"].items()
                    if key not in {"runtime_log", "raw_output"}
                }
            }
            for row in rows
        ],
    }
    (output / "results.json").write_text(json.dumps(run, indent=2) + "\n")
    (output / "report.md").write_text(render_report(run))
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 19, 41])
    args = parser.parse_args()
    try:
        run = run_comparison(args.output, args.seeds)
    except (ValueError, IntakeConfigurationError) as exc:
        parser.error(str(exc))
    print(json.dumps(run["summary"]["profiles"], indent=2))
    print(f"Report: {args.output / 'report.md'}")
    # Classification misses are observations, not harness failures.
    return int(
        any(row["errors"] or row["missing_usage_records"] for row in run["summary"]["profiles"].values())
    )


if __name__ == "__main__":
    raise SystemExit(main())
