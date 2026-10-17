# Abstract and document status

Large mixture-of-experts (MoE) models can exceed a consumer GPU's memory while activating only a fraction of their routed weights for each token. This creates an engineering opportunity: retain useful experts in GPU memory, execute cold experts on the CPU, and avoid transferring every cache miss across the host-device link. SYNAPSE combines an optional experimental implementation of that strategy with local chat, an OpenAI-compatible API, model controls, and hardware monitoring.

This paper documents the architecture, measurement protocol, reported results, and qualification limits of that work. Four separate three-run, 512-token technical screens at 16K context report median generation improvements of 54%, 73%, 36%, and 71% against their recorded controls. The experiments use a Ryzen 9 9950X, RTX 5070 Ti 16GB-class GPU, and 123.48 GiB of usable host RAM. Controls, residency budgets, quantizations, and experimental patch revisions vary between series and are identified rather than treated as interchangeable. [3-8]

The intended invariant is that every expert selected by a run's router retains its contribution; target GGUF weights are not pruned or requantized for acceleration. That invariant does not prove identical logits, routing trajectories, or answer quality across backends. Strict reference-logit comparisons and an earlier structured-answer check remain failed. New targeted passes, including exact same-placement pipeline comparisons, do not establish broad quality qualification.

A separate Mistral Small 4 integration demonstrates the importance of that distinction. Its isolated hybrid build executes through SYNAPSE and measures 33.01 tok/s in a research screen, but fails independent native-reference equivalence. It is therefore excluded from the four-model headline table and normal accelerated installation. [9]

> **Publication boundary:** this is a project-reported engineering white paper, not a peer-reviewed study, a universal speedup guarantee, or a production-quality certification. Mistral timings are research-only.

| Document control | Research snapshot |
| --- | --- |
| Edition | Technical white paper, research edition 1.0 |
| Evidence date | 17 October 2026 |
| Application baseline | SYNAPSE e601f93 |
| Reviewed evidence snapshot | unified-memory-scheduler 934bbbf |
| Native base | llama.cpp 620d2225c |

<!-- page -->
# Contents

<!-- contents -->

## Reading this paper

Sections 1-3 explain the hardware problem and execution design. Sections 4-6 define the measurements and separate throughput evidence from correctness and quality claims. Sections 7-8 treat Mistral as a deliberately unqualified case study. Sections 9-13 cover resource accounting, operational boundaries, limitations, related work, and reproducibility.

**Three different claims must not be conflated.** A configuration may load and generate; a pipeline may match a same-placement reference; and a model may preserve independent native behavior. Evidence for one is not evidence for all three.

**A note on units.** GiB and MiB are binary capacities. GB/s refers to a decimal transfer-rate convention when explicitly reported. tok/s denotes generated-token throughput under the stated protocol, not visible characters, SSE events, or speculative proposals.

**A note on scope.** The paper concerns tested text-generation configurations on one machine. The application is cross-platform, while the custom accelerated path discussed here is experimental Linux/NVIDIA work.

<!-- page -->
# 1. The problem is more than model size

A model's total stored weights determine a capacity requirement. Its active weights, attention state, shared layers, synchronization, and movement between devices determine a different execution problem. Sparse activation can make a large MoE interactive without making the entire model resident on a small GPU.

For routed layers, a useful accounting quantity is:

```text
B_selected = sum over routed layers l of (k_l * expert_bytes_l)
```

Here, `k_l` is the number of selected experts and `expert_bytes_l` is the relevant stored projection payload per expert. This is a logical selected-weight budget, not measured DRAM traffic. It excludes other model operations, cache reuse, physical transfer amplification, and implementation-specific reads.

<!-- figure: constraints -->

Figure 1. Capacity, host execution, and transfers are separate constraints. A larger allocation or fuller utilization graph does not identify which constraint limits decode.

Three distinctions drive the design:

- **GPU capacity is not GPU compute availability.** The GPU may have arithmetic headroom but insufficient space for all expert weights, especially after backbone, KV, and compute buffers are reserved.
- **Host RAM capacity is not host bandwidth.** Already-resident weights can still be expensive to read and multiply. More occupied RAM need not increase throughput.
- **A cache miss need not imply a weight upload.** CPU execution of a cold expert can be cheaper than moving its weights to the GPU for one use.

