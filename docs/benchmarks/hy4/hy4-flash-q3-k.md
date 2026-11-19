# Hy4 Flash Q3_K: optional backend and coding benchmarks

**Tested November 18, 2026 on Linux:** Ryzen 9 9950X, RTX 5070 Ti 16 GB,
123.48 GiB usable RAM. The text-only tests used both
[`Hy4-flash-Q3_K` GGUF shards](https://huggingface.co/AngelSlim/Hy4-flash-GGUF)
from AngelSlim (about 144.8 GiB combined), starting with
`Hy4-flash-Q3_K-00001-of-00002.gguf`. The optional backend was llama.cpp
[`0a054d0b0`](https://github.com/ggml-org/llama.cpp/commit/0a054d0b02454c998e068381d15f3f6615bdd987)
from [ggml-org/llama.cpp#32517](https://github.com/ggml-org/llama.cpp/pull/32517),
built separately with `GGML_CUDA=ON` and `CMAKE_CUDA_ARCHITECTURES=120`.
The 8K/16K screen used an isolated Synapse 0.2.5rc1 instance with that
backend; the routing checks used the source build with both backends configured.

## What loaded, and what failed

| Setup | Result |
| --- | --- |
| Installer-pinned llama.cpp b11669 (`620d2225`) | Rejected GGML type 43 on `per_layer_token_embd.weight` in the second shard. No generation ran. |
| Hy4 CUDA build, forced GPU offload (`-ngl 99`) | Disabled automatic fitting and failed when CUDA tried to allocate an 85.3 GiB model buffer on the 16 GB card. No generation ran. |
| Hy4 CUDA build, automatic placement and 2,048 MiB fit reserve | Loaded with CPU/GPU placement and on-demand reads of the 59 GiB Engram table. The first successful standalone 8K load took about 53 s; later warm 8K Synapse loads were about 4.5 s. These were different runs, not a matched startup comparison. |

With the [optional backend configured](../../installing.md#optional-hy4-flash-backend-linuxcuda),
Synapse routes only GGUFs whose `general.architecture` is `hy_v4_flash` to
that executable. It checks CUDA model allocation, lazy Engram reads and
the requested context before marking the model ready, and does not fall
back if verification fails. Non-Hy4 routing tests preserved existing launch
commands for Qwen3-Coder, Qwen3.8 and GPT-OSS fixtures; their GPU throughput
was not rebenchmarked. The installed backend and saved settings were not changed.

## 8K versus 16K coding screen

Each configuration ran the same Python output-prediction task twice: once
as a 106-token prompt, and once with unrelated code added for a 1,092-token
prompt. Each cell represents one request, not a median. All runs used
16 prompt threads, FP16 K/V, automatic placement, a 2,048 MiB fit reserve,
temperature zero, seed 42, prompt caching off and a 256-token generation
cap. All eight requests returned the exact expected answer and stopped
normally. Generated-token rates include reasoning.

| Allocated context | Generation threads | Short wall time | Short decode | 1,092-token wall time | 1,092-token decode | Free VRAM after load |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8,192 | 8 | **18.67 s** | **13.77 tok/s** | **27.92 s** | **13.52 tok/s** | 2,093 MiB |
| 8,192 | 16 | 44.75 s | 6.18 tok/s | 60.52 s | 8.73 tok/s | 2,069 MiB |
| 16,384 | 8 | 21.27 s | 12.33 tok/s | 29.66 s | 12.19 tok/s | 2,501 MiB |
| **16,384** | **16** | 20.01 s | 13.32 tok/s | 28.37 s | 13.16 tok/s | 2,489 MiB |

**Balanced starting point: 16K with 16 generation / 16 prompt threads.**
It roughly matched the fastest observed 8K run while leaving more space
for instructions and history. The 8K / 8-thread setup won on latency for
these two prompts. The runs were not repeated or randomized, so the slow
8K / 16-thread result does not isolate a thread-count penalty.

## Synapse routing checks at 16K

Both checks used the optional Hy4 route with 16 generation / 16 prompt
threads, automatic placement and a 2,048 MiB reserve. Prompt caching was
off; both requests used temperature zero, seed 42 and a 384-token cap.

| Check | Input tokens | Generated tokens | Prompt processing | Decode | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Arithmetic | 35 | 69 | 33.66 tok/s | 13.79 tok/s | Correct `323`; normal stop in 5.97 s |
| Retrieve two constants from code | 1,787 | 72 | 97.38 tok/s | 7.63 tok/s | Correct `1703,2917`; normal stop |

A longer code prompt did not finish within the smoke-test deadline. The
16K allocation is verified; near-capacity throughput and retrieval are not.
Earlier 8K tests hit a 96-token cap during reasoning without producing a
visible answer. A short arithmetic test with `reasoning_effort: "none"`
also generated reasoning and hit its 64-token cap, so do not assume that
setting disables thinking on this build. A larger output cap can help a
reply complete, but it does not guarantee completion.

For Pi, start with `maxTokens: 2048` on the 16K profile rather than carrying
over an output limit from a larger-context model. Consider 4096 only if
real replies truncate and there is room for the prompt and history. This
is a starting recommendation, not a measured Pi optimum. These tests
used API requests, not a Pi tool-using session. They do not qualify vision,
other quantizations or GPUs, Hybrid, or speculative decoding, and the
single-request rates are not comparable to the main benchmark table's
three-request medians.
