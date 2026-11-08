# Tested Compatibility And Validation Status

Compatibility here means a tested text-generation configuration can load and
execute. It does not establish reference-model equivalence, general answer
quality, fit on other hardware, or a universal speedup.

The reported hardware is Ryzen 9 9950X, RTX 5070 Ti 16GB and 123.48 GiB usable
RAM. Accelerated paths are experimental Linux/NVIDIA configurations; the
standard application is separate and cross-platform.

Ready/activation-verified status confirms the requested runtime configuration,
not answer quality or equivalence to an independent reference.

For an unlisted local GGUF, use **Check hybrid eligibility** in Model Controls.
The [read-only pre-check](application_notes.md#hybrid-eligibility-pre-check)
explains metadata/profile eligibility and Automatic selection without loading
weights. It is not a kernel, fit, performance or quality qualification.

## Modular execution profiles

SYNAPSE bundles a declarative catalog in
[`execution-profiles.json`](../synapse_app/execution-profiles.json) for the
existing native Automatic/CPU and Classic/Hosted expert-sharing components.
It also declares a guarded native GPU expert-cache profile with a
positive measured cache budget. CLI capability discovery does not load a
model; actual cache allocation and KV precision are checked at load.
The read-only pre-check returns each profile's requirements, candidate
eligibility, missing capabilities and qualification scope. Routed-MoE
metadata and the installed engine policy gate accelerated candidates;
Hosted additionally requires its capability and direct transfers.
A candidate still needs successful backend loading, fit and runtime
activation checks. It is not a declaration of architecture/kernel support.

Keep **Engine: Automatic**. Auto Tune uses these profile templates with
the model's measured context, cache size, threads and Balanced/Maximum goal,
then remembers the winning settings per model, KV precision, machine and
backend build. New measurements also record the profile ID and definition
fingerprint. If its definition changes, that measurement is not reused;
saved files are not rewritten and legacy measurements remain readable.
The native backend's matching shared-library identities are now included
in the machine/build key, so earlier weakly keyed measurements may require
Auto Tune again.
`execution_profile_id` in status identifies the current existing engine.

Profiles do not relabel GGUF architectures, change model weights, skip
experts, add arbitrary environment flags or introduce user-facing engine
switches. The catalog preserves the existing engine contracts and their
runtime guards. Existing accelerated paths remain explicitly experimental,
not newly quality-qualified by this catalog. No tandem/Clover backend,
concurrent-agent optimization or unqualified speed preset is bundled.
New optimized components require research qualification and a
reviewed contract before becoming production profiles.

The native-cache tuning adaptation uses existing backend operations:
all selected experts are retained, F16 is the qualified tuning preset,
and inherited experimental sharing/routing/default bundles are suppressed
for the native-cache path. Local hardware validation includes Coder,
the modified SC117 Qwen3.8 target and GPT-OSS on the pinned b11669 build.
Coder's 16K near-capacity tuning and Automatic reload select a passing
8 GiB cache; GPT retains uncached fitting where cache trials do not win.
These are scoped engineering checks, not a new intelligence/agentic
leaderboard or an assertion that every MoE layout is qualified.
CPU/GPU overlap, MTP and diffusion remain separate gates.
The optional Strata provider is now part of Automatic/Auto Tune when a
locally qualified installation profile is present. It is bound to the
actual model file, component/controller files, cache residency and F16/MTP
activation; another similarly named GGUF cannot reuse its pack.
The backend component is separate from the application and is not
installed or selected silently. Users keep Engine: Automatic.
CPU-only, unsupported platforms/models, or Standard-only tuning retain
the native paths. Provider winners are saved separately from legacy
native engine choices, and an unrelated model's native choice key does
not change merely because Strata is installed.

The reviewed Qwen integration passes same-cache scalar/MTP full-vocabulary
checks, actual Auto Tune selection/reload, streamed/non-streamed API use,
and a 14,333-token capacity check at 16K. Balanced may recommend the
provider's supported context with updated client limits; Maximum never
reduces capacity just to select it. This is not a native llama.cpp MTP
port, Clover/diffusion support or a general intelligence qualification.
See the sister repository's `docs/research/strata-upstream-reuse.md`.

## Optional serialized causal provider

The separately installed provider is pinned to one verified Clover GGUF,
the measured binary components, Ryzen 9 9950X, one RTX 5070 Ti and NVIDIA
driver 595.58.03. It is not a general Clover, diffusion, concurrent-slot,
speculative-decoding, Q8-KV or cross-platform implementation. Different
model files, packages or machines remain unavailable until qualified.

On that host, a single isolated 131,072-token slot retrieved anchors from
122,878 input tokens in 2,035 seconds. Short-generation screens measured
57.49–57.89 tokens/s in that load; this shared-host result is not a general
speed guarantee or broad quality assessment. Bounded same-placement
full-vocabulary and prefix-reuse controls passed. Loading also requires
actual execution and package-local library bindings; a missing marker or
changed precision, context or package is an error.
The packaged app also loaded the separately staged provider at 128K through
Automatic and returned a chat completion in an isolated configuration.

The application does not bundle or install the backend. A separately
prepared exact package can be registered only with explicit confirmation;
see [installation](installing.md#optional-qualified-causal-provider).
The [research patch and evidence](https://github.com/appatalks/unified-memory-scheduler/blob/2dab9aff90631a3e1094f60eea7e69a76a1a3063/docs/research/clover-diffusion.md)
are pinned to research commit `2dab9aff90631a3e1094f60eea7e69a76a1a3063`.
The execution-marker patch SHA-256 is
`c7a5b362ceb26f585859febb78fa9b2eda06ec00913dfabcde7ad071aee7b7f3`.

## Tested hybrid configurations

| Target (GGUF downloads) | Tested accelerated path | Validation limits |
| --- | --- | --- |
| [GPT-OSS-120B MXFP4](https://huggingface.co/ggml-org/gpt-oss-120b-GGUF/blob/238abdd290bb874b90a5da1b4549881b7d05c091/gpt-oss-120b-MXFP4.gguf) | Trained/direct-DMA hybrid profile | Technical speed screens and targeted checks; strict CPU-reference and earlier answer failures remain unresolved. |
| [Qwen3.8-Flash-Next IQ3_S](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/ed59f92082b1e93c0e96d60a8b11aab089b52f09/IQ3_S) | Generic/hybrid expert dispatch | Limited same-placement and separate canonical numerical checks; not broad quality qualification. |
| [GLM-4.5-Air IQ4_XS](https://huggingface.co/unsloth/GLM-4.5-Air-GGUF/tree/506d64aa8c5cfe9dbbf00bc7a15739438f83204d/IQ4_XS) | Causal hybrid with a manual 6 GiB bank at 16K | The 8 GiB attempt failed to fit. Original thinking/format failures remain; separate thinking-off checks pass. |
| [Qwen3.6-35B-A3B Q8_0](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/blob/a483e9e6cbd595906af30beda3187c2663a1118c/Qwen3.6-35B-A3B-Q8_0.gguf) | Empty-causal hybrid with an 8 GiB bank | Six small answer checks and sampled same-placement checks pass; not native-reference or general-quality qualification. |
| [Qwen3-Coder-30B-A3B-Instruct Q4_K_M](https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/blob/b17cb02dd882d5b6ab62fc777ad2995f19668350/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf) | Empty-causal direct hybrid, 8/10 GiB at 16K | 48/48 routed layers verified; faster than bracketed Standard controls; narrow checks pass, but output hashes differ and native-reference logits are untested. |
| [GLM-4.7-Flash Q4_K_M](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/blob/0d32489ecb9db6d2a4fc93bd27ef01519f95474d/GLM-4.7-Flash-Q4_K_M.gguf) | Empty-causal direct hybrid, 8/10 GiB at 16K | 46/46 routed layers verified; faster than bracketed Standard controls; narrow checks pass, but output hashes differ and native-reference logits are untested. |
| [Mistral Small 4 UD-IQ4_XS](https://huggingface.co/unsloth/Mistral-Small-4-119B-2603-GGUF/tree/bd93c721735aa32c035c0f19e738cb3371fd56ff/UD-IQ4_XS) | **Isolated experimental backend only** | Loads/generates through a temporary SYNAPSE profile, but **strict native equivalence fails**. Not included in default accelerated installation or the headline speedup table. |

These links provide the corresponding model families and quantizations, not a
claim that every repack matches the benchmarked bytes. Review each model's
license, download all shards of a split GGUF, and select its first shard when
loading. No model weights are bundled with SYNAPSE.

The ordinary native backend recognizes Mistral's architecture, but the current
installer-pinned hybrid engine lacks the required FP32-source expert operation.
The separate prototype does not change the installed engine, installer defaults
or managed-update behavior. Automatic descriptor selection is not a guarantee
that every required operation is supported.

## Additional Standard text-generation baselines

The October 20, 2026 UTC batch successfully loaded and generated three exact
512-token samples per model through SYNAPSE's Standard backend at actual 16K
context, with 8 generation / 16 prompt threads on the reference host.

| Pinned GGUF | Standard decode median | Exact integer / AST checks | Hybrid status in this batch |
| --- | ---: | --- | --- |
| [LFM2.5-1.2B-Instruct Q4_K_M](benchmarks/lfm/lfm25-12b-q4-km.json) | 660.30 tok/s | **Fail / fail** | No complete routed-MoE descriptor |
| [Qwen3-4B Q4_K_M](benchmarks/qwen/qwen3-4b-q4-km.json) | 190.56 tok/s | Pass / pass | Dense; no complete routed-MoE descriptor |
| [GPT-OSS-20B MXFP4](benchmarks/gpt-oss/gpt-oss20b-mxfp4.json) | 199.92 tok/s | Pass / pass | [Hybrid verified at 8/10 GiB but slower than fresh Standard controls](benchmarks/gpt-oss/gpt-oss20b-hybrid-screen.md) |
| [Qwen3.8-27B UD-Q4_K_M](benchmarks/qwen/qwen38-27b-ud-q4-km.json) | 11.02 tok/s | Pass / pass | Dense; no complete routed-MoE descriptor |

These are technical throughput baselines, not broad answer-quality or
independent native-reference qualifications. Read the
[model-choice guide](benchmarks/model-guide.md) for exact download revisions,
licenses, prompt/request timings, resource caveats and next candidates.
These rows do not establish performance at Automatic's default context or a
hybrid gain.

The [explicit hybrid follow-up](benchmarks/gpt-oss/gpt-oss20b-hybrid-screen.md)
records HTTP 400 rejections before backend startup for LFM2.5 1.2B, Qwen3 4B
and Qwen3.8 27B. GPT-OSS-20B completed activation and narrow checks but remains
without independent native-reference qualification; its variable hybrid
output hashes are retained. Compatibility does not imply a speedup.

## Evidence

- [Headline technical screens and shared caveats](../README.md#why-use-it).
- [GLM protocol and RAM controls](benchmarks/glm/glm45-air-iq4-xs.md).
- [Qwen3.6 protocol and verification limits](benchmarks/qwen/qwen36-q8.md).
- [Qwen3-Coder-30B-A3B Q4_K_M matched hybrid screen](benchmarks/qwen/qwen3-coder30b-q4-km-hybrid.md).
- [GLM-4.7-Flash Q4_K_M matched hybrid screen](benchmarks/glm/glm47-flash-q4-km-hybrid.md).
- [Mistral compatibility boundary and primitive work](benchmarks/mistral/mistral4-compatibility.md).
- [Mistral isolated native integration and research timings](benchmarks/mistral/mistral4-native-experimental.md).

These rows do not qualify image/video input, audio, MTP, speculation, concurrent
requests or arbitrary contexts. A full-GPU native model can already be faster
than a hybrid cache; more resident RAM or a higher GPU-load graph is not proof
of better inference.

If a requested hybrid configuration fails capability, fit or activation checks,
SYNAPSE reports an error rather than calling the run accelerated or silently
substituting CPU-only execution. Standard mode remains available with an
appropriate native backend. Check important answers independently.
