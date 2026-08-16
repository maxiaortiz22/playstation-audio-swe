"""Explicit approved-baseline lifecycle and read-only load boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from .contracts import ContractError, LoadedContract, dump_contract, load_contract_bytes
from .stimuli import GeneratedStimulus, canonical_pcm_bytes


class BaselineApprovalError(ValueError):
    """An explicit baseline create/replace operation is invalid."""


@dataclass(frozen=True)
class ApprovedBaseline:
    descriptor: Mapping[str, Any]
    descriptor_sha256: str
    pcm: np.ndarray

    def candidate_copy(self) -> np.ndarray:
        """Return an explicit writable copy; the approved input remains immutable."""
        return np.array(self.pcm, dtype=np.float32, order="C", copy=True)


@dataclass(frozen=True)
class BaselineLoadOutcome:
    validity: Literal["valid", "invalid_input"]
    code: str
    message: str
    baseline: ApprovedBaseline | None


def _freeze_mapping(document: dict[str, Any]) -> Mapping[str, Any]:
    def freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return MappingProxyType({key: freeze(child) for key, child in value.items()})
        if isinstance(value, list):
            return tuple(freeze(child) for child in value)
        return value

    return freeze(document)


def _invalid(code: str, message: str) -> BaselineLoadOutcome:
    return BaselineLoadOutcome(
        validity="invalid_input", code=code, message=message, baseline=None
    )


def load_baseline(descriptor_path: str | Path) -> BaselineLoadOutcome:
    """Load and verify an approved baseline without any write capability."""
    path = Path(descriptor_path)
    try:
        descriptor_raw = path.read_bytes()
    except FileNotFoundError:
        return _invalid("baseline_missing", f"baseline descriptor not found: {path}")
    except OSError as error:
        return _invalid("baseline_unreadable", f"cannot read baseline descriptor: {error}")

    try:
        loaded = load_contract_bytes(descriptor_raw, contract="baseline")
    except (ContractError, OSError) as error:
        return _invalid("baseline_descriptor_invalid", str(error))

    descriptor = loaded.document
    pcm_path = path.parent / descriptor["pcm"]["relative_path"]
    try:
        pcm_raw = pcm_path.read_bytes()
    except FileNotFoundError:
        return _invalid("baseline_pcm_missing", f"baseline PCM not found: {pcm_path}")
    except OSError as error:
        return _invalid("baseline_pcm_unreadable", f"cannot read baseline PCM: {error}")

    expected_bytes = descriptor["pcm"]["byte_count"]
    if len(pcm_raw) != expected_bytes:
        return _invalid(
            "baseline_pcm_size_mismatch",
            f"baseline PCM byte count {len(pcm_raw)} != descriptor {expected_bytes}",
        )
    actual_digest = hashlib.sha256(pcm_raw).hexdigest()
    if actual_digest != descriptor["pcm"]["sha256"]:
        return _invalid(
            "baseline_pcm_digest_mismatch",
            f"baseline PCM SHA-256 {actual_digest} != descriptor digest",
        )
    if actual_digest != descriptor["generator_metadata"]["pcm_sha256"]:
        return _invalid(
            "baseline_metadata_digest_mismatch",
            "baseline PCM digest differs from generated-stimulus metadata",
        )

    shape = tuple(descriptor["pcm"]["shape"])
    if shape[0] * shape[1] * np.dtype("<f4").itemsize != len(pcm_raw):
        return _invalid("baseline_pcm_shape_mismatch", "baseline PCM shape is inconsistent")
    pcm = np.frombuffer(pcm_raw, dtype="<f4").reshape(shape, order="C")
    if not np.isfinite(pcm).all():
        return _invalid("baseline_pcm_non_finite", "baseline PCM contains non-finite samples")
    if np.any(pcm < np.float32(-1.0)) or np.any(pcm > np.float32(1.0)):
        return _invalid("baseline_pcm_out_of_range", "baseline PCM exceeds full scale")

    return BaselineLoadOutcome(
        validity="valid",
        code="baseline_valid",
        message="approved baseline descriptor and PCM verified",
        baseline=ApprovedBaseline(
            descriptor=_freeze_mapping(descriptor),
            descriptor_sha256=loaded.sha256,
            pcm=pcm,
        ),
    )


def _approval(reviewer: str, rationale: str, approved_at: str) -> dict[str, str]:
    values = {
        "reviewer": reviewer.strip(),
        "rationale": rationale.strip(),
        "approved_at": approved_at.strip(),
    }
    for name, value in values.items():
        if not value:
            raise BaselineApprovalError(f"{name} must be explicit and non-empty")
    return values


def _descriptor_name(path: Path, generation: int) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", path.stem):
        raise BaselineApprovalError(
            "baseline descriptor stem must use only letters, digits, dot, underscore, or hyphen"
        )
    return f"{path.stem}.g{generation}.pcm.f32le"


def _write_generation(
    *,
    descriptor_path: Path,
    baseline_id: str,
    generation: int,
    manifest: LoadedContract,
    stimulus: GeneratedStimulus,
    environment_class: str,
    approval: dict[str, str],
    prior_generations: list[dict[str, Any]],
) -> dict[str, Any]:
    if stimulus.metadata.manifest_sha256 != manifest.sha256:
        raise BaselineApprovalError("stimulus metadata does not bind to this manifest")
    pcm_raw = canonical_pcm_bytes(stimulus.pcm)
    pcm_digest = hashlib.sha256(pcm_raw).hexdigest()
    if pcm_digest != stimulus.metadata.pcm_sha256:
        raise BaselineApprovalError("stimulus PCM digest changed before approval")
    environment_class = environment_class.strip()
    if not environment_class:
        raise BaselineApprovalError("environment_class must be explicit and non-empty")

    pcm_name = _descriptor_name(descriptor_path, generation)
    descriptor = {
        "schema_version": "1.0.0",
        "baseline_id": baseline_id,
        "generation": generation,
        "test_id": manifest.document["test"]["id"],
        "manifest_schema_version": manifest.document["schema_version"],
        "manifest_sha256": manifest.sha256,
        "sut": manifest.document["sut"],
        "environment_class": environment_class,
        "generator_metadata": stimulus.metadata.to_document(),
        "pcm": {
            "relative_path": pcm_name,
            "sha256": pcm_digest,
            "byte_count": len(pcm_raw),
            "encoding": "ieee754_float32_little_endian_frames_channels",
            "shape": list(stimulus.pcm.shape),
        },
        "approval": approval,
        "prior_generations": prior_generations,
    }
    descriptor_raw = dump_contract(descriptor, contract="baseline")
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    pcm_path = descriptor_path.parent / pcm_name
    try:
        with pcm_path.open("xb") as output:
            output.write(pcm_raw)
    except FileExistsError as error:
        raise BaselineApprovalError(f"baseline PCM generation already exists: {pcm_path}") from error
    try:
        descriptor_path.write_bytes(descriptor_raw)
    except OSError:
        pcm_path.unlink(missing_ok=True)
        raise
    return descriptor


def create_approved_baseline(
    descriptor_path: str | Path,
    *,
    baseline_id: str,
    manifest: LoadedContract,
    stimulus: GeneratedStimulus,
    environment_class: str,
    reviewer: str,
    rationale: str,
    approved_at: str,
) -> dict[str, Any]:
    """Explicitly create generation one; never called by stimulus generation/load."""
    path = Path(descriptor_path)
    if path.exists():
        raise BaselineApprovalError("approved baseline already exists; use explicit replacement")
    return _write_generation(
        descriptor_path=path,
        baseline_id=baseline_id,
        generation=1,
        manifest=manifest,
        stimulus=stimulus,
        environment_class=environment_class,
        approval=_approval(reviewer, rationale, approved_at),
        prior_generations=[],
    )


def replace_approved_baseline(
    descriptor_path: str | Path,
    *,
    manifest: LoadedContract,
    stimulus: GeneratedStimulus,
    environment_class: str,
    reviewer: str,
    rationale: str,
    approved_at: str,
) -> dict[str, Any]:
    """Explicitly replace an existing valid baseline and retain its provenance."""
    path = Path(descriptor_path)
    if not path.exists():
        raise BaselineApprovalError("approved baseline does not exist; use explicit creation")
    old_raw = path.read_bytes()
    outcome = load_baseline(path)
    if outcome.baseline is None:
        raise BaselineApprovalError(
            f"cannot replace an invalid baseline: {outcome.code}: {outcome.message}"
        )
    old = load_contract_bytes(old_raw, contract="baseline").document
    prior = list(old["prior_generations"])
    prior.append(
        {
            "generation": old["generation"],
            "descriptor_sha256": hashlib.sha256(old_raw).hexdigest(),
            "pcm_sha256": old["pcm"]["sha256"],
            "approval": old["approval"],
        }
    )
    return _write_generation(
        descriptor_path=path,
        baseline_id=old["baseline_id"],
        generation=old["generation"] + 1,
        manifest=manifest,
        stimulus=stimulus,
        environment_class=environment_class,
        approval=_approval(reviewer, rationale, approved_at),
        prior_generations=prior,
    )


__all__ = [
    "ApprovedBaseline",
    "BaselineApprovalError",
    "BaselineLoadOutcome",
    "create_approved_baseline",
    "load_baseline",
    "replace_approved_baseline",
]
