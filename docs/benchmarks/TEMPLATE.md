# MODEL / QUANTIZATION — SETUP — DATE

Copy this file into the appropriate model-family folder. Replace every
placeholder, remove these instructions, and mark unmeasured fields **not
tested/unavailable**. Do not copy another setup's numbers.
See [contribution instructions](CONTRIBUTING.md) before submitting a PR.

## Outcome

- What ran: Standard / verified Hybrid / rejected / failed.
- Observed result and scope: speedup, slowdown, baseline only or no generation.
- Evidence: link the companion JSON/log using a relative path.
- UTC measurement date and optional contributor GitHub handle:

## Hardware and software

- CPU model, physical/logical cores, affinity/thread limits:
- GPU model(s), count, total/free VRAM before the run; or CPU-only:
- Installed/usable RAM, available RAM before the run, swap:
- OS/version, driver, CUDA/Metal/ROCm version where applicable:
- Storage medium/filesystem for weights; cold/warm loading conditions:
- Other CPU/GPU workloads during measurements:
- SYNAPSE version and Git commit; note uncommitted changes:
- Backend revision/build/compiler and patch/binary/library hashes:
- Same backend executable and libraries across controls and hybrid: yes/no;
  explain any differences:

## Exact model identity

- Publisher/model repository and model license:
- GGUF repository and immutable revision:
- Every shard filename, byte size and verified SHA256:
- Quantization, GGUF architecture and important tensor/layout distinctions:
- Expert count/top-k/routed-layer coverage if relevant:

Do not infer a publisher/checkpoint identity from a local filename alone.

## Protocol and configurations

- Exact throughput prompt and any system/template settings:
- Actual context, slot count, generation/prompt threads, KV precision:
- Temperature, seed, output cap, forced EOS behavior and reasoning settings:
- Prompt caching, draft/MTP/speculation and concurrent request settings:
- Each mode's exact sanitized launch command/API payload:
- Control placement, fit margin and host-operation settings:
- Hybrid cache budget, transfer policy, plan initialization/binding,
  pipeline flags and capability/coverage/context verification:
- Repetition count, measured order and warm-up policy:
- Residency lifetime across requests/repetitions/reloads:
- Timing metric/formula, units, included/excluded overhead:

For the common screen, use the exact prompt and parameters from the
contribution instructions. Clearly label any deviation.

## Results

Use one row per measured configuration/block; add rows as needed. Do not put
Automatic/native fallback measurements in the Hybrid column of the index.

| Configuration / measured order | Individual decode samples, tok/s | Median tok/s | Check status / failure |
| --- | --- | --- | --- |
| Standard control before | NOT MEASURED | NOT MEASURED | NOT TESTED |
| Hybrid, CACHE MiB | NOT MEASURED | NOT MEASURED | NOT TESTED |
| Standard control after | NOT MEASURED | NOT MEASURED | NOT TESTED |

- Gain/slowdown and named control block, computed from unrounded medians:
- Load, prompt, request and first-streamed-text times:
- Resource observations and whether they are snapshots or measured peaks:
- Full failures/rejections, partial runs and retries:

If loading failed, include the error and do not publish a throughput value.
Keep the failed configuration even if a later cache/context change succeeds.

## Verification and limits

- Actual hybrid activation / routed-layer coverage: verified / failed /
  not applicable, with evidence:
- Exact-integer check: pass / fail / not tested; prompt, token budget and
  termination reason:
- AST-only code check: pass / fail / not tested; no generated code executed:
- Repeated output hashes within modes and between controls/hybrid, if measured:
- Independent native-reference numerical checks: exact method/thresholds and
  result, or **not tested**:
- Broader workload/quality evaluation: describe it, or **not tested**:
- Known failures, output differences, confounders and untested conditions:

A successful load or narrow answer check does not establish equivalent logits,
general answer quality, universal fit or a speedup on other hardware.

## Reproduce and index

Provide exact sanitized steps to repeat the run. State whether installed
defaults were changed and whether benchmark-owned processes were stopped.

In the benchmark index, reuse the existing setup's table or add one new setup
heading/table. Keep one row per model/quantization using the best observed
configuration's block median, not a single-run peak. Preserve every other
configuration in this report and label a faster Standard path as such.
Use these columns and replace placeholders with measured values
or `—`. Link the model name to **this copied report**, not the template:

```markdown
## CPU + GPU(s) + RAM

OS/backend; context; generation/prompt threads; measurement method.

| Model / quantization | Control tok/s | Hybrid tok/s | Hybrid cache MiB | Change | Conditions / checks |
| --- | ---: | ---: | ---: | ---: | --- |
| [MODEL QUANT](family/report.md) | — | — | — | — | Measured path; checks and limits |
```