The relevant target is end-to-end accepted target-model execution, not maximizing a device-wide utilization percentage. Busy polling, desktop GPU activity, or repeated uploads can raise counters without increasing useful token throughput. SYNAPSE does not claim that the reported configurations exhaust the hardware's performance potential. [3,11,14]

<!-- page -->
# 2. Architecture and contribution boundary

SYNAPSE has two distinct layers. The product layer provides local interaction and observability. The optional research backend performs expert placement and execution on a pinned llama.cpp base. The reported acceleration belongs to that backend, not to the chat interface. [1-3]

<!-- figure: architecture -->

Figure 2. The data path retains all selected contributions. The dashed admission link is a control-plane decision about future placement, not a rule for dropping a selected expert.

The native model builder supplies routing, projection, activation, weighting, and aggregation rules. Tensor-derived descriptors identify routed layers, expert counts, active counts, dimensions, component types, and compatible bank groups. A residency/dispatch layer partitions each selected expert set between GPU-resident work and CPU cold work, then reconciles their weighted outputs.

The architecture is intended to preserve:

- The selected target GGUF weight artifact, without an additional weight-pruning or requantization step.
- Every expert selected by that run's router, including cold experts.
- The model's original routing and expert-math rules, subject to explicit operation support.
- Resource and activation validation before reporting an accelerated model Ready.

These are not bit-identity claims. Different kernels, activation quantization, fusion, and reduction order can change numerical results. A changed numerical state can in turn change realized routing or generated tokens even when the routing algorithm itself has not been modified.

The engineering contribution is an integration of descriptor-driven placement, CPU-miss execution, guarded scheduling, monitoring, and auditable evaluation. It builds on upstream expert-cache machinery rather than claiming that machinery as a new invention. [12]

<!-- page -->
# 3. Dispatch, residency, and guarded execution

Descriptors matter because MoE layouts are not uniform. The tested families differ in expert counts, top-k selection, quantization, biases, and projection structure. Mistral also demonstrates that a fused gate/up tensor is not the same layout as three separate expert projections.

| Target family | Routed layout observed | Headline-series bank |
| --- | --- | --- |
| GPT-OSS-120B | 36 layers; 128 experts; top-4 | 10,240 MiB; trained residency seed |
| Qwen3.8-Flash-Next | 48 layers; 512 experts; top-10 | 8,192 MiB; empty causal bank |
| GLM-4.5-Air | 45 routed trunk layers; 128 experts; top-8 | 6,144 MiB; empty causal bank |
| Qwen3.6-35B-A3B | 40 layers; 256 experts; top-8 | 8,192 MiB; empty causal bank |

A trained residency seed is a list of initial expert placements, not a fine-tuning of model weights. Bound plans must match the target layout. Empty-causal modes start without a checkpoint-trained seed and admit weights from observed execution history. Residency persists between requests until unload/reload, including between repetitions in the reported screens.

The measured design uses CPU cold-expert execution, guarded overlap where eligible, direct-DMA admissions from immutable registered sources, optional gate/up projection fusion, and event-protected GPU-ID handoff. These features have costs: synchronization, transfers, bank space, and metadata are not free.

Direct registration retains a 64 GiB source cap and 24 GiB available-RAM headroom guard. Those are implementation safeguards, not proofs that the OS's availability estimate perfectly describes driver-pinned pages. Banks must also coexist with model backbone, KV, compute, and desktop allocations.

Budgets are configuration-specific. The paired GPT screen used 10,240 MiB; a later local profile uses 12,000 MiB. GLM's 8 GiB attempt failed at 16K, while 6 GiB ran. Recognizing a descriptor is necessary but not sufficient: the backend must support every required operation and confirm coverage and activation. [3-9]

<!-- page -->
# 4. Measurement protocol and controls

The four headline entries are separate technical screens, not one cross-model intelligence evaluation. Their common reported conditions are one request slot, actual 16,384-token context, 8 generation threads, 16 prompt threads, temperature zero, seed 42, prompt caching disabled, and three exact 512-output-token samples per profile.

EOS suppression forces the requested sample length. Consequently, these are not guaranteed 512-token natural answers. Reasoning tokens can be part of generated-token usage, and a visible final answer is not the entire timed output.
Reasoning/template settings are series-specific; they must be taken from each source record rather than assumed identical across models.

