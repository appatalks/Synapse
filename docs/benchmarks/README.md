# SYNAPSE benchmark results

Quick reference for measured inference performance and links to the supporting
reports. These are results from one real system, not estimates or guarantees
for other hardware.

## Headline results

Three-run medians from 512-token technical screens at a 16K context:

| Model and quantization | Control | SYNAPSE hybrid | Gain |
| --- | ---: | ---: | ---: |
| GPT-OSS-120B MXFP4 | 25.69 tok/s | **39.46 tok/s** | **54%** |
| Qwen3.8-Flash-Next IQ3_S | 25.39 tok/s | **43.88 tok/s** | **73%** |
| GLM-4.5-Air 106B IQ4_XS | 12.67 tok/s | **17.28 tok/s** | **36%** |
| Qwen3.6-35B-A3B Q8_0 | 45.50 tok/s | **77.99 tok/s** | **71%** |

All four screens used a Ryzen 9 9950X, RTX 5070 Ti 16GB, 123.48 GiB usable
RAM, 8 generation threads, and 16 prompt-processing threads. The controls are
not identical across models: GPT-OSS and Qwen3.6 use standard automatic
placement; Qwen3.8 uses native CPU experts with a GPU backbone; GLM uses the
fastest observed non-hybrid control. GLM's hybrid result used a 6 GiB cache;
its 8 GiB allocation attempt did not fit.

Rates are decode throughput, not end-to-end response time. These short,
sequential technical screens are not randomized studies, sustained natural
workload tests, or broad answer-quality certification. Experimental
acceleration is not yet quality-qualified. See the model reports and the
[technical white paper](../whitepaper/synapse-whitepaper.pdf) for methods,
limitations, and qualification details.

## Expanded model matrix

This matched screen adds smaller and mid-sized models to the coverage. It uses
the same Ryzen 9 9950X and RTX 5070 Ti 16GB system, actual 16K context, 8
generation / 16 prompt threads, and three exact 512-token technical samples
per profile. Values are decode medians in tokens per second.

| Model and quantization | Standard mode | Automatic mode | Automatic execution |
| --- | ---: | ---: | --- |
| GPT-OSS-120B MXFP4 | 25.69 | **39.46** | Experimental hybrid, direct DMA |
| Gemma 3 12B Q4_K_M | 80.94 | 80.50 | Standard fallback |
| DeepSeek-R1-0528-Qwen3 8B Q4_K_M | 130.08 | 128.50 | Standard fallback |
| Qwen3.5 Q8_0, `qwen35` architecture | 79.48 | 80.26 | Standard fallback |
| LFM2 1.2B Q8_0 | 485.67 | 486.55 | Standard fallback |

The automatic mode uses the experimental hybrid path only for GPT-OSS in this
matrix. The other architectures correctly use standard execution; their small
timing differences are not hybrid gains. GPT-OSS is the only model in this
five-model screen larger than the GPU's VRAM. The Qwen3.5 model is identified
by its GGUF architecture, not by its local filename.

This is a repeated single-prompt technical screen, not a randomized study or
sustained natural-workload qualification. Small answer checks had mixed
outcomes: the Gemma exact-integer check failed, the DeepSeek arithmetic answer
reached its token limit, and the LFM2 exact-integer and strict AST checks
failed. Passing checks do not establish broad model quality or numerical
equivalence. The full evidence preserves every sample, checks, model metadata,
and execution profile in the
[reviewed matrix report](https://github.com/appatalks/unified-memory-scheduler/blob/main/benchmarks/results/20261016-downloaded-model-matrix.json);
see its [ledger entry](https://github.com/appatalks/unified-memory-scheduler/blob/main/benchmarks/RESULTS.md#october-16-model-aware-defaults-and-downloaded-model-matrix)
for the complete conditions and caveats.

## Additional local measurement

A separate `llama-bench` run adds a locally available small-to-mid-sized model.
It uses synthetic benchmark tokens and reports prompt processing separately
from generation, so these values are **not directly comparable** with the
512-token technical-request medians above.

| Model and quantization | Prompt median | Generation median |
| --- | ---: | ---: |
| Mistral Nemo 12B Instruct Q4_K_M | 4,247.36 tok/s | **89.71 tok/s** |

The run used the same Ryzen 9 9950X and RTX 5070 Ti 16GB, 8 threads, three
repetitions, and a minimum 16K context with a 1 GiB fit margin. Prompt and
generation sample rates, backend identity, and full settings are in the
[measurement record](mistral/mistral-nemo-12b-q4-km.json). Reproduce it with the
matching llama.cpp build:

```bash
llama-bench -m /path/to/Mistral-Nemo-Instruct-2407-Q4_K_M.gguf \
  -p 512 -n 512 -r 3 -t 8 -ngl -1 \
  --fit-target 1024 --fit-ctx 16384 -o json
```

## Detailed reports

### [GPT-OSS](gpt-oss/)

- [GPT-OSS and llama.cpp PR 29887 study](gpt-oss/upstream-pr29887.md) —
  local cache comparisons, loading-mode observations, and retained failures.

### [GLM](glm/)

- [GLM-4.5-Air IQ4_XS](glm/glm45-air-iq4-xs.md) — matched controls, cache fit,
  retained failures, and RAM observations.

### [Mistral](mistral/)

- [Mistral Nemo 12B Q4_K_M measurement](mistral/mistral-nemo-12b-q4-km.json).
- [Mistral Small 4 compatibility and FP32 prototype](mistral/mistral4-compatibility.md) —
  compatibility limits and primitive checks.
- [Mistral Small 4 experimental native integration](mistral/mistral4-native-experimental.md) —
  isolated timings with unresolved native-reference and answer-check failures.

### [Qwen](qwen/)

- [Qwen3.6-35B-A3B Q8_0](qwen/qwen36-q8.md) — matched controls, placement
  details, and numerical and answer-check limits.
- [Full four-model results and conditions](https://github.com/appatalks/unified-memory-scheduler/blob/main/benchmarks/RESULTS.md) —
  includes the GPT-OSS and Qwen3.8 headline evidence.

## Machine-readable reports

The JSON files retain measurements and diagnostics behind the corresponding
studies:

- GPT-OSS: [`upstream-pr29887-gpt120b.json`](gpt-oss/upstream-pr29887-gpt120b.json)
- GLM: [`glm45-air-iq4-xs.json`](glm/glm45-air-iq4-xs.json)
- Mistral:
  [`mistral-nemo-12b-q4-km.json`](mistral/mistral-nemo-12b-q4-km.json),
  [`mistral4-fp32-compatibility.json`](mistral/mistral4-fp32-compatibility.json),
  [`mistral4-fused-fp32.json`](mistral/mistral4-fused-fp32.json), and
  [`mistral4-native-experimental.json`](mistral/mistral4-native-experimental.json)
- Qwen: [`qwen36-q8.json`](qwen/qwen36-q8.json)

The reports include unsuccessful checks and failed configurations where
applicable; a measured throughput result alone should not be read as evidence
of equivalent answer quality.
