"""Requirement-traced tests for explicit approved-baseline governance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from avsys.baselines import (
    BaselineApprovalError,
    create_approved_baseline,
    load_baseline,
    replace_approved_baseline,
)
from avsys.cli import main
from avsys.contracts import load_contract, load_contract_bytes
from avsys.stimuli import generate_stimulus


ROOT = Path(__file__).resolve().parents[2]
VALID_MANIFEST = ROOT / "tests" / "fixtures" / "manifest" / "valid.json"
DEMO_MANIFEST = ROOT / "configs" / "manifests" / "m1-deterministic-stereo.json"
APPROVED_AT = "2026-08-16T01:00:00Z"


def _create(path: Path, manifest_path: Path = VALID_MANIFEST) -> dict[str, object]:
    manifest = load_contract(manifest_path, contract="manifest")
    return create_approved_baseline(
        path,
        baseline_id="m1.reference",
        manifest=manifest,
        stimulus=generate_stimulus(manifest),
        environment_class="portable-deterministic",
        reviewer="baseline-reviewer",
        rationale="Approve the reviewed deterministic reference generation.",
        approved_at=APPROVED_AT,
    )


def test_t_base_001_pol_base_001_generation_does_not_create_baseline(tmp_path: Path) -> None:
    manifest = load_contract(VALID_MANIFEST, contract="manifest")
    generate_stimulus(manifest)
    assert list(tmp_path.iterdir()) == []


def test_t_base_001_pol_base_002_003_create_binds_identity_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    descriptor = _create(path)
    loaded = load_contract_bytes(path.read_bytes(), contract="baseline")
    manifest = load_contract(VALID_MANIFEST, contract="manifest")

    assert descriptor == loaded.document
    assert descriptor["test_id"] == manifest.document["test"]["id"]
    assert descriptor["manifest_schema_version"] == manifest.document["schema_version"]
    assert descriptor["manifest_sha256"] == manifest.sha256
    assert descriptor["sut"] == manifest.document["sut"]
    assert descriptor["environment_class"] == "portable-deterministic"
    assert descriptor["generator_metadata"]["pcm_sha256"] == descriptor["pcm"]["sha256"]
    assert descriptor["approval"]["rationale"]


def test_t_base_001_pol_base_004_missing_is_structured_invalid_input(tmp_path: Path) -> None:
    outcome = load_baseline(tmp_path / "missing.json")
    assert outcome.validity == "invalid_input"
    assert outcome.code == "baseline_missing"
    assert outcome.baseline is None


def test_t_base_001_pol_base_003_load_verifies_digest_and_is_immutable(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    _create(path)
    outcome = load_baseline(path)
    assert outcome.validity == "valid"
    assert outcome.baseline is not None
    with pytest.raises(ValueError):
        outcome.baseline.pcm[0, 0] = 0.5
    with pytest.raises(ValueError):
        outcome.baseline.pcm.setflags(write=True)


def test_t_base_001_pol_base_004_altered_digest_never_yields_baseline(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    descriptor = _create(path)
    pcm_path = path.parent / descriptor["pcm"]["relative_path"]
    corrupted = bytearray(pcm_path.read_bytes())
    corrupted[0] ^= 1
    pcm_path.write_bytes(corrupted)

    outcome = load_baseline(path)
    assert outcome.validity == "invalid_input"
    assert outcome.code == "baseline_pcm_digest_mismatch"
    assert outcome.baseline is None


def test_t_base_001_pol_base_001_implicit_update_is_prohibited(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    original = path.read_bytes() if path.exists() else None
    _create(path)
    approved = path.read_bytes()
    assert original is None
    with pytest.raises(BaselineApprovalError, match="explicit replacement"):
        _create(path)
    assert path.read_bytes() == approved


@pytest.mark.parametrize("rationale", ["", "   "])
def test_t_base_001_pol_base_002_creation_without_rationale_is_rejected(
    tmp_path: Path, rationale: str
) -> None:
    manifest = load_contract(VALID_MANIFEST, contract="manifest")
    with pytest.raises(BaselineApprovalError, match="rationale"):
        create_approved_baseline(
            tmp_path / "baseline.json",
            baseline_id="m1.reference",
            manifest=manifest,
            stimulus=generate_stimulus(manifest),
            environment_class="portable-deterministic",
            reviewer="reviewer",
            rationale=rationale,
            approved_at=APPROVED_AT,
        )


def test_t_base_001_pol_base_005_replacement_retains_prior_provenance(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    first = _create(path)
    first_pcm = path.parent / first["pcm"]["relative_path"]
    first_bytes = first_pcm.read_bytes()
    manifest = load_contract(DEMO_MANIFEST, contract="manifest")
    second = replace_approved_baseline(
        path,
        manifest=manifest,
        stimulus=generate_stimulus(manifest),
        environment_class="portable-deterministic",
        reviewer="second-reviewer",
        rationale="Approve an intentional expected feature change.",
        approved_at="2026-08-16T02:00:00Z",
    )

    assert second["generation"] == 2
    assert second["pcm"]["sha256"] != first["pcm"]["sha256"]
    assert second["prior_generations"][0]["generation"] == 1
    assert second["prior_generations"][0]["pcm_sha256"] == first["pcm"]["sha256"]
    assert second["prior_generations"][0]["approval"] == first["approval"]
    assert first_pcm.read_bytes() == first_bytes
    assert load_baseline(path).validity == "valid"


def test_t_base_001_pol_base_002_cli_requires_separate_explicit_operation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "baseline.json"
    common = [
        "--manifest",
        str(VALID_MANIFEST),
        "--descriptor",
        str(path),
        "--environment-class",
        "portable-deterministic",
        "--reviewer",
        "reviewer",
        "--rationale",
        "Explicit CLI approval for a reviewed baseline.",
        "--approved-at",
        APPROVED_AT,
    ]
    assert main(["baseline-create", *common, "--baseline-id", "m1.cli-reference"]) == 0
    assert load_baseline(path).validity == "valid"
