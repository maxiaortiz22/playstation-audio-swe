"""DEMO-2 residual, gain, polarity, channel, and dropout measurements."""

from __future__ import annotations

import numpy as np
import pytest

from avsys.analysis import (
    AlignedViews,
    ChannelMappingConfig,
    DropoutConfig,
    analyze_stereo_channel_mapping,
    compute_gain_metrics,
    compute_residual_metrics,
    detect_dropouts,
    diagnose_polarity,
)
from avsys.faults import inject_dropout, inject_stereo_channel_swap


SAMPLE_RATE_HZ = 48_000
RESIDUAL_RMS_FLOOR_LINEAR_FS = 1e-12
RESIDUAL_RATIONALE = (
    "1e-12 linear FS keeps exact-null RMS finite at -240 dBFS in this float32 test"
)
GAIN_RMS_FLOOR_LINEAR_FS = 1e-9
GAIN_RATIONALE = "1e-9 linear FS is below the 0.25-FS active fixture by 168 dB"
POLARITY_RMS_FLOOR_LINEAR_FS = 1e-5
POLARITY_MINIMUM_ABS_CORRELATION = 0.99
POLARITY_RATIONALE = (
    "0.99 unitless separates exact inversion/identity from unrelated test content"
)
MAPPING_MINIMUM_MARGIN = 0.25
MAPPING_RMS_FLOOR_LINEAR_FS = 1e-5
MAPPING_RATIONALE = (
    "0.25 unitless permutation-score margin is below the fixture's near-1.0 separation"
)
DROPOUT_ACTIVE_FLOOR_LINEAR_FS = 0.10
DROPOUT_NEAR_SILENCE_FLOOR_LINEAR_FS = 1e-6
DROPOUT_MINIMUM_DURATION_FRAMES = 16
DROPOUT_RATIONALE = (
    "active >=0.10 FS, quiet <=1e-6 FS, duration >=16 frames; calibrated only for these fixtures"
)


def _independent_stereo(frames: int = 256) -> np.ndarray:
    index = np.arange(frames, dtype=np.int64)
    left = np.where(((index * 17 + 3) % 31) < 15, 0.5, -0.5)
    right = np.where(((index * 29 + 11) % 37) < 18, 0.25, -0.25)
    return np.ascontiguousarray(np.column_stack((left, right)), dtype=np.float32)


def _views(baseline: np.ndarray, candidate: np.ndarray, *, baseline_start: int = 0) -> AlignedViews:
    assert baseline.shape == candidate.shape
    return AlignedViews(
        baseline,
        candidate,
        baseline_start,
        baseline_start + len(baseline),
        baseline_start,
        baseline_start + len(candidate),
    )


def _dropout_config(minimum_duration_frames: int = DROPOUT_MINIMUM_DURATION_FRAMES) -> DropoutConfig:
    return DropoutConfig(
        DROPOUT_ACTIVE_FLOOR_LINEAR_FS,
        DROPOUT_NEAR_SILENCE_FLOOR_LINEAR_FS,
        minimum_duration_frames,
        DROPOUT_RATIONALE,
    )


def test_demo2_cmp_met_001_002_clean_null_residual_uses_explicit_floor() -> None:
    baseline = _independent_stereo()
    metrics = compute_residual_metrics(
        _views(baseline, baseline.copy()),
        rms_floor_linear_fs=RESIDUAL_RMS_FLOOR_LINEAR_FS,
        rationale=RESIDUAL_RATIONALE,
    )

    assert len(metrics) == 2
    assert all(metric.peak_linear_fs == 0.0 for metric in metrics)
    assert all(metric.rms_linear_fs == 0.0 for metric in metrics)
    assert all(metric.rms_dbfs == pytest.approx(-240.0, abs=1e-12) for metric in metrics)
    assert all(metric.rms_was_floored for metric in metrics)


def test_demo2_cmp_met_001_002_residual_peak_and_rms_remain_per_channel() -> None:
    baseline = _independent_stereo()
    candidate = baseline.copy()
    candidate[10, 1] += np.float32(0.125)

    metrics = compute_residual_metrics(
        _views(baseline, candidate),
        rms_floor_linear_fs=RESIDUAL_RMS_FLOOR_LINEAR_FS,
        rationale=RESIDUAL_RATIONALE,
    )

    assert metrics[0].peak_linear_fs == 0.0
    assert metrics[1].peak_linear_fs == pytest.approx(0.125, abs=1e-12)
    assert metrics[1].rms_linear_fs == pytest.approx(0.125 / np.sqrt(256), abs=1e-12)


