"""Requirement-traced tests for deterministic M1 generated PCM."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket

import numpy as np
import pytest

from avsys.contracts import ContractError, LoadedContract, load_contract, load_contract_bytes
from avsys.stimuli import StimulusGenerationError, generate_stimulus


ROOT = Path(__file__).resolve().parents[2]
VALID_MANIFEST = ROOT / "tests" / "fixtures" / "manifest" / "valid.json"
DEMO_MANIFEST = ROOT / "configs" / "manifests" / "m1-deterministic-stereo.json"


def _manifest(
    *,
    generator_id: str,
    version: str = "1",
    seed: int = 0,
    parameters: dict[str, object],
    frames: int = 16,
    channels: int = 1,
) -> LoadedContract:
    document = json.loads(VALID_MANIFEST.read_text(encoding="utf-8"))
    document["stimulus"] = {
        "generator": {"id": generator_id, "version": version},
        "seed": seed,
        "parameters": parameters,
    }
    document["audio_format"]["frame_count"] = frames
    document["channel_map"] = [
        {"index": index, "id": f"channel-{index}"} for index in range(channels)
    ]
    return load_contract_bytes(
        (json.dumps(document, sort_keys=True) + "\n").encode(), contract="manifest"
    )


def test_t_sys_001_sys_rep_001_003_004_same_seed_same_bytes_digest_metadata() -> None:
    manifest = load_contract(DEMO_MANIFEST, contract="manifest")
    first = generate_stimulus(manifest)
    second = generate_stimulus(manifest)

    assert first.pcm.tobytes() == second.pcm.tobytes()
    assert first.metadata == second.metadata
    assert first.metadata.manifest_sha256 == hashlib.sha256(DEMO_MANIFEST.read_bytes()).hexdigest()
    assert first.metadata.pcm_sha256 == hashlib.sha256(first.pcm.tobytes()).hexdigest()
    assert first.metadata.seed == 4660


def test_t_sys_001_sys_rep_001_different_prbs_seed_changes_pcm() -> None:
    first = generate_stimulus(
        _manifest(generator_id="prbs15", seed=1, parameters={"amplitude": 0.5})
    )
    second = generate_stimulus(
        _manifest(generator_id="prbs15", seed=2, parameters={"amplitude": 0.5})
    )
    assert first.pcm.tobytes() != second.pcm.tobytes()
    assert first.metadata.pcm_sha256 != second.metadata.pcm_sha256


def test_t_sys_001_sys_rep_001_prbs15_known_vector() -> None:
    generated = generate_stimulus(
        _manifest(
            generator_id="prbs15",
            seed=1,
            parameters={"amplitude": 1.0},
            frames=20,
        )
    )
    expected = np.array(
        [1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 1, -1, -1, -1, -1],
        dtype=np.float32,
    )
    np.testing.assert_array_equal(generated.pcm[:, 0], expected)


@pytest.mark.parametrize("channels", [1, 2], ids=["mono", "stereo"])
def test_t_sys_001_sys_rep_004_mono_stereo_shape_dtype_layout(channels: int) -> None:
    generated = generate_stimulus(
        _manifest(
            generator_id="constant",
            parameters={"value": -0.25},
            frames=7,
            channels=channels,
        )
    )
    assert generated.pcm.shape == (7, channels)
    assert generated.pcm.dtype == np.dtype(np.float32)
    assert generated.pcm.flags.c_contiguous
    assert not generated.pcm.flags.writeable
    assert np.isfinite(generated.pcm).all()


@pytest.mark.parametrize("value", [-1.0, 1.0])
def test_t_sys_001_sys_rep_004_constant_frame_and_full_scale_boundaries(value: float) -> None:
    generated = generate_stimulus(
        _manifest(generator_id="constant", parameters={"value": value}, frames=1)
    )
    assert generated.pcm.shape == (1, 1)
    assert generated.pcm[0, 0] == np.float32(value)


def test_t_sys_001_sys_rep_004_impulse_and_channel_identification_semantics() -> None:
    impulse = generate_stimulus(
        _manifest(
            generator_id="impulse",
            parameters={"amplitude": -1.0, "frame_index": 3, "channel_indices": [1]},
            frames=5,
            channels=2,
        )
    )
    assert np.count_nonzero(impulse.pcm) == 1
    assert impulse.pcm[3, 1] == -1.0

    identification = generate_stimulus(
        _manifest(
            generator_id="channel-identification",
            parameters={"amplitude": 1.0, "start_frame": 1, "spacing_frames": 2},
            frames=4,
            channels=2,
        )
    )
    np.testing.assert_array_equal(np.argwhere(identification.pcm), [[1, 0], [3, 1]])


@pytest.mark.parametrize(
    "mutation",
    [
        ("unknown-generator", "1", 0, {"value": 0.0}),
        ("constant", "2", 0, {"value": 0.0}),
        ("constant", "1", 0, {"value": 0.0, "unknown": 1}),
        ("prbs15", "1", 0, {"amplitude": 0.5}),
        ("prbs15", "1", 32768, {"amplitude": 0.5}),
    ],
    ids=["generator", "version", "parameter", "zero-state", "seed-too-large"],
)
def test_t_sys_001_sys_rep_001_rejects_unknown_or_invalid_generator_contract(
    mutation: tuple[str, str, int, dict[str, object]],
) -> None:
    generator_id, version, seed, parameters = mutation
    with pytest.raises(ContractError):
        _manifest(
            generator_id=generator_id,
            version=version,
            seed=seed,
            parameters=parameters,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 1.01, -1.01])
def test_t_sys_001_sys_rep_004_rejects_non_finite_or_out_of_range(value: float) -> None:
    document = json.loads(VALID_MANIFEST.read_text(encoding="utf-8"))
    document["stimulus"]["parameters"]["value"] = value
    loaded = LoadedContract(document=document, sha256="0" * 64)
    with pytest.raises((ContractError, StimulusGenerationError)):
        generate_stimulus(loaded)


@pytest.mark.parametrize(
    ("generator_id", "parameters"),
    [
        ("impulse", {"amplitude": 1.0, "frame_index": 16, "channel_indices": [0]}),
        ("impulse", {"amplitude": 1.0, "frame_index": 0, "channel_indices": [1]}),
        (
            "channel-identification",
            {"amplitude": 1.0, "start_frame": 16, "spacing_frames": 1},
        ),
    ],
    ids=["frame", "channel", "identification-does-not-fit"],
)
def test_t_sys_001_sys_rep_004_rejects_invalid_frame_or_channel_indices(
    generator_id: str, parameters: dict[str, object]
) -> None:
    with pytest.raises(StimulusGenerationError):
        generate_stimulus(_manifest(generator_id=generator_id, parameters=parameters))


@pytest.mark.parametrize("indices", [[0, 0], [1], [0, 2]])
def test_t_sys_001_sys_rep_004_rejects_inconsistent_channel_map(indices: list[int]) -> None:
    loaded = _manifest(generator_id="constant", parameters={"value": 0.0}, channels=len(indices))
    loaded.document["channel_map"] = [
        {"index": index, "id": f"id-{position}"} for position, index in enumerate(indices)
    ]
    with pytest.raises(StimulusGenerationError):
        generate_stimulus(loaded)


def test_t_sys_001_sys_rep_005_reference_is_immutable_and_copy_is_explicit() -> None:
    generated = generate_stimulus(
        _manifest(generator_id="constant", parameters={"value": 0.0})
    )
    with pytest.raises(ValueError):
        generated.pcm[0, 0] = 1.0
    with pytest.raises(ValueError):
        generated.pcm.setflags(write=True)
    with pytest.raises(TypeError):
        generated.metadata.parameters["value"] = 1.0

    candidate = generated.candidate_copy()
    assert candidate.flags.writeable
    candidate[0, 0] = 1.0
    assert generated.pcm[0, 0] == 0.0


def test_t_ci_001_ci_run_009_generation_has_no_network_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    generated = generate_stimulus(load_contract(DEMO_MANIFEST, contract="manifest"))
    assert generated.pcm.shape == (32, 2)
