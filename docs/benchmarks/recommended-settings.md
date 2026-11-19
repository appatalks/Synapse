# Recommended settings by model

**Reference system:** Linux, Ryzen 9 9950X, RTX 5070 Ti 16 GB, and
123.48 GiB usable RAM. Match the exact GGUF checkpoint and quantization before
using a row. These are starting points from tests on this system, not default
settings shipped by Synapse.

Most request benchmarks used **16,384 tokens of allocated context**, **FP16
K/V**, **8 generation / 16 prompt threads**, and no drafting. A Standard row
means native CPU/GPU placement with no explicit expert cache unless noted.
For Hybrid rows, the cache is the GPU expert bank, not the attention KV cache
or total VRAM use. See the linked reports for the backend build, placement,
and any exceptions.

## Qwen3.8-Flash-Next SC117 abliterated IQ3_S

Use **96K** unless you need the extra capacity at 128K. The 96K profile was
also loaded and verified in Synapse 0.2.5rc1 on the reference system.

| Allocated context | Engine | Expert cache | Measured decode | Standard at the same context |
| ---: | --- | ---: | ---: | ---: |
| **98,304 (96K)** | **Classic Hybrid** | **6,144 MiB** | **40.44–45.13 tok/s** | 29.35–29.39 tok/s |
| 131,072 (128K) | Classic Hybrid | 4,096 MiB | 33.77–36.86 tok/s | 26.29–27.12 tok/s |

These are ranges across three workload medians (prose, reasoning, and
coding), not variation across single runs. Both used FP16 K/V, 8/16 threads,
automatic placement, and no drafting. An 8 GiB bank failed to allocate at
both contexts; the 6 GiB bank fit at 96K but failed at 128K. The 128K result
is a benchmark profile, not a setting to force into an installed 96K profile.
See the [matched SC117 benchmark][sc117] for the full protocol and longer-input
screen. This is the **SC117 abliterated** GGUF, not the Flash-Next GSQ-RCO
checkpoint used in the separate 16K study below.

## Other measured models

**Compared** means the recommendation comes from testing alternatives.
**Baseline** means the listed setup worked, but the best settings have not
been established. **Experimental** means the result has material fit,
quality, or backend caveats; prefer the linked setup and limits to copying
the numbers into a different profile.

