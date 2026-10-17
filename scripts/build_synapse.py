#!/usr/bin/env python3
"""Build the dependency-free SYNAPSE zipapp from an explicit public-file list."""

import argparse
from pathlib import Path
import shutil
import tempfile
import zipapp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    source = root / "synapse_app"
    if not source.is_dir():
        source = root / "tools/vrambridge"
    public = ["__init__.py", "__main__.py", "app.py", "telemetry.py", "hybrid-profile.example.json",
              "web/index.html", "web/app.js", "web/chat-stream.mjs", "web/style.css",
              "web/monitor.mjs", "web/navigation.mjs", "web/icon.svg"]
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "SYNAPSE.pyz"
    with tempfile.TemporaryDirectory(prefix="synapse-build-") as directory:
        package = Path(directory) / "synapse_app"
        shutil.copyfile(root / "LICENSE", Path(directory) / "LICENSE")
        for name in public:
            destination = package / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination)
        zipapp.create_archive(directory, target, main="synapse_app.app:main",
                              interpreter="/usr/bin/env python3", compressed=True)
    print(target.resolve())


if __name__ == "__main__":
    main()
