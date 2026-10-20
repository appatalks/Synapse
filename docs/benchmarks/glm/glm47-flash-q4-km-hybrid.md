# GLM-4.7-Flash: larger-than-VRAM hybrid screen

**Observed throughput benefit, not broad quality or numerical qualification.**
The 8 GiB causal hybrid bank measured **87.45 tok/s**, versus **64.87 tok/s**
for the fastest fresh Standard block: **+34.8%**. Both tested hybrid budgets
outperformed both Standard blocks.

[Complete numeric evidence](glm47-flash-q4-km-hybrid.json) retains every
sample, answer check, activation log, model/backend hash, resource snapshot
and generated-text hash. This is a new 30B-class target, distinct from
GLM-4.5-Air 106B and the unmeasured GLM-5.3 candidate.

## Why this model

- Publisher: [GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash/tree/7dd20894a642a0aa287e9827cb1a1f7f91386b67),
  described as a 30B-A3B MoE; MIT license.
- Exact [Unsloth Q4_K_M GGUF](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/blob/0d32489ecb9db6d2a4fc93bd27ef01519f95474d/GLM-4.7-Flash-Q4_K_M.gguf):
  **18,312,339,808 bytes (17.06 GiB)**, pinned revision and SHA256 verified.
  This exceeds the reference GPU's **17,094,934,528 bytes (15.92 GiB) total
  VRAM**, not merely its free VRAM.
- Popularity snapshot, October 20, 2026 UTC: selected GGUF repository
  **174,557 downloads / 728 likes**; publisher repository
  **1,125,508 downloads / 1,879 likes**. These repository counters are not
  unique users, selected-quantization downloads, quality scores or lifetime
  totals. The record includes the API URLs and observation date.
- The publisher config calls this `glm4_moe_lite`; the tested GGUF uses
  **`deepseek2`**. Actual GGUF metadata has 47 blocks, 64 experts/top-4,
  hidden width 2048 and expert FFN width 1536. Native activation confirms
  46 routed layers; not every trunk layer is an MoE layer.

## Matched results

Ryzen 9 9950X, RTX 5070 Ti 16GB-class, 123.48 GiB usable RAM. All rows use the
**same patched executable and explicitly selected matching CUDA plugin**,
source pin `620d2225cc436ab0b001e3200e590e3b286ef9ab`. Binary/plugin hashes
are retained. No model/quantization change is made between modes.

Actual context is 16,384 tokens, with 8 generation / 16 prompt threads,
one slot and FP16 attention cache. Each row loads once and generates three
exact 512-token samples. Rows are in measured order:

| Configuration | Three decode samples, tok/s | Decode median | Change vs fastest Standard block |
| --- | --- | ---: | ---: |
| Standard automatic placement, before | 63.48 / 64.41 / 65.27 | 64.41 tok/s | First control |
| Require hybrid, 8,192 MiB causal bank | 77.14 / 87.87 / 87.45 | **87.45 tok/s** | **+34.8%** |
| Require hybrid, 10,240 MiB causal bank | 76.51 / 88.43 / 87.39 | 87.39 tok/s | +34.7% |
| Standard automatic placement, after | 65.63 / 64.59 / 64.87 | 64.87 tok/s | Faster control |

The denominator is the faster block median, 64.87407727618 tok/s, not the
slower initial control. This sequential bracket is not randomized significance
or an exhaustive native CPU-expert/thread/cache search. The nearly identical
8/10 GiB medians do not establish a meaningful cache-size effect.

Causal residency starts empty on each load and persists between repetitions
and answer checks. The first lower sample is retained; no checkpoint-trained
expert plan or warmest-only reporting is used.

Median 512-token request times were 8.20 / 6.18 / 6.15 / 8.13 seconds.
Median time to first streamed text was 270 / 346 / 314 / 260 ms. Faster decode
did not improve first-text latency in this short-prompt screen. The model's
reasoning tokens count toward output length and timing.

## Activation and resources

Both hybrid budgets reached activation-verified Ready with **46/46 routed-layer
coverage**, direct asynchronous admissions, and **16,770,441,216 registered
immutable source bytes**. The pipeline and protected GPU IDs were configured;
guarded overlap and protected-ID markers were observed. **Gate/up fusion was
not observed**, so configuration alone is not reported as active fusion.

Standard used native automatic placement with a 1,024 MiB reserve and no
expert cache. Hybrid disabled fitting/repacking/host-op offload and used an
untrained causal bank with CPU cold-expert execution. It did not reuse the
bound GPT-OSS-120B seed. No speculative/MTP drafting, model conversion or
intentional omission of selected expert contributions was used.

GPU memory snapshots after requests were 14,804 / 11,969 / 13,972 / 14,858 MiB
in table order. These include desktop use and are not peaks or minimum requirements.
Direct registration also pins host memory; separate RAM snapshots are retained.

## Checks and interpretation

All eight narrow checks passed: exact integer `323` and the unchanged
AST-only Python `clamp` predicate in every row. Generated code was parsed,
never executed. This is not broad reasoning, coding or tool-use qualification.

Standard throughput hashes repeat within each block but **differ between the
two Standard loads**. Hybrid hashes vary across repetitions and do not all
match a Standard sample. Identical-output generation is not established; the
screen does not identify the cause, and differing hashes alone do not show an
incorrect answer.

**No independent native-reference logit gate was run.** The gate/up-fusion
observation, activation verification, narrow answers and measured throughput
must not be substituted for numerical or general-quality qualification.

See the [batch protocol and reproduction steps](../model-guide.md#popular-larger-than-vram-moe-batch)
for the exact prompt, timing formula, mode settings and limits. The installation
profile was not edited, and all benchmark-owned processes stopped.
