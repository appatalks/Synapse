# Choosing a local model

This guide combines public model discovery with SYNAPSE text-generation
measurements. A popular repository is a useful candidate source, not a
compatibility certificate or a quality ranking.

## First batch: small through large

The October 20, 2026 UTC discovery batch selects four public GGUFs within a
30 GiB download budget. Sizes below are **weight-file sizes**, not RAM or VRAM
requirements. Context/KV or recurrent state, backend buffers, and the desktop
need additional memory. No model weights are bundled with SYNAPSE.

| Model | Design and intended starting point | Exact GGUF | Weight file | License |
| --- | --- | --- | ---: | --- |
| [LFM2.5-1.2B-Instruct](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct) | Small on-device instruction model; try extraction and simple chat, not a programming-quality baseline | [Q4_K_M](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF/blob/8ed288026e23958ad9dfa92d53ed773a8eee7125/LFM2.5-1.2B-Instruct-Q4_K_M.gguf) | 0.68 GiB | [LFM Open License v1.0](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct/blob/0f604ada3f766f9f257460c4c9f0b5d6f69d431b/LICENSE), custom commercial terms |
| [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) | Compact dense model for general chat, multilingual tasks and reasoning experiments | [Q4_K_M](https://huggingface.co/Qwen/Qwen3-4B-GGUF/blob/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf) | 2.33 GiB | Apache-2.0 |
| [GPT-OSS-20B](https://huggingface.co/openai/gpt-oss-20b) | Smaller MoE: approximately 21B total / 3.6B active parameters; local reasoning comparison | [MXFP4](https://huggingface.co/ggml-org/gpt-oss-20b-GGUF/blob/15dcfc7e7c608c6161507211ed43c5b590801b4b/gpt-oss-20b-MXFP4.gguf) | 11.28 GiB | Apache-2.0 |
| [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) | Large **dense**, not MoE, model; useful CPU/GPU placement and memory-pressure comparison | [UD-Q4_K_M](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/blob/4ca720788d1e01f1bff70c033e0d0028fd02e502/Qwen3.8-27B-UD-Q4_K_M.gguf) | 15.33 GiB | Apache-2.0 |

These intended-use descriptions come from publisher model cards, not a
SYNAPSE task-quality evaluation. LFM2.5's "hybrid" convolution/attention
architecture is unrelated to SYNAPSE's hybrid CPU/GPU **expert** scheduler.
Qwen3.8-27B is also distinct from the much larger Qwen3.8-Flash-Next MoE.

## Measured decision baselines

All four pinned GGUFs **loaded and generated through SYNAPSE** in Standard
mode at actual 16K context. The benchmark completed October 20, 2026 UTC
(October 19 on the reference host).

| Model | Decode median | First streamed text median | Exact integer / AST checks | Evidence |
| --- | ---: | ---: | --- | --- |
| LFM2.5-1.2B-Instruct Q4_K_M | 660.30 tok/s | 10.7 ms | **Fail / fail** | [All samples and checks](lfm/lfm25-12b-q4-km.json) |
| Qwen3-4B Q4_K_M | 190.56 tok/s | 33.6 ms | Pass / pass | [All samples and checks](qwen/qwen3-4b-q4-km.json) |
| GPT-OSS-20B MXFP4 | 199.92 tok/s | 74.0 ms | Pass / pass | [All samples and checks](gpt-oss/gpt-oss20b-mxfp4.json) |
| Qwen3.8-27B UD-Q4_K_M | 11.02 tok/s | 547.5 ms | Pass / pass | [All samples and checks](qwen/qwen38-27b-ud-q4-km.json) |

**How to use this evidence:**

- **Try Qwen3-4B first for a compact general-purpose baseline.** Its pinned
  file is much smaller than GPT-OSS-20B, and it passed both narrow checks.
  This is a practical starting point, not proof it is the best model for a task.
- **Try GPT-OSS-20B for a larger MoE comparison on this 16GB-class system.**
  It ran Standard at 16K without needing hybrid dispatch. Its low-effort
  reasoning stream is counted in throughput and first-token timing.
- **Treat LFM2.5 as a small, task-specific candidate, not a speed-based winner.**
  Both strict predicates failed despite successful loading and fast decode.
  Stored checks retain answer hashes, not answer text, so we cannot attribute
  the failures to formatting versus incorrect content from these records.
- **Budget substantial latency for Qwen3.8-27B at this quantization on this
  host.** The median 512-token request took 46.89 seconds. It is a dense-model
  placement baseline, not a hybrid result or evidence of superior answers.

GPU memory snapshots after the requests were 2,146 / 5,915 / 12,639 / 14,522 MiB
in the table's order, including other desktop GPU use. About 939 MiB was in use
before the batch. These are **not peaks or required VRAM**, and subtracting
the initial snapshot does not establish a reliable minimum. Process RAM and
other resource snapshots are retained in the JSON. Do not add RSS to GPU
memory or use the weight-file sizes as total memory estimates.

The current installed-profile pre-check predicted Standard for all four:
three files had no complete routed-MoE descriptor; GPT-OSS-20B was a generic
hybrid candidate but the small-file heuristic preferred native fitting.
**Only Standard at 16K was measured in that initial batch.** Automatic's predicted defaults use 4K
context here, so these results must not be labeled measured Automatic rates.
No new hybrid speedup or independent native-reference equivalence is claimed.

### Explicit hybrid follow-up

The [subsequent hybrid experiment](gpt-oss/gpt-oss20b-hybrid-screen.md) actually
requested Require hybrid for all four new models. GPT-OSS-20B activated at
8 GiB and 10 GiB causal cache budgets, measuring **143.19 and 143.99 tok/s**,
respectively, against fresh Standard controls of **207.08 and 203.75 tok/s**
and a same-patched-build Standard control of **207.00 tok/s**.
Both hybrid budgets were slower; the earlier 199.92 baseline was not used as
the denominator. Standard is the better measured choice here.

All narrow GPT answer checks passed, but hybrid text hashes varied and did
not match the Standard output. No independent native-reference logit gate was
run. The report preserves these limits, the warm-up progression, binary/
toolchain identities, the same-build control and the fact that no installation
defaults were changed.

The other three models explicitly rejected forced hybrid before starting
a backend. No hybrid rate exists for those rejected requests. Their Standard
measurements remain useful; hybrid is not the execution path for these dense
or convolution/attention models.

## Popularity evidence, not a leaderboard

The following counters describe the initial small-to-large batch. The later
larger-than-VRAM batch has its own dated popularity evidence below.

Hugging Face API values observed October 20, 2026 UTC:

| Model | Original repository downloads | Selected GGUF repository downloads |
| --- | ---: | ---: |
| LFM2.5-1.2B-Instruct | 113,941 | 346,255 |
| Qwen3-4B | 11,821,887 | 563,901 |
| GPT-OSS-20B | 5,897,765 | 210,786 |
| Qwen3.8-27B | 7,458,401 | 6,656,041 |

These are repository download counters from the API's observation window,
not lifetime totals, unique users, downloads of the selected quantization,
or evidence of correctness. Base and GGUF counters use different counting
rules and must not be added together. See
[Hugging Face's counting explanation](https://huggingface.co/docs/hub/models-download-stats).
The small LFM model adds architectural and resource breadth; this is a curated
batch, not a claim that all four are the most popular models.

## How the baselines are measured

Use the Ryzen 9 9950X, RTX 5070 Ti 16GB reference host with 123.48 GiB usable
RAM and the pinned llama.cpp
`620d2225cc436ab0b001e3200e590e3b286ef9ab` backend through SYNAPSE.
The common screen uses actual 16,384-token context, 8 generation / 16 prompt
threads, one slot, FP16 attention cache, native automatic placement with a
1,024 MiB reserve, and no explicit expert cache or speculation.

Each model is loaded once in **Standard mode** and generates three exact
512-token responses to the same technical explanation prompt. Temperature is
zero, seed 42, reasoning effort is low, prompt caching is disabled, and EOS is
ignored. This forced-length protocol can continue past a natural answer's end
and includes reasoning tokens. It is not a recommended chat sampling preset.

Decode rate is `511 / (request wall seconds - reported prompt milliseconds / 1000)`.
Downloads and loading are excluded; transport and remaining scheduling costs
are included. Individual rates, request/prompt/first-token times, and output
hashes are retained. No model-generated code is executed.

After selecting **Standard backend (manual settings)** in Model Controls, set
the context/threads/placement above and use the following streamed request.
Replace the port with the app's actual loopback port; repeat it three times
without reloading the model:

```bash
curl --fail --no-buffer http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "local-model",
    "messages": [{"role": "user", "content": "Explain how a CPU and GPU can cooperate to execute a mixture-of-experts model. Discuss memory bandwidth, expert placement, synchronization, and correctness in detail."}],
    "max_tokens": 512,
    "temperature": 0,
    "seed": 42,
    "reasoning_effort": "low",
    "ignore_eos": true,
    "cache_prompt": false,
    "stream": true,
    "stream_options": {"include_usage": true},
    "timings_per_token": true
  }'
```

Use the pinned research
[stream sampler](https://github.com/appatalks/unified-memory-scheduler/blob/cc52e4b5588e31233793bbfec743b488182613a2/tools/benchmark/vrambridge-execution-sweep.py)
to measure request wall time and validate final token counts/timings; do not
treat the server's decode rate or curl's transfer speed as the same metric.
The separate [exact-answer predicates](https://github.com/appatalks/unified-memory-scheduler/blob/cc52e4b5588e31233793bbfec743b488182613a2/tools/benchmark/vrambridge-model-matrix.py)
are unchanged. Records include the helper hashes and exact prompts.

Two separate 1,024-token checks require the exact integer `323` for `17 * 19`
and the exact AST of the requested Python `clamp` function with no Markdown.
A failure can reflect formatting, reasoning truncation, or task failure.
Passing both is not broad quality, numerical-equivalence, tool-use, or coding
qualification.

This is a sequential single-prompt screen, not randomized significance or a
sustained multi-category evaluation. Different tokenizers and quantizations
make tokens/second unsuitable as a cross-model quality score. RAM/GPU snapshots
are not peak memory measurements or minimum hardware requirements.

## Choosing between Standard and Hybrid

Start with the model size and task, not the execution-mode label. Small models
may already fit on the GPU and need no expert scheduler. Large dense models can
use ordinary CPU/GPU placement, but have no routed experts for hybrid dispatch.
MoE models may be hybrid candidates without benefiting from it.

Use [Check hybrid eligibility](../application_notes.md#hybrid-eligibility-pre-check)
against the installed engine. The result is metadata/profile eligibility,
not proof of kernel support, memory fit or answer quality. A predicted
Automatic selection is not a measured Automatic or Hybrid benchmark.

For measured larger-than-VRAM MoE results, see the
[setup results table](README.md#ryzen-9-9950x--rtx-5070-ti-16gb) and
[qualification limits](../compatibility.md).

## Popular larger-than-VRAM MoE batch

The next batch deliberately selected **popular MoEs whose exact Q4_K_M files
exceed even total GPU VRAM**. Both completed real hybrid execution through
SYNAPSE; these are not metadata-only predictions.

| Model | Pinned weight size | GGUF repository downloads / likes | Fastest fresh Standard block | Hybrid, 8 GiB bank | Change |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Qwen3-Coder-30B-A3B-Instruct](qwen/qwen3-coder30b-q4-km-hybrid.md) | 17.28 GiB | 1,478,416 / 1,157 | 70.08 tok/s | **110.06 tok/s** | **+57.1%** |
| [GLM-4.7-Flash](glm/glm47-flash-q4-km-hybrid.md) | 17.06 GiB | 174,557 / 728 | 64.87 tok/s | **87.45 tok/s** | **+34.8%** |

Popularity values were observed October 20, 2026 UTC. The original publisher
repositories separately showed **515,009 / 1,125,508 downloads** for Qwen/GLM,
respectively. Counters are request-based repository signals, not unique users
or quality scores. Do not add publisher and GGUF totals or infer downloads of
the selected file. Each linked report includes the primary model card, exact
GGUF revision, SHA256, license and API provenance. Qwen is Apache-2.0; GLM is MIT.

The reference GPU reported **15.92 GiB total VRAM**; both weights exceed that
before context, runtime buffers or desktop use. The approved new downloads
totaled **34.337 GiB**. Weight-file size is not a total RAM/VRAM requirement.
This does not make every larger-than-VRAM model an acceleration candidate:
both selected checkpoints are routed MoEs, unlike dense Qwen3.8-27B.

### Matched protocol and reproduction

Use the pinned backend, Ryzen 9 9950X / RTX 5070 Ti reference host, and the
same exact files linked in the model reports. This screen used **the same
patched executable and explicitly selected CUDA plugin for every control
and hybrid block**, avoiding the earlier installed-build difference.

To reproduce that configuration, launch a separate app with placeholders
replaced by the matching installed paths:

```bash
GGML_BACKEND_PATH=/path/to/matching/libggml-cuda.so \
  python -m synapse_app --llama-server /path/to/patched/llama-server \
  --hybrid-profile /path/to/hybrid-profile.json --port 0 --no-update-check
```

Use a version-2 generic profile with 16K hybrid context, direct generic
transfers, decode pipeline and protected GPU IDs enabled. Do not reuse a
GPT-OSS-trained expert seed for these models. This is the measured installation
configuration, not a universal hardware recommendation.

For each unchanged GGUF, use the following order:

1. **Standard before:** actual 16,384 context, 8 generation / 16 prompt threads,
   automatic placement, 1,024 MiB reserve, default loading, host-op offload on,
   polling 50, host-op batch threshold 32, FP16 attention cache and no expert
   cache or draft.
2. **Require hybrid, 8192 MiB:** unload/reload, retain 16K/8/16 and FP16 cache;
   host-op offload and fitting are disabled by the hybrid path. Confirm full
   routed-layer coverage, direct registration and actual context.
3. **Require hybrid, 10240 MiB:** unload/reload and change only the causal bank
   budget. Keep the initial cold-start sample in the result.
4. **Standard after:** unload/reload and repeat the first configuration.

For each load, send the same three forced-512-token requests and two separate
exact-answer requests described in
[the baseline protocol](#how-the-baselines-are-measured). Temperature zero,
seed 42, low reasoning effort, no prompt caching and EOS ignored are unchanged.
Qwen3-Coder is a non-thinking checkpoint; the requested effort parameter does
not imply it generates reasoning tokens.

Each hybrid bank starts empty and learns causally; residency persists across
that load's repetitions and checks. Downloads/loading/registration are outside
decode timing. The metric remains `511 / (request wall seconds - prompt_ms / 1000)`,
not the backend-only counter or end-to-end request rate.

### Findings and limits

Both 8 GiB and 10 GiB banks beat both corresponding Standard blocks. Ten GiB
measured **108.08 tok/s for Qwen** and **87.39 tok/s for GLM**; it did not improve
either model's median. Eight GiB is the better observed budget of two, not a
proven optimum. Gains use the **fastest Standard block median**, not the slower
control or an older result. No exhaustive native CPU-expert/thread sweep was
performed.

All **16 narrow answer checks passed** across eight blocks. Native activation
confirmed 48/48 Qwen and 46/46 GLM routed layers. Qwen's gate/up-fusion marker
was observed; GLM's was not, despite pipeline configuration.

**These are not quality-qualified gains.** Hybrid throughput hashes vary.
Standard hashes repeat within a block but also differ between before/after
reloads for both models. The cause is not isolated, identical output is not
established, and no independent native-reference logit comparison was run.
Passing two predicates or observing routing coverage does not resolve that.

This is a sequential, forced-length single-prompt screen, not randomized
significance, sustained coding/reasoning/prose qualification, or evidence of
maximum hardware speed. Initial 512-token request latency improved, but
first-streamed-text latency did not; both are retained separately in the
reports. GPU/RAM snapshots are not peaks or fit guarantees.

These results add two useful **hybrid research options**, while the smaller
GPT-OSS-20B result still favors Standard. Installation defaults and the bound
training plan were not edited; benchmark-owned backends were stopped.

## Further candidates

These are discovery leads, **not newly tested configurations in this batch**:

- [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) with its
  [publisher GGUF](https://huggingface.co/Qwen/Qwen3-8B-GGUF): a dense
  middle tier between Qwen3-4B and the larger targets.
- [Gemma 3 4B IT](https://huggingface.co/google/gemma-3-4b-it) with a
  [GGUF conversion](https://huggingface.co/unsloth/gemma-3-4b-it-GGUF):
  another dense family; review Gemma's custom license and access terms.

All new compatibility claims require a successful SYNAPSE load and request
with the chosen GGUF/backend. This guide covers **text only**; publisher vision,
audio, tool-use, context and agent benchmarks are not SYNAPSE qualifications.