The wall decode-rate convention used by the screening helper is:

```text
decode_tok_s = 511 / (request_wall_seconds - prompt_seconds)
```

The numerator counts 511 intervals for a 512-token generation. Prompt time is backend-reported. Download and model-load time are excluded; remaining request transport and scheduling overhead are not subtracted. Request, first-token, and loading costs should be reviewed separately where retained. The metric is not an SSE-chunk count.

| Protocol element | Interpretation |
| --- | --- |
| Native base | Pinned llama.cpp 620d2225c |
| Experimental patches | Vary by series; per-run hashes are retained |
| Repetitions | Three per reported configuration block |
| Output count | Exactly 512 target tokens, checked against backend usage |
| Speculation / MTP | Not used for the headline table |
| Ordering | Sequential blocks, not randomized interleaving |
| Residency | Can warm across repetitions and answer checks |

Controls intentionally differ. GPT and Qwen3.6 use standard automatic placement. Qwen3.8 uses native CPU experts with a GPU backbone. GLM uses the fastest observed non-hybrid block median, rather than a slower alternative control. These are not interchangeable baselines and are not a Strata comparison.

Standard/native denotes the recorded execution profile on its measured build. It does not prove binary or numerical identity with an arbitrary upstream release. The source records and hashes, rather than a generic backend label, define the comparison. [3-8]

<!-- page -->
# 5. Reported technical throughput

The following medians are the four published headline screens. The gain column is rounded from the full-precision recorded medians, not recalculated from display-rounded rates.

<!-- figure: headline -->

Figure 3. Matched controls and accelerated profiles on the reported host. The control profile varies by row; the chart is not a comparison of model intelligence or response quality.

| Target and quantization | Control tok/s | Accelerated tok/s | Rounded gain |
| --- | --- | --- | --- |
| GPT-OSS-120B MXFP4 | 25.69 | 39.46 | 54% |
| Qwen3.8-Flash-Next IQ3_S | 25.39 | 43.88 | 73% |
| GLM-4.5-Air IQ4_XS | 12.67 | 17.28 | 36% |
| Qwen3.6-35B-A3B Q8_0 | 45.50 | 77.99 | 71% |

The target files and quantizations remain unchanged within each pair, and no selected expert is intentionally omitted. Source records retain exact medians, samples, profile settings, patch identifiers, checks, and limitations. The rows represent different native layouts and experimental revisions; they are not a universal default-setting promise. [4-8]

Qwen3.6 illustrates warm-up sensitivity: its hybrid samples are 73.47, 77.99, and 80.24 tok/s. Reporting the median does not erase the lower first sample or make the warmest sample the overall result.

> Throughput is not quality preservation. A faster profile still needs numerical and answer validation. These screens establish neither world-record performance nor the separate goal of sustained GPT-OSS-120B throughput above 60 tok/s across representative workloads.

<!-- page -->
# 6. Verification is a hierarchy, not one pass flag

SYNAPSE distinguishes configuration activation, complete generation, local numerical agreement, and model quality. Combining them into one success label would overstate the evidence.

| Evidence class | What it can establish | What it cannot establish |
| --- | --- | --- |
| Ready / activation markers | Requested context, coverage, transfer and pipeline configuration were confirmed | Reliable answers or native equivalence |
| Exact output-count screen | A complete technical sample with valid usage/timings | Natural-answer quality or sustained workload performance |
| Integer / AST checks | Compliance with specific small expected outputs | Broad reasoning or coding accuracy |
| Same-placement logits | Agreement between tested execution variants under that placement | Independent native-reference equivalence |
| Native-reference logits | Whether a candidate satisfies the fixed numerical limits against that reference | General factual accuracy by itself |
| Application CI | Lifecycle, packaging, UI logic and platform contracts | CUDA/model quality qualification on every platform |

The independent strict limits are maximum absolute logit error at most 0.01 and relative-L2 error at most 0.001. Teacher forcing aligns continuation tokens even when candidate argmax differs. Token/header checks prevent an unaligned comparison from being called a numerical test.

Some stock GPU and hybrid configurations fail strict CPU-reference diagnostics. An earlier structured numerical/JSON answer check also remains failed. Those failures do not by themselves prove that acceleration caused an incorrect answer, but they prevent a general native-equivalence or answer-quality-preservation claim.

