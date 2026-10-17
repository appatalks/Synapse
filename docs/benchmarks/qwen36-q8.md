# Qwen3.6-35B-A3B Q8_0

## Matched Technical Screen

| Configuration | Three-sample decode median |
| --- | ---: |
| Stock automatic placement | 45.50 tok/s |
| Native CPU experts / GPU backbone | 34.07 tok/s |
| SYNAPSE causal hybrid, 8 GiB cache | **77.99 tok/s** |

The gain is **71.4% against the faster non-hybrid control**, not the slower
CPU-expert control. The [reviewed numeric report](qwen36-q8.json) contains every
sample, small answer check, resource snapshot and numerical-gate summary.

Hardware: Ryzen 9 9950X, RTX 5070 Ti 16GB, 123.48 GiB usable RAM. All profiles
use the same pinned backend and unchanged GGUF, actual 16,384-token context,
8 generation / 16 prompt threads, one server slot, and three exact 512-token
technical samples. Temperature is zero, seed 42, reasoning effort low, prompt
caching off, and EOS ignored. No speculation, draft proposals or MTP are used.

Weights were staged on the mounted WD_BLACK SN850XE NVMe with exFAT, not the
RAM disk. Warm second/third samples in every profile read zero new disk bytes.
This is not a direct measurement of physical memory bandwidth.

Decode rate is 511 token intervals divided by request wall time minus reported
prompt-processing time. Loading/downloads are excluded; transport and remaining
scheduling overhead are included. Request, prompt, first-token and load times
are retained separately.

## Target And Placement

- Repository: [unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF).
- Revision: `a483e9e6cbd595906af30beda3187c2663a1118c`, Apache-2.0.
- One Q8_0 GGUF, 36,903,140,320 bytes, verified against the pinned LFS SHA256.
- Native architecture: `qwen35moe`; 40 routed layers, 256 experts/top-8.
- Routed weight tensors: 34,225,520,640 bytes, all Q8_0.
- Logical selected routed weights: 1,069,547,520 bytes/token, not measured DRAM traffic.

Stock uses automatic fitting with a 1,024 MiB reserve. The native CPU-expert
control keeps the backbone on GPU and disables host-op offload. Hybrid uses
the same backbone/CPU-cold-expert arrangement, disables repacking and host
buffers, and adds an 8,192 MiB resident bank, direct registered-source DMA,
guarded overlap, gate/up fusion and event-protected GPU IDs.

The hybrid throughput cache starts empty and learns causally: **no trained
checkpoint-specific plan**. Residency persists across repetitions. Its three
rates are **73.47, 77.99 and 80.24 tok/s**; the progression is retained rather
than reporting only the warmest run.

Measured dispatch totals retain all top-8 contributions: 148,713 CPU plus
608,143 GPU contributions equal 94,607 dispatches times eight. No selected
expert, router probability or target weight was intentionally removed.

## Verification And Limits

All six small checks pass: exact integer and exact AST-only Python checks for
each of stock, native CPU-expert and hybrid profiles. Generated code is parsed,
never executed. These checks are not a general model-quality evaluation.

Separate frozen-placement numerical checks use a descriptor-only seed of the
first eight expert IDs per layer, not observations from the evaluation prompts.
The base self-check and optimized-versus-base hybrid check each pass 96 sampled
full-vocabulary positions with **maximum absolute and relative-L2 error zero**.
Both CPU and GPU experts are exercised; no active tensor capture is enabled.

Those numerical gates establish same-placement pipeline agreement, not
CPU-only/all-native equivalence or equivalence of every adaptive throughput
placement. Earlier failed model diagnostics remain unresolved.

This is one forced-length technical prompt in sequential three-sample blocks,
not randomized significance or sustained natural coding/reasoning/prose
qualification. Exceeding 60 tok/s on this smaller target does **not** meet the
separate GPT-OSS-120B cross-workload milestone.

## Reproducing In SYNAPSE

With a compatible experimental Linux/NVIDIA installation, open **Chat → Model
Controls**, choose this unchanged GGUF, select **Require hybrid expert dispatch**,
and set the unbound causal cache to **8192 MiB**, with 8 generation / 16 prompt
threads. The measured installation uses 16K context. Confirm actual context,
full routed-layer coverage and direct-DMA activation before comparing rates.
Fit and speed are not guaranteed on other hardware or contexts.

The benchmark restored the original GPT model settings afterward. No native
backend default was changed.
