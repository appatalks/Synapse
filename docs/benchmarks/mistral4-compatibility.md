# Mistral Small 4: Compatibility And FP32 GPU Prototype

## Outcome

Mistral Small 4's native architecture and fused expert layout are recognized,
but **the installed experimental hybrid engine cannot execute this target**.
It fails explicitly rather than silently changing precision or falling back.
No Mistral acceleration row has been added to the README.

An initial isolated, opt-in GPU prototype passes 16 FP32-reference checks, including
activations beyond FP16 range. It establishes a possible arithmetic building
block, **not a full-model compatibility fix or a demonstrated throughput gain**.
The installed native backend and target weights remain unchanged.

[Reviewed measurements, failures and prototype checks](mistral4-fp32-compatibility.json).
The [fused-kernel follow-up](#fused-fp32-gpu-follow-up) removes the expanded-weight
intermediate and improves primitive latency, but is still not integrated into
full-model execution.

## Model And Native Controls

- [Mistral Small 4](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603):
  119B total / 6.5B active, Apache-2.0.
- GGUF: [unsloth/Mistral-Small-4-119B-2603-GGUF](https://huggingface.co/unsloth/Mistral-Small-4-119B-2603-GGUF),
  UD-IQ4_XS at revision `bd93c721735aa32c035c0f19e738cb3371fd56ff`.
- Three SHA256-verified shards, 58,126,815,232 bytes in total.
  The first is metadata-only; both tensor shards are required.
- Actual architecture `mistral4`: 36 routed layers, 128 experts/top-4.
  Fused gate/up weights are IQ3_S; down weights are IQ4_XS in 32 layers and
  Q6_K in four. The quantization label does not mean every tensor is IQ4_XS.

On Ryzen 9 9950X, RTX 5070 Ti 16GB and 123.48 GiB usable RAM:

| Configuration | Three-sample technical decode median |
| --- | ---: |
| Native automatic placement | 5.64 tok/s |
| Native CPU experts / GPU backbone | **19.89 tok/s** |
| Current hybrid, 8 GiB bank | Rejected before inference |

Both controls use the unchanged target, actual 16K context, 8 generation /
16 prompt threads, three exact 512-token samples, temperature zero, seed 42,
model-default reasoning, prompt caching off and EOS ignored. Decode timing
excludes prompt processing and model loading, but includes remaining request
overhead. Weights are on the mounted WD_BLACK NVMe, not a RAM disk.

The CPU-expert control is substantially faster here. This is a native placement
comparison, not a SYNAPSE hybrid gain. More profiling is needed to attribute
the gap to particular transfers, kernels or graph splits.

Both modes pass the exact integer check but fail the original coding check.
They produce the same fenced source with reversed min/max nesting; removing
fences alone does not satisfy the unchanged AST predicate. The two expressions
are not equivalent for inverted bounds. Generated code was parsed, never
executed. Failures have not been reclassified as passes.

## Why Hybrid Rejects It

The model graph requests `GGML_PREC_F32` for the activation input of its down
projection: values may exceed FP16 range. The pinned CUDA backend explicitly
rejects `MUL_MAT_ID` when that source-precision requirement is present.
The current hybrid branch requires resident expert operations to run on its
assigned GPU, so the unsupported down projection stops graph construction.

Sources at the pinned revision:

- [Model expert graph and precision requirement](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/src/llama-graph.cpp).
- [CUDA operation capability checks](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/ggml/src/ggml-cuda/ggml-cuda.cu).

Declaring an input tensor F32 is not enough: internal kernel conversions must
also respect the requested range. Removing the precision flag or bypassing
`supports_op` is not a valid compatibility fix.

The failed load confirms all 36 routed layers, both storage groups, an
8,170.46 MiB bank and 54,996,008,960 registered source bytes. It fails at the
operation check, not because the model is missing or the bank ran out of VRAM.

The initial inspection helper assumed separate gate/up tensors, then the initial
log reader rejected a native tokenizer-metadata line truncated inside a UTF-8
character. Both harness failures remain recorded. Fused descriptors are now
recognized; diagnostic parsing explicitly escapes invalid bytes while retaining
raw log bytes. Model API responses are not decoded permissively.

## Isolated FP32-Safe GPU Prototype

The initial prototype uses the existing pinned GGML/CUDA libraries, without installing
a new native backend or compiling a new kernel:

1. Keep a small bank of original quantized down-projection weights.
2. Gather selected expert rows and dequantize them into FP32.
3. Reshape into per-expert matrices and apply FP32 batched matrix multiplication,
   requesting both FP32 source precision and FP32 accumulation.

Real IQ4_XS and Q6_K down tensors are exercised at input/output dimensions
2048/4096, four selected experts, one or three positions, and activation scales
1 and 1,000,000. A reserved zero expert checks masked contributions. The
cache-pressure run also varies expert ordering across positions.

Across the original and cache-pressure runs, **all 16 checks pass**:

- CPU/GPU dequantized weights match exactly.
- Outputs remain finite with activations exceeding 65,504.
- Relative-L2 error versus the dequantized FP32 CPU reference is at most
  **1.55e-7**, below the fixed 1e-5 gate.
- Normalized maximum-absolute error is below its independent 1e-5 gate.
- Masked zero-expert outputs stay zero.
- Capability queries reproduce native GPU rejection of the original operation,
  while the FP32 decomposition executes successfully.

### Why It Is Not Promoted

The decomposition materializes **128 MiB of FP32 selected weights per position**:
384 MiB at three positions, under an explicit 512 MiB scratch cap. Repeatedly
expanding weights creates substantial memory traffic.

For single-position probes:

| Timing condition | GPU FP32 gather/GEMM | Native CPU quantized expert matmul |
| --- | ---: | ---: |
| Warm small bank, across types/scales | 0.37-0.38 ms | 0.09-0.11 ms |
| 256 MiB CPU cache-pressure control | 0.46-0.48 ms | 0.28-0.49 ms |

Cache pressure is applied outside the timed computation. It is a separate
sensitivity check, not proof of a particular DRAM hit rate. Primitive timings
exclude weight loading and are not full-inference tok/s estimates.

The FP32 decomposition also differs from native CPU quantized expert matmul by
about **0.0032 relative L2** in these synthetic-activation probes. Matching a
dequantized FP32 reference is not the same as reproducing the native CPU kernel.
No full-model native-reference or answer-quality gate has passed for a modified
Mistral hybrid. Existing numerical tolerances have not been weakened.

## Next Optimization Work

The useful objective is **range-safe math without repeatedly materializing large
FP32 expert matrices**, not merely making the unsupported-operation check pass.

Candidate directions, not implemented optimizations:

1. A quantized-weight, FP32-activation GPU expert kernel that dequantizes on the
   fly and preserves the required range, avoiding the 128 MiB intermediate.
   The standalone follow-up below tests this direction; full-model integration
   and qualification remain open.
2. Precision/cost-aware per-projection scheduling: accelerate compatible gate/up
   work while keeping the protected down projection on CPU, rather than forcing
   an entire expert onto one device.
3. Budget-aware caching of expanded weights only if measured reuse pays for
   their much larger VRAM footprint.

Any integration must be opt-in, retain every selected contribution, respect
scratch/VRAM limits, pass representative full-model numerical and answer checks,
and beat the **19.89 tok/s faster native control**, not just automatic placement.
No model-name exception or silent precision reduction is justified.

All screens and prototypes restored the original GPT profile. Automatic hybrid
selection is not a compatibility guarantee; use standard execution until the
required operations are supported and verified.

## Fused FP32 GPU Follow-Up

The [reviewed fused-kernel evidence](mistral4-fused-fp32.json) tests a standalone,
opt-in CUDA kernel on the RTX 5070 Ti, compiled for SM 120. It reuses the pinned
IQ4_XS and Q6_K dequantizers, combines block dequantization with FP32 dot products,
and does not quantize or narrow the activation input.

Instead of writing a large FP32 matrix to global memory, it uses short-lived
per-block shared tiles: 4,096 bytes for IQ4_XS and 2,064 bytes for Q6_K, plus a
four-byte global error flag. There is **no expanded-weight global intermediate**.
An additional variant uses warp-local synchronization for IQ4_XS; Q6_K retains
the required multi-warp barriers.

### Completed Checks

- **24 completed timing fixtures:** both real down-projection types, one/three
  positions, normal and 1e6-scale synthetic activations, warm and CPU
  cache-pressure conditions.
- Fixed FP32-reference gates pass: worst relative-L2 error **1.88e-7**, below
  1e-5; normalized maximum-absolute error also passes its independent 1e-5 gate.
- Zero/negative-one masked experts, repeated IDs, position-dependent routing,
  partial output tiles and invalid ID/block-size rejection are exercised.
- Four separate safety fixtures pass. Compute Sanitizer **memcheck reports zero
  errors**, and **racecheck reports zero hazards, errors or warnings** for the
  refined kernel. Instrumented timings are not performance evidence.

### Primitive Timing, Not Mistral Decode Throughput

In the completed isolated refined-kernel window, with CPU cache pressure:

| Single-position operation | Median range across types/scales |
| --- | ---: |
| Expanded-weight GGML GPU prototype | 0.464-0.503 ms |
| Fused quantized-weight/FP32-activation kernel | **0.075-0.087 ms** |
| Native CPU quantized expert matmul | 0.365-0.500 ms |

The fused measurements include kernel launch, events and completion
synchronization, but not initial host/device uploads or the final error-flag
copy. The GGML comparator uses a different API boundary. Device-event timings
are retained separately; the primitive ratios are not end-to-end speedups.
The warm small-bank CPU control is also retained rather than hidden.

These are synthetic-activation probes using real weights, not a full-model
cache simulation or a coding/reasoning evaluation. Native CPU quantized
matmul is still numerically different from the FP32 reference. No native
equivalence threshold was relaxed, and no new Mistral tok/s result is claimed.

### Retained Restoration Failure And Fix

One early refined-kernel run passed its eight primitive cases but the subsequent
GPT reload ran out of VRAM while the probe process still retained CUDA context
state. That run is excluded from headline timings and retained in the evidence.
GPT was recovered after the probe exited.

The probe lifecycle now uses a non-CUDA parent and a separate CUDA worker:
the parent restores the original model only after the worker and its context
have exited. The repeated timing run and both sanitizer runs verified successful
restoration. Final GPT settings are confirmed at 16K, 8/16 threads and
12,000 MiB residency. No driver reset, installed-backend replacement or runtime
default change was used.

This is now a promising **integration candidate**, not a production fix. The
next gate is an isolated llama.cpp graph integration with full-model numerical,
answer-quality and matched-throughput checks against the 19.89 tok/s native
control. The README's Mistral compatibility warning remains applicable.
