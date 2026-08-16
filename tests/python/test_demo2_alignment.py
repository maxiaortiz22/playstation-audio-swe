"""DEMO-2 production integer-alignment tests linked to SPEC-001."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from avsys.analysis import (
    AlignmentPolicyError,
    AlignmentRequest,
    AudioDescription,
    StructuralValidationConfig,
    TimeAlignmentRequest,
    apply_integer_time_alignment,
    estimate_integer_alignment,
    load_m1_alignment_operating_point,
    validate_and_estimate_integer_alignment,
)
from avsys.faults import inject_integer_delay


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "configs" / "policies" / "m1-alignment-operating-point.json"
SAMPLE_RATE_HZ = 48_000
SEARCH_LIMIT_FRAMES = 32
SEARCH_RATIONALE = (
    "inclusive +/-32-frame test bound covers the injected fixture delays; unit=frames"
)
MEASUREMENT_MINIMUM_OVERLAP_FRAMES = 64


@pytest.fixture(scope="module")
def operating_point():
    return load_m1_alignment_operating_point(POLICY_PATH)


def _broadband(frames: int = 769, channels: int = 2, seed: int = 0x13579BDF) -> np.ndarray:
    state = seed & 0xFFFFFFFF
    output = np.empty((frames, channels), dtype=np.float32)
    for frame in range(frames):
        for channel in range(channels):
            state ^= (state << 13) & 0xFFFFFFFF
            state ^= state >> 17
            state ^= (state << 5) & 0xFFFFFFFF
            state &= 0xFFFFFFFF
            output[frame, channel] = np.float32(0.5 if state & 1 else -0.5)
    return output


def _request(
    baseline_frames: int,
    candidate_frames: int,
    *,
    search_min: int = -SEARCH_LIMIT_FRAMES,
    search_max: int = SEARCH_LIMIT_FRAMES,
    baseline_start: int = 0,
    candidate_start: int = 0,
    sync_frames: int | None = None,
    remove_dc: bool = False,
) -> AlignmentRequest:
    length = sync_frames if sync_frames is not None else min(
        baseline_frames - baseline_start, candidate_frames - candidate_start
    )
    return AlignmentRequest(
        search_min,
        search_max,
        baseline_start,
        baseline_start + length,
        candidate_start,
        candidate_start + length,
        0,
        remove_dc,
    )


def _estimate(baseline: np.ndarray, candidate: np.ndarray, operating_point, **request_values):
    return estimate_integer_alignment(
        baseline,
        candidate,
        sample_rate_hz=SAMPLE_RATE_HZ,
        request=_request(len(baseline), len(candidate), **request_values),
        operating_point=operating_point,
    )


def test_demo2_cmp_align_002_op_b_is_loaded_exactly_from_versioned_policy(operating_point) -> None:
    assert SEARCH_RATIONALE.endswith("unit=frames")
    assert operating_point.id == "OP-B-intermediate"
    assert operating_point.scope == "m1-manifest-policy-only"
    assert operating_point.source_sha256 == hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
    assert operating_point.plateau_epsilon == 1e-5
    assert operating_point.maximum_primary_plateau_width_frames == 2
    assert operating_point.secondary_exclusion_radius_frames == 4
    assert operating_point.minimum_primary_abs_correlation == 0.50
    assert operating_point.minimum_accepted_peak_ratio == 1.10
    assert operating_point.sync_rms_floor_linear_fs == 1e-5
    assert operating_point.minimum_overlap_frames == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("automatic_selection", True),
        ("fallback_operating_point_id", "OP-A-permissive"),
        ("universal_default", True),
        ("selected_operating_point_id", "OP-C-conservative"),
    ],
)
def test_demo2_cmp_align_002_policy_loader_rejects_fallback_or_non_op_b(
    field: str, value: object
) -> None:
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    document[field] = value
    raw = json.dumps(document).encode("utf-8")
    with mock.patch.object(Path, "read_bytes", return_value=raw), pytest.raises(
        AlignmentPolicyError
    ):
        load_m1_alignment_operating_point(POLICY_PATH)


@pytest.mark.parametrize("delay_frames", [-23, 0, 19, -32, 32])
def test_demo2_cmp_align_001_to_005_negative_zero_positive_and_boundary_lags(
    operating_point, delay_frames: int
) -> None:
    baseline = _broadband()
    candidate = inject_integer_delay(
        baseline, delay_frames=delay_frames, label=f"delay-{delay_frames}"
    ).candidate

    result = _estimate(baseline, candidate, operating_point)

    assert result.status == "valid"
    assert result.reason == "accepted"
    assert result.lag_frames == delay_frames
    assert result.latency_ms == pytest.approx(delay_frames * 1000.0 / SAMPLE_RATE_HZ, abs=1e-12)
    assert result.signed_primary_correlation == pytest.approx(1.0, abs=1e-12)
    assert result.search_min_lag_frames == -SEARCH_LIMIT_FRAMES
    assert result.search_max_lag_frames == SEARCH_LIMIT_FRAMES
    assert result.input_buffers_unchanged


def test_demo2_cmp_align_002_delay_outside_search_range_is_not_accepted(operating_point) -> None:
    baseline = _broadband()
    candidate = inject_integer_delay(baseline, delay_frames=41, label="outside-search").candidate

    result = _estimate(baseline, candidate, operating_point)

    assert result.status == "invalid"
    assert result.reason == "primary_below_minimum"
    assert result.lag_frames != 41


def test_demo2_sys_anl_005_structural_failure_prevents_similarity_measurement(
    operating_point,
) -> None:
    baseline = _broadband()
    candidate = baseline.copy()
    result = validate_and_estimate_integer_alignment(
        baseline,
        candidate,
        baseline_description=AudioDescription(
            SAMPLE_RATE_HZ, ("L", "R"), "frames_channels_interleaved"
        ),
        candidate_description=AudioDescription(
            44_100, ("L", "R"), "frames_channels_interleaved"
        ),
        structural_config=StructuralValidationConfig(
            64,
            "64 frames equals the accepted OP-B minimum evidence; unit=frames",
        ),
        alignment_request=_request(len(baseline), len(candidate)),
        operating_point=operating_point,
    )

    assert result.structural.status == "invalid"
    assert "sample_rate_mismatch" in {
        issue.code for issue in result.structural.issues
    }
    assert result.alignment is None


def test_demo2_cmp_align_006_periodic_equivalent_peaks_are_ambiguous(operating_point) -> None:
    baseline = np.tile(np.array([[0.5], [-0.5]], dtype=np.float32), (256, 1))
    candidate = baseline.copy()

    result = _estimate(
        baseline, candidate, operating_point, search_min=-8, search_max=8
    )

    assert result.status == "ambiguous"
    assert result.reason == "equivalent_primary_peaks"
    assert result.equivalent_primary_peak_count > 1
    assert result.primary_plateau_width_frames == 17
    assert result.signed_primary_correlation == pytest.approx(1.0)


def test_demo2_cmp_align_005_polarity_peak_sign_is_preserved(operating_point) -> None:
    baseline = _broadband()
    delayed = inject_integer_delay(baseline, delay_frames=13, label="delay-plus-polarity").candidate
    candidate = np.ascontiguousarray(-delayed, dtype=np.float32)

    result = _estimate(baseline, candidate, operating_point)

    assert result.status == "valid"
    assert result.lag_frames == 13
    assert result.signed_primary_correlation == pytest.approx(-1.0, abs=1e-12)


def test_demo2_cmp_align_007_dc_removal_is_sync_only_and_inputs_are_immutable(operating_point) -> None:
    baseline = _broadband()
    candidate = inject_integer_delay(baseline, delay_frames=-11, label="dc-sync").candidate
    baseline_before = baseline.copy()
    candidate_before = candidate.copy()

    result = _estimate(baseline, candidate, operating_point, remove_dc=True)

    assert result.status == "valid"
    assert result.lag_frames == -11
    assert result.sync_dc_removal_applied
    assert result.input_buffers_unchanged
    assert np.array_equal(baseline, baseline_before)
    assert np.array_equal(candidate, candidate_before)


def test_demo2_cmp_align_003_sync_origins_convert_local_to_reported_lag(operating_point) -> None:
    baseline = _broadband(frames=900)
    candidate = inject_integer_delay(baseline, delay_frames=17, label="origin-delay").candidate

    result = _estimate(
        baseline,
        candidate,
        operating_point,
        baseline_start=29,
        candidate_start=7,
        sync_frames=700,
    )

    assert result.status == "valid"
    assert result.lag_frames == 17
    assert result.local_lag_frames == 39
    assert result.lag_frames == 7 + result.local_lag_frames - 29


def test_demo2_cmp_str_004_short_sync_overlap_is_structured_invalid(operating_point) -> None:
    baseline = _broadband(frames=128)
    result = _estimate(baseline, baseline.copy(), operating_point, sync_frames=48)

    assert result.status == "invalid"
    assert result.reason == "no_lag_passed_energy_and_overlap"
    assert result.valid_lag_count == 0


@pytest.mark.parametrize("delay_frames", [-23, 0, 19])
def test_demo2_sys_anl_001_002_cmp_comp_002_003_005_raw_latency_and_exact_pairs(
    operating_point, delay_frames: int
) -> None:
    baseline = _broadband()
    candidate = inject_integer_delay(
        baseline, delay_frames=delay_frames, label="align-view"
    ).candidate
    alignment = _estimate(baseline, candidate, operating_point)

    application = apply_integer_time_alignment(
        baseline,
        candidate,
        alignment,
        TimeAlignmentRequest(True, ("residual", "gain", "polarity", "dropout")),
        minimum_overlap_frames=MEASUREMENT_MINIMUM_OVERLAP_FRAMES,
    )

    assert alignment.lag_frames == delay_frames
    assert application.status == "applied"
    assert application.views is not None
    assert application.compensation is not None
    assert application.compensation.measured_lag_frames == delay_frames
    assert application.compensation.units == "frames"
    assert np.array_equal(application.views.baseline, application.views.candidate)
    assert application.views.baseline.shape[0] == len(baseline) - abs(delay_frames)
    assert application.views.baseline.shape == application.views.candidate.shape


def test_demo2_cmp_comp_001_disabled_or_ambiguous_alignment_produces_no_views(operating_point) -> None:
    baseline = _broadband()
    valid = _estimate(baseline, baseline.copy(), operating_point)
    disabled = apply_integer_time_alignment(
        baseline,
        baseline.copy(),
        valid,
        TimeAlignmentRequest(False, ()),
        minimum_overlap_frames=64,
    )
    periodic = np.tile(np.array([[0.5], [-0.5]], dtype=np.float32), (256, 1))
    ambiguous = _estimate(periodic, periodic.copy(), operating_point, search_min=-8, search_max=8)
    rejected = apply_integer_time_alignment(
        periodic,
        periodic.copy(),
        ambiguous,
        TimeAlignmentRequest(True, ("residual",)),
        minimum_overlap_frames=64,
    )

    assert disabled.status == "disabled" and disabled.views is None
    assert rejected.status == "rejected_non_valid_alignment" and rejected.views is None
