"""Optional, explicit Pi installation and local-provider configuration."""

import hashlib
import http.client
import io
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from urllib.parse import urlsplit

from .updates import download

PI_VERSION = "1.5.2"
PI_HASHES = {
    "pi-windows-x64.zip": "e6adb8cb8c84eca14391ad24b363de9d2be98a89ca3ba3fdee1fa4de32b7f2e8",
    "pi-windows-arm64.zip": "e83404bc5a6003ac950683edd9b6cf499dac91ec890d8439a8c32528de534a77",
    "pi-linux-x64.tar.gz": "811c6f2c9e7aaee252b5404252e556fb713aa209c1f7f924226aa77d4ef70cb5",
    "pi-linux-arm64.tar.gz": "42805cd5615952fcbbfc9c56b04f8feb84395134952e169a6cdc8d7676975666",
    "pi-darwin-x64.tar.gz": "f997a088613514ac97d913aeea7642094d84fe6d46854ff7e64e2c12e536dc50",
    "pi-darwin-arm64.tar.gz": "56b5e194d485ced555667b8ba3276157a8272e9ecde9e001e428af80985bdd9b",
}


def release_asset():
    system = {"win32": "windows", "linux": "linux", "darwin": "darwin"}.get(sys.platform)
    machine = os.environ.get("PROCESSOR_ARCHITEW6432", platform.machine()).lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if system is None or architecture is None:
        raise ValueError("Optional Pi installation supports x64/ARM64 Windows, Linux and macOS.")
    return f"pi-{system}-{architecture}." + ("zip" if system == "windows" else "tar.gz")


def existing_pi():
    executable = shutil.which("pi")
    if executable:
        return executable
    candidate = agent_directory() / "bin" / ("pi.cmd" if sys.platform == "win32" else "pi")
    return str(candidate) if candidate.is_file() else None


def install_pi(directory):
    name = release_asset()
    print(f"Downloading verified Pi {PI_VERSION}: {name}", flush=True)
    body = download(f"https://github.com/earendil-works/pi/releases/download/v{PI_VERSION}/{name}", 128 * 1024 * 1024)
    if hashlib.sha256(body).hexdigest() != PI_HASHES[name]:
        raise ValueError("Pi release checksum verification failed; nothing was installed.")
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Refusing a symlinked Pi installation directory.")
    root = Path(tempfile.mkdtemp(prefix=f"pi-{PI_VERSION}-", dir=directory))
    installed = False
    try:
        archive = zipfile.ZipFile(io.BytesIO(body)) if name.endswith(".zip") else tarfile.open(fileobj=io.BytesIO(body), mode="r:gz")
        with archive:
            zipped = isinstance(archive, zipfile.ZipFile)
            entries = archive.infolist() if zipped else archive.getmembers()
            sizes = [entry.file_size if zipped else entry.size for entry in entries]
            if len(entries) > 4096 or sum(sizes) > 1024 * 1024 * 1024:
                raise ValueError("Pi archive is unexpectedly large.")
            destinations, seen = [], set()
            for entry in entries:
                relative = (entry.filename if zipped else entry.name).replace("\\", "/").rstrip("/")
                while relative.startswith("./"):
                    relative = relative[2:]
                parts = relative.split("/")
                target = root / relative
                invalid_type = stat.S_ISLNK(entry.external_attr >> 16) if zipped else not (entry.isfile() or entry.isdir())
                if (invalid_type or not relative or any(part in ("", ".", "..") or ":" in part or
                        part.rstrip(" .") != part or PureWindowsPath(part).is_reserved() for part in parts) or
                        not target.resolve().is_relative_to(root.resolve()) or relative.casefold() in seen):
                    raise ValueError("Unsafe or duplicate Pi archive entry.")
                seen.add(relative.casefold())
                destinations.append(target)
            for entry, target in zip(entries, destinations):
                is_directory = entry.is_dir() if zipped else entry.isdir()
                if is_directory:
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.open(entry) if zipped else archive.extractfile(entry)
                    with source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    if not zipped:
                        target.chmod(entry.mode & 0o755)
        executables = [path for path in root.rglob("pi.exe" if sys.platform == "win32" else "pi") if path.is_file()]
        if len(executables) != 1:
            raise ValueError("Pi archive must contain exactly one Pi executable.")
        executable = executables[0]
        result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=30,
                                env={**os.environ, "PI_OFFLINE": "1"})
        if result.returncode != 0 or result.stdout.strip() != PI_VERSION:
            raise ValueError("The downloaded Pi could not pass its version check: " + (result.stdout + result.stderr)[-2000:])
        installed = True
        return str(executable)
    except (zipfile.BadZipFile, tarfile.TarError) as error:
        raise ValueError("Pi release archive is invalid or corrupt.") from error
    finally:
        if not installed:
            shutil.rmtree(root)


