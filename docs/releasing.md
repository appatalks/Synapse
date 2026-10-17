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
are separate requirements. No backend/model downloads happen during installation.

## Validate and build

```sh
python tests/test_local_app.py synapse_app/app.py
python tests/test_telemetry.py synapse_app/telemetry.py
node --test tests/test_chat_stream.mjs tests/test_monitor.mjs
python scripts/build_synapse.py --output dist
python tests/test_release.py dist/SYNAPSE.pyz
python -m pip wheel --no-deps --wheel-dir dist .
```

Node is used for tests only, never required to run the app. Wheel building uses
the setuptools/wheel build requirements declared in the project manifest.
The zipapp builder copies only an explicit public-file list; no model files,
profiles, logs, research results, caches or local editor files enter the artifact.
The shipped example profile contains placeholders, not machine-specific paths.

The CI matrix tests Linux, Windows and macOS with Python 3.10 and 3.13.
A release tag builds a wheel and zipapp and creates a **draft prerelease**;
it does not silently publish a stable release.

Before publishing that draft, inspect CI, run a browser navigation/streaming
and monitoring check, verify Ctrl+C releases the owned backend, and review
the platform limitations. Do not describe the experimental hybrid engine as
production-qualified or imply performance guarantees from application CI.
