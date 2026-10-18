# Release candidate and development

SYNAPSE is the clean application distribution. The inference research and its
full history remain in [unified-memory-scheduler](https://github.com/appatalks/unified-memory-scheduler).
Internal `VRAMBRIDGE_HYBRID_*` names and backend log markers are retained for
compatibility; renaming them would break installed research profiles.

## Run from source

```sh
python -m synapse_app --llama-server /path/to/llama-server
```

Python 3.10+ is the only application runtime dependency. A recent compatible
llama.cpp server, GPU driver where applicable, and user-provided GGUF weights
are separate requirements. Ordinary app/package installation does not download
models; the explicit acceleration option downloads/builds a pinned native backend.
The loopback app listener does not perform reverse DNS during startup; local
name-service problems must not delay opening the UI or checking backend health.

## Validate and build

```sh
python tests/test_local_app.py synapse_app/app.py
python -m unittest discover -s tests -p test_tuning.py
python tests/test_telemetry.py synapse_app/telemetry.py
python tests/test_updates.py
node --test tests/test_chat_stream.mjs tests/test_monitor.mjs tests/test_preferences.mjs tests/test_model_controls.mjs
python scripts/build_synapse.py --output dist
python tests/test_release.py dist/SYNAPSE.pyz
python -m pip wheel --no-deps --wheel-dir dist .
```

Node is used for tests only, never required to run the app. Wheel building uses
the setuptools/wheel build requirements declared in the project manifest.
The zipapp builder copies only an explicit public-file list; no model files,
profiles, logs, research results, caches or local editor files enter the artifact.
The shipped example profile contains placeholders, not machine-specific paths.

## Manual releases

Releases are prepared and published manually. Pushing a version tag does not
build assets or create a GitHub release. Application CI and code scanning remain
enabled; the CI matrix tests Linux, Windows and macOS with Python 3.10 and 3.13.

Start from a clean, synced `main`. Update `synapse_app/__init__.py` and the release
smoke-test version expectation together, commit the bump, and wait for CI/security
checks on that exact commit. Resolve or explicitly review scanner findings before
publishing; a successful analysis job alone does not mean there are no alerts.

Run the validation above, a browser navigation/streaming and monitoring check,
and verify that Ctrl+C releases the owned backend. Review the platform limitations.
Experimental hybrid execution and Q8 cache precision are not broadly
quality-qualified; do not imply universal fit, quality or speed guarantees.

Build the assets from the verified commit into a version-specific directory:

```sh
version=$(python -c 'from synapse_app import __version__; print(__version__)')
tag="v$version"
release_dir="dist/$tag"
python scripts/build_synapse.py --output "$release_dir"
python tests/test_release.py "$release_dir/SYNAPSE.pyz"
python -m pip wheel --no-deps --wheel-dir "$release_dir" .
python - "$release_dir" <<'PY'
import hashlib
from pathlib import Path
import sys

directory = Path(sys.argv[1])
assets = sorted(p for p in directory.iterdir() if p.suffix in (".pyz", ".whl"))
assert len(assets) == 2, "Expected exactly one zipapp and one wheel"
(directory / "SHA256SUMS").write_text("".join(
    f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in assets))
PY
```

Check the zipapp's `--version` and wheel metadata against the source version.
Keep model files, private profiles, logs and local configuration out of release
assets. `SYNAPSE.pyz` and `SHA256SUMS` must retain these exact names for the
installer/updater; also attach the versioned wheel.

Create an annotated tag at the verified commit, push it, and create a reviewable
draft. Release-candidate versions use a prerelease, not a stable release:

```sh
git tag -a "$tag" -m "SYNAPSE $version"
git push origin "$tag"
gh release create "$tag" "$release_dir/SYNAPSE.pyz" "$release_dir/"*.whl \
  "$release_dir/SHA256SUMS" --verify-tag --draft --prerelease \
  --title "SYNAPSE $version" --generate-notes
```

Review the draft notes and asset list. Download the uploaded assets to a separate
directory and verify them against `SHA256SUMS` before explicitly publishing:

```sh
gh release edit "$tag" --draft=false --prerelease
```

Only intentionally stable versions should omit `--prerelease`. Checksums protect
download integrity; they are not an independent publisher signature.
