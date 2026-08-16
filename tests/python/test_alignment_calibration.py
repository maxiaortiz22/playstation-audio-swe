"""Traceable unit tests for the T-CMP-CAL-001 spike, not production behavior."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from tools.alignment_calibration import (
    CalibrationCase,
    LagObservation,
    OperatingPoint,
    _canonical_json,
    _curated_summary,
    _float32_bytes,
    build_candidates,
    build_corpus,
    compute_lag_observations,
    estimate_case,
    evaluate_observations,
    load_config,
    make_case,
    run_experiment,
    validate_corpus_separation,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "calibration" / "t_cmp_cal_001.json"


def _point(**overrides: object) -> OperatingPoint:
    values: dict[str, object] = {
        "id": "test-point",
        "plateau_epsilon": 1e-6,
        "maximum_primary_plateau_width_frames": 2,
        "secondary_exclusion_radius_frames": 1,
        "minimum_primary_abs_correlation": 0.25,
        "minimum_accepted_peak_ratio": 1.01,
        "sync_rms_floor_linear_fs": 1e-8,
        "minimum_overlap_frames": 16,
    }
    values.update(overrides)
    return OperatingPoint.from_mapping(values)


def _observation(lag: int, score: float, *, overlap: int = 128, rms: float = 0.5) -> LagObservation:
    return LagObservation(
        reported_lag_frames=lag,
        local_lag_frames=lag,
        overlap_frames=overlap,
        baseline_rms_linear_fs=rms,
        candidate_rms_linear_fs=rms,
        signed_correlation=score,
    )


@pytest.mark.parametrize("lag", [-64, -23, 0, 41, 64])
def test_t_cmp_cal_001_cmp_align_002_sign_and_boundary_lags(lag: int) -> None:
    case = make_case(
        split="unit", family_id="sign", case_index=0, generator_id="uniform-noise-v1",
        seed=701 + lag, length=640, lag_frames=lag, oracle_class="unique",
        oracle_reason="unit oracle", level=0.5,
    )
    result, _ = estimate_case(case, _point())

    assert result.classification == "valid"
    assert result.reported_lag_frames == lag
    assert result.local_lag_frames == lag


def test_t_cmp_cal_001_cmp_align_005_polarity_preserves_lag_and_signed_peak() -> None:
    normal = make_case(
        split="unit", family_id="polarity", case_index=0, generator_id="lfsr-prbs15-v1",
        seed=77, length=769, lag_frames=29, oracle_class="unique", oracle_reason="unit oracle",
    )
    inverted = replace(normal, case_id="unit-polarity-01", candidate=tuple(-value for value in normal.candidate))

    normal_result, _ = estimate_case(normal, _point())
    inverted_result, _ = estimate_case(inverted, _point())

    assert normal_result.reported_lag_frames == inverted_result.reported_lag_frames == 29
    assert normal_result.signed_primary_correlation == pytest.approx(1.0)
    assert inverted_result.signed_primary_correlation == pytest.approx(-1.0)
    assert inverted_result.primary_abs_correlation == pytest.approx(normal_result.primary_abs_correlation)


def test_t_cmp_cal_001_cmp_align_006_equivalent_peaks_are_ambiguous_even_when_excluded() -> None:
    observations = [_observation(-1, 0.2), _observation(0, 1.0), _observation(1, 1.0), _observation(2, 0.1)]
    point = _point(
        minimum_accepted_peak_ratio=1.0,
        secondary_exclusion_radius_frames=8,
        maximum_primary_plateau_width_frames=8,
    )
    result = evaluate_observations(observations, point)

    assert result.classification == "ambiguous"
    assert result.reason == "equivalent_primary_peaks"
    assert result.reported_lag_frames == 0
    assert result.equivalent_primary_peak_count == 2


def test_t_cmp_cal_001_cmp_align_006_exact_tie_rule_uses_abs_then_lower_signed_lag() -> None:
    observations = [_observation(-2, -0.9), _observation(-1, 0.1), _observation(1, 0.1), _observation(2, 0.9)]
    result = evaluate_observations(observations, _point(secondary_exclusion_radius_frames=0))

    assert result.classification == "ambiguous"
    assert result.reason == "equivalent_primary_peaks"
    assert result.reported_lag_frames == -2
    assert result.signed_primary_correlation == -0.9


def test_t_cmp_cal_001_cmp_align_006_plateau_width_rejection_and_boundary() -> None:
    observations = [
        _observation(-2, 0.2),
        _observation(-1, 0.99995),
        _observation(0, 1.0),
        _observation(1, 0.99996),
        _observation(2, 0.2),
    ]
    rejected = evaluate_observations(
        observations,
        _point(plateau_epsilon=1e-4, maximum_primary_plateau_width_frames=2),
    )
    accepted_width = evaluate_observations(
        observations,
        _point(plateau_epsilon=1e-4, maximum_primary_plateau_width_frames=3),
    )

    assert rejected.classification == "ambiguous"
    assert rejected.reason == "primary_plateau_too_wide"
    assert rejected.primary_plateau_width_frames == 3
    assert accepted_width.reason != "primary_plateau_too_wide"


def test_t_cmp_cal_001_cmp_align_006_secondary_exclusion_is_inclusive_at_radius() -> None:
    observations = [
        _observation(0, 1.0),
        _observation(1, 0.1),
        _observation(2, 0.8),
        _observation(3, 0.9),
        _observation(4, 0.1),
    ]
    radius_two = evaluate_observations(observations, _point(secondary_exclusion_radius_frames=2))
    radius_three = evaluate_observations(observations, _point(secondary_exclusion_radius_frames=3))

    assert radius_two.secondary_peak_lag_frames == 3
    assert radius_two.peak_ratio_value == pytest.approx(1.0 / 0.9)
    assert radius_three.secondary_peak_lag_frames is None
    assert radius_three.peak_ratio_kind == "positive_infinity_no_secondary"


def test_t_cmp_cal_001_cmp_align_002_no_padding_and_lag_dependent_overlap() -> None:
    case = CalibrationCase(
        case_id="unit-overlap-00", split="unit", family_id="overlap", oracle_class="unique",
        oracle_lag_frames=1, oracle_reason="manual pair", generator_id="manual", generator_version="1",
        seed=0, parameters={}, strata={}, baseline=(1.0, 2.0, 3.0), candidate=(0.0, 1.0, 2.0),
        baseline_sync_origin_frames=0, candidate_sync_origin_frames=0,
        baseline_sync_length_frames=3, candidate_sync_length_frames=3,
        search_min_reported_lag_frames=1, search_max_reported_lag_frames=1,
    )
    observation = compute_lag_observations(case)[0]

    assert observation.local_lag_frames == 1
    assert observation.overlap_frames == 2
    assert observation.signed_correlation == pytest.approx(1.0)
    assert observation.baseline_rms_linear_fs == pytest.approx((2.5) ** 0.5)
    assert observation.candidate_rms_linear_fs == pytest.approx((2.5) ** 0.5)


def test_t_cmp_cal_001_cmp_align_002_minimum_overlap_equality_is_valid_and_one_less_is_invalid() -> None:
    point = _point(minimum_overlap_frames=16)
    exact = evaluate_observations([_observation(0, 1.0, overlap=16)], point)
    short = evaluate_observations([_observation(0, 1.0, overlap=15)], point)

    assert exact.classification == "valid"
    assert short.classification == "invalid"
    assert short.reason == "no_lag_passed_energy_and_overlap"


def test_t_cmp_cal_001_cmp_align_006_rms_floor_equality_is_invalid_on_either_input() -> None:
    point = _point(sync_rms_floor_linear_fs=1e-4)
    baseline_equal = LagObservation(0, 0, 64, 1e-4, 0.5, 0.9)
    candidate_equal = LagObservation(0, 0, 64, 0.5, 1e-4, 0.9)

    assert evaluate_observations([baseline_equal], point).classification == "invalid"
    assert evaluate_observations([candidate_equal], point).classification == "invalid"


def test_t_cmp_cal_001_cmp_align_002_sync_origin_conversion_reports_full_buffer_lag() -> None:
    case = make_case(
        split="unit", family_id="origins", case_index=0, generator_id="uniform-noise-v1",
        seed=991, length=887, lag_frames=23, oracle_class="unique", oracle_reason="origin oracle",
        origins=(17, 3),
    )
    result, _ = estimate_case(case, _point())

    assert result.classification == "valid"
    assert result.reported_lag_frames == 23
    assert result.local_lag_frames == 37
    assert result.reported_lag_frames == 3 + result.local_lag_frames - 17


def test_t_cmp_cal_001_cmp_align_007_measurement_buffers_remain_unchanged() -> None:
    case = make_case(
        split="unit", family_id="immutability", case_index=0, generator_id="uniform-noise-v1",
        seed=510, length=521, lag_frames=-37, oracle_class="unique", oracle_reason="immutable oracle",
        origins=(13, 5), polarity=-1, sync_copy_transform="remove_dc",
    )
    before = (
        hashlib.sha256(_float32_bytes(case.baseline)).hexdigest(),
        hashlib.sha256(_float32_bytes(case.candidate)).hexdigest(),
    )
    result, _ = estimate_case(case, _point())
    after = (
        hashlib.sha256(_float32_bytes(case.baseline)).hexdigest(),
        hashlib.sha256(_float32_bytes(case.candidate)).hexdigest(),
    )

    assert result.input_buffers_unchanged
    assert before == after


def test_t_cmp_cal_001_sys_ttv_004_calibration_holdout_are_disjoint() -> None:
    config, _ = load_config(CONFIG_PATH)
    cases = build_corpus(config)
    checks = validate_corpus_separation(cases, config)

    assert set(checks) == {"case_ids", "seeds", "generator_families", "parameter_digests", "pcm_pair_digests"}
    assert all(check["disjoint"] for check in checks.values())
    assert {case.seed for case in cases if case.split == "calibration"}.isdisjoint(
        {case.seed for case in cases if case.split == "holdout"}
    )


def test_t_cmp_cal_001_sys_ttv_004_holdout_candidate_set_is_frozen_in_config() -> None:
    config, _ = load_config(CONFIG_PATH)
    candidates = build_candidates(config)
    digest_before = hashlib.sha256(_canonical_json([candidate.__dict__ for candidate in candidates])).hexdigest()
    build_corpus(config)
    digest_after = hashlib.sha256(_canonical_json([candidate.__dict__ for candidate in candidates])).hexdigest()

    assert len(candidates) == 3
    assert digest_before == digest_after


def test_t_cmp_cal_001_sys_ttv_004_reproduction_is_deterministic() -> None:
    first = _curated_summary(run_experiment(CONFIG_PATH))
    second = _curated_summary(run_experiment(CONFIG_PATH))

    assert json.loads(json.dumps(first, allow_nan=False, sort_keys=True)) == json.loads(
        json.dumps(second, allow_nan=False, sort_keys=True)
    )