def test_demo2_cmp_met_009_gain_change_is_reported_without_normalization() -> None:
    baseline = _independent_stereo()
    gain_db = 1.0
    linear_gain = np.float32(10.0 ** (gain_db / 20.0))
    candidate = np.ascontiguousarray(baseline * linear_gain, dtype=np.float32)
    views = _views(baseline, candidate)

    gain = compute_gain_metrics(
        views,
        rms_floor_linear_fs=GAIN_RMS_FLOOR_LINEAR_FS,
        rationale=GAIN_RATIONALE,
    )
    residual = compute_residual_metrics(
        views,
        rms_floor_linear_fs=RESIDUAL_RMS_FLOOR_LINEAR_FS,
        rationale=RESIDUAL_RATIONALE,
    )

    assert all(metric.gain_delta_db == pytest.approx(1.0, abs=1e-5) for metric in gain)
    assert all(metric.peak_linear_fs > 0.0 for metric in residual)


@pytest.mark.parametrize(("factor", "expected"), [(1.0, "normal"), (-1.0, "inverted")])
def test_demo2_cmp_ch_004_polarity_is_a_distinct_diagnosis(
    factor: float, expected: str
) -> None:
    baseline = _independent_stereo()
    candidate = np.ascontiguousarray(baseline * np.float32(factor), dtype=np.float32)

    result = diagnose_polarity(
        _views(baseline, candidate),
        signal_rms_floor_linear_fs=POLARITY_RMS_FLOOR_LINEAR_FS,
        minimum_abs_correlation=POLARITY_MINIMUM_ABS_CORRELATION,
        rationale=POLARITY_RATIONALE,
    )

    assert [metric.diagnosis for metric in result] == [expected, expected]
    expected_correlation = 1.0 if factor > 0 else -1.0
    assert all(metric.signed_correlation == pytest.approx(expected_correlation) for metric in result)


@pytest.mark.parametrize(
    ("swap", "expected_mapping"),
    [(False, (0, 1)), (True, (1, 0))],
)
def test_demo2_cmp_ch_001_002_clean_and_swapped_stereo_mapping(
    swap: bool, expected_mapping: tuple[int, int]
) -> None:
    baseline = _independent_stereo()
    candidate = (
        inject_stereo_channel_swap(baseline, label="mapping-swap").candidate
        if swap
        else baseline.copy()
    )

    result = analyze_stereo_channel_mapping(
        _views(baseline, candidate),
        expected_labels=("L", "R"),
        config=ChannelMappingConfig(
            MAPPING_MINIMUM_MARGIN,
            MAPPING_RMS_FLOOR_LINEAR_FS,
            MAPPING_RATIONALE,
        ),
    )

    assert result.status == "confident"
    assert result.observed_to_expected_indices == expected_mapping
    assert result.observed_to_expected_labels == tuple(("L", "R")[i] for i in expected_mapping)
    assert result.mapping_score == pytest.approx(1.0, abs=1e-12)
    assert result.mapping_confidence == pytest.approx(1.0, abs=1e-12)
    assert result.mapping_margin is not None and result.mapping_margin >= MAPPING_MINIMUM_MARGIN
    assert result.minimum_mapping_margin == MAPPING_MINIMUM_MARGIN
    assert "normalized cross-correlation" in result.scoring_method


def test_demo2_cmp_ch_002_non_independent_stereo_is_ambiguous() -> None:
    mono_content = np.where(np.arange(256) % 2, 0.5, -0.5).astype(np.float32)
    baseline = np.ascontiguousarray(np.column_stack((mono_content, mono_content)), dtype=np.float32)

    result = analyze_stereo_channel_mapping(
        _views(baseline, baseline.copy()),
        expected_labels=("L", "R"),
        config=ChannelMappingConfig(
            MAPPING_MINIMUM_MARGIN,
            MAPPING_RMS_FLOOR_LINEAR_FS,
            MAPPING_RATIONALE,
        ),
    )

    assert result.status == "ambiguous"
    assert result.mapping_margin == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("fill", "classification"),
    [(0.0, "exact_zero"), (1e-7, "near_silence")],
)
def test_demo2_cmp_evt_002_exact_and_near_silence_dropout_are_localized(
    fill: float, classification: str
) -> None:
    baseline = _independent_stereo()
    candidate = inject_dropout(
        baseline,
        start_frame=40,
        end_frame=72,
        channel_indices=(0, 1),
        fill_value_linear_fs=fill,
        label=f"{classification}-dropout",
    ).candidate

    events = detect_dropouts(
        _views(baseline, candidate),
        sample_rate_hz=SAMPLE_RATE_HZ,
        config=_dropout_config(),
    )

    assert len(events) == 1
    event = events[0]
    assert (event.start_frame, event.end_frame) == (40, 72)
    assert event.start_seconds == pytest.approx(40 / SAMPLE_RATE_HZ, abs=1e-15)
    assert event.end_seconds == pytest.approx(72 / SAMPLE_RATE_HZ, abs=1e-15)
    assert event.duration_frames == 32
    assert event.duration_seconds == pytest.approx(32 / SAMPLE_RATE_HZ, abs=1e-15)
    assert event.channel_indices == (0, 1)
    assert event.classification == classification


