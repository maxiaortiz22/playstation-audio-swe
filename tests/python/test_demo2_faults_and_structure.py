"""DEMO-2 fault and structural contracts with requirement-linked cases."""

from __future__ import annotations

import numpy as np
import pytest

from avsys.analysis import (
    AudioDescription,
    StructuralValidationConfig,
    validate_structure,
)
from avsys.faults import (
    FaultParameterError,
    inject_dropout,
    inject_integer_delay,
    inject_stereo_channel_swap,
)


SAMPLE_RATE_HZ = 48_000
MINIMUM_OVERLAP_FRAMES = 64
STRUCTURAL_RATIONALE = (
    "64 frames is the accepted OP-B minimum synchronization evidence; unit=frames"
)


def _pcm(frames: int = 128, channels: int = 2) -> np.ndarray:
    values = np.arange(frames * channels, dtype=np.int64).reshape(frames, channels)
    return (((values * 73 + 19) % 257) / 256.0 - 0.5).astype(np.float32)


def _description(*labels: str, sample_rate_hz: int = SAMPLE_RATE_HZ) -> AudioDescription:
    return AudioDescription(sample_rate_hz, tuple(labels), "frames_channels_interleaved")


def _config(minimum: int = MINIMUM_OVERLAP_FRAMES) -> StructuralValidationConfig:
    return StructuralValidationConfig(minimum, STRUCTURAL_RATIONALE)


@pytest.mark.parametrize("delay_frames", [-17, 0, 23])
def test_demo2_sys_ttv_002_integer_delay_is_deterministic_labeled_and_detached(
    delay_frames: int,
) -> None:
    source = _pcm()
    before = source.copy()

    first = inject_integer_delay(source, delay_frames=delay_frames, label="known-delay")
    second = inject_integer_delay(source, delay_frames=delay_frames, label="known-delay")

    assert np.array_equal(source, before)
    assert first.candidate is not source
    assert first.candidate.dtype == np.dtype(np.float32)
    assert first.candidate.shape == source.shape
    assert first.candidate.flags.c_contiguous
    assert np.array_equal(first.candidate, second.candidate)
    assert first.record == second.record
    assert first.record.type == "integer_delay"
    assert first.record.label == "known-delay"
    assert first.record.parameters == {"delay_frames": delay_frames}
    assert first.record.units == {"delay_frames": "frames"}


def test_demo2_sys_ttv_002_integer_delay_semantics_are_exact() -> None:
    source = _pcm(frames=8, channels=1)

    later = inject_integer_delay(source, delay_frames=2, label="later").candidate
    earlier = inject_integer_delay(source, delay_frames=-2, label="earlier").candidate

    assert np.array_equal(later[:2], np.zeros((2, 1), dtype=np.float32))
    assert np.array_equal(later[2:], source[:-2])
    assert np.array_equal(earlier[:-2], source[2:])
    assert np.array_equal(earlier[-2:], np.zeros((2, 1), dtype=np.float32))


def test_demo2_sys_ttv_002_stereo_swap_is_deterministic_labeled_and_detached() -> None:
    source = _pcm()
    before = source.copy()

    result = inject_stereo_channel_swap(source, label="swap-L-R")

    assert np.array_equal(source, before)
    assert np.array_equal(result.candidate[:, 0], source[:, 1])
    assert np.array_equal(result.candidate[:, 1], source[:, 0])
    assert result.candidate.flags.c_contiguous
    assert result.record.type == "stereo_channel_swap"
    assert result.record.parameters == {"observed_to_source_channel_indices": (1, 0)}
    assert result.record.units == {"observed_to_source_channel_indices": "channel_index"}


@pytest.mark.parametrize("fill", [0.0, 1e-7])
def test_demo2_sys_ttv_002_dropout_reproduction_retains_interval_channels_and_units(
    fill: float,
) -> None:
    source = _pcm()
    before = source.copy()

    first = inject_dropout(
        source,
        start_frame=31,
        end_frame=47,
        channel_indices=(0, 1),
        fill_value_linear_fs=fill,
        label="dropout-31-47",
    )
    second = inject_dropout(
        source,
        start_frame=31,
        end_frame=47,
        channel_indices=(0, 1),
        fill_value_linear_fs=fill,
        label="dropout-31-47",
    )

    assert np.array_equal(source, before)
    assert np.array_equal(first.candidate, second.candidate)
    assert first.record == second.record
    assert np.all(first.candidate[31:47, :] == np.float32(fill))
    assert first.record.type == "dropout"
    assert first.record.parameters["start_frame"] == 31
    assert first.record.parameters["end_frame"] == 47
    assert first.record.parameters["channel_indices"] == (0, 1)
    assert first.record.units["fill_value_linear_fs"] == "linear_FS"


