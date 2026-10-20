# Qwen3-Coder-30B-A3B: larger-than-VRAM hybrid screen

**Observed throughput benefit, not broad quality or numerical qualification.**
The 8 GiB causal hybrid bank measured **110.06 tok/s**, versus **70.08 tok/s**
for the fastest fresh Standard block: **+57.1%**. Both tested hybrid budgets
outperformed both Standard blocks.

[Complete numeric evidence](qwen3-coder30b-q4-km-hybrid.json) retains every
sample, exact answer checks, activation logs, model/backend hashes, resource
snapshots and output hashes. These results do not replace the historical
four-model headline table or older Q3_K_L short-generation measurements.

## Why this model

- Publisher: [Qwen3-Coder-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct/tree/b2cff646eb4bb1d68355c01b18ae02e7cf42d120),
  30.5B total / 3.3B active parameters, 128 experts/top-8, Apache-2.0.
- Exact [Unsloth Q4_K_M GGUF](https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/blob/b17cb02dd882d5b6ab62fc777ad2995f19668350/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf):
  **18,556,689,568 bytes (17.28 GiB)**, pinned revision and SHA256 verified.
  This exceeds the reference GPU's **17,094,934,528 bytes (15.92 GiB) total
  VRAM**, not merely its free VRAM.
- Popularity snapshot, October 20, 2026 UTC: selected GGUF repository
  **1,478,416 downloads / 1,157 likes**; publisher repository
  **515,009 downloads / 1,295 likes**. These are repository-level counters,
  not unique users, selected-file downloads, quality scores or lifetime totals.
  The record includes the API source URLs and observation date.
- Actual GGUF architecture is `qwen3moe`; 48 blocks, 128 experts, top-8,
  hidden width 2048 and expert FFN width 768. The publisher identifies this
  checkpoint as non-thinking; requesting low reasoning effort does not turn
  it into a thinking model.

## Matched results

Ryzen 9 9950X, RTX 5070 Ti 16GB-class, 123.48 GiB usable RAM. All rows use the
**same patched executable and explicitly selected matching CUDA plugin**,
source pin `620d2225cc436ab0b001e3200e590e3b286ef9ab`. Binary/plugin hashes
are retained. The model and quantization are unchanged.

Actual context is 16,384 tokens, with 8 generation / 16 prompt threads,
one slot and FP16 attention cache. Each row loads once, then generates three
exact 512-token samples. Rows are in measured order:

| Configuration | Three decode samples, tok/s | Decode median | Change vs fastest Standard block |
| --- | --- | ---: | ---: |
| Standard automatic placement, before | 70.08 / 70.38 / 69.89 | 70.08 tok/s | Control |
| Require hybrid, 8,192 MiB causal bank | 101.55 / 110.06 / 110.36 | **110.06 tok/s** | **+57.1%** |
| Require hybrid, 10,240 MiB causal bank | 98.09 / 108.08 / 108.60 | 108.08 tok/s | +54.2% |
| Standard automatic placement, after | 66.82 / 63.95 / 61.24 | 63.95 tok/s | Second control |

The denominator is the faster block median, 70.0785173531843 tok/s, not the
slower after-control. Standard declined about 8.8% between blocks; this
variation is retained rather than claiming randomized statistical significance.
Only two hybrid budgets and native automatic placement were screened, not
every possible native CPU-expert/thread/cache policy.

Eight GiB was the faster observed budget, **not an established optimum**.
Residency starts empty on each hybrid load and persists across its three
samples and later answer checks; the initial lower rate is included.
There is no checkpoint-trained expert seed.

Median 512-token request times were 7.55 / 4.91 / 5.00 / 8.25 seconds.
Median time to first streamed text was 258 / 291 / 287 / 270 ms. Faster decode
did not improve first-text latency in this short-prompt screen.

## Activation and resources

Both hybrid budgets reached activation-verified Ready with **48/48 routed-layer
coverage**, direct asynchronous admissions, and **17,553,555,456 registered
immutable source bytes**. The decode pipeline and protected GPU IDs were
configured; guarded overlap, gate/up fusion and protected-ID markers were
observed during the requests.

Standard used native automatic placement, a 1,024 MiB reserve and no expert
cache. Hybrid disabled fitting/repacking/host-op offload, used causal admissions
and CPU cold-expert execution, and did not reuse the bound GPT-OSS-120B plan.
No speculative drafting, model conversion or intentional removal of selected
expert contributions was used.

GPU memory snapshots after all requests were 15,027 / 12,062 / 14,304 / 14,859
MiB in table order, including desktop use. These are not peaks or minimum fit
requirements. Host registration adds pinned-memory pressure; RAM snapshots are
retained separately and must not be added indiscriminately to GPU or file-cache
accounting.

## Checks and interpretation

All eight narrow checks passed: exact integer `323` and the unchanged AST-only
Python `clamp` predicate for each row. Generated code was parsed, never executed.
This is not a representative coding, tool-use or general-answer evaluation.

Each Standard block repeats its own throughput text hash, but the hashes
**differ between the two Standard loads**. Hybrid hashes vary across repetitions
and do not all match a Standard sample. Identical-output generation is not
established. The records do not attribute these differences to a specific
placement, arithmetic or scheduling effect, and differing hashes alone do not
establish an incorrect answer.

**No independent native-reference logit gate was run.** Activation, routing
coverage and narrow answers are distinct from numerical equivalence or broad
quality qualification.

See the [batch protocol and reproduction steps](../model-guide.md#popular-larger-than-vram-moe-batch)
for the prompt, timing formula, mode settings and sampling limits. The
installation profile was not edited, and all benchmark-owned processes stopped.