def test_demo2_cmp_evt_002_dropout_reports_aligned_full_buffer_coordinates() -> None:
    baseline = _independent_stereo(frames=128)
    candidate = inject_dropout(
        baseline,
        start_frame=16,
        end_frame=32,
        channel_indices=(1,),
        fill_value_linear_fs=0.0,
        label="offset-view-dropout",
    ).candidate
    views = _views(baseline, candidate, baseline_start=100)

    event = detect_dropouts(
        views, sample_rate_hz=SAMPLE_RATE_HZ, config=_dropout_config()
    )[0]

    assert (event.start_frame, event.end_frame) == (116, 132)
    assert (event.candidate_start_frame, event.candidate_end_frame) == (116, 132)
    assert event.channel_indices == (1,)


def test_demo2_cmp_evt_002_legitimate_reference_silence_is_not_a_false_dropout() -> None:
    baseline = _independent_stereo()
    baseline[80:120, :] = np.float32(0.0)
    candidate = baseline.copy()

    events = detect_dropouts(
        _views(baseline, candidate),
        sample_rate_hz=SAMPLE_RATE_HZ,
        config=_dropout_config(),
    )

    assert events == ()


def test_demo2_cmp_evt_002_minimum_duration_boundary_is_inclusive() -> None:
    baseline = _independent_stereo()
    exact = inject_dropout(
        baseline, start_frame=20, end_frame=36, channel_indices=(0,),
        fill_value_linear_fs=0.0, label="exact-boundary",
    ).candidate
    short = inject_dropout(
        baseline, start_frame=20, end_frame=35, channel_indices=(0,),
        fill_value_linear_fs=0.0, label="short-boundary",
    ).candidate

    exact_events = detect_dropouts(
        _views(baseline, exact), sample_rate_hz=SAMPLE_RATE_HZ, config=_dropout_config()
    )
    short_events = detect_dropouts(
        _views(baseline, short), sample_rate_hz=SAMPLE_RATE_HZ, config=_dropout_config()
    )

    assert len(exact_events) == 1
    assert short_events == ()


def test_demo2_cmp_str_005_all_metric_inputs_remain_unchanged() -> None:
    baseline = _independent_stereo()
    candidate = baseline.copy()
    before = (baseline.copy(), candidate.copy())
    views = _views(baseline, candidate)

    compute_residual_metrics(
        views, rms_floor_linear_fs=RESIDUAL_RMS_FLOOR_LINEAR_FS,
        rationale=RESIDUAL_RATIONALE,
    )
    compute_gain_metrics(
        views, rms_floor_linear_fs=GAIN_RMS_FLOOR_LINEAR_FS,
        rationale=GAIN_RATIONALE,
    )
    diagnose_polarity(
        views, signal_rms_floor_linear_fs=POLARITY_RMS_FLOOR_LINEAR_FS,
        minimum_abs_correlation=POLARITY_MINIMUM_ABS_CORRELATION,
        rationale=POLARITY_RATIONALE,
    )
    analyze_stereo_channel_mapping(
        views, expected_labels=("L", "R"),
        config=ChannelMappingConfig(
            MAPPING_MINIMUM_MARGIN, MAPPING_RMS_FLOOR_LINEAR_FS, MAPPING_RATIONALE
        ),
    )
    detect_dropouts(views, sample_rate_hz=SAMPLE_RATE_HZ, config=_dropout_config())

    assert np.array_equal(baseline, before[0])
    assert np.array_equal(candidate, before[1])