@pytest.mark.parametrize(
    "operation",
    [
        lambda pcm: inject_integer_delay(pcm, delay_frames=128, label="bad"),
        lambda pcm: inject_integer_delay(pcm, delay_frames=-128, label="bad"),
        lambda pcm: inject_dropout(
            pcm, start_frame=5, end_frame=5, channel_indices=(0,),
            fill_value_linear_fs=0.0, label="bad",
        ),
        lambda pcm: inject_dropout(
            pcm, start_frame=0, end_frame=129, channel_indices=(0,),
            fill_value_linear_fs=0.0, label="bad",
        ),
        lambda pcm: inject_dropout(
            pcm, start_frame=1, end_frame=2, channel_indices=(0, 0),
            fill_value_linear_fs=0.0, label="bad",
        ),
        lambda pcm: inject_dropout(
            pcm, start_frame=1, end_frame=2, channel_indices=(2,),
            fill_value_linear_fs=0.0, label="bad",
        ),
        lambda pcm: inject_dropout(
            pcm, start_frame=1, end_frame=2, channel_indices=(0,),
            fill_value_linear_fs=float("nan"), label="bad",
        ),
    ],
)
def test_demo2_sys_ttv_002_fault_parameters_outside_exact_domains_are_rejected(
    operation: object,
) -> None:
    with pytest.raises(FaultParameterError):
        operation(_pcm())  # type: ignore[operator]


def test_demo2_sys_ttv_002_swap_rejects_non_stereo_and_faults_reject_noncanonical_pcm() -> None:
    with pytest.raises(FaultParameterError):
        inject_stereo_channel_swap(_pcm(channels=1), label="bad")
    with pytest.raises(FaultParameterError):
        inject_integer_delay(_pcm().astype(np.float64), delay_frames=1, label="bad")
    with pytest.raises(FaultParameterError):
        inject_integer_delay(_pcm()[:, ::-1], delay_frames=1, label="bad")


def test_demo2_cmp_str_001_to_005_clean_structure_is_valid_and_inputs_immutable() -> None:
    baseline = _pcm()
    candidate = baseline.copy()
    before = (baseline.copy(), candidate.copy())

    result = validate_structure(
        baseline,
        candidate,
        _description("L", "R"),
        _description("L", "R"),
        _config(),
    )

    assert result.status == "valid"
    assert result.issues == ()
    assert result.input_buffers_unchanged
    assert np.array_equal(baseline, before[0])
    assert np.array_equal(candidate, before[1])


def test_demo2_cmp_str_001_sample_rate_mismatch_precedes_similarity() -> None:
    result = validate_structure(
        _pcm(), _pcm(), _description("L", "R"),
        _description("L", "R", sample_rate_hz=44_100), _config(),
    )
    assert result.status == "invalid"
    assert "sample_rate_mismatch" in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("candidate", "candidate_description", "expected_code"),
    [
        (_pcm(channels=1), _description("L"), "channel_count_mismatch"),
        (_pcm(), _description("left", "right"), "channel_label_mismatch"),
        (_pcm().astype(np.float64), _description("L", "R"), "unsupported_dtype"),
        (_pcm()[:, 0], _description("L"), "unsupported_rank"),
        (_pcm()[:, ::-1], _description("L", "R"), "non_contiguous_layout"),
    ],
)
def test_demo2_cmp_str_002_dtype_rank_layout_channels_and_labels_are_structural(
    candidate: np.ndarray,
    candidate_description: AudioDescription,
    expected_code: str,
) -> None:
    result = validate_structure(
        _pcm(), candidate, _description("L", "R"), candidate_description, _config()
    )
    assert result.status == "invalid"
    assert expected_code in {issue.code for issue in result.issues}


def test_demo2_cmp_str_002_object_dtype_is_structured_invalid_and_immutable() -> None:
    baseline = _pcm()
    candidate = np.empty(baseline.shape, dtype=object)
    candidate[:, :] = object()
    baseline_before = baseline.copy()
    candidate_references_before = tuple(candidate.flat)

    result = validate_structure(
        baseline,
        candidate,
        _description("L", "R"),
        _description("L", "R"),
        _config(),
    )

    assert result.status == "invalid"
    assert {issue.code for issue in result.issues} == {"unsupported_dtype"}
    assert result.input_buffers_unchanged
    assert np.array_equal(baseline, baseline_before)
    assert all(
        after is before
        for after, before in zip(candidate.flat, candidate_references_before, strict=True)
    )


@pytest.mark.parametrize(("value", "frame", "channel"), [(np.nan, 17, 1), (np.inf, 23, 0)])
def test_demo2_cmp_str_003_non_finite_is_localized(
    value: float, frame: int, channel: int
) -> None:
    candidate = _pcm()
    candidate[frame, channel] = value

    result = validate_structure(
        _pcm(), candidate, _description("L", "R"), _description("L", "R"), _config()
    )

    issue = next(issue for issue in result.issues if issue.code == "non_finite_sample")
    assert issue.buffer == "candidate"
    assert issue.frame_index == frame
    assert issue.channel_index == channel
    assert issue.channel_label == ("L", "R")[channel]


def test_demo2_cmp_str_004_empty_and_short_overlap_are_invalid_with_boundary() -> None:
    empty = np.empty((0, 2), dtype=np.float32)
    empty_result = validate_structure(
        _pcm(), empty, _description("L", "R"), _description("L", "R"), _config()
    )
    short_result = validate_structure(
        _pcm(64), _pcm(63), _description("L", "R"), _description("L", "R"), _config()
    )
    boundary_result = validate_structure(
        _pcm(64), _pcm(64), _description("L", "R"), _description("L", "R"), _config()
    )

    assert "empty_input" in {issue.code for issue in empty_result.issues}
    assert "insufficient_unaligned_overlap" in {issue.code for issue in short_result.issues}
    assert boundary_result.status == "valid"