| Exact model / quantization | Starting engine and settings | Decode (tok/s) | Evidence and limits |
| --- | --- | ---: | --- |
| DeepSeek-R1-0528-Qwen3 8B Q4_K_M | Standard, 16K | 130.08 | **Baseline.** Arithmetic truncated; AST check passed. [Report][matrix] |
| Gemma 3 12B Q4_K_M | Standard, 16K | 80.94 | **Baseline.** Integer check failed; AST check passed. [Report][matrix] |
| GLM-4.5-Air 106B IQ4_XS | Hybrid direct, 16K, 6,144 MiB | 17.28 vs. 12.67 | **Experimental.** 8 GiB failed to allocate; original answer failures retained. [Report](glm/glm45-air-iq4-xs.md) |
| GLM-4.7-Flash Q4_K_M | Hybrid direct, 16K, 8,192 MiB | 87.45 vs. 64.87 | **Compared.** Same build and full routed-layer coverage. [Report](glm/glm47-flash-q4-km-hybrid.md) |
| GPT-OSS-20B MXFP4 | Standard, 16K | 207.08 vs. 143.99 Hybrid | **Compared.** Standard also won on the same patched build. [Report](gpt-oss/gpt-oss20b-hybrid-screen.md) |
| GPT-OSS-120B MXFP4 | Trained Hybrid profile, 16K, 12,000 MiB | 47.89–48.92 | **Experimental.** Range of three Hybrid block medians; the model-bound plan and quality limits matter. [Report](gpt-oss/upstream-pr29887.md) |
| LFM2 1.2B Q8_0 | Automatic (native), 16K | 486.55 | **Baseline.** Integer and AST checks failed. [Report][matrix] |
| LFM2.5-1.2B-Instruct Q4_K_M | Standard, 16K | 660.30 | **Baseline.** No routed-MoE descriptor; integer and AST checks failed. [Report](lfm/lfm25-12b-q4-km.json) |
| Mistral Nemo 12B Instruct Q4_K_M | Native; 16K was the minimum fit tested, 8 threads | 89.71 | **Baseline.** Synthetic `llama-bench`, not a Synapse chat rate. [Report](mistral/mistral-nemo-12b-q4-km.json) |
| Mistral Small 4 UD-IQ4_XS | Standard with CPU experts, 16K | 19.89 | **Baseline.** Installed Hybrid rejected; AST check failed. [Report](mistral/mistral4-compatibility.md) |
| Qwen3 4B Q4_K_M | Standard, 16K | 190.56 | **Baseline.** Dense model; integer and AST checks passed. [Report](qwen/qwen3-4b-q4-km.json) |
| Qwen3.5 local Q8_0 (`qwen35` architecture) | Automatic (native), 16K | 80.26 | **Baseline.** Exact publisher checkpoint identity unverified; don't generalize to other Qwen3.5 GGUFs. [Report][matrix] |
| Qwen3.6-35B-A3B Q8_0 | Hybrid direct, 16K, 8,192 MiB | 77.99 vs. 45.50 | **Compared.** Warm-up affected speed; narrow checks passed. [Report](qwen/qwen36-q8.md) |
| Qwen3.8-27B UD-Q4_K_M | Standard, 16K | 11.02 | **Baseline.** Dense model, not Flash-Next; integer and AST checks passed. [Report](qwen/qwen38-27b-ud-q4-km.json) |
| Qwen3.8-Flash-Next GSQ-RCO IQ3_S (16K study) | Hybrid direct, 16K, 8,192 MiB | 43.88 vs. 25.39 | **Experimental.** Control uses CPU experts and a GPU backbone; do not copy this bank size to the SC117 96K profile. [Report][flash-next] |
| Qwen3-Coder-30B-A3B Q4_K_M | Hybrid direct, 16K, 8,192 MiB | 110.06 vs. 70.08 | **Compared.** Same build, full routed-layer coverage; 10 GiB measured slower. [Report](qwen/qwen3-coder30b-q4-km-hybrid.md) |

## Applying and updating these settings

1. **Start with Automatic.** Use **Pre-check** on the exact GGUF to see what
   the installed profile supports. It does not measure fit, speed, or quality.
   A different profile or backend build can yield different settings.
2. **Use Auto Tune when you want a remembered choice for your installation.**
   It may unload the current model. Check the context it will target first:
   a shared context default can differ from the context in this guide.
3. **Use Require Hybrid only for a controlled comparison or troubleshooting.**
   Verify the *active* engine, context, and expert cache after loading. If the
   form shows values different from the model's pre-check, don't assume they
   will be corrected on load. In 0.2.5rc1 the form can submit a general cache
   size and use the shared default context instead of the model's Hybrid
   profile; a rejected load leaves the prior saved settings in place.
4. **Compare like with like.** Keep the GGUF, prompt, occupied context,
   output budget, and reasoning setting fixed. Record first-token latency
   separately for fresh and cached prompts, and use backend decode tok/s for
   generation speed. Short-prompt results at large *allocated* contexts do
   not predict near-full-context speed. Speed and narrow answer checks are
   not quality qualification.

Models and quantizations not listed here have **no recommendation yet**.
To add or replace a row, link a reference-system report with the exact GGUF,
backend/profile revision, allocated context, cache and thread settings, and
measured results. Mark a single tested setup as a baseline, and preserve
failed fit and answer checks in the evidence. Keep other hardware in the
[community benchmark tables](README.md#community-results-welcome).

[sc117]: https://github.com/appatalks/unified-memory-scheduler/blob/0653115dcf8a935e087812dd4142868bbdcdbd84/docs/research/sc117-core-decode.md
[matrix]: https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf3c763dc77cb74ff2a4ceebd868f6f89ac/benchmarks/results/20261016-downloaded-model-matrix.json
[flash-next]: https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf3c763dc77cb74ff2a4ceebd868f6f89ac/benchmarks/results/moe-cold-work-and-qwen38-summary.json
