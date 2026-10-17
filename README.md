# SYNAPSE

**Run larger local models. Get more from the hardware you already own.**

SYNAPSE brings local chat, model controls, hardware monitoring and an
OpenAI-compatible API into one small app. Its optional experimental MoE engine
keeps frequently used experts on the GPU and executes cold experts on the CPU,
instead of forcing every operation through the same placement strategy.

## Why use it?

Our research has demonstrated substantially faster generation on two
larger-than-VRAM models, **without changing target weights or skipping selected experts**:

| Model | Matched control | Accelerated | Gain |
| --- | ---: | ---: | ---: |
| GPT-OSS-120B MXFP4 | 25.69 tok/s | **39.46 tok/s** | **54%** |
| Qwen3.8-Flash-Next IQ3_S | 25.39 tok/s | **43.88 tok/s** | **73%** |

These are **three-run, 512-token technical-screen medians at 16K context** on a
Ryzen 9 9950X, RTX 5070 Ti 16GB and 123.48 GiB usable RAM, with 8 generation /
16 prompt threads. GPT's control uses standard automatic placement; Qwen's uses
native CPU experts with a GPU backbone. They are different controls, not a
Strata comparison. [Conditions and retained failures](https://github.com/appatalks/unified-memory-scheduler/blob/main/benchmarks/RESULTS.md).

The gains belong to the **optional Linux/NVIDIA research backend**, not the UI
or standard llama.cpp mode. They are not promises for every model or machine.
Strict diagnostics and an answer-quality check remain failed. Later GPT tuning
reached a separate 50.06 tok/s technical median, but that is **not** the matched
comparison above or a sustained cross-workload 60 tok/s result.

> **Release candidate. Experimental acceleration is not quality-qualified.**
> Standard execution remains available. Check important model answers independently.

## Install in one line

On **Linux or macOS**, with Python 3.10+ and curl:

```bash
curl -fsSL https://raw.githubusercontent.com/appatalks/synapse/main/install.sh | bash -s -- --launch
```

This installs per-user, without sudo, and opens the app. On Linux it offers
experimental NVIDIA acceleration; an existing compatible research profile can
be reused. Building that backend requires Git, CMake, a C++ compiler and the
CUDA toolkit. **Drivers, toolkits and model weights are never installed automatically.**
macOS uses a separately installed llama.cpp CPU/Metal backend.

The installer prefers a checksummed public release. Until the first release is
published, it explicitly installs a **main-branch preview**. Prefer to inspect
scripts before running them? [Download and review `install.sh`](install.sh) first.

Already have a backend? Add `--llama-server /path/to/llama-server` to the
installer arguments. Skip the acceleration offer with `--no-accelerated`;
request it non-interactively with `--accelerated`.

**Windows:** download `SYNAPSE.pyz` from [Releases](https://github.com/appatalks/synapse/releases)
and run `py SYNAPSE.pyz --llama-server C:\path\to\llama-server.exe`.
For a managed Windows install, [follow the short source-install instructions](docs/installing.md).
Without a public release yet, use those source instructions on any platform.

## Open it. Pick a model. Go.

1. Open **Chat → Model Controls**. Browse for a local GGUF or paste its path.
2. Load the model and chat. Output limits and reasoning effort are in the same pop-up.
3. Open **Monitor** for speed, CPU/GPU, VRAM, temperature, power, PCIe, read I/O,
   RAM and context fill—or **Connect an app** to use your local model in another tool.

No account, hosted inference or model uploads. Chats stay in the page.
The app needs only Python and a browser; models and an appropriate
[llama.cpp backend](https://github.com/ggml-org/llama.cpp) are separate.
The reference backend revision is b11669. [Platform and sensor limits](docs/monitoring.md).

## Updates without reinstalling

Click the **version in the sidebar**. It lights up when a newer compatible
public release is found. Managed installs can download a verified update and
restart after your confirmation. Models, backends and local profiles are not
replaced. Source/pip installs get release information, not overwritten files.

Update checks contact GitHub for release metadata only, never prompts or
hardware data. Use `--no-update-check` to disable automatic checks.
Checksums verify the downloaded artifact's integrity; they are not a separate
publisher signature. [Installation and update details](docs/installing.md).

## Inspired by Strata, aimed at model-agnostic execution

[Strata](https://github.com/Niko1221/Strata) is a **direct inspiration**. Its
practical heterogeneous-inference work and integrated monitoring gave this
project a needed push toward a more useful local-model experience.

Strata offers an integrated engine/setup experience centered on its supported
lineup. SYNAPSE aims for **metadata-driven MoE scheduling across models**, with
transparent counters and an independently usable local app. It does not bundle
Strata, its engine or model packs, is not affiliated with Strata, and does not
claim feature parity or superior performance to it.

The experiments, native patches, benchmark methodology and full history live in
[unified-memory-scheduler](https://github.com/appatalks/unified-memory-scheduler).

---

**Local only:** the API has no app authentication. Do not expose it through a
tunnel or reverse proxy. No universal speedup, fit guarantee or quality
qualification is implied.

[Installation](docs/installing.md) · [Monitoring](docs/monitoring.md) ·
[Development](docs/releasing.md) · [MIT license](LICENSE)
