#!/usr/bin/env bash
set -euo pipefail
if ! command -v python3 >/dev/null 2>&1; then
  printf 'SYNAPSE needs Python 3.10 or newer. Install Python, then run this command again.\n' >&2
  exit 1
fi
python3 - "$@" <<'PY'
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

if sys.version_info < (3, 10):
    raise SystemExit("SYNAPSE requires Python 3.10 or newer.")
url = "https://api.github.com/repos/appatalks/synapse/zipball/main"
request = urllib.request.Request(url, headers={"User-Agent": "SYNAPSE-installer"})
print("Downloading the SYNAPSE installer from appatalks/synapse...", flush=True)
with urllib.request.urlopen(request, timeout=30) as response:
    body = response.read(16 * 1024 * 1024 + 1)
if len(body) > 16 * 1024 * 1024:
    raise SystemExit("Installer source exceeds its size limit.")
with tempfile.TemporaryDirectory(prefix="synapse-installer-") as directory:
    root = Path(directory)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 32 * 1024 * 1024:
            raise SystemExit("Installer source is unexpectedly large.")
        prefixes = {name.split("/", 1)[0] for name in archive.namelist()}
        if len(prefixes) != 1:
            raise SystemExit("Unexpected source archive layout.")
        prefix = prefixes.pop() + "/"
        for name in archive.namelist():
            relative = name.removeprefix(prefix)
            parts = Path(relative).parts
            allowed = relative in ("install.py", "LICENSE", "scripts/build_synapse.py",
                                    "scripts/setup_acceleration.py") or (
                len(parts) >= 2 and parts[0] == "synapse_app" and
                Path(relative).suffix in (".py", ".mjs", ".js", ".json", ".svg", ".html", ".css"))
            if not allowed or name.endswith("/"):
                continue
            destination = root / relative
            if not destination.resolve().is_relative_to(root):
                raise SystemExit("Unsafe installer archive path.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
    try:
        result = subprocess.run([sys.executable, str(root / "install.py"), *sys.argv[1:]])
    except KeyboardInterrupt:
        raise SystemExit(130)
    raise SystemExit(result.returncode)
PY
