# GPT-OSS-20B: hybrid runs, but Standard is faster here

The explicit hybrid follow-up successfully activated GPT-OSS-20B MXFP4 at
8 GiB and 10 GiB causal cache budgets. **Both were slower than all three fresh
Standard controls, including a same-build control.** This is a retained negative performance result, not a
new acceleration claim.

[Complete numeric evidence](gpt-oss20b-hybrid-screen.json) includes every
sample, activation logs, checks, output hashes, binary identities and settings.
The [earlier 199.92 tok/s Standard baseline](gpt-oss20b-mxfp4.json) remains
unchanged; it is not used as this experiment's control.

## Fresh matched screen

Ryzen 9 9950X, RTX 5070 Ti 16GB, 123.48 GiB usable RAM. Same unchanged,
SHA256-reverified GPT-OSS-20B MXFP4 file, actual 16,384-token context,
8 generation / 16 prompt threads, FP16 attention cache and one slot.
Each row is one fresh load followed by three exact 512-token samples.

Measured order: Standard before, hybrid 8 GiB, hybrid 10 GiB, Standard after.
A separate final Standard control then used the patched hybrid executable
and its explicitly selected matching CUDA plugin.

| Configuration | Three-sample decode median | Change vs fastest Standard block | Exact integer / AST checks |
| --- | ---: | ---: | --- |
| Standard automatic placement, before | 207.08 tok/s | Control | Pass / pass |
| Require hybrid, 8,192 MiB causal bank | 143.19 tok/s | **-30.9%** | Pass / pass |
| Require hybrid, 10,240 MiB causal bank | 143.99 tok/s | **-30.5%** | Pass / pass |
| Standard automatic placement, after | 203.75 tok/s | Second control | Pass / pass |
| Standard placement, same patched build/plugin | 207.00 tok/s | Same-build control | Pass / pass |

Changes use the fastest block median, 207.08301039018025 tok/s, not the
warmest individual sample or the older baseline. Both hybrid medians also
trail the slower 203.75 tok/s control and the 207.00 tok/s same-build control.
Sequential bracketing is not randomized
statistical significance or an exhaustive cache/thread search.

Each causal bank starts **empty**, with residency retained across repetitions:

- 8 GiB: **122.59, 143.19, 150.43 tok/s**.
- 10 GiB: **121.52, 143.99, 151.91 tok/s**.

The progression is retained, not replaced by the warmest run. Even the highest
observed hybrid sample was slower than every Standard sample in this screen.
The small difference between the two hybrid medians does not establish a
meaningful cache-size win.

## What actually activated

Both hybrid loads reached activation-verified Ready with:

- Complete **24/24 routed-layer coverage**.
- An untrained causal plan, not GPT-OSS-120B's bound trained seed.
- Direct asynchronous admissions from **10,179,084,288 registered immutable
  source bytes**, with the native registration cap/headroom checks intact.
- Configured decode pipeline and event-protected GPU IDs; guarded overlap,
  gate/up fusion and protected-ID markers were observed after requests.
- Fitting, host-operation offload and repacking disabled; no draft/speculation.

The log's zero initially selected experts denotes an empty residency seed,
not intentionally omitting routed expert contributions.

Standard used native automatic placement with a 1,024 MiB reserve and no
explicit expert cache. The Standard and hybrid executables report the same
pinned llama.cpp source revision, but are **different binaries/toolchains**:
Standard reports GNU 13.3.0; the patched hybrid build reports GNU 14.2.0.
Their hashes and reported versions are retained. This compares the installed
execution paths. The separate fifth row removes that binary/toolchain
difference by using the hybrid executable and matching CUDA plugin in Standard
mode, again without an expert cache. Hybrid was still about **30.8% / 30.4%
slower** than that same-build control at 8/10 GiB, respectively. This does not
isolate individual scheduling, placement or kernel costs.

