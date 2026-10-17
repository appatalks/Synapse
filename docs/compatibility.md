# Tested Compatibility And Validation Status

Compatibility here means a tested text-generation configuration can load and
execute. It does not establish reference-model equivalence, general answer
quality, fit on other hardware, or a universal speedup.

The reported hardware is Ryzen 9 9950X, RTX 5070 Ti 16GB and 123.48 GiB usable
RAM. Accelerated paths are experimental Linux/NVIDIA configurations; the
standard application is separate and cross-platform.

Ready/activation-verified status confirms the requested runtime configuration,
not answer quality or equivalence to an independent reference.

| Target | Tested accelerated path | Validation limits |
| --- | --- | --- |
| GPT-OSS-120B MXFP4 | Trained/direct-DMA hybrid profile | Technical speed screens and targeted checks; strict CPU-reference and earlier answer failures remain unresolved. |
| Qwen3.8-Flash-Next IQ3_S | Generic/hybrid expert dispatch | Limited same-placement and separate canonical numerical checks; not broad quality qualification. |
| GLM-4.5-Air IQ4_XS | Causal hybrid with a manual 6 GiB bank at 16K | The 8 GiB attempt failed to fit. Original thinking/format failures remain; separate thinking-off checks pass. |
| Qwen3.6-35B-A3B Q8_0 | Empty-causal hybrid with an 8 GiB bank | Six small answer checks and sampled same-placement checks pass; not native-reference or general-quality qualification. |
| Mistral Small 4 UD-IQ4_XS | **Isolated experimental backend only** | Loads/generates through a temporary SYNAPSE profile, but **strict native equivalence fails**. Not included in default accelerated installation or the headline speedup table. |

The ordinary native backend recognizes Mistral's architecture, but the current
installer-pinned hybrid engine lacks the required FP32-source expert operation.
The separate prototype does not change the installed engine, installer defaults
or managed-update behavior. Automatic descriptor selection is not a guarantee
that every required operation is supported.

## Evidence

- [Headline technical screens and shared caveats](../README.md#why-use-it).
- [GLM protocol and RAM controls](benchmarks/glm45-air-iq4-xs.md).
- [Qwen3.6 protocol and verification limits](benchmarks/qwen36-q8.md).
- [Mistral compatibility boundary and primitive work](benchmarks/mistral4-compatibility.md).
- [Mistral isolated native integration and research timings](benchmarks/mistral4-native-experimental.md).

These rows do not qualify image/video input, audio, MTP, speculation, concurrent
requests or arbitrary contexts. A full-GPU native model can already be faster
than a hybrid cache; more resident RAM or a higher GPU-load graph is not proof
of better inference.

If a requested hybrid configuration fails capability, fit or activation checks,
SYNAPSE reports an error rather than calling the run accelerated or silently
substituting CPU-only execution. Standard mode remains available with an
appropriate native backend. Check important answers independently.
