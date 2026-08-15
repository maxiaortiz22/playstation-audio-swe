"""Download the recorded CMake/Ninja archives and verify their SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "toolchain" / "m1-v1.json"


def _download(url: str, expected_sha256: str) -> Path:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url) as response, tempfile.NamedTemporaryFile(
        delete=False
    ) as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
        archive = Path(output.name)
    actual = digest.hexdigest()
    if actual != expected_sha256:
        archive.unlink(missing_ok=True)
        raise RuntimeError(
            f"checksum mismatch for {url}: expected {expected_sha256}, got {actual}"
        )
    return archive


def _extract(archive: Path, url: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if url.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
    elif url.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(destination)
    else:
        raise RuntimeError(f"unsupported toolchain archive: {url}")


def _install_archive(entry: dict[str, str], destination: Path) -> None:
    archive = _download(entry["url"], entry["sha256"])
    try:
        _extract(archive, entry["url"], destination)
    finally:
        archive.unlink(missing_ok=True)


def _append_github_path(paths: list[Path]) -> None:
    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        with Path(github_path).open("a", encoding="utf-8") as output:
            for path in paths:
                output.write(f"{path}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    system = platform.system()
    platform_key = {"Linux": "linux-x86_64", "Windows": "windows-x86_64"}.get(
        system
    )
    if platform_key is None or platform.machine().lower() not in {
        "amd64",
        "x86_64",
    }:
        raise RuntimeError(f"unsupported M1 bootstrap platform: {system} {platform.machine()}")

    destination = args.destination.resolve()
    build_root = (ROOT / "build").resolve()
    if destination == build_root or not destination.is_relative_to(build_root):
        raise RuntimeError(
            f"bootstrap destination must be a child of {build_root}, got {destination}"
        )
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    cmake_destination = destination / "cmake"
    ninja_destination = destination / "ninja"
    _install_archive(record["cmake"]["archives"][platform_key], cmake_destination)
    _install_archive(record["ninja"]["archives"][platform_key], ninja_destination)

    cmake_root_name = (
        f"cmake-{record['cmake']['version']}-"
        + ("windows-x86_64" if system == "Windows" else "linux-x86_64")
    )
    cmake_bin = cmake_destination / cmake_root_name / "bin"
    paths = [cmake_bin, ninja_destination]
    _append_github_path(paths)

    cmake_executable = cmake_bin / ("cmake.exe" if system == "Windows" else "cmake")
    ninja_executable = ninja_destination / ("ninja.exe" if system == "Windows" else "ninja")
    cmake_output = subprocess.check_output(
        [cmake_executable, "--version"], text=True
    ).splitlines()[0]
    ninja_output = subprocess.check_output([ninja_executable, "--version"], text=True).strip()
    if record["cmake"]["version"] not in cmake_output:
        raise RuntimeError(f"unexpected CMake version: {cmake_output}")
    if ninja_output != record["ninja"]["version"]:
        raise RuntimeError(f"unexpected Ninja version: {ninja_output}")

    print(cmake_output)
    print(f"ninja version {ninja_output}")
    print(f"toolchain record sha256 {hashlib.sha256(RECORD_PATH.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
