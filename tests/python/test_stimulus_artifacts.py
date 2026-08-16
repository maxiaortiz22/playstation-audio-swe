"""Requirement-traced tests for the canonical deterministic package command."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from avsys.artifacts import write_stimulus_package
from avsys.cli import main
from avsys.contracts import load_contract


ROOT = Path(__file__).resolve().parents[2]
DEMO_MANIFEST = ROOT / "configs" / "manifests" / "m1-deterministic-stereo.json"


def test_t_rpt_003_rpt_rep_003_004_preserves_manifest_and_identifies_pcm(tmp_path: Path) -> None:
    package = write_stimulus_package(DEMO_MANIFEST, tmp_path / "package")
    metadata = load_contract(package.metadata_path, contract="stimulus_metadata").document

    assert package.manifest_path.read_bytes() == DEMO_MANIFEST.read_bytes()
    assert metadata["manifest_sha256"] == hashlib.sha256(DEMO_MANIFEST.read_bytes()).hexdigest()
    assert metadata["pcm_sha256"] == hashlib.sha256(package.pcm_path.read_bytes()).hexdigest()


def test_t_sys_001_sys_rep_004_repeated_packages_are_byte_identical(tmp_path: Path) -> None:
    first = write_stimulus_package(DEMO_MANIFEST, tmp_path / "first")
    second = write_stimulus_package(DEMO_MANIFEST, tmp_path / "second")
    for first_path, second_path in [
        (first.manifest_path, second.manifest_path),
        (first.metadata_path, second.metadata_path),
        (first.pcm_path, second.pcm_path),
    ]:
        assert first_path.read_bytes() == second_path.read_bytes()


def test_t_rpt_003_rpt_rep_003_canonical_cli_writes_only_selected_directory(
    tmp_path: Path, capsys: object
) -> None:
    output = tmp_path / "explicit-artifacts"
    assert main(["generate", "--manifest", str(DEMO_MANIFEST), "--output", str(output)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["output_directory"] == str(output)
    assert sorted(path.name for path in output.iterdir()) == [
        "manifest.json",
        "stimulus.metadata.json",
        "stimulus.pcm.f32le",
    ]
