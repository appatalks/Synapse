# Investigating llama.cpp PR 29887

## Already Included, Not An Additional Speed Multiplier

[ggml-org/llama.cpp#29887](https://github.com/ggml-org/llama.cpp/pull/29887)
merged on October 7, 2026. Its merge commit is an ancestor of SYNAPSE's pinned
`620d2225cc436ab0b001e3200e590e3b286ef9ab` backend. The pin also includes
[ggml-org/llama.cpp#30112](https://github.com/ggml-org/llama.cpp/pull/30112),
the multi-GPU cache follow-up; SYNAPSE's custom hybrid path remains single-GPU.

The upstream cache keeps host experts in GPU banks and uploads selected cache
misses for GPU execution, using LRU eviction. SYNAPSE extends that tensor/slot
machinery with CPU cold-expert execution and guarded causal admissions, avoiding
an upload for every miss. Neither policy intentionally skips selected experts.

The PR's 67.8 tok/s headline uses Qwen3.8-Flash-Next Q4_0, an RTX 5090 32GB and
a 19,000 MiB cache. It is not a result for our 16GB card, target quantization or
context, and cannot be multiplied onto SYNAPSE's existing rates.

## Local GPT-OSS-120B Screen

[Reviewed numeric evidence](upstream-pr29887-gpt120b.json) retains every window,
sample, small answer check and failed configuration.

| Configuration | Cache | Decode median tok/s |
| --- | ---: | ---: |
| Stock automatic fitting, mapped weights | None | 24.42 |
| Automatic fitting plus upstream LRU, mapped weights | 6 GiB | 14.26 |
| CPU experts plus upstream LRU, mapped weights | 10 GiB | 17.31 |
| CPU experts plus upstream LRU, copied CUDA-host buffers | 10 GiB | **29.36** |
| Existing SYNAPSE trained hybrid profile | 12,000 MiB | **47.89 / 48.66 / 48.92** |

Conditions: Ryzen 9 9950X, RTX 5070 Ti 16GB, 123.48 GiB usable RAM;
unchanged GPT-OSS-120B MXFP4; actual 16,384-token context; 8 generation / 16
prompt threads; three exact 512-token samples per block; temperature zero,
seed 42, low reasoning effort, prompt caching off and EOS ignored.
No MTP or speculative proposals are counted.

Rates use 511 token intervals divided by request wall time minus reported
prompt-processing time. Download/model loading is excluded; remaining transport
and scheduling overhead is included. The public research execution-sweep helper
defines the prompt and measurement method.

These are sequential technical screens, not a randomized study or an exhaustive
cache-size/thread/model search. The three SYNAPSE windows are all retained; the
lowest block median is 47.89 tok/s. They do not replace the older matched README
comparison or establish a sustained cross-workload 60 tok/s result.

## The Useful RAM Finding

At the same 10 GiB cache size, copying improves upstream LRU throughput from
17.31 to 29.36 tok/s, **69.6%**. Corresponding generated-text hashes match across
all three samples. Small-batch LRU counters also match exactly: 153,617 hits,
76,465 misses, 66.77% hit rate and 963,979.84 MiB uploaded. Those aggregate
counters include quality requests and small-batch setup, not decode alone.

Native loader logs identify `CPU_Mapped` buffers for mapped loading and
`CUDA_Host` buffers for copied loading. Both modes already have roughly
58-59 GiB backend RSS. Copy mode reports 57.5 GiB shared/driver-mapped residency,
not private anonymous RAM. OS-unavailable memory rises from about 8.9 to
66.8 GiB, while warm samples in both modes read zero new bytes from disk.

This points to the loading/buffer and upload path, rather than more resident
model bytes or better cache reuse. Pinned host buffers can help GPU uploads;
simply allocating more RAM is not the optimization. The earlier GLM CPU-expert
control's negligible copy-mode gain remains valid: it tested a different path.
SYNAPSE already uses immutable registered sources for direct-DMA admissions.

The 29.36 tok/s upstream configuration is about 20% above the stock control,
but it changes placement, caching and loading together. That is not an isolated
cache-only gain, and it remains slower than the tested SYNAPSE profile.

## Retained Failures And Quality Limits

- The 12,000 MiB upstream cache with copied loading failed to allocate a
  652,376,192-byte prefill compute buffer. No smaller context or silent fallback
  was substituted.
- An initial 6 GiB fit/cache block measured 14.70 tok/s, but default verbosity
  hid native cache statistics. Its original failed activation-check status is
  retained. An independent verbosity-4 repeat confirmed allocation, slots and
  LRU activity, measuring 14.26 tok/s.
- Exact-integer and AST-only checks pass for completed tested modes. Generated
  Python is parsed, never executed. These are not broad quality certification or
  CPU-reference logit-equivalence gates; earlier failed diagnostics remain.

No native optimization, automatic budget or application default was changed.
The original GPT profile was restored and verified after every screen.

## Reproducing The Upstream Loading Comparison

Use the pinned backend and matching GPU libraries, one server at a time.
Replace the model placeholder with the unchanged two-shard target's first file.
For the copied-loading case:

```bash
GGML_OP_OFFLOAD_MIN_BATCH=32 llama-server \
  --model /models/gpt-oss-120b-MXFP4-00001-of-00002.gguf \
  --host 127.0.0.1 --ctx-size 16384 --parallel 1 \
  --threads 8 --threads-batch 16 --poll 50 --verbosity 4 \
  --n-gpu-layers all --cpu-moe --fit off \
  --moe-cache-mib 10240 --load-mode none
```

Change only `--load-mode none` to `--load-mode auto` for the mapped control.
For combined automatic fitting/cache, use `--n-gpu-layers auto --fit on
--fit-target 1024 --moe-cache-mib 6144 --load-mode auto`, without `--cpu-moe`.
Confirm actual context and native cache allocation rather than assuming fit.
The app's Standard cache option requests CPU experts, not this combined
whole-layer fit/cache mode; the commands above are native benchmark settings.
