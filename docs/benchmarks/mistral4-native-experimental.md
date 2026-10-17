# Mistral Small 4: Experimental Native Integration

> **Research evidence, not a validated speedup claim.**
> The isolated build runs through SYNAPSE, but strict native-reference
> equivalence still fails. It is not production-qualified, is not part of the
> default accelerated installation, and is deliberately absent from the
> four-model headline performance table.

[Reviewed numeric evidence](mistral4-native-experimental.json) retains the
timings, failed gates, targeted passes and temporary application/API proof.
Null execution flags in earlier records mean they were not recorded, not that
the feature was disabled.

## Separately Labeled Research Timings

| Isolated-build configuration | Three-sample decode median | Answer/numerical status |
| --- | ---: | --- |
| Native CPU experts / GPU backbone; new flags off | 21.09 tok/s | Integer passes; original strict coding check fails. |
| Automatic placement; experimental kernels enabled | 23.96 tok/s | Integer passes; original strict coding check fails. |
| Causal hybrid, 8 GiB bank; experimental kernels enabled | 33.01 tok/s | Integer passes; original strict coding check and native-reference equivalence fail. |

All rows use the same isolated backend/plugin, unchanged Mistral Small 4
119B/6.5B UD-IQ4_XS target, actual 16K context, 8 generation / 16 prompt threads,
one slot, and three exact 512-token samples. Temperature is zero, seed 42,
reasoning uses the model default, prompt caching is off and EOS is ignored.
No MTP, speculation, expert pruning or weight requantization is used.

Decode rate is 511 token intervals divided by request wall time minus reported
prompt-processing time. Loading/downloads are excluded; remaining scheduling
and transport overhead is included. Every sample and load/request timing is
retained. These are sequential technical blocks, not randomized significance
or sustained natural-workload qualification.

The model and earlier native controls are documented in the
[initial study](mistral4-compatibility.md). These new numbers are not substituted
for that earlier measurement window.

## What Changed In The Isolated Backend

The first integrated FP32 kernel ran, but deviated substantially from native
logits. The study therefore continued instead of promoting the primitive gain.

- Quantized fusion paths were prevented from bypassing the protected expert
  operation's precision requirement.
- A separate opt-in path reproduces the CPU's Q8_K activation-quantization
  semantics using FP32 scales, including for IQ3_S gate/up tensors. It is not
  the original unquantized-FP32 prototype.
- The activation conversion uses bounded GPU scratch, not the earlier
  128 MiB-per-position expanded weight matrix.
- Kernels use the existing CUDA stream and graph machinery; original weights
  and selected contributions remain present.

The selection is based on operation precision, dtype and shape, not a model-name
exception. The two opt-in flags are `GGML_CUDA_MMVQ_F32=1` and
`GGML_CUDA_MMVQ_Q8_K=1`. Default behavior is unchanged when they are absent.

## What Passed

- Twelve actual-weight primitive cases cover IQ3_S, IQ4_XS and Q6_K, normal and
  high-range synthetic activations, one/three positions, and padded/broadcast
  layouts. Primitive error versus native CPU expert operations remains below
  the fixed 1e-5 gates.
- Integrated memcheck reports zero errors; racecheck zero hazards/errors/warnings
  for the tested activation-conversion and expert kernels.
- Frozen and adaptive optimized-versus-base hybrid comparisons each pass at
  96 sampled full-vocabulary positions with zero error and both backends used.
- The latest throughput run records 109,575 CPU and 115,093 GPU expert
  contributions: their sum equals four contributions per 56,167 dispatches.
- The unchanged managed SYNAPSE zipapp loaded the prototype with a temporary
  profile, confirmed 16K/8/16/8192 MiB, returned the exact integer answer, and
  completed a 128-token API smoke. Its 11,318 CPU plus 7,418 GPU contributions
  also match the required top-4 total. That smoke is not a published speed sample.

## What Failed And Remains Unresolved

