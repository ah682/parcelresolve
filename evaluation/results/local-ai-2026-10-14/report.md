# Frozen synthetic intake comparison — actual local CPU model

Run: 2026-10-14T03:49:39.645300+00:00; 36 unique requests; seeds [7, 19, 41]. Repeated seeds are trials, not independent samples.

The local-model profile executes pinned Qwen2.5-0.5B-Instruct Q4_K_M through llama.cpp on CPU. Both profiles share the existing unsupported-scope and prompt-injection guard. Guarded requests use deterministic refusal without inference. The interpreter never receives expected labels. No fine-tuning, prompt changes or model selection was performed after the frozen comparison began.

| Profile | Correct / trials | False actionable | Needless clarification | Wrong actionable | Actual model calls | Input / output tokens | Intake seconds | Provider USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deterministic | 57 / 108 | 9 | 42 | 0 | 0 | 0 / 0 | 0.004 | 0.00 |
| local-model | 51 / 108 | 21 | 9 | 27 | 102 | 12108 / 231 | 77.968 | 0.00 |

Provider charges are zero because no paid service is called; local hardware and electricity are unpriced. Token totals come from llama.cpp's runtime counters, including EOS. Latency includes per-request CLI inference startup, but provisioning/hash verification and harness I/O are excluded. Total harness time is separately recorded. Temperature is zero, so distinct seeds may yield identical predictions.

False actionable means the classifier proposed cancel/address for an annotated ambiguous or unsupported request. It is not an executed write or a false resolved case: the backend still requires trusted identity, fresh evidence and operator approval. Terminal recovery safety is measured in the separate workflow evaluation.

## Paired predictions

| Request | Expected | Deterministic | Local model |
|---|---|---|---|
| intake-eval-address-01 | address | unknown | cancel |
| intake-eval-address-02 | address | address | cancel |
| intake-eval-address-03 | address | address | cancel |
| intake-eval-address-04 | address | unknown | cancel |
| intake-eval-address-05 | address | unknown | unknown |
| intake-eval-address-06 | address | unknown | unknown |
| intake-eval-address-07 | address | unknown | cancel |
| intake-eval-address-08 | address | address | cancel |
| intake-eval-address-09 | address | address | cancel |
| intake-eval-address-10 | address | unknown | cancel |
| intake-eval-address-11 | address | address | cancel |
| intake-eval-address-12 | address | unknown | unknown |
| intake-eval-cancel-01 | cancel | unknown | cancel |
| intake-eval-cancel-02 | cancel | unknown | cancel |
| intake-eval-cancel-03 | cancel | cancel | cancel |
| intake-eval-cancel-04 | cancel | unknown | cancel |
| intake-eval-cancel-05 | cancel | cancel | cancel |
| intake-eval-cancel-06 | cancel | unknown | cancel |
| intake-eval-cancel-07 | cancel | cancel | cancel |
| intake-eval-cancel-08 | cancel | unknown | cancel |
| intake-eval-cancel-09 | cancel | unknown | cancel |
| intake-eval-cancel-10 | cancel | unknown | cancel |
| intake-eval-cancel-11 | cancel | cancel | cancel |
| intake-eval-cancel-12 | cancel | cancel | cancel |
| intake-eval-unknown-01 | unknown | unknown | unknown |
| intake-eval-unknown-02 | unknown | unknown | unknown |
| intake-eval-unknown-03 | unknown | unknown | cancel |
| intake-eval-unknown-04 | unknown | unknown | cancel |
| intake-eval-unknown-05 | unknown | cancel | cancel |
| intake-eval-unknown-06 | unknown | unknown | cancel |
| intake-eval-unknown-07 | unknown | unknown | unknown |
| intake-eval-unknown-08 | unknown | unknown | cancel |
| intake-eval-unknown-09 | unknown | cancel | cancel |
| intake-eval-unknown-10 | unknown | unknown | unknown |
| intake-eval-unknown-11 | unknown | cancel | unknown |
| intake-eval-unknown-12 | unknown | unknown | cancel |

## Decision and limitations

Keep deterministic intake as the default. This small synthetic comparison does not establish merchant benefit or justify silently enabling a model. Local AI remains an explicit opt-in, with operator clarification and approval required by the same backend policy.

The corpus contains original synthetic text with openly visible annotations. Its prompt/config/corpus hashes were fixed before the first full run, and development texts are disjoint, but it is not a concealed external test or a merchant sample. No real recovery rate, human handling time, demand, or financial benefit is inferred. Hosted OpenAI comparison remains unperformed and no paid calls were authorized.

`traces.jsonl` retains every exact input, label, output, seed, runtime stdout/stderr, usage counter and error. `results.json` retains all grades and source hashes; the copied corpus, manifest and freeze permit reproduction. Errors are retained unchanged.
