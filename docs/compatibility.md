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
