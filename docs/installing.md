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
