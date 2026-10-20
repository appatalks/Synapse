# GLM-4.5-Air: a third trained large MoE

The [reviewed numeric evidence](glm45-air-iq4-xs.json) contains every measured
screen, the failed allocation, original answer checks, and separate diagnostics.
This is not broad answer-quality or production qualification.

## Target and protocol

- [GLM-4.5-Air](https://huggingface.co/zai-org/GLM-4.5-Air), 106B total / 12B active.
- [Unsloth IQ4_XS GGUF](https://huggingface.co/unsloth/GLM-4.5-Air-GGUF/tree/506d64aa8c5cfe9dbbf00bc7a15739438f83204d/IQ4_XS):
  two shards, 60,480,900,352 bytes, both verified against pinned LFS SHA256.
- Actual layout: `glm4moe`, 46 trunk layers plus one unused NextN block,
  45 routed layers, 128 experts/top8, hidden4096, expert FFN1408.
  Routed tensors mix IQ4_XS and IQ4_NL; no target conversion or expert pruning.
- Ryzen 9 9950X, RTX 5070 Ti 16GB, 123.48 GiB usable RAM.
- Same 16,384-token context and 8 generation / 16 prompt threads.
- Three exact 512-token technical samples per configuration, T0/seed42,
  no prompt caching, forced output length, all reasoning tokens counted.
- Non-speculative target generation. The wall decode rate is 511 token intervals
  divided by request wall time minus backend-reported prompt processing time.
  Transport and remaining scheduling costs are not subtracted. Download and
  loading are excluded; request, prompt, load and first-token times are separate.

| Configuration | Cache | Median decode tok/s |
| --- | ---: | ---: |
| Standard automatic placement, initial window | 0 | 12.67 |
| Native CPU experts / GPU backbone, mapped weights | 0 | 11.30 |
| SYNAPSE causal direct-DMA, measured before reversed control | 6,144 MiB | **17.28** |
| Standard automatic placement, reversed-order window | 0 | 12.14 |
| Native CPU experts / GPU backbone, copy-to-RAM control | 0 | 11.43 |

The README conservatively uses the **fastest control block median**, 12.67,
not the slower native control or reversed window. That yields **36.4%**.
This is a sequential/reverse-order screen, not randomized statistical significance.
An initial 8,192 MiB bank failed to allocate; the failure is retained. Context
was not lowered to make the candidate fit.

## Run the measured profile in the app

With the optional experimental Linux/NVIDIA backend installed:

1. Open Chat → Model Controls, unload the current model, and select the first shard.
2. Choose **Require hybrid expert dispatch**.
3. In Advanced performance, set **GPU MoE expert cache to 6144 MiB**.
   Keep 16K context and 8/16 threads, then load.

Manual budgets are allowed only for causal/unbound layouts. They do not alter
Automatic defaults or the separate GPT training plan/budget. The generic
Automatic 8 GiB configuration is not a fit guarantee for this GLM at 16K.

For a public model-matrix replay, make a local copy of the installation profile,
set its `generic_cache_mib` to 6144, and launch with `--hybrid-profile` pointing
to that copy. The research repository's `vrambridge-model-matrix.py` then runs
its usual matched Standard/Automatic protocol. The complete private screen
also included native mapped/copied controls; their flags and conditions are
retained in the reviewed JSON. Never publish local profiles or raw references.

## Checks and limits

The optimized decode pipeline matched its non-overlapped **same-placement**
frozen-hybrid reference at **96 full-vocabulary positions, zero error**.
Both CPU and GPU expert contributions were exercised using an untrained
metadata-derived seed, not held-out routing observations. This does not prove
equivalence to CPU-only/all-native placement.

Original default-thinking checks included a 1024-token arithmetic truncation
without a final answer and Markdown-fenced code failing the strict AST format
rule. They remain failures in the report. Separate diagnostics with thinking
disabled passed the **unchanged exact integer and AST checks in both modes**.
Stripping Markdown was diagnostic only; no model-generated code was executed.
The throughput screen itself retained default thinking. Quality is not qualified.

## What the RAM test found

Mapped native and hybrid execution already had roughly 54 GiB of backend RSS.
Warm decode samples read **zero additional bytes from disk**. Copying weights
instead of mapping them measured 11.43 versus 11.30 tok/s for the native control,
about 1.2%—not a useful established win over either stock or hybrid execution.
Its OS-unavailable RAM estimate rose from about 10 GiB to 59 GiB. This is changed
allocation/accounting, not evidence that occupying more RAM makes inference faster.

The monitor previously showed `MemTotal - MemAvailable`, which excludes much
cached model data. Linux RAM occupancy now includes cached pages, with free,
OS-available, file-cache, shared and overlapping backend-resident values shown
separately. Cache/RSS must not be added together. OS availability can be optimistic
for driver-pinned pages; the allocation guard was not relaxed.

The model selects about 3.37 GB of logical routed weight data per token. Native
throughput corresponds to about 38.1 GB/s of that logical read budget. This is
**not a measured DRAM-bandwidth counter**, but supports investigating bandwidth,
kernel efficiency and GPU residency rather than simply filling unused capacity.
The experiment does not establish the hardware's maximum possible speed.

GLM-5.3-Flash was considered: its 320B/18B architecture is recognized by the
pinned backend, but the checked IQ2_XXS GGUF was 94.85 GiB, exceeding available
disk space. No GLM-5.3 performance claim is made.