**Strict native-reference equivalence fails** at the unchanged limits:
maximum absolute logit error 0.01 and relative-L2 error 0.001.
Matching the base hybrid is not a substitute for matching the independent
native execution.

The failures are not explained by one isolated primitive discrepancy:

- Observer-enabled tensor captures can match while unobserved runs differ.
  Active capture changes scheduling/fusion and is diagnostic, never a passing
  qualification result.
- A short CPU-empty control matches with CUDA fusion disabled; disabling CUDA
  graphs alone does not resolve the mismatch.
- Disabling only router/top-k fusion did not resolve it.
- Mixed CPU/GPU execution still fails the 96-position native gate with global
  CUDA fusion disabled.
- A controlled first-layer GPU case has expert outputs close to CPU values,
  yet final logits differ substantially. This does not establish that
  accumulation, fusion or quantization sensitivity is the sole cause.

All three timing profiles fail the original strict coding predicate. Arithmetic
passes do not repair that failure or establish broad quality. Generated code
is parsed, never executed. No failed check was relabeled after stripping format
markers, changing a reference or relaxing a threshold.

**Consequently, no Mistral headline gain or native-equivalent compatibility
claim is published.** The remaining work is numerical attribution and
representative model-quality evaluation, not just a faster kernel.

## Reproducing The Experimental Build

This is an advanced developer experiment, not a one-line installation option.
Do not overwrite a working backend or install these flags into a production
service expecting equivalent answers.

Use a separate checkout of llama.cpp commit
`620d2225cc436ab0b001e3200e590e3b286ef9ab`. Apply these patches in order from
the immutable research revision
[`ff8c352`](https://github.com/appatalks/unified-memory-scheduler/tree/ff8c3520eac94f531c2e35eb558941a7069e5bae):

| Patch | SHA256 |
| --- | --- |
| [Existing hybrid patch](https://github.com/appatalks/unified-memory-scheduler/blob/ff8c3520eac94f531c2e35eb558941a7069e5bae/third_party/patches/llama-b11669-hybrid-experts.patch) | `961544562fa0f9c45c1b5ee71e91196d693b01285572c40197c5c260df07319b` |
| [Additional experimental FP32/Q8_K patch](https://github.com/appatalks/unified-memory-scheduler/blob/ff8c3520eac94f531c2e35eb558941a7069e5bae/third_party/patches/llama-b11669-fp32-experts-experimental.patch) | `b8351e4aa70209d8f0e0f732446ea8c0183d6f887fc227014ee06d0ebe048085` |

Both patches were checked on a fresh pinned checkout; critical source components
match the measured build. The tested build uses CUDA 13.1, SM 120a, Release,
CUDA and dynamic backends on, `GGML_NATIVE=OFF`, all CPU variants on, and
matching server/CUDA libraries from the same build. Follow the upstream
[build documentation](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/docs/build.md);
other hardware/toolchains are not qualified by this experiment.

Create a separate schema-version-2 hybrid profile pointing at that build's
server and CUDA plugin, with `plan: "auto"`, context 16384, cache/generic cache
8192 MiB, direct/generic direct transfers, `decode_pipeline: true` and
`async_ids: true`. Unload other GPU models before starting a test instance.

```bash
GGML_CUDA_MMVQ_F32=1 GGML_CUDA_MMVQ_Q8_K=1 \
  synapse --llama-server /path/to/experimental/build/bin/llama-server \
  --hybrid-profile /path/to/experimental-profile.json --port 8081
```

Choose an unused port. Load the unchanged target in Require hybrid mode and
confirm context, routed-layer coverage, registrations and activation in the
backend logs. The flags apply to that experimental process: do not assume its
Standard button reproduces a flags-off baseline. Use a separate process with
both new flags unset or zero for that control.

The normal installer remains pinned to the prior backend artifacts and does not
apply this additional patch. No public release/tag or installed-backend update
was performed. All local tests restored the original GPT profile afterward.
