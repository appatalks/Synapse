# SYNAPSE benchmark results

One table per hardware setup. Model links open the measurements and limitations.
[Model-choice guide](model-guide.md) · [Contribute results by PR](CONTRIBUTING.md) · [Report template](TEMPLATE.md)

## Ryzen 9 9950X + RTX 5070 Ti 16GB

**Linux/NVIDIA · 123.48 GiB usable RAM · 16K context · 8 generation / 16 prompt threads.**
Unless marked otherwise, rates are decode **tok/s medians of three 512-token requests**.
One row per model/quantization: best observed native and hybrid configurations,
not single-run peaks. Changes use matched controls from the selected study;
failed isolated prototypes are not promoted. Other settings remain in the reports.
`—` means not measured/applicable; **Rejected** means no hybrid generation ran.

| Model / quantization | Control tok/s | Hybrid tok/s | Hybrid cache MiB | Change | Conditions / checks |
| --- | ---: | ---: | ---: | ---: | --- |
| [DeepSeek-R1-0528-Qwen3 8B Q4_K_M](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf3c763dc77cb74ff2a4ceebd868f6f89ac/benchmarks/results/20261016-downloaded-model-matrix.json) | 130.08 | — | — | — | Best: Standard; arithmetic truncated; AST passes |
| [Gemma 3 12B Q4_K_M](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf3c763dc77cb74ff2a4ceebd868f6f89ac/benchmarks/results/20261016-downloaded-model-matrix.json) | 80.94 | — | — | — | Best: Standard; integer fails; AST passes |
| [GLM-4.5-Air 106B IQ4_XS](glm/glm45-air-iq4-xs.md) | 12.67 | 17.28 | 6144 | +36.4% | Fastest observed non-hybrid control; 8 GiB allocation failed; original answer failures retained |
| [GLM-4.7-Flash Q4_K_M](glm/glm47-flash-q4-km-hybrid.md) | 64.87 | **87.45** | 8192 | +34.8% | Same build/plugin; 46/46 routed layers; narrow checks pass |
| [GPT-OSS-20B MXFP4](gpt-oss/gpt-oss20b-hybrid-screen.md) | **207.08** | 143.99 | 10240 | **-30.5%** | Best: Standard; different installed builds; same-build native control 207.00 also faster; narrow checks pass |
| [GPT-OSS-120B MXFP4](gpt-oss/upstream-pr29887.md) | 29.36 | **48.92** | 12000 | +66.6% | Control: upstream LRU 10 GiB/copied loading; best of three hybrid blocks; reference/quality limits remain |
| [LFM2 1.2B Q8_0](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf3c763dc77cb74ff2a4ceebd868f6f89ac/benchmarks/results/20261016-downloaded-model-matrix.json) | 486.55 | — | — | — | Best: Automatic, **native**, not hybrid; integer / AST fail |
| [LFM2.5 1.2B Instruct Q4_K_M](lfm/lfm25-12b-q4-km.json) | 660.30 | **Rejected** | — | — | No routed-MoE descriptor; integer / AST fail |
| [Mistral Nemo 12B Instruct Q4_K_M](mistral/mistral-nemo-12b-q4-km.json) | 89.71 | — | — | — | **Synthetic llama-bench**, 8 threads, minimum fit context 16K; prompt: 4247.36 tok/s; not comparable to request rates |
| [Mistral Small 4 UD-IQ4_XS](mistral/mistral4-compatibility.md) | 19.89 | **Rejected** | 8192 | — | Best installed path: CPU experts; unsupported FP32 hybrid operation; AST fails; isolated prototype fails native equivalence |
| [Qwen3 4B Q4_K_M](qwen/qwen3-4b-q4-km.json) | 190.56 | **Rejected** | — | — | Dense; integer / AST pass |
| [Qwen3.5 local Q8_0, qwen35 architecture](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf3c763dc77cb74ff2a4ceebd868f6f89ac/benchmarks/results/20261016-downloaded-model-matrix.json) | 80.26 | — | — | — | Best: Automatic, **native**; local checkpoint identity not publisher-verified |
| [Qwen3.6-35B-A3B Q8_0](qwen/qwen36-q8.md) | 45.50 | 77.99 | 8192 | +71.4% | Standard automatic-placement control; narrow / same-placement checks pass |
| [Qwen3.8-27B UD-Q4_K_M](qwen/qwen38-27b-ud-q4-km.json) | 11.02 | **Rejected** | — | — | Dense, not Flash-Next; integer / AST pass |
| [Qwen3.8-Flash-Next IQ3_S](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf3c763dc77cb74ff2a4ceebd868f6f89ac/benchmarks/results/moe-cold-work-and-qwen38-summary.json) | 25.39 | 43.88 | 8192 | +72.8% | Native CPU experts / GPU backbone control; causal bank |
| [Qwen3-Coder-30B-A3B Q4_K_M](qwen/qwen3-coder30b-q4-km-hybrid.md) | 70.08 | **110.06** | 8192 | +57.1% | Same build/plugin; 48/48 routed layers; narrow checks pass |

**Experimental hybrid is not quality-qualified.** Narrow answer checks do not
prove native equivalence. Failed checks, differing output hashes, all samples
and control definitions remain in the linked evidence. Rates are not quality
rankings or fit guarantees; native Automatic selection is not hybrid execution.

## Community results welcome

Help expand model and hardware coverage: copy the [report template](TEMPLATE.md),
add sanitized measurements under the model-family folder, and submit a PR.
Add rows to an existing setup or a new setup heading/table for different hardware.
[Contribution instructions](CONTRIBUTING.md) explain the protocol and evidence needed.
