"""Explicit, per-user updates from the project's public GitHub releases."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile

LOG = logging.getLogger("synapse.updates")
REPOSITORY = "appatalks/synapse"
API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=10"
ARCHIVE_LIMIT = 16 * 1024 * 1024


def version_key(value: str) -> tuple | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?", value)
    if not match:
        return None
    major, minor, patch, stage, number = match.groups()
    return int(major), int(minor), int(patch), {"a": 0, "b": 1, "rc": 2, None: 3}[stage], int(number or 0)


class HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise ValueError("Refusing an insecure download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str, limit: int) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Downloads require HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "SYNAPSE-release-check",
                                                  "Accept": "application/vnd.github+json"})
    with urllib.request.build_opener(HttpsRedirect()).open(request, timeout=20) as response:
        result = response.read(limit + 1)
    if len(result) > limit:
        raise ValueError("Download exceeds its size limit")
    return result


def latest_release() -> dict | None:
    releases = json.loads(download(API, 512 * 1024))
    if not isinstance(releases, list):
        raise ValueError("GitHub did not return a release list")
    compatible = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        tag = release.get("tag_name", "")
        if not isinstance(tag, str) or version_key(tag) is None:
            continue
        assets = {a.get("name") for a in release.get("assets", []) if isinstance(a, dict)}
        if {"SYNAPSE.pyz", "SHA256SUMS"} <= assets:
            compatible.append({"tag": tag, "version": tag.removeprefix("v"),
                               "url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}"})
    return max(compatible, key=lambda r: version_key(r["tag"]), default=None)


def validate_archive(path: Path, expected_version: str | None = None) -> str:
    if path.stat().st_size > ARCHIVE_LIMIT:
        raise ValueError("Application archive exceeds its size limit")
    try:
        return _archive_version(path, expected_version)
    except (SyntaxError, UnicodeError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise ValueError(f"Invalid application archive: {exc}") from exc


def _archive_version(path: Path, expected_version: str | None) -> str:
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 256 or sum(i.file_size for i in archive.infolist()) > 32 * 1024 * 1024:
            raise ValueError("Application archive is unexpectedly large")
        names = archive.namelist()
        if len(names) != len(set(names)) or not {"__main__.py", "synapse_app/app.py",
                                               "synapse_app/__init__.py"} <= set(names):
            raise ValueError("Not a SYNAPSE application archive")
        if archive.testzip() is not None:
            raise ValueError("Application archive is corrupt")
        tree = ast.parse(archive.read("synapse_app/__init__.py").decode("utf-8"))
        values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    if len(values) != 1 or not isinstance(values[0], str) or version_key(values[0]) is None:
        raise ValueError("Application archive has no valid version")
    if expected_version is not None and values[0] != expected_version:
        raise ValueError("Application version does not match its release tag")
    return values[0]


def release_archive(release: dict, directory: Path) -> Path:
    tag = release["tag"]
    if version_key(tag) is None:
        raise ValueError("Invalid release version")
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}"
    checksums = download(base + "/SHA256SUMS", 16384).decode("ascii")
    hashes = re.findall(r"^([0-9a-fA-F]{64})[ \t]+\*?SYNAPSE\.pyz[ \t]*$", checksums, re.MULTILINE)
    if len(hashes) != 1:
        raise ValueError("Release must contain exactly one SYNAPSE.pyz checksum")
    body = download(base + "/SYNAPSE.pyz", ARCHIVE_LIMIT)
    if hashlib.sha256(body).hexdigest() != hashes[0].lower():
        raise ValueError("Application checksum verification failed")
    descriptor, name = tempfile.mkstemp(prefix=".synapse-update-", suffix=".pyz.part", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        validate_archive(path, release["version"])
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def managed_receipt(archive: Path | None) -> tuple[dict | None, str]:
    if archive is None:
        return None, "Source and pip installs are not modified. Use the one-line installer for in-app updates."
    receipt = archive.parent / "install.json"
    try:
        if archive.name != "SYNAPSE.pyz" or archive.is_symlink() or receipt.is_symlink():
            raise ValueError("The managed application path is not a regular installation")
        if hasattr(os, "getuid") and (archive.stat().st_uid != os.getuid() or
                                     archive.parent.stat().st_uid != os.getuid() or
                                     archive.parent.stat().st_mode & 0o022):
            raise ValueError("Managed updates require a private, user-owned installation directory")
        if receipt.stat().st_size > 4096:
            raise ValueError("Installation receipt exceeds its size limit")
        data = json.loads(receipt.read_text())
        if data.get("schema_version") != 1 or data.get("app") != "SYNAPSE" or data.get("mode") != "managed":
            raise ValueError("Installation receipt is not recognized")
        if not archive.is_file():
            raise ValueError("Managed application file is missing")
        return data, "Managed per-user installation. Updates replace only the application, not models or backends."
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return None, f"In-app installation unavailable: {exc}"


def install_archive(staged: Path, destination: Path, receipt: dict) -> None:
    backup = destination.with_suffix(".pyz.previous")
    receipt_path = destination.parent / "install.json"
    receipt_temp = destination.parent / ".install.json.part"
    if backup.is_symlink() or receipt_temp.exists() or receipt_temp.is_symlink():
        raise ValueError("Update scratch paths already exist or are unsafe; inspect the installation directory")
    shutil.copyfile(destination, backup)
    backup.chmod(0o600)
    try:
        with receipt_temp.open("x") as stream:
            json.dump(receipt, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        receipt_temp.chmod(0o600)
        os.replace(staged, destination)
        try:
            os.replace(receipt_temp, receipt_path)
        except OSError:
            os.replace(backup, destination)
            raise
    finally:
        receipt_temp.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)


class UpdateManager:
    def __init__(self, current: str, archive: Path | None, *, automatic: bool = True):
        self.current = current
        self.archive = archive
        self.automatic = automatic
        self.receipt, self.installation = managed_receipt(archive)
        self.lock = threading.RLock()
        self.checked = 0.0
        self.busy = False
        self.release: dict | None = None
        self.state = "not_checked"
        self.error: str | None = None

    def snapshot(self) -> dict:
        with self.lock:
            return {"current_version": self.current, "state": self.state, "error": self.error,
                    "release": dict(self.release) if self.release else None,
                    "managed": self.receipt is not None, "installation": self.installation,
                    "automatic": self.automatic}

    def check(self, *, force: bool = False) -> None:
        with self.lock:
            if self.busy or not force and (not self.automatic or self.checked and time.monotonic() - self.checked < 3600):
                return
            self.busy, self.state, self.error = True, "checking", None
        threading.Thread(target=self._check, name="synapse-release-check", daemon=True).start()

    def _check(self) -> None:
        try:
            release = latest_release()
            newer = release is not None and (version_key(release["version"]) > version_key(self.current) or
                version_key(release["version"]) == version_key(self.current) and
                self.receipt is not None and self.receipt.get("channel") == "preview")
            with self.lock:
                self.release = release
                self.state = "available" if newer else "current" if release else "no_release"
        except (OSError, ValueError, TypeError, KeyError) as exc:
            LOG.warning("Release check failed: %s", exc)
            with self.lock:
                self.state, self.error = "error", str(exc)
        finally:
            with self.lock:
                self.checked, self.busy = time.monotonic(), False

    def apply(self, version: object, restart) -> None:
        with self.lock:
            if self.busy or self.state != "available" or self.release is None:
                raise ValueError("Check for an available release before installing")
            if self.receipt is None or self.archive is None:
                raise ValueError(self.installation)
            if version != self.release["version"]:
                raise ValueError("The selected release changed; check again")
            release = dict(self.release)
            self.busy, self.state, self.error = True, "installing", None

        def worker():
            staged = None
            try:
                staged = release_archive(release, self.archive.parent)
                restart(staged, {**self.receipt, "channel": "release", "version": release["version"]})
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
                LOG.error("Application update failed: %s", exc)
                with self.lock:
                    self.state, self.error, self.busy = "error", str(exc), False
            finally:
                if staged:
                    staged.unlink(missing_ok=True)
        threading.Thread(target=worker, name="synapse-app-update", daemon=True).start()