Temperature zero, seed 42, reasoning effort low, no prompt caching, and EOS
ignored match the [baseline protocol](../model-guide.md#how-the-baselines-are-measured).
Decode rate is `511 / (request wall seconds - prompt_ms / 1000)`.
Loading and registration are excluded; request, load and first-text times
remain separate. Median time to first streamed text was about **72 / 729 /
720 / 74 / 72 ms** in table order. These short-prompt times include reasoning text.

## Checks and qualification limits

All ten narrow answer checks passed: exact `323` and the unchanged AST-only
`clamp` predicate for each of five configurations. Generated Python was parsed,
never executed. These do not qualify general coding, reasoning or factual
quality.

The nine Standard throughput text hashes match across all three control blocks.
Hybrid hashes vary across repetitions, and **none match the Standard hash**.
Those differences do not alone demonstrate an incorrect answer, but they
prevent any claim of identical generated output.

**No independent native-reference logit comparison was run in this screen.**
Activation verification and passing narrow answers do not establish numerical
equivalence or broad quality. Earlier experimental qualification limits remain.

GPU memory snapshots after requests were 12,658 / 11,180 / 12,713 / 12,648 MiB
for the first four rows, including desktop use. They are not peaks or minimum fit
requirements. The smaller bank's lower snapshot is a resource tradeoff, not
a speed win; its direct-transfer path also registers host memory.

## Other new models: explicit rejection, not hidden fallback

Require hybrid was also actually requested for the three other new GGUFs:

| Model | Outcome | Evidence |
| --- | --- | --- |
| LFM2.5-1.2B-Instruct Q4_K_M | HTTP 400 before a backend started: no complete routed-MoE descriptor | [Attempt record](../lfm/lfm25-12b-q4-km-hybrid-attempt.json) |
| Qwen3-4B Q4_K_M | HTTP 400 before a backend started: no complete routed-MoE descriptor | [Attempt record](../qwen/qwen3-4b-q4-km-hybrid-attempt.json) |
| Qwen3.8-27B UD-Q4_K_M | HTTP 400 before a backend started: no complete routed-MoE descriptor | [Attempt record](../qwen/qwen38-27b-ud-q4-km-hybrid-attempt.json) |

No fallback generation was relabeled Hybrid, and no throughput was fabricated
for rejected loads. These files retain their earlier Standard baselines.
Qwen3.8-27B is dense, not the Flash-Next MoE; LFM's convolution/attention
"hybrid" architecture is unrelated to expert dispatch.

## Reproduce and interpret

Use the pinned GGUF linked in the earlier baseline, a compatible installed
generic hybrid engine, and the measured 16K context with 8/16 threads.
In Model Controls:

1. Select **Standard backend (manual settings)** and set the matched context,
   threads, automatic placement, zero expert cache, and FP16 attention cache.
   Run the three-request baseline protocol and two checks.
2. Unload, select **Require hybrid expert dispatch**, and set the causal bank
   to **8192 MiB**. Confirm actual context, layer coverage and direct-transfer
   activation, then repeat the same requests/checks.
3. Unload and repeat with **10240 MiB**, then repeat the Standard control.
4. For the same-build control, run Standard using the patched executable and
   explicitly select its matching CUDA plugin. For example, start a separate
   app with the placeholders below and repeat the Standard 16K/8/16 settings:

   ```bash
   GGML_BACKEND_PATH=/path/to/matching/libggml-cuda.so \
     python -m synapse_app --llama-server /path/to/patched/llama-server \
     --execution-mode standard --port 0 --no-update-check
   ```

The measured installation had direct generic transfers, decode pipeline and
protected GPU IDs enabled. Manual causal budgets do not edit installation
defaults or the bound GPT-OSS-120B plan. All benchmark-owned processes were
stopped afterward and the installation profile hash was unchanged.

**Use Standard for this GPT-OSS-20B configuration on the measured host.**
Automatic already prefers native fitting for this small-file case. That is
consistent with this result, not proof that the heuristic or any budget is
optimal on other hardware, contexts, prompts or model quantizations.