def loaded_context(port=8080):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/api/v1/status")
        response = connection.getresponse()
        body = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(body) > 1024 * 1024:
            raise ValueError("Cannot read Synapse model status.")
        status = json.loads(body)
        if not isinstance(status, dict):
            raise ValueError("Synapse status must be an object.")
        context = status.get("context")
        if (status.get("app_name") != "SYNAPSE" or status.get("state") != "ready" or
                isinstance(context, bool) or not isinstance(context, int) or not 512 <= context <= 262144):
            raise ValueError("Load a model in Synapse before refreshing Pi context limits.")
        return context
    finally:
        connection.close()


def agent_directory():
    return Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi/agent")).expanduser()


def read_config(path):
    if path.is_symlink():
        raise ValueError(f"Refusing a symlinked Pi configuration: {path}")
    if not path.exists():
        return {}
    if path.stat().st_size > 1024 * 1024:
        raise ValueError(f"Pi configuration exceeds 1 MiB: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Pi configuration must be an object: {path}")
    return data


def write_config(path, data):
    descriptor, name = tempfile.mkstemp(prefix=".synapse-pi-", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        staged.chmod(0o600)
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def configure_pi(directory=None, context=4096, port=8080, refresh=False):
    if (isinstance(context, bool) or not isinstance(context, int) or not 512 <= context <= 262144 or
            isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535):
        raise ValueError("Pi configuration requires a valid loaded context and listening port.")
    directory = Path(directory) if directory is not None else agent_directory()
    if directory.is_symlink():
        raise ValueError("Refusing a symlinked Pi agent directory.")
    models_path, settings_path = directory / "models.json", directory / "settings.json"
    models, settings = read_config(models_path), read_config(settings_path)
    endpoint = f"http://127.0.0.1:{port}/v1"
    providers = models.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("Pi providers must be an object.")
    provider = providers.setdefault("synapse", {"name": "Synapse", "baseUrl": endpoint,
                                               "api": "openai-completions", "apiKey": "synapse", "models": []})
    if isinstance(provider, dict) and refresh and provider.get("api") == "openai-completions":
        previous_endpoint = provider.get("baseUrl")
        if isinstance(previous_endpoint, str):
            parsed = urlsplit(previous_endpoint)
            if parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.path == "/v1":
                provider["baseUrl"] = endpoint
    if not isinstance(provider, dict) or provider.get("baseUrl") != endpoint or provider.get("api") != "openai-completions":
        raise ValueError("An existing Pi provider named synapse has different settings; it was not replaced.")
    entries = provider.setdefault("models", [])
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("Pi provider models must be a list of objects.")
    matches = [entry for entry in entries if entry.get("id") == "local-model"]
    if len(matches) > 1:
        raise ValueError("Pi has duplicate local-model entries.")
    model = matches[0] if matches else {"id": "local-model"}
    if not matches:
        entries.append(model)
    defaults = {"name": "Synapse Local", "input": ["text"], "contextWindow": context,
                "maxTokens": min(4096, max(128, context // 8)),
                "compat": {"maxTokensField": "max_tokens"},
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}
    for key, value in defaults.items():
        if refresh and key in ("contextWindow", "maxTokens"):
            model[key] = value
        else:
            model.setdefault(key, value)
    settings.setdefault("defaultProvider", "synapse")
    settings.setdefault("defaultModel", "local-model")
    if os.name == "nt":
        settings.setdefault("defaultTools", ["-bash", "+powershell"])
    compaction = settings.setdefault("compaction", {})
    if not isinstance(compaction, dict):
        raise ValueError("Pi compaction settings must be an object.")
    overrides = compaction.setdefault("modelOverrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("Pi compaction modelOverrides must be an object.")
    budget = {"reserveTokens": min(8192, max(256, context // 4)),
              "keepRecentTokens": min(12000, max(128, context // 4))}
    existing = overrides.setdefault("synapse/local-model", {})
    if not isinstance(existing, dict):
        raise ValueError("Pi's Synapse compaction override must be an object.")
    for key, value in budget.items():
        if refresh:
            existing[key] = value
        else:
            existing.setdefault(key, value)
    directory.mkdir(parents=True, exist_ok=True)
    write_config(models_path, models)
    write_config(settings_path, settings)
    return directory