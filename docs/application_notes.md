# Application notes

[Back to SYNAPSE](../README.md).

## Runtime requirements and local data

No account, hosted inference or model uploads. Chats stay in the page.
The app needs only Python and a browser; models and an appropriate
[llama.cpp backend](https://github.com/ggml-org/llama.cpp) are separate.
The reference backend revision is b11669.
[Platform and sensor limits](monitoring.md).

## Auto Tune

**Auto Tune** in Model Controls measures near-capacity input on your system and
applies a passing configuration, then offers copyable VS Code/OpenAI-client limits.
Balanced daily use tests up to 32K; Maximum Context can test up to the model limit
or 256K and take an hour or more. Experimental hybrid trials require a separate
opt-in. Tuning temporarily owns the model; cancellation restores the previous
configuration when possible. It tests input capacity and short anchor-retrieval
replies, not general answer quality or an exhaustive speed search.

[Tuning scope, saved results and client settings](installing.md#auto-tune) ·
[Optional Q8 attention cache](installing.md#optional-q8-attention-cache).

## Updates without reinstalling

Click the **version in the sidebar**. It lights up when a newer compatible
public release is found. Managed installs can download a verified update and
restart after your confirmation. Models, backends and local profiles are not
replaced. Source/pip installs get release information, not overwritten files.

Update checks contact GitHub for release metadata only, never prompts or
hardware data. Use `--no-update-check` to disable automatic checks.
Checksums verify the downloaded artifact's integrity; they are not a separate
publisher signature. [Installation and update details](installing.md).

## Benchmark interpretation and experimental compatibility

The [README performance table](../README.md#why-use-it) contains matched
three-run, 512-token technical-screen medians at 16K context, not universal
speed or quality guarantees. The monitoring screenshot illustrates the UI,
not a separate benchmark result.

Later GPT tuning reached a separate 50.06 tok/s technical median, but that is
**not** the matched comparison in the README or a sustained cross-workload
60 tok/s result.

Not every MoE is hybrid-compatible: the
[Mistral Small 4 study](benchmarks/mistral4-compatibility.md) records its FP32
operation requirement and unpromoted prototype. Its
[isolated native integration and research timings](benchmarks/mistral4-native-experimental.md)
are experimental only: strict native equivalence still fails, so it is not
included in the README's headline performance table.

[Detailed compatibility status and evidence](compatibility.md).

## Engine lineage

The engine builds on llama.cpp's upstream expert-cache machinery, including
[ggml-org/llama.cpp#29887](https://github.com/ggml-org/llama.cpp/pull/29887),
already included in our pinned backend. That cache uploads misses for GPU
execution; SYNAPSE's experimental hybrid dispatcher extends the tensor/slot
machinery with CPU cold-expert execution and guarded causal admissions.
The PR's published speedups are not an additional multiplier on SYNAPSE's results.
[Local upstream-cache investigation and the pinned-host-loading result](benchmarks/upstream-pr29887.md).

The experiments, native patches, benchmark methodology and full history live in
[unified-memory-scheduler](https://github.com/appatalks/unified-memory-scheduler).

## Local-only API

The API has no app authentication. Do not expose it through a tunnel or reverse
proxy. No universal speedup, fit guarantee or quality qualification is implied.

[Installation](installing.md) · [Monitoring](monitoring.md) ·
[Development](releasing.md) · [MIT license](../LICENSE).