Qwen3.6's six small checks pass. Separate descriptor-seeded base and optimized hybrid checks pass at 96 sampled full-vocabulary positions with zero error. GLM has passing same-placement checks and separate thinking-off diagnostics, but original default-thinking/format failures remain. Later Qwen canonical checks use explicitly different settings and do not qualify every headline configuration.

References, generated-code text, logits and activation captures require care. Model code is parsed, never executed by the quality predicates. Active captures can perturb scheduling/fusion and are diagnostic, not substitutes for observer-free qualification. Failed checks remain in the evidence ledger. [3,7-10]

<!-- page -->
# 7. Mistral exposes a real compatibility boundary

Mistral Small 4 is a useful stress case because native architecture recognition and tensor coverage do not imply that all required expert operations are executable on the selected GPU path.

The verified UD-IQ4_XS target has three shards, with a metadata-only first shard. Its 36 routed layers use 128 experts and top-4 selection. Fused gate/up tensors are IQ3_S; down tensors are IQ4_XS in 32 layers and Q6_K in four. The file's quantization label does not describe every component.

<!-- figure: precision -->

Figure 4. The protected down projection requires FP32 activation range. A valid optimization must preserve that requirement rather than merely bypassing a capability check.

The model graph requests FP32 source precision because down-projection activations may exceed FP16 range. The pinned CUDA expert-ID matmul originally rejects that setting. The installed hybrid path therefore stops instead of silently narrowing precision or reporting a fallback as acceleration.

The first isolated decomposition gathered/dequantized selected weights into FP32 and applied batched FP32 matmuls. It passed its targeted range/reference checks, but materialized 128 MiB of selected FP32 weights per decode position. It was not a consistent win against the native CPU primitive.

A subsequent standalone CUDA kernel combines block dequantization with FP32 dot products. It removes that global expanded-weight intermediate, uses small shared tiles, and passes targeted reference, routing, bounds, memory, and race checks. Those primitive results are promising but do not prove whole-model behavior.

The initial native controls measured 5.64 tok/s with automatic placement and 19.89 tok/s with CPU experts/GPU backbone. They belong to an earlier window, not the latest integrated table. Their substantial difference also warns against choosing an artificially weak baseline. [9,10]

<!-- page -->
# 8. Mistral integration: published as research only

The later isolated build protects precision from incompatible quantized fusions and adds a separate mode reproducing CPU Q8_K activation semantics with FP32 scales. This is different from the original unquantized-FP32 prototype. Selection is dtype/precision/shape-based rather than a model-name exception.

| Same isolated build, 16K / 8 and 16 threads | Median decode tok/s |
| --- | --- |
| Native CPU experts / GPU backbone; new flags off | 21.09 |
| Automatic placement; experimental kernels on | 23.96 |
| Empty-causal 8 GiB hybrid; experimental kernels on | 33.01 |

These are three-run, 512-token technical medians with temperature zero, seed 42 and model-default reasoning, not a natural-workload quality evaluation.

> **Research-only timings:** all three profiles fail the original strict coding predicate, and independent native-reference equivalence fails. Mistral is not added to the four-model headline table or default accelerated installation.

Twelve actual-weight primitive cases and padded/broadcast layouts pass their native-CPU primitive gates. Integrated memcheck reports zero errors; racecheck reports zero hazards/errors/warnings for the tested kernels. Frozen and adaptive optimized-versus-base hybrid comparisons each pass at 96 sampled positions with zero error and both expert backends exercised.

The unchanged SYNAPSE zipapp also loads the prototype through a temporary profile, confirms 16K/8/16/8192 MiB, returns the exact integer answer, and completes a 128-token API smoke. That smoke is not a published throughput sample. The latest 512-token screen retains 109,575 CPU plus 115,093 GPU contributions, equal to four per 56,167 dispatches.

Independent native checks still fail at the original limits. Captures can match while unobserved runs differ. A short CPU-empty control matches with global CUDA fusion disabled, but disabling graphs or only router fusion does not resolve the general case; mixed CPU/GPU checks also fail with global fusion disabled.

Small first-layer expert differences can coexist with substantial final-logit differences. The evidence does not establish one sole numerical cause or broad quality preservation. A temporary restoration OOM was retained and recovered; later probes use a non-CUDA parent to restore the original model only after the CUDA worker exits.

