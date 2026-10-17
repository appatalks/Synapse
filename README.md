# SYNAPSE

**Local models. A clear view of your machine.**

Run a GGUF model, chat with it, connect your tools, and watch the hardware doing the work.
No account. No hosted inference. No model uploads.

> **Release candidate — not a stable, quality-qualified inference engine.**
> The application targets Linux, Windows and macOS. GPU sensor coverage and the
> optional research engine have narrower support; see [platform notes](docs/monitoring.md).

## What you get

- **Run a model:** start and stop your own llama.cpp backend with explicit model and resource settings.
- **Chat:** streamed answers and reasoning, cancellation, output budgets, and backend-reported speed.
- **Monitor:** graphs for tok/s, GPU load, VRAM, temperature, power, PCIe, CPU, RAM, read I/O and context fill.
- **Connect an app:** a loopback OpenAI-compatible models/chat API for your local tools.

The app uses Python's standard library and a browser. Missing sensors are labeled
**unavailable**, not guessed. No analytics or chat-history persistence is built in.
Your chosen model and backend can have their own behavior and licenses.

## Get started

You need **Python 3.10+**, a compatible [llama.cpp `llama-server`](https://github.com/ggml-org/llama.cpp) (tested with b11669),
a local GGUF model, and enough RAM/VRAM for it. Backends, drivers and models are **not bundled or downloaded**.

Download `SYNAPSE.pyz` from [Releases](https://github.com/appatalks/synapse/releases), then:

```sh
python SYNAPSE.pyz --llama-server /path/to/llama-server
```

On Windows, use `py SYNAPSE.pyz --llama-server C:\path\to\llama-server.exe`.
Your browser opens at `http://127.0.0.1:8080`. Choose a model in **Run a model**,
then open **Chat**, **Monitor**, or **Connect an app** in the sidebar.
Stop with **Ctrl+C** to unload the backend. Navigation preserves your chat; refreshing does not.

Prefer an isolated install? Download the release wheel and run:

```sh
pipx install /path/to/synapse_local-0.1.0rc1-py3-none-any.whl
synapse --llama-server /path/to/llama-server
```

Use `--port 0` for a free port, `--no-browser` for a headless launch, or
`--execution-mode standard` to explicitly bypass experimental profiles.
To run directly from this repository instead of a release artifact:

```sh
git clone https://github.com/appatalks/synapse.git
cd synapse
python -m synapse_app --llama-server /path/to/llama-server
```

## How is it different from Strata?

[Strata](https://github.com/Niko1221/Strata) is a **direct inspiration**.
Its integrated monitoring and practical heterogeneous-inference work gave this
project a needed push toward a more useful, observable local-model experience.

Strata offers an integrated engine/setup experience centered on its supported
model lineup. SYNAPSE currently takes a **bring-your-own GGUF and llama.cpp backend**
approach: a small, independent application with transparent local controls and monitoring.
It does not bundle Strata, its engine, or its model packs, and is not affiliated with Strata.
We do not claim feature parity or that SYNAPSE is faster.

Our longer-term direction is **model-agnostic MoE scheduling**: use model metadata,
tensor layouts and measured hardware costs rather than a checkpoint-name whitelist.
The experiments, benchmark conditions and retained failures live in
[unified-memory-scheduler](https://github.com/appatalks/unified-memory-scheduler).

## What is still experimental?

Standard inference is performed by your llama.cpp backend. The optional patched
CPU/GPU MoE dispatcher is **Linux/NVIDIA research software**, not installed by this
package, and still has unresolved diagnostic/answer checks. Its benefits are
model- and workload-dependent. Speculation is off by default. No universal
speedup, model-fit guarantee, or 60 tok/s promise is made.

The API is local-only and has no app authentication. **Do not expose it through
a tunnel or reverse proxy.** Check important model answers independently.

---

[Monitoring & platform details](docs/monitoring.md) · [Release/development guide](docs/releasing.md) ·
[Research](https://github.com/appatalks/unified-memory-scheduler) · [MIT license](LICENSE)
