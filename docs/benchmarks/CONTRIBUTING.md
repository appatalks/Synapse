# Contributing benchmark results

We welcome new models, different hardware, Standard-only results, hybrid
comparisons, slower results and explicit failures. You do not need to demonstrate
a speedup. Please submit measurements through a **pull request**, not screenshots
or estimated token rates alone.

## Submit a PR

1. Fork SYNAPSE and create a branch for your benchmark.
2. Copy [TEMPLATE.md](TEMPLATE.md) to
   `<family>/<model>-<quant>-<setup>-<date>.md` inside this benchmark folder.
   Reuse a family folder or create one when needed.
3. Fill in the report and add a similarly named, sanitized JSON measurement
   record or small text log. Link the evidence from the report.
4. Update [README.md](README.md): use one row per model/quantization in your setup's table,
   or add **one new heading and table** if that physical setup is not listed.
   Keep the index brief; settings, all samples and explanations belong in
   the report. Label differing contexts, threads, methods and backend builds.
5. Open a [pull request](https://github.com/appatalks/Synapse/compare) from your
   fork/branch. Include the setup, model, measured execution path, and whether
   checks passed, failed or were not run. Maintainers will review the evidence.

Keep the best observed configuration's block median in the index, not a
single-run peak. If Standard is faster, say so and retain the best measured
hybrid result as a slowdown. Do not promote an isolated prototype that fails
qualification as the best installed configuration.

Do not overwrite previous evidence from another date, backend, quantization
or setup. Update the model's index row when appropriate, but preserve all
older, slower and failed configurations in linked reports.
Do not commit model weights, private profiles, API keys, usernames/hostnames,
absolute personal paths, private prompts or unreviewed generated answers.
Keep the actual numbers; replace identifying path prefixes with `/models/`
or another neutral placeholder.

## Preferred common screen

This is a comparison protocol, not a required everyday chat preset:

- Use SYNAPSE with an identified backend build. Record the app commit/version,
  backend commit, patch or binary hashes, OS, driver and CUDA/Metal/ROCm details.
- Use the **exact same GGUF bytes** in both modes. Record repository, immutable
  revision, all filenames/shards, byte sizes and SHA256s. State the model license.
- Use one slot, actual **16,384-token context**, **8 generation / 16 prompt
  threads**, FP16 attention cache, temperature zero, seed 42, low reasoning
  effort, prompt caching off, no draft/speculation and forced **512 output
  tokens**, including reasoning. Record whether effort is honored by the model.
- If those settings cannot run on your hardware, report the settings that did
  run and clearly label the difference. Do not silently reduce context after
  a failed attempt or put unlike protocols in one gain calculation.
- Run **three repetitions per configuration**. Retain all samples, not just
  the warmest. Record load/request/prompt/first-streamed-text times separately.
- For a hybrid comparison, prefer **Standard before → Hybrid → Standard after**
  using the same patched executable and matching libraries. Record actual
  placement, cache size, transfer policy, trained versus empty-causal seed,
  pipeline settings, fit behavior and verified routed-layer coverage.
- Verify actual context and activation from backend output. Choosing Automatic
  or seeing a metadata candidate is not proof that hybrid ran.
- State whether residency resets per request, persists across repetitions or
  resets on reload. Preserve cold-start samples and allocation failures.

The exact throughput prompt, streamed request and measurement helper are in
[the shared protocol](model-guide.md#how-the-baselines-are-measured). Decode
rate is `511 / (request wall seconds - backend prompt_ms / 1000)` for exact
512-token requests. Retain final token counts and timings so this can be checked.

Do not substitute the backend's decode counter, end-to-end request rate or
`llama-bench` synthetic rate without labeling that different metric. Such
results are welcome, but must not be presented as the common request screen.

## Evidence and checks

Your JSON/log should retain, for each repetition:

- Configuration name, requested and actual context, threads and execution path.
- Completion token count, backend `predicted_n`, `prompt_ms`, request wall
  seconds, computed decode tok/s and first-streamed-text time if available.
- The median derived from those samples, and every failure/error encountered.
- Activation/coverage evidence for hybrid; unavailable fields marked as such.

Use the [report template](TEMPLATE.md) for the report's structure. Existing
[Qwen](qwen/qwen3-coder30b-q4-km-hybrid.json) and
[GLM](glm/glm47-flash-q4-km-hybrid.json) records are examples, not a requirement
to copy their entire structure or claim their qualification level.

For gains, use unrounded medians:
`100 * (hybrid median / control median - 1)`. Identify the exact control;
if several matched control blocks exist, use the fastest block median.
Identify a nonstandard control explicitly (for example, upstream LRU/copied
loading rather than ordinary automatic placement).
Only compare identical workloads, token counts, contexts, threads and weights.
List different-build comparisons explicitly; do not attribute them to one flag.

Report the exact-integer and AST-only checks from the shared protocol if run.
Keep failed/truncated/format-limited checks as failures. Never execute generated
code for these checks. Mark unrun checks **not tested**, not pass.
Record output-hash agreement if measured; hashes alone cannot prove numerical
equivalence or explain a different answer.

Distinguish metadata eligibility, successful load/activation, narrow answers,
independent native-reference checks and broad quality evaluation. None implies
the next. A compatibility claim is limited to the tested file/build/settings.
Hardware snapshots are not peak or minimum memory requirements.

## Before opening the PR

- [ ] All measurements are real and every claimed hybrid run was verified.
- [ ] Source revisions, model hashes, hardware and actual settings are recorded.
- [ ] Individual samples, medians, failures and check results are included.
- [ ] Index values match the report; gains use a named, matched control.
- [ ] Unmeasured values are `—` in the index and `null`/explicitly unavailable
      in records, not invented zero rates.
- [ ] No weights, credentials, private profiles or identifying logs are included.
- [ ] Local Markdown links resolve and `git diff --check` passes.