The publication decision is deliberate: expose the failure boundary and research measurements, not a production-compatible or native-equivalent success claim. [9,10,16]

<!-- page -->
# 9. RAM and disk: optimize the path, not the pie

Low pressure-based RAM readings can coexist with a large resident model. Linux `MemAvailable` estimates availability, including reclaimable pages; it is not a count of physically unoccupied RAM.

<!-- figure: memory -->

Figure 5. Occupancy, cache, shared pages and process RSS overlap. They are not additive slices of independent memory allocations.

| Counter | Interpretation |
| --- | --- |
| Physical occupancy | Total minus free pages, where the OS provides that distinction |
| Pressure estimate | Total minus OS-reported available memory |
| File cache/buffers | Linux cache/buffers excluding Shmem in the refined sampler |
| Backend RSS | Process residency; overlaps physical occupancy and mapped file cache |
| Shared/driver-mapped RSS | Separately reported on Linux; not automatically private anonymous RAM |

GLM mapped native and hybrid execution already had roughly 54 GiB of backend RSS. Warm samples read zero new bytes from disk. Copying native weights into RAM measured 11.43 versus 11.30 tok/s for the mapped CPU-expert control, not a useful established win over the faster stock or hybrid profiles.

A different upload-on-miss path behaved differently. The upstream 10 GiB LRU cache measured 17.31 tok/s with mapped loading and 29.36 with copied CUDA-host buffers. Corresponding outputs and final cache counters matched. Both modes already had roughly 58-59 GiB RSS; the buffer/transfer path, not simply resident capacity, changed. [7,11]

Later Qwen3.6 and Mistral targets were staged on NVMe. Inactive files were archived with checksums; a 64 GiB tmpfs was not used because it consumes the same host RAM needed for residency and pinned transfers. Warm-cache decode findings do not establish cold-start, storage-tiering, or RAM-disk gains.

Pinned pages can make OS availability optimistic. A fuller RAM chart is not an inference optimization, and logical selected bytes per token are not a measured physical bandwidth counter. [14]

<!-- page -->
# 10. Product and operational boundary

The local application is intentionally separate from native backend experimentation. It uses Python's standard library and browser assets without a frontend build dependency. Chat, model controls, monitoring and an OpenAI-compatible API share one local service.

| Surface | Scope |
| --- | --- |
| Standard execution | Appropriate separately installed native backend; application targets Linux, Windows and macOS |
| Custom hybrid engine | Experimental Linux/NVIDIA path with compatible pinned source/plugin/profile |
| GPU monitoring | NVIDIA NVML where available; unsupported sensors remain unavailable rather than zero |
| Monitor history | Bounded in-memory samples; CPU/RAM/I/O semantics are OS-specific |
| Updates | Managed app update workflow, not automatic replacement of models, backends or profiles |

The monitor includes backend-reported speed, CPU/GPU load, VRAM, GPU temperature and power, PCIe throughput, backend read I/O, RAM and context fill. GPU counters are device-wide. CPU busy waiting is not necessarily productive work; slot occupancy is not a physical KV-byte measurement.

Ready/activation-verified means the requested configuration was observed, not that independent model quality passed. Failures remain visible. A selected hybrid configuration is not silently renamed accelerated after CPU-only fallback.

The API is local-only and has no application authentication. Do not expose it through a tunnel or reverse proxy. Model browsing is a bounded convenience around existing filesystem permissions, not a sandbox. Backend installation and update checks are network operations distinct from local inference.

Update checks query fixed-repository release metadata, not prompts or weights. Managed updates verify downloaded artifacts and use guarded replacement/restart behavior; checksums establish integrity, not a separate publisher signature. Source/pip installations are not silently overwritten.

At this evidence snapshot, the app is a release candidate/main-branch preview rather than a tagged, quality-qualified inference release. Models and native backends retain their own licensing and support requirements. [14-16]

<!-- page -->
# 11. Threats to validity and limits of inference

| Threat | Consequence |
| --- | --- |
| Three samples per block | Insufficient basis for strong significance or confidence-interval claims |
| Sequential ordering | Clock, thermal, desktop and residency state can vary between profiles |
| Repeated fixed prompt | Causal cache warm-up is part of the screen, not broad unseen-workload coverage |
| Forced output length | A valid 512-token technical sample need not be a natural completed answer |
| Different controls | Speedup percentages cannot be combined as one universal backend multiplier |
| Patch/profile evolution | Same native base does not imply identical experimental builds |
| Numerical sensitivity | Unchanged weights/routing rules do not prove identical realized results |
| Single hardware host | No cross-hardware performance ceiling or general portability result |

