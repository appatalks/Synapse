# Installation and updates

## One-line Linux/macOS install

```bash
curl -fsSL https://raw.githubusercontent.com/appatalks/synapse/main/install.sh | bash -s -- --launch
```

Requirements: Python 3.10+, bash, curl, a browser and your own GGUF model.
The script bootstraps from this repository over HTTPS, prefers a public
checksummed zipapp, and clearly labels a source preview if no release exists.
Review the script first if you do not want to pipe a network script into bash.

- Application: `~/.local/share/synapse/SYNAPSE.pyz`
- Launcher: `~/.local/bin/synapse` (use this full path if that folder is not on `PATH`)
- No sudo, driver installation, model downloads or changes to your system Python.
- Supply an existing backend with `--llama-server /path/to/llama-server`.
- `--prefix /private/folder` puts both app and launcher under that folder.
- For an offline/local build, run `python install.py --local-package dist/SYNAPSE.pyz --no-accelerated`.

The app opens `http://127.0.0.1:8080`. Ctrl+C stops it and its owned backend.
`--port 0` chooses a free port; `--no-browser` suppresses browser opening.

## Windows managed install

Install Python 3.10+ from [python.org](https://www.python.org/downloads/windows/).
SYNAPSE uses **llama.cpp's `llama-server.exe`, not Ollama**. If you do not already
have it, the installer can download and configure it after asking for your
consent. Manual installation from [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)
is also supported: extract the entire ZIP into a permanent folder, keeping
the accompanying DLLs beside the executable; do not copy just the EXE.
Model weights and drivers are never downloaded by the installer.

In PowerShell, download and review the installer, then run it:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/appatalks/synapse/main/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Launch
```

`-ExecutionPolicy Bypass` applies only to that PowerShell process; it does not
change your saved execution policy. No administrator prompt is needed. The
installer downloads source over HTTPS, prefers a checksummed public application
release, and labels a source fallback as a preview, like the Linux/macOS installer.

The default managed installation creates:

- Application: `%LOCALAPPDATA%\Programs\SYNAPSE\SYNAPSE.pyz`.
- CLI launcher: `%LOCALAPPDATA%\Programs\SYNAPSE\bin\synapse.cmd`, added to **user** PATH.
- **SYNAPSE** shortcuts on your Desktop and in the Start Menu.

The shortcuts use the SYNAPSE logo. Rerunning the installer refreshes existing
managed shortcuts and their icon without replacing your saved backend.

Close and reopen your terminal application after installation, then run `synapse`.
You can also use the shortcuts immediately. The console stays open while the
app runs; Ctrl+C stops it. Use `synapse --stop` from another terminal to stop it.

The installer checks `LLAMA_SERVER`/PATH and looks beside a supplied local
package for `llama-server.exe`. If it cannot find the backend, interactive setup
first asks **Auto-install llama-server.exe and configure SYNAPSE? [y/N]**.
Accepting offers CPU (default), GPU via Vulkan, or **NVIDIA CUDA 13.4** for
x64/ARM64 Windows. GPU builds require an already installed compatible driver;
successful executable startup is not proof that a particular model will fit
or generate faster. CUDA setup downloads both the server and matching runtime
DLL package (about 552 MiB total on x64), verifies both pinned SHA-256 hashes,
places the DLLs beside the server and requires `--list-devices` to detect a
CUDA GPU. No NVIDIA driver or system CUDA toolkit is installed. An absent or
unusable CUDA GPU fails explicitly rather than accepting CPU-only execution.

Automatic setup downloads the official **b11669** package over HTTPS, verifies
its pinned SHA-256, safely extracts the EXE and DLLs into a new private folder
under the app directory, and checks `--version` and server CLI support before
remembering its path in the launchers. It does not replace existing backends,
install drivers/system runtimes, download models, or enable research patches.
Download/verification/startup failures are explained and failed extraction is
cleaned up; a different backend is never silently substituted.

Declining (the default), or a failed automatic setup, leads to the manual EXE
path/folder prompt. You may skip setup, but no model can load until a compatible
backend is configured. To save or change the backend location, rerun the same installer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -LlamaServer "C:\llama.cpp\llama-server.exe" -Launch
```

The saved path is reused by the CLI launcher and shortcuts, including after
application updates. An installed Ollama service does not satisfy this requirement.

### Switch an existing Windows backend

Normal reruns preserve a working backend. Use `-SwitchBackend` to reopen the
backend choices even when the saved executable is found:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -SwitchBackend -NoPi
```

Accept automatic setup and choose **3** for CUDA. New backend files go into a
separate private folder; the existing Vulkan/CPU backend is never deleted or
overwritten. Declining or skipping after a failed download keeps the saved
backend path. Successful setup updates the CLI launcher and shortcuts.
Restart Synapse to use the new backend; an already running app retains its old
executable. Model settings and model weights are not changed. To return to the
old backend, rerun with `-LlamaServer` and its original EXE path.

From a checkout, `python install.py --switch-backend --no-pi` is equivalent.
Switching requires an interactive Windows terminal and cannot be combined with
`-NonInteractive` or `-LlamaServer`. It does not enable the Linux-only hybrid
engine. Compare matched requests and run Auto Tune before claiming a speedup.

Use `-NoShortcuts` or `-NoPath` to skip those integrations. `-NonInteractive`
disables backend prompts and never downloads a backend. `-Prefix "C:\my folder\Synapse"` isolates the app and
launcher under that folder without changing PATH or creating shortcuts. For a
source checkout or offline package, the same installer supports
`-LocalPackage .\dist\SYNAPSE.pyz`; no application download is performed. In a
source checkout you may equivalently use `python install.py`; its Windows
default creates the same integrations. Rerunning preserves an existing saved
backend unless you supply a new one, and refuses unrelated launchers/shortcuts.

## Windows portable app

Download `SYNAPSE.pyz` from [Releases](https://github.com/appatalks/synapse/releases),
verify it against the release's `SHA256SUMS`, and run:

```powershell
py -3 .\SYNAPSE.pyz --llama-server "C:\llama.cpp\llama-server.exe"
```

This runs the application **without installing it**: no Desktop shortcut,
Start Menu entry or `synapse` command is created. Use the managed installer
above to get those integrations and the optional consent-based backend setup.
Neither method installs Ollama, GPU drivers or model weights, or replaces your
existing backend.

## Optional Pi coding agent

The interactive installer offers Pi on Windows, Linux and macOS. Decline with
Enter (the default), use `--no-pi` (`-NoPi` in PowerShell), or use
`--non-interactive` to skip all optional offers. To explicitly consent:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -WithPi
```

From a Linux/macOS source checkout:

```sh
python3 install.py --with-pi --no-accelerated
```

The one-line installer also accepts `--with-pi`. This option permits Pi
installation and adding a Synapse provider to its user configuration.
An existing Pi on PATH or in its managed agent `bin` directory is reused,
never upgraded or replaced. Otherwise SYNAPSE downloads a SHA-256-pinned Pi
1.5.2 standalone release into a new private app subdirectory. x64 and ARM64
builds are available for all three platforms. No system Node/npm installation,
sudo, model download or background agent startup is performed.
Pi setup requires an installed SYNAPSE release with the Pi commands. If the
latest published release is older, the installer reports this without installing
Pi; wait for a compatible release or explicitly build a source preview and
install it using `--local-package`.

Pi runs with your user permissions and can edit files and execute commands;
it is not a sandbox. Install only when you trust this capability. Failures are
reported separately; SYNAPSE remains installed when optional Pi setup fails.
An explicit `--with-pi`/`-WithPi` request exits nonzero if Pi setup fails.

Configuration uses `PI_CODING_AGENT_DIR` when set, otherwise `~/.pi/agent`.
The installer adds `synapse/local-model` at `http://127.0.0.1:8080/v1`, preserves
other providers, startup choices, tool settings and credentials. `synapse-pi`
selects **Synapse Local** for that invocation without changing ordinary `pi`
startup defaults. On Windows the launcher selects PowerShell instead of Bash;
on Unix it leaves Pi's tool selection unchanged.

The Synapse Pi launcher requires a ready model with at least 8192 context tokens.
Pi 1.5.2 reserves 4096 tokens when calculating output room, so a 4K context
can limit responses to one token. The 8192 minimum is not a guarantee that a
large project prompt will fit. The launcher checks the running model and refuses
to use Pi settings that advertise more context than the loaded model has.
If no model is ready during installation, Pi installation completes but provider
configuration is deferred. After loading a model or changing its context, refresh:

```sh
synapse --configure-pi
# If Synapse uses another listening port:
synapse --configure-pi --port 8081
```

Use `--port` for the port of the running Synapse app; the launcher reads that
port from Pi's Synapse provider. This command adds the Synapse provider if
needed, updates its endpoint, and refreshes its model context/output limits and
model-specific compaction reserve/recent-history defaults. It does not load
models or run inference. It requires a running, ready Synapse model. Default
output is capped at 4096 tokens; compaction reserves up to 8192 and keeps up to
12000 recent tokens, scaled down for small contexts. Adjust these values in
Pi's `models.json` and `settings.json`; `/reload` then `/model` reloads them.
Explicit refresh resets those budgets to derived defaults, so rerun only when
you want that reset. No cloud provider is silently selected by Synapse setup.

## First-turn latency

Backend startup warm-up and processing a new conversation's prompt are separate.
A new coding session sends system instructions, tool schemas and project context;
the backend must evaluate any uncached prefix before generating output. Follow-up
turns can reuse matching prompt/KV state and therefore respond much faster.
Model disk reads, GPU initialization and generated reasoning are other possible
contributors. Fast generation alone does not identify the slow first-turn phase.

SYNAPSE preserves the client's prompt-cache settings and does not send a hidden
dummy prompt when a model loads or a conversation starts. A generic warm-up cannot
guarantee it precomputes Pi's actual prompt, and can consume resources or evict
useful cache state. No general pre-warmer has been qualified for production here.
Diagnose using actual prompt-processing time, time to first streamed reasoning or
answer token, cache reuse and decode timing, comparing a new session with its
follow-up on the same loaded model. Do not infer a remedy from cache allocation
size alone. Prefill/engine experiments belong in the research repository until
measured and qualified; automatic generation behavior is unchanged.

## Context size and editor clients

In **Chat -> Model Controls -> Run settings**, standard execution accepts
512 through 262,144 context tokens (256K). Unload and reload the model to change
its allocation. This is an application limit, not a fit, speed or model-support
guarantee. Try larger contexts progressively and check the reported loaded
context, memory use and a real long-prompt response, not just successful loading.
Automatic fitting may reduce GPU weight placement as context memory grows.

When no Hybrid profile is installed (including standard Windows/macOS setups),
Automatic also allows an explicit context for the next load. Editing the context
applies it to the currently selected model. When selecting a different model,
the displayed value is not sent until edited; Automatic instead uses that model's
remembered Auto Tune choice or installation defaults. Checking **Allow
experimental Hybrid acceleration** does not lock that input or install Hybrid;
other run settings remain automatic. Unload an active model before editing.
Installations with a real Hybrid profile retain their profile/Auto Tune context
policy and its validation guards.

Experimental hybrid execution still uses the context budget in its installation
profile, capped by model metadata. Profiles may explicitly configure up to
262,144 tokens, but existing defaults and exact-context checks are unchanged.
Hybrid fitting is disabled: larger contexts compete with the fixed GPU expert
bank and may fail to allocate. Preserve the original profile before experimenting;
successful allocation or generation does not establish answer quality.

For VS Code or another OpenAI-compatible client, advertise limits that fit the
backend's **actual loaded context**, allowing room for output and token-count
differences. Editor settings do not increase the server allocation. For example,
a 32,768-token server can start with 24,576 input and 4,096 output tokens.
The browser chat's output limit is separate from an editor client's output limit.
JSON request bodies are limited to 8 MiB so long prompts can pass through the API;
the backend still enforces its token limit.

### Compaction and overlapping API requests

The backend still processes one chat request at a time with its full context.
Up to four additional requests wait in a first-in, first-out queue, for at most
15 minutes each. This lets a client send background compaction or other chat
requests without immediately failing because another request is running.
Streaming and non-streaming requests use the same queue. No model-name detection,
parallel context slots, extra GPU allocation or prompt truncation is involved.

The wait limit applies only to admission, not to the total time spent generating.
Your client's own timeout may be shorter, especially when compaction processes
a long prompt. Cancelled clients are removed from the queue without running
their queued prompt. Cancellation is also monitored while forwarding an active
request and waiting for the backend's first response.

A full queue returns HTTP 429; an expired wait or model unloaded/replaced while
waiting returns HTTP 503 with an explanation. Auto Tune still owns the model
exclusively and rejects chat requests with HTTP 409. Model Controls and the
connection status show the queued count; `/api/v1/status` exposes `chat_queued`.
The queue is not saved across app restarts.

### Optional Q8 attention cache

Under **Run settings -> Advanced performance**, the official llama.cpp backend
offers an explicit **Q8 K/V + Flash Attention** preset. FP16 backend defaults
remain unchanged unless selected. The preset passes `--cache-type-k q8_0`,
`--cache-type-v q8_0` and `--flash-attn on`; it does not reduce context length
or change model weights. Auto Tune retains the selected preset through trials,
application and restoration.

Q8 can roughly halve attention K/V storage compared with FP16, but does not
halve total model memory or quantize every recurrent-state buffer. It changes
cache precision and can affect answer quality. Extra memory headroom may improve
placement or enable a larger hybrid expert bank; speedups are not guaranteed.
SYNAPSE requires backend confirmation of both Q8 attention-cache types and enabled
Flash Attention before marking this preset ready. A reported precision fallback
fails explicitly. Other backend adapters retain their existing defaults.
The Q8 preset also enables the pinned backend's library-info diagnostics
(`--log-verbosity 4`) so these confirmations are visible. Debug and verbose-prompt
logging are not enabled, and backend authentication diagnostic lines are redacted.

### Optional native MTP drafting

Launch with `--experimental-speculation`, then choose **Native MTP** under
**Model Controls -> Advanced performance**, select a compatible native MTP
GGUF, and start with four draft tokens. The official llama.cpp backend must
support `draft-mtp` and report an active speculative decoder through `/slots`.
The existing DFlash method remains Standard-only; drafting stays Off by default.

Hybrid MTP also requires the matching patched backend's native MTP and
multi-position hybrid dispatch hooks. It verifies up to 31 proposals plus one
target token and needs extra draft VRAM. Reduce the causal expert-bank budget
explicitly if the combined target/draft does not fit. No smaller context, changed
weights, or target-only fallback is silently substituted.

[Draft compatibility, API fields and qualification limits](application_notes.md#experimental-speculative-decoding).

## Optional qualified causal provider

The application does not download this backend. With a separately prepared
package matching the [qualification](compatibility.md#optional-serialized-causal-provider),
explicitly install it from a source checkout:

```sh
python3 scripts/setup_causal_provider.py \
  --source-bin /path/to/qualified/package/bin \
  --model /path/to/qualified/model.gguf \
  --destination /path/to/new/provider/bin --confirm
```

The command refuses an existing destination or profile, checks the exact
model and component hashes and the qualified machine/driver, and registers
the provider only after verifying the copied files. Restart SYNAPSE to
discover it. The model weights are read for a full SHA-256 verification.
Keep Engine: Automatic; no new user-facing engine switch is required.

## Auto Tune

Open **Model Controls -> Auto Tune for this system**, choose a goal and explicitly
confirm that SYNAPSE may unload/reload the selected GGUF and run local benchmarks.
Balanced tests progressively through 8K, 16K and 32K, capped by model metadata.
Maximum Context continues through 64K, 128K and 256K where previous trials pass.
A near-capacity synthetic prompt must produce a complete streamed response,
backend-reported input usage and the correct start/middle/end anchors.
Successful loading alone never qualifies a context as verified.

Tuning uses automatic backend fitting (or explicitly selected CPU placement),
up to 8 generation / 16 prompt threads within CPU topology/affinity, and a
1024 MiB VRAM reserve. Thread counts are derived defaults, not individually
benchmarked optima. This is a context-capacity tuner, not an exhaustive search
of threads, quantization, loading modes or cache policies. Long prompts can take
minutes each; Maximum Context can take an hour or more. RAM availability is
checked, but OS availability includes reclaimable cache and is not a fit guarantee.
Allocation failures are retained in the results rather than hidden.

Auto Tune measures every engine this installation supports for the model; there
is nothing to select. Standard execution is tried first to find the largest
passing context. When a hybrid profile is installed and the model is a
compatible MoE with automatic placement, GPU + CPU expert sharing is then
tried at that context. Unbound causal layouts may try progressively smaller
expert banks; bound training plans retain their budget. An allocation/headroom
failure is preserved even when the backend later emits generic loader errors,
so those trailing messages do not prevent the existing smaller-bank retries.
If Standard cannot load a model but a matching qualified causal provider is
available, Auto Tune records the failed Standard trial and tests that provider.
Failed trials remain visible; context and KV precision are not silently reduced.
If the GPU backend
supports in-graph expert calls, that method is tried with the same bank and
replaces the classic method only when it is at least 5% better. Profiles and training plans are
not rewritten. Every passing trial also measures generation speed after a short
prompt: 128-token chunks are generated until two consecutive chunks agree within
5% (at most six), because adaptive expert residency keeps improving during the
first few hundred tokens. The steady chunk speed is reported. The goal decides
which execution mode wins at the selected context:

- **Balanced** selects hybrid only if its generation speed is at least 5% higher,
  because everyday replies are dominated by generation.
- **Maximum Context** selects hybrid only if its near-capacity
  prompt-plus-answer time is at least 5% lower, because long prompts are
  dominated by prompt processing.

Trials show both, plus prompt-processing speed. Hybrid execution often
generates faster but processes long prompts more slowly; for example, Qwen3-Coder-30B-A3B
on a 16 GB GPU generated about 37% faster in hybrid at 16K but processed a 28K
prompt at half the standard speed. None of this establishes broad answer quality.

Other chat/load/unload/update operations are blocked during a run. **Cancel &
restore** cancels a probe and attempts to reload the previous configuration.
Application shutdown cancels tuning without starting another model. Failed
restoration is reported explicitly, including when RAM headroom prevents it.

After completion, recommended model settings and the browser's output allowance
are applied, and the UI shows
copyable VS Code `maxInputTokens` / `maxOutputTokens`, the backend context,
model ID and safety margin. Other apps are never edited automatically.
Recommendations are marked stale and cannot be copied as current limits when
the active model/context no longer matches the measured settings. The output
allowance is a conservative allocation, not a sustained long-generation test.

The latest report is saved privately in `tuning.json` under
`$XDG_CONFIG_HOME/synapse` (normally `~/.config/synapse`) on Linux,
`~/Library/Application Support/SYNAPSE` on macOS, or `%LOCALAPPDATA%/SYNAPSE`
on Windows. It contains the local model path, hardware summary, settings and
measurements, not prompt text or chat history. Page refresh/app restart retains
the report but does not automatically load its model.

## Remembered model settings

Synapse privately saves the last successfully loaded model path and run settings
in `model-settings.json`, in the same configuration directory as `tuning.json`.
This includes your selected engine (including **Standard only**), requested
context, CPU threads, placement, KV cache, loading, offload, expert-cache and draft
settings. Restarting or refreshing restores the controls; **Load model** is still
required. No model loads or Auto Tune trials start automatically.

Failed or cancelled loads do not replace the saved configuration. Auto Tune's
intermediate trials are not saved as your last model; only its successfully
applied final choice replaces it. A later manual load takes precedence over that
choice. Saved settings are checked again when loading, so a missing model,
changed backend or unavailable experimental feature is reported rather than
silently switching settings. Save/read failures are shown in the UI.

This does not save browser chat history or change another app's token limits.
Versions without this feature did not save manual settings; those settings
cannot be recovered from an earlier restart unless recorded separately.

## Loading feedback

The loading banner remains visible outside Model Controls and shows the actual
phase, elapsed time, latest backend output and pending experimental checks.
Its progress bar is indeterminate unless actual prompt-processing progress is
reported; there is no invented percentage or completion-time estimate.
**Cancel loading** unloads the in-progress backend without closing the app.

Backend API readiness and experimental activation are separate checks. If the API
is ready but required hybrid activation markers remain missing for 60 seconds,
loading fails with the unconfirmed checks instead of appearing to load indefinitely.
The safety checks are not bypassed. Normal weight loading retains its existing
overall timeout.

## Optional accelerated engine

On Linux the installer offers acceleration through the terminal. Use
`--accelerated` for an explicit non-interactive request or `--no-accelerated`
to skip the offer. It never silently installs system dependencies.

An existing legacy VRAMBridge profile is validated and reused. Otherwise the
setup requires Git, CMake, a C++ compiler, NVIDIA drivers, `nvidia-smi` and `nvcc`.
It downloads the exact llama.cpp source revision and checksummed research patch,
builds matching CPU/CUDA libraries, and writes a private profile. Building can
take several minutes and substantial disk space. Partial failed builds are
retained for diagnosis, not silently erased.

The conservative profile uses causal initialization and bounded staging.
On systems with at least 16,000 MiB reported VRAM and 96 GiB RAM, it enables the
research direct-DMA budgets and a training plan bound to the exact GPT layout;
other routed layouts use their own causal initialization, never that plan.
Actual tensors, capacities, registration/headroom and activation are validated
again by the backend. Desktop load and model/context size can still cause OOM.

### Automatic engine choice

Engine methods are internal; leave **Allow experimental Hybrid acceleration**
checked for **Automatic** selection. Unchecking it selects **Standard only**
for loading and Auto Tune; it does not merely enable manual settings. A
Standard-only tuning run leaves that choice off and does not overwrite an
existing Automatic winner. Existing saved Standard choices remain off until
explicitly changed. Advanced performance retains an engine override for
troubleshooting.

Automatic manages context and run settings; displayed manual values are not
sent, and switching to Automatic can change context. Its hint shows the
installed Hybrid context default when available. Standard-only enables manual
context/settings, with in-page edits preserved when toggling back for the same
model. The checkbox does not itself load or unload anything.

Without
measurements, Automatic uses native fitting when the weights fit and GPU + CPU
expert sharing (classic method) for larger compatible MoE models. After an Auto
Tune run, Automatic reuses the measured winner (engine, method, context,
threads and expert bank) for that model file, KV precision, machine and backend
build. Choices are saved in `engine-choices.json` next to the tuning results;
changing the model file, hardware or backend build discards them. Requesting a
draft model or settings that conflict with the measured choice uses the
defaults instead. The status line explains which engine runs and why.

The in-graph method (hosted MoE) runs CPU experts inside the CUDA graph through
a pinned mailbox while the GPU computes resident experts, with
frequency-gated admissions (free slot after one use, replacement after six). It
is available when the CUDA plugin was built from the patched checkout (detected
from the library, or declared with `"hosted_moe": true` in the profile) and
direct transfers are configured. It is never used with MTP drafting until that
pairing is validated, and loading fails unless the backend confirms hosted
execution and the LFU policy. In local screens it was about 30% faster on
Qwen3-Coder-30B-A3B, neutral on a 512-expert Qwen3.8 model and about 6% slower
on gpt-oss-120b, which is why it is chosen by measurement rather than by
default. Advanced API clients may still request `hybrid_variant: "classic"` or
`"hosted"` for troubleshooting.

This is **experimental Linux/NVIDIA code**, not a production-qualified model
executor. CPU/native numerical and answer checks remain unresolved. No model
weights are downloaded, converted or pruned by setup. Use standard execution
with `--execution-mode standard` to bypass the experimental profile.
The measured 16GB GPU profile pins substantial RAM; do not assume a small
machine can reproduce the README's large-model results.

## Windows and source installs

For a standalone app, run the release `SYNAPSE.pyz` with Python:

```powershell
py SYNAPSE.pyz --llama-server C:\path\to\llama-server.exe
```

For a managed install with in-app updates before/after the first release:

```powershell
git clone https://github.com/appatalks/synapse.git
cd synapse
py install.py --no-accelerated --llama-server C:\path\to\llama-server.exe
```

Run the printed `synapse.cmd` launcher. Linux/macOS can also clone the repository
and run `python3 install.py`. Ordinary development still uses
`python -m synapse_app`; that source tree is never modified by in-app updates.

## Release details and self-update

The sidebar version opens a release-details dialog. A mint indicator means an
eligible public release is newer (or a matching public release replaces a
preview). Stable and `a`/`b`/`rc` semantic versions are ordered explicitly;
drafts, invalid tags and releases without both required assets are ignored.

Checks run at most hourly through the fixed `appatalks/synapse` GitHub API;
manual checks can be requested in the dialog. They send no model, prompt or
hardware information. Network errors are shown in that dialog, not reported as
“up to date.” Disable automatic checks with `--no-update-check`.

Only the private, user-owned managed zipapp is eligible for in-place updates.
SYNAPSE verifies a bounded download against the release's `SHA256SUMS`, checks
ZIP structure and the embedded version, and atomically replaces the app.
The prior app is retained as `SYNAPSE.pyz.previous`. No archive paths are
extracted onto the filesystem.

The download/checksum and metadata come from the project's GitHub account over
HTTPS. This verifies integrity, not an independent signing identity; you trust
the repository/release maintainers just as with the installer.

Installing requires confirmation that the model will be unloaded and the app
restarted. A busy request/model transition blocks installation; if a request
starts during download, the update fails explicitly without interrupting it.
The browser can reconnect on the same port. Chats remain in the open page,
but the model must be loaded again. Models, native backends and profiles are
not self-updated. Source, wheel and pipx installations show release details
and must be updated through their original installation method.