Small integer and AST predicates are deliberately strict. A failure may involve format, token budget, mathematical content, or a combination; it should not be simplified into a general intelligence score. Passing them is also not a comprehensive factual, reasoning or coding evaluation.

Teacher-forced native-reference failures remain important even when same-placement variants agree. Conversely, failure to meet a strict logit tolerance does not, by itself, identify a particular wrong answer or prove that acceleration caused one. The appropriate response is attribution and qualification, not erasing a failed gate.

Active captures, callbacks and synchronization diagnostics can change the execution they observe. Their role is to localize differences; observer-free tests remain necessary. Logical contribution counts verify coverage of routed selections but do not prove every intermediate arithmetic value is reference-equivalent.

Resource sensors have scope and availability limits. A high utilization graph, greater physical occupancy, zero warm disk reads, or fewer CPU calls does not establish optimal inference. No driver/governor tuning, hardware ceiling, energy-efficiency leadership, or comparison with every competing engine is claimed.

Application CI is not a model-quality benchmark. Cross-platform lifecycle, UI and packaging passes do not qualify the custom CUDA path on Windows/macOS or validate AMD/Metal GPU monitoring. [3,9,14]

<!-- page -->
# 12. Related work and engineering agenda

The pinned base already includes llama.cpp's host-expert GPU cache, introduced in ggml-org/llama.cpp#29887 and followed by multi-GPU cache work. The upstream LRU policy uploads selected misses for GPU execution. SYNAPSE extends that machinery with CPU cold-expert execution and guarded causal admissions; it does not claim the upstream cache as its own invention. [1,12]

The PR's advertised 67.8 tok/s uses a different Qwen quantization, a 32GB RTX 5090 and a roughly 19 GiB cache. It is not a result for the reported 16GB-class machine and is not an additional multiplier on the four-model table.

Strata is a direct practical inspiration for heterogeneous inference and integrated monitoring. SYNAPSE does not bundle Strata, claim affiliation or feature parity, or present a matched Strata comparison. Inspiration and comparative evidence are different statements. [13]

The engineering agenda is qualification-led:

1. **Resolve numerical attribution.** Trace independent native differences without relying on observer-induced passes, including activation quantization, fusion, routing and reduction behavior.
2. **Broaden quality evidence.** Use representative held-out tasks and natural completions; retain formatting/content/budget failures rather than replacing them with easier questions.
3. **Charge placement costs honestly.** Measure admission reuse, transfers, CPU kernels, synchronization and actual VRAM/scratch use. More GPU work can still be slower.
4. **Improve capability and fit planning.** Tensor-layout detection must be followed by operation-level precision/support checks and actual resource validation.
5. **Expand portability deliberately.** Standard application portability is not a substitute for new backend kernels, GPU sensors or multi-GPU hybrid qualification.

The separate GPT-OSS-120B sustained cross-workload 60 tok/s milestone remains unmet. Smaller-model throughput, a single fast prose segment, draft proposals, or a primitive latency ratio does not satisfy it.

This paper therefore presents an auditable engineering direction and a bounded set of measurements, not a completed proof of universal model-agnostic optimality.

<!-- page -->
# 13. Reproducibility, provenance and review

Reproduction starts with the exact target artifact, profile and native/plugin build, not just a model-family name. The reviewed JSON records contain per-series source/patch identifiers, exact samples and retained limitations; model revisions and shard hashes are recorded where available.

| Review item | Required discipline |
| --- | --- |
| Source | Pinned native base plus the recorded experimental patch revision |
| Artifact | Same GGUF/quantization and complete shard set; verify recorded hashes |
| Runtime | Actual context, thread counts, fit policy, bank size and activation markers |
| State | Explicit reload/seed policy and residency history |
| Timing | Complete output count, prompt/decode separation, load and request costs |
| Qualification | Failed as well as passing numerical and answer checks |

The application baseline is SYNAPSE e601f93; the reviewed evidence snapshot is unified-memory-scheduler 934bbbf. The native base is 620d2225c. Per-series patch hashes differ, and the experimental Mistral addition is separate from the default installer pin. The source bundle accompanying this PDF records full identifiers and source digests.

The document can be rebuilt offline from its Markdown source, evidence snapshot and ReportLab renderer. Figures are vector graphics, text is searchable, and references are clickable. No raw model weights, token-ID references, logits, activation arrays or local-user paths are included.

## Working glossary

**Resident bank:** GPU storage for selected expert components. **Cold expert:** a selected expert not resident in that bank. **Causal admission:** a placement update based on observations already available. **Trained seed:** an initial residency plan, not a model-weight update. **Same placement:** a comparison holding the relevant expert residency fixed. **Native reference:** the independently selected recorded execution used for a numerical comparison.

**Compatibility:** ability to execute the stated configuration. **Qualification:** evidence sufficient for a particular numerical or quality claim. **Logical bytes:** accounting derived from selected tensors, not measured physical traffic. **Release candidate:** an application-distribution status, not certification of every experimental model path.

> Reviewers should be able to trace each number to its source and each claim to its scope. A retained failure is evidence, not an editorial inconvenience.

<!-- page -->
# References and evidence access

[1] llama.cpp project and native backend. [Project repository](https://github.com/ggml-org/llama.cpp).

[2] Pinned native base, commit 620d2225cc436ab0b001e3200e590e3b286ef9ab. [Immutable source](https://github.com/ggml-org/llama.cpp/tree/620d2225cc436ab0b001e3200e590e3b286ef9ab).

[3] Reviewed benchmark ledger, evidence snapshot 934bbbf. [Methods, conditions and failures](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf/benchmarks/RESULTS.md).

[4] GPT-OSS-120B and standard-fallback downloaded-model matrix. [Three-by-512 technical evidence](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf/benchmarks/results/20261016-downloaded-model-matrix.json).

[5] Qwen3.8 native-versus-causal screen and cold-work experiments. [Reviewed summary](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf/benchmarks/results/moe-cold-work-and-qwen38-summary.json).

[6] Screening helper and wall decode-rate definition. [Execution-sweep implementation](https://github.com/appatalks/unified-memory-scheduler/blob/934bbbf/tools/benchmark/vrambridge-execution-sweep.py).

[7] GLM-4.5-Air IQ4_XS measurements and RAM controls. [Reviewed evidence](https://github.com/appatalks/Synapse/blob/e601f93/docs/benchmarks/glm45-air-iq4-xs.json).

[8] Qwen3.6 Q8_0 matched profiles and numerical gates. [Reviewed evidence](https://github.com/appatalks/Synapse/blob/e601f93/docs/benchmarks/qwen36-q8.json).

[9] Mistral native integration, failed native gates, research timings and app proof. [Experimental evidence](https://github.com/appatalks/Synapse/blob/e601f93/docs/benchmarks/mistral4-native-experimental.json).

[10] Mistral standalone FP32-safe fused-kernel study. [Primitive evidence](https://github.com/appatalks/Synapse/blob/e601f93/docs/benchmarks/mistral4-fused-fp32.json).

[11] Upstream-cache policy and copied-versus-mapped loading controls. [Local investigation](https://github.com/appatalks/Synapse/blob/e601f93/docs/benchmarks/upstream-pr29887-gpt120b.json).

[12] ggml-org/llama.cpp#29887, host-expert GPU cache; merged 7 October 2026. [Upstream pull request](https://github.com/ggml-org/llama.cpp/pull/29887).

[13] Strata, credited as direct practical inspiration; not a matched comparator. [Project repository](https://github.com/Niko1221/Strata).

[14] SYNAPSE monitoring semantics and sensor limitations. [Monitoring documentation](https://github.com/appatalks/Synapse/blob/e601f93/docs/monitoring.md).

[15] SYNAPSE installation and update boundaries. [Installation documentation](https://github.com/appatalks/Synapse/blob/e601f93/docs/installing.md).

[16] Tested compatibility and qualification status at the application baseline. [Compatibility matrix](https://github.com/appatalks/Synapse/blob/e601f93/docs/compatibility.md).

Project-reported results should be independently reproduced before stronger deployment or quality claims are made. Project code, native backends and model artifacts retain their respective licenses. No model weights are distributed with this paper.
