"""M1 integer alignment and focused DEMO-2 audio measurements.

This module intentionally contains no policy evaluation or reporting engine.
It produces structured, policy-ready observations while keeping raw latency,
declared time compensation, and compensated measurements separate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np


AlignmentStatus = Literal["valid", "ambiguous", "invalid"]


class AnalysisInputError(ValueError):
    """An analysis parameter violates its explicit domain contract."""


class AlignmentPolicyError(ValueError):
    """The versioned M1 alignment decision is missing or inconsistent."""


@dataclass(frozen=True)
class AudioDescription:
    sample_rate_hz: int
    channel_labels: tuple[str, ...]
    layout: str


@dataclass(frozen=True)
class StructuralValidationConfig:
    minimum_overlap_frames: int
    rationale: str


@dataclass(frozen=True)
class StructuralIssue:
    code: str
    message: str
    buffer: str | None = None
    frame_index: int | None = None
    channel_index: int | None = None
    channel_label: str | None = None


@dataclass(frozen=True)
class StructuralValidationResult:
    status: Literal["valid", "invalid"]
    issues: tuple[StructuralIssue, ...]
    input_buffers_unchanged: bool


@dataclass(frozen=True)
class ValidatedAlignment:
    structural: StructuralValidationResult
    alignment: AlignmentResult | None


@dataclass(frozen=True)
class AlignmentOperatingPoint:
    id: str
    decision_id: str
    decision_version: str
    scope: str
    source_sha256: str
    selected_operating_point_digest: str
    plateau_epsilon: float
    maximum_primary_plateau_width_frames: int
    secondary_exclusion_radius_frames: int
    minimum_primary_abs_correlation: float
    minimum_accepted_peak_ratio: float
    sync_rms_floor_linear_fs: float
    minimum_overlap_frames: int
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class AlignmentRequest:
    search_min_lag_frames: int
    search_max_lag_frames: int
    baseline_sync_start_frame: int
    baseline_sync_end_frame: int
    candidate_sync_start_frame: int
    candidate_sync_end_frame: int
    sync_channel_index: int
    remove_dc_from_sync: bool


@dataclass(frozen=True)
class LagObservation:
    reported_lag_frames: int
    local_lag_frames: int
    overlap_frames: int
    baseline_rms_linear_fs: float | None
    candidate_rms_linear_fs: float | None
    signed_correlation: float | None


@dataclass(frozen=True)
class AlignmentResult:
    status: AlignmentStatus
    reason: str
    lag_frames: int | None
    latency_ms: float | None
    local_lag_frames: int | None
    signed_primary_correlation: float | None
    primary_abs_correlation: float | None
    primary_plateau_min_lag_frames: int | None
    primary_plateau_max_lag_frames: int | None
    primary_plateau_width_frames: int | None
    equivalent_primary_peak_count: int
    secondary_peak_lag_frames: int | None
    secondary_peak_abs_correlation: float | None
    secondary_peak_present: bool
    peak_ratio_value: float | None
    peak_ratio_kind: str
    search_min_lag_frames: int
    search_max_lag_frames: int
    valid_lag_count: int
    selected_overlap_frames: int | None
    sync_dc_removal_applied: bool
    operating_point_id: str
    operating_point_source_sha256: str
    input_buffers_unchanged: bool
    observations: tuple[LagObservation, ...]


@dataclass(frozen=True)
class TimeAlignmentRequest:
    enabled: bool
    affected_metrics: tuple[str, ...]


@dataclass(frozen=True)
class TimeCompensationRecord:
    type: str
    method: str
    measured_lag_frames: int
    units: str
    affected_metrics: tuple[str, ...]


@dataclass(frozen=True)
class AlignedViews:
    baseline: np.ndarray
    candidate: np.ndarray
    baseline_start_frame: int
    baseline_end_frame: int
    candidate_start_frame: int
    candidate_end_frame: int


@dataclass(frozen=True)
class AlignmentApplication:
    status: str
    views: AlignedViews | None
    compensation: TimeCompensationRecord | None


@dataclass(frozen=True)
class ResidualMetric:
    channel_index: int
    peak_linear_fs: float
    rms_linear_fs: float
    rms_dbfs: float
    rms_floor_linear_fs: float
    rms_was_floored: bool


@dataclass(frozen=True)
class GainMetric:
    channel_index: int
    baseline_rms_linear_fs: float
    candidate_rms_linear_fs: float
    gain_delta_db: float
    rms_floor_linear_fs: float
    baseline_was_floored: bool
    candidate_was_floored: bool


@dataclass(frozen=True)
class PolarityMetric:
    channel_index: int
    diagnosis: Literal["normal", "inverted", "indeterminate"]
    signed_correlation: float | None
    minimum_abs_correlation: float
    signal_rms_floor_linear_fs: float


@dataclass(frozen=True)
class ChannelMappingConfig:
    minimum_mapping_margin: float
    signal_rms_floor_linear_fs: float
    rationale: str


@dataclass(frozen=True)
class StereoChannelMapping:
    status: Literal["confident", "ambiguous", "invalid"]
    observed_to_expected_indices: tuple[int, int] | None
    observed_to_expected_labels: tuple[str, str] | None
    score_matrix: tuple[tuple[float | None, float | None], tuple[float | None, float | None]]
    mapping_score: float | None
    mapping_confidence: float | None
    mapping_margin: float | None
    minimum_mapping_margin: float
    scoring_method: str


@dataclass(frozen=True)
class DropoutConfig:
    active_reference_floor_linear_fs: float
    near_silence_floor_linear_fs: float
    minimum_duration_frames: int
    rationale: str


@dataclass(frozen=True)
class DropoutEvent:
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    duration_frames: int
    duration_seconds: float
    candidate_start_frame: int
    candidate_end_frame: int
    channel_indices: tuple[int, ...]
    classification: Literal["exact_zero", "near_silence"]


_PARAMETER_NAMES = (
    "plateau_epsilon",
    "maximum_primary_plateau_width_frames",
    "secondary_exclusion_radius_frames",
    "minimum_primary_abs_correlation",
    "minimum_accepted_peak_ratio",
    "sync_rms_floor_linear_fs",
    "minimum_overlap_frames",
)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: object, name: str) -> int:
    if not _is_int(value) or value <= 0:
        raise AnalysisInputError(f"{name} must be a positive integer")
    return value


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisInputError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise AnalysisInputError(f"{name} must be finite")
    return result


def _rationale(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisInputError("threshold rationale must be a non-empty string")


def _snapshot(pcm: np.ndarray) -> tuple[tuple[int, ...], str, tuple[int, ...], bytes]:
    return pcm.shape, pcm.dtype.str, pcm.strides, pcm.tobytes(order="A")


def _first_non_finite(
    pcm: np.ndarray, labels: tuple[str, ...]
) -> tuple[int, int, str | None] | None:
    locations = np.argwhere(~np.isfinite(pcm))
    if locations.size == 0:
        return None
    frame, channel = (int(value) for value in locations[0])
    label = labels[channel] if channel < len(labels) else None
    return frame, channel, label


def validate_structure(
    baseline: np.ndarray,
    candidate: np.ndarray,
    baseline_description: AudioDescription,
    candidate_description: AudioDescription,
    config: StructuralValidationConfig,
) -> StructuralValidationResult:
    """Validate format and first non-finite locations before similarity scoring."""

    if not isinstance(baseline, np.ndarray) or not isinstance(candidate, np.ndarray):
        raise AnalysisInputError("baseline and candidate must be NumPy arrays")
    minimum_overlap = _positive_int(
        config.minimum_overlap_frames, "minimum_overlap_frames"
    )
    _rationale(config.rationale)
    before = (_snapshot(baseline), _snapshot(candidate))
    issues: list[StructuralIssue] = []

    for name, pcm, description in (
        ("baseline", baseline, baseline_description),
        ("candidate", candidate, candidate_description),
    ):
        if not _is_int(description.sample_rate_hz) or description.sample_rate_hz <= 0:
            issues.append(StructuralIssue("invalid_sample_rate", "sample rate must be a positive integer Hz", name))
        if description.layout != "frames_channels_interleaved":
            issues.append(StructuralIssue("unsupported_layout", "layout must be frames_channels_interleaved", name))
        if pcm.dtype != np.dtype(np.float32):
            issues.append(StructuralIssue("unsupported_dtype", "dtype must be float32", name))
        if pcm.ndim != 2:
            issues.append(StructuralIssue("unsupported_rank", "rank must be 2 with shape (frames, channels)", name))
            continue
        if not pcm.flags.c_contiguous:
            issues.append(StructuralIssue("non_contiguous_layout", "PCM must be C-contiguous", name))
        if pcm.shape[0] == 0 or pcm.shape[1] == 0:
            issues.append(StructuralIssue("empty_input", "PCM must contain frames and channels", name))
        if len(description.channel_labels) != pcm.shape[1]:
            issues.append(StructuralIssue("channel_label_count_mismatch", "channel label count must equal PCM channel count", name))
        elif any(not isinstance(label, str) or not label for label in description.channel_labels):
            issues.append(StructuralIssue("invalid_channel_label", "channel labels must be non-empty strings", name))
        elif len(set(description.channel_labels)) != len(description.channel_labels):
            issues.append(StructuralIssue("duplicate_channel_label", "channel labels must be unique", name))
        if pcm.dtype == np.dtype(np.float32):
            non_finite = _first_non_finite(pcm, description.channel_labels)
            if non_finite is not None:
                frame, channel, label = non_finite
                issues.append(
                    StructuralIssue(
                        "non_finite_sample",
                        "PCM contains NaN or infinity",
                        name,
                        frame,
                        channel,
                        label,
                    )
                )

    if baseline_description.sample_rate_hz != candidate_description.sample_rate_hz:
        issues.append(StructuralIssue("sample_rate_mismatch", "sample rates differ; silent resampling is prohibited"))
    if baseline.ndim == candidate.ndim == 2:
        if baseline.shape[1] != candidate.shape[1]:
            issues.append(StructuralIssue("channel_count_mismatch", "baseline and candidate channel counts differ"))
        if baseline_description.channel_labels != candidate_description.channel_labels:
            issues.append(StructuralIssue("channel_label_mismatch", "baseline and candidate channel labels differ"))
        if min(baseline.shape[0], candidate.shape[0]) < minimum_overlap:
            issues.append(
                StructuralIssue(
                    "insufficient_unaligned_overlap",
                    f"maximum unaligned overlap is shorter than {minimum_overlap} frames",
                )
            )

    after = (_snapshot(baseline), _snapshot(candidate))
    unchanged = before == after
    if not unchanged:
        issues.append(StructuralIssue("input_buffer_mutation", "structural validation modified an input buffer"))
    return StructuralValidationResult(
        status="valid" if not issues else "invalid",
        issues=tuple(issues),
        input_buffers_unchanged=unchanged,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AlignmentPolicyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_non_finite(token: str) -> None:
    raise AlignmentPolicyError(f"non-finite JSON number token {token!r}")


def load_m1_alignment_operating_point(path: str | Path) -> AlignmentOperatingPoint:
    """Load the explicit OP-B decision; there is no implicit path or fallback."""

    raw = Path(path).read_bytes()
    try:
        document = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AlignmentPolicyError(f"invalid strict UTF-8 JSON policy: {error}") from error
    if not isinstance(document, dict):
        raise AlignmentPolicyError("alignment decision root must be an object")
    required_decision = {
        "decision_id": "M1-ALIGNMENT-OP-001",
        "selected_operating_point_id": "OP-B-intermediate",
        "selection_method": "explicit_human_owner_decision",
        "automatic_selection": False,
        "fallback_operating_point_id": None,
        "scope": "m1-manifest-policy-only",
        "universal_default": False,
    }
    for key, expected in required_decision.items():
        if document.get(key) != expected:
            raise AlignmentPolicyError(f"{key} does not identify the accepted M1 OP-B decision")
    parameters = document.get("selected_parameters")
    if not isinstance(parameters, dict) or set(parameters) != set(_PARAMETER_NAMES):
        raise AlignmentPolicyError("selected_parameters must contain the exact OP-B parameter set")
    rationale = document.get("rationale")
    if not isinstance(rationale, list) or not rationale or not all(
        isinstance(item, str) and item.strip() for item in rationale
    ):
        raise AlignmentPolicyError("alignment decision rationale must be a non-empty string list")

    def policy_float(name: str) -> float:
        value = parameters[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AlignmentPolicyError(f"{name} must be a JSON number without coercion")
        return float(value)

    def policy_int(name: str) -> int:
        value = parameters[name]
        if not _is_int(value):
            raise AlignmentPolicyError(f"{name} must be a JSON integer without coercion")
        return value

    try:
        point = AlignmentOperatingPoint(
            id=document["selected_operating_point_id"],
            decision_id=document["decision_id"],
            decision_version=document["decision_version"],
            scope=document["scope"],
            source_sha256=hashlib.sha256(raw).hexdigest(),
            selected_operating_point_digest=document["selected_operating_point_digest"],
            plateau_epsilon=policy_float("plateau_epsilon"),
            maximum_primary_plateau_width_frames=policy_int("maximum_primary_plateau_width_frames"),
            secondary_exclusion_radius_frames=policy_int("secondary_exclusion_radius_frames"),
            minimum_primary_abs_correlation=policy_float("minimum_primary_abs_correlation"),
            minimum_accepted_peak_ratio=policy_float("minimum_accepted_peak_ratio"),
            sync_rms_floor_linear_fs=policy_float("sync_rms_floor_linear_fs"),
            minimum_overlap_frames=policy_int("minimum_overlap_frames"),
            rationale=tuple(rationale),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AlignmentPolicyError(f"malformed alignment decision: {error}") from error
    _validate_operating_point(point)
    digest_input = {"id": point.id, **{name: parameters[name] for name in _PARAMETER_NAMES}}
    digest = hashlib.sha256(
        (json.dumps(digest_input, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()
    if digest != point.selected_operating_point_digest:
        raise AlignmentPolicyError("selected operating-point digest does not match its parameters")
    return point


def _validate_operating_point(point: AlignmentOperatingPoint, search_span_frames: int | None = None) -> None:
    finite = (
        point.plateau_epsilon,
        point.minimum_primary_abs_correlation,
        point.minimum_accepted_peak_ratio,
        point.sync_rms_floor_linear_fs,
    )
    if not all(math.isfinite(value) for value in finite):
        raise AlignmentPolicyError("operating-point numeric values must be finite")
    if not 0.0 <= point.plateau_epsilon < 1.0:
        raise AlignmentPolicyError("plateau_epsilon must be in [0, 1)")
    if not _is_int(point.maximum_primary_plateau_width_frames) or point.maximum_primary_plateau_width_frames <= 0:
        raise AlignmentPolicyError("maximum plateau width must be positive integer frames")
    if not _is_int(point.secondary_exclusion_radius_frames) or point.secondary_exclusion_radius_frames < 0:
        raise AlignmentPolicyError("secondary exclusion radius must be non-negative integer frames")
    if search_span_frames is not None and point.secondary_exclusion_radius_frames >= search_span_frames:
        raise AlignmentPolicyError("secondary exclusion radius must be smaller than the lag search span")
    if not 0.0 < point.minimum_primary_abs_correlation <= 1.0:
        raise AlignmentPolicyError("minimum primary correlation must be in (0, 1]")
    if point.minimum_accepted_peak_ratio < 1.0:
        raise AlignmentPolicyError("minimum accepted peak ratio must be at least 1")
    if point.sync_rms_floor_linear_fs < 0.0:
        raise AlignmentPolicyError("sync RMS floor must be non-negative")
    if not _is_int(point.minimum_overlap_frames) or point.minimum_overlap_frames <= 0:
        raise AlignmentPolicyError("minimum overlap must be positive integer frames")


def _alignment_pcm(pcm: np.ndarray, name: str) -> None:
    if not isinstance(pcm, np.ndarray) or pcm.dtype != np.dtype(np.float32) or pcm.ndim != 2:
        raise AnalysisInputError(f"{name} must be a rank-2 float32 NumPy array")
    if not pcm.flags.c_contiguous:
        raise AnalysisInputError(f"{name} must be C-contiguous")
    if pcm.shape[0] == 0 or pcm.shape[1] == 0:
        raise AnalysisInputError(f"{name} must not be empty")
    non_finite = _first_non_finite(pcm, ())
    if non_finite is not None:
        raise AnalysisInputError(f"{name} contains a non-finite sample at frame {non_finite[0]}, channel {non_finite[1]}")


def estimate_integer_alignment(
    baseline: np.ndarray,
    candidate: np.ndarray,
    *,
    sample_rate_hz: int,
    request: AlignmentRequest,
    operating_point: AlignmentOperatingPoint,
) -> AlignmentResult:
    """Estimate signed integer lag using lag-dependent, non-padded overlap."""

    _alignment_pcm(baseline, "baseline")
    _alignment_pcm(candidate, "candidate")
    rate = _positive_int(sample_rate_hz, "sample_rate_hz")
    if baseline.shape[1] != candidate.shape[1]:
        raise AnalysisInputError("baseline and candidate channel counts must match")
    if not _is_int(request.search_min_lag_frames) or not _is_int(request.search_max_lag_frames):
        raise AnalysisInputError("lag search bounds must be integer frames")
    if request.search_min_lag_frames > request.search_max_lag_frames:
        raise AnalysisInputError("minimum lag must not exceed maximum lag")
    span = request.search_max_lag_frames - request.search_min_lag_frames
    _validate_operating_point(operating_point, span)
    if not isinstance(request.remove_dc_from_sync, bool):
        raise AnalysisInputError("remove_dc_from_sync must be Boolean")
    channel = request.sync_channel_index
    if not _is_int(channel) or channel < 0 or channel >= baseline.shape[1]:
        raise AnalysisInputError("sync_channel_index is outside the common channel range")
    for name, start, end, frames in (
        ("baseline", request.baseline_sync_start_frame, request.baseline_sync_end_frame, baseline.shape[0]),
        ("candidate", request.candidate_sync_start_frame, request.candidate_sync_end_frame, candidate.shape[0]),
    ):
        if not _is_int(start) or not _is_int(end) or not 0 <= start < end <= frames:
            raise AnalysisInputError(f"{name} sync interval must satisfy 0 <= start < end <= frame_count")

    before = (_snapshot(baseline), _snapshot(candidate))
    baseline_sync = baseline[
        request.baseline_sync_start_frame : request.baseline_sync_end_frame, channel
    ].astype(np.float64, copy=True)
    candidate_sync = candidate[
        request.candidate_sync_start_frame : request.candidate_sync_end_frame, channel
    ].astype(np.float64, copy=True)
    if request.remove_dc_from_sync:
        baseline_sync -= float(np.mean(baseline_sync, dtype=np.float64))
        candidate_sync -= float(np.mean(candidate_sync, dtype=np.float64))

    observations: list[LagObservation] = []
    for reported_lag in range(request.search_min_lag_frames, request.search_max_lag_frames + 1):
        local_lag = (
            reported_lag
            + request.baseline_sync_start_frame
            - request.candidate_sync_start_frame
        )
        start = max(0, -local_lag)
        stop = min(len(baseline_sync), len(candidate_sync) - local_lag)
        overlap = max(0, stop - start)
        if overlap == 0:
            observations.append(LagObservation(reported_lag, local_lag, 0, None, None, None))
            continue
        baseline_overlap = baseline_sync[start:stop]
        candidate_overlap = candidate_sync[start + local_lag : stop + local_lag]
        baseline_energy = float(np.sum(baseline_overlap * baseline_overlap, dtype=np.float64))
        candidate_energy = float(np.sum(candidate_overlap * candidate_overlap, dtype=np.float64))
        baseline_rms = math.sqrt(baseline_energy / overlap)
        candidate_rms = math.sqrt(candidate_energy / overlap)
        denominator = math.sqrt(baseline_energy * candidate_energy)
        correlation = (
            float(np.sum(baseline_overlap * candidate_overlap, dtype=np.float64)) / denominator
            if denominator > 0.0
            else None
        )
        if correlation is not None and abs(correlation) > 1.0:
            if abs(correlation) <= 1.0 + 1e-12:
                correlation = math.copysign(1.0, correlation)
            else:
                raise ArithmeticError(f"non-physical correlation at lag {reported_lag}: {correlation}")
        observations.append(
            LagObservation(
                reported_lag,
                local_lag,
                overlap,
                baseline_rms,
                candidate_rms,
                correlation,
            )
        )

    unchanged = before == (_snapshot(baseline), _snapshot(candidate))
    return _evaluate_alignment(
        observations,
        sample_rate_hz=rate,
        request=request,
        operating_point=operating_point,
        inputs_unchanged=unchanged,
    )


def validate_and_estimate_integer_alignment(
    baseline: np.ndarray,
    candidate: np.ndarray,
    *,
    baseline_description: AudioDescription,
    candidate_description: AudioDescription,
    structural_config: StructuralValidationConfig,
    alignment_request: AlignmentRequest,
    operating_point: AlignmentOperatingPoint,
) -> ValidatedAlignment:
    """Run the mandatory structural gate before any correlation is computed."""

    structural = validate_structure(
        baseline,
        candidate,
        baseline_description,
        candidate_description,
        structural_config,
    )
    if structural.status != "valid":
        return ValidatedAlignment(structural, None)
    alignment = estimate_integer_alignment(
        baseline,
        candidate,
        sample_rate_hz=baseline_description.sample_rate_hz,
        request=alignment_request,
        operating_point=operating_point,
    )
    return ValidatedAlignment(structural, alignment)


def _evaluate_alignment(
    observations: Sequence[LagObservation],
    *,
    sample_rate_hz: int,
    request: AlignmentRequest,
    operating_point: AlignmentOperatingPoint,
    inputs_unchanged: bool,
) -> AlignmentResult:
    valid = [
        item
        for item in observations
        if item.overlap_frames >= operating_point.minimum_overlap_frames
        and item.baseline_rms_linear_fs is not None
        and item.candidate_rms_linear_fs is not None
        and item.baseline_rms_linear_fs > operating_point.sync_rms_floor_linear_fs
        and item.candidate_rms_linear_fs > operating_point.sync_rms_floor_linear_fs
        and item.signed_correlation is not None
    ]

    def result(status: AlignmentStatus, reason: str, **values: Any) -> AlignmentResult:
        empty = {
            "lag_frames": None,
            "latency_ms": None,
            "local_lag_frames": None,
            "signed_primary_correlation": None,
            "primary_abs_correlation": None,
            "primary_plateau_min_lag_frames": None,
            "primary_plateau_max_lag_frames": None,
            "primary_plateau_width_frames": None,
            "equivalent_primary_peak_count": 0,
            "secondary_peak_lag_frames": None,
            "secondary_peak_abs_correlation": None,
            "secondary_peak_present": False,
            "peak_ratio_value": None,
            "peak_ratio_kind": "unavailable",
            "valid_lag_count": len(valid),
            "selected_overlap_frames": None,
        }
        empty.update(values)
        return AlignmentResult(
            status=status,
            reason=reason,
            search_min_lag_frames=request.search_min_lag_frames,
            search_max_lag_frames=request.search_max_lag_frames,
            sync_dc_removal_applied=request.remove_dc_from_sync,
            operating_point_id=operating_point.id,
            operating_point_source_sha256=operating_point.source_sha256,
            input_buffers_unchanged=inputs_unchanged,
            observations=tuple(observations),
            **empty,
        )

    if not valid:
        return result("invalid", "no_lag_passed_energy_and_overlap")

    def tie_key(item: LagObservation) -> tuple[float, int, int]:
        assert item.signed_correlation is not None
        return (-abs(item.signed_correlation), abs(item.reported_lag_frames), item.reported_lag_frames)

    representative = min(valid, key=tie_key)
    assert representative.signed_correlation is not None
    primary_score = abs(representative.signed_correlation)
    exact_maxima = [item for item in valid if abs(item.signed_correlation or 0.0) == primary_score]
    by_lag = {item.reported_lag_frames: item for item in valid}
    plateau_lags = {representative.reported_lag_frames}
    for direction in (-1, 1):
        lag = representative.reported_lag_frames + direction
        while lag in by_lag:
            score = abs(by_lag[lag].signed_correlation or 0.0)
            if primary_score - score > operating_point.plateau_epsilon:
                break
            plateau_lags.add(lag)
            lag += direction
    plateau_min = min(plateau_lags)
    plateau_max = max(plateau_lags)
    plateau_width = plateau_max - plateau_min + 1
    local_peaks: list[LagObservation] = []
    for item in valid:
        score = abs(item.signed_correlation or 0.0)
        left = by_lag.get(item.reported_lag_frames - 1)
        right = by_lag.get(item.reported_lag_frames + 1)
        if left is not None and score < abs(left.signed_correlation or 0.0):
            continue
        if right is not None and score < abs(right.signed_correlation or 0.0):
            continue
        local_peaks.append(item)
    exclusion_min = plateau_min - operating_point.secondary_exclusion_radius_frames
    exclusion_max = plateau_max + operating_point.secondary_exclusion_radius_frames
    secondary_candidates = [
        item
        for item in local_peaks
        if item.reported_lag_frames < exclusion_min
        or item.reported_lag_frames > exclusion_max
    ]
    secondary = min(secondary_candidates, key=tie_key) if secondary_candidates else None
    secondary_score = abs(secondary.signed_correlation or 0.0) if secondary else None
    if secondary is None:
        ratio = None
        ratio_kind = "positive_infinity_no_secondary"
    elif secondary_score == 0.0:
        ratio = None
        ratio_kind = "degenerate_zero_secondary"
    else:
        ratio = primary_score / secondary_score
        ratio_kind = "finite"
    common = {
        "lag_frames": representative.reported_lag_frames,
        "latency_ms": 1000.0 * representative.reported_lag_frames / sample_rate_hz,
        "local_lag_frames": representative.local_lag_frames,
        "signed_primary_correlation": representative.signed_correlation,
        "primary_abs_correlation": primary_score,
        "primary_plateau_min_lag_frames": plateau_min,
        "primary_plateau_max_lag_frames": plateau_max,
        "primary_plateau_width_frames": plateau_width,
        "equivalent_primary_peak_count": len(exact_maxima),
        "secondary_peak_lag_frames": secondary.reported_lag_frames if secondary else None,
        "secondary_peak_abs_correlation": secondary_score,
        "secondary_peak_present": secondary is not None,
        "peak_ratio_value": ratio,
        "peak_ratio_kind": ratio_kind,
        "selected_overlap_frames": representative.overlap_frames,
    }
    if not inputs_unchanged:
        return result("invalid", "input_buffer_mutation", **common)
    if primary_score < operating_point.minimum_primary_abs_correlation:
        return result("invalid", "primary_below_minimum", **common)
    if len(exact_maxima) > 1:
        return result("ambiguous", "equivalent_primary_peaks", **common)
    if plateau_width > operating_point.maximum_primary_plateau_width_frames:
        return result("ambiguous", "primary_plateau_too_wide", **common)
    if ratio_kind == "degenerate_zero_secondary":
        return result("invalid", "degenerate_zero_secondary", **common)
    if ratio is not None and ratio < operating_point.minimum_accepted_peak_ratio:
        return result("ambiguous", "peak_ratio_below_minimum", **common)
    return result("valid", "accepted", **common)


def apply_integer_time_alignment(
    baseline: np.ndarray,
    candidate: np.ndarray,
    alignment: AlignmentResult,
    request: TimeAlignmentRequest,
    *,
    minimum_overlap_frames: int,
) -> AlignmentApplication:
    """Create exact paired measurement views only for declared, valid alignment."""

    _alignment_pcm(baseline, "baseline")
    _alignment_pcm(candidate, "candidate")
    minimum_overlap = _positive_int(minimum_overlap_frames, "minimum_overlap_frames")
    if not isinstance(request.enabled, bool):
        raise AnalysisInputError("time alignment enabled flag must be Boolean")
    if not request.enabled:
        return AlignmentApplication("disabled", None, None)
    if not request.affected_metrics or any(not isinstance(item, str) or not item for item in request.affected_metrics):
        raise AnalysisInputError("enabled time alignment requires named affected metrics")
    if alignment.status != "valid" or alignment.lag_frames is None:
        return AlignmentApplication("rejected_non_valid_alignment", None, None)
    lag = alignment.lag_frames
    baseline_start = max(0, -lag)
    baseline_end = min(baseline.shape[0], candidate.shape[0] - lag)
    overlap = max(0, baseline_end - baseline_start)
    if overlap < minimum_overlap:
        return AlignmentApplication("invalid_insufficient_measurement_overlap", None, None)
    candidate_start = baseline_start + lag
    candidate_end = baseline_end + lag
    views = AlignedViews(
        baseline=baseline[baseline_start:baseline_end, :],
        candidate=candidate[candidate_start:candidate_end, :],
        baseline_start_frame=baseline_start,
        baseline_end_frame=baseline_end,
        candidate_start_frame=candidate_start,
        candidate_end_frame=candidate_end,
    )
    return AlignmentApplication(
        "applied",
        views,
        TimeCompensationRecord(
            type="integer_time_alignment",
            method="measured_integer_lag_valid_overlap",
            measured_lag_frames=lag,
            units="frames",
            affected_metrics=request.affected_metrics,
        ),
    )


def _paired_views(views: AlignedViews) -> None:
    _alignment_pcm(views.baseline, "aligned baseline")
    _alignment_pcm(views.candidate, "aligned candidate")
    if views.baseline.shape != views.candidate.shape:
        raise AnalysisInputError("aligned views must contain exactly paired shapes")


def compute_residual_metrics(
    views: AlignedViews, *, rms_floor_linear_fs: float, rationale: str
) -> tuple[ResidualMetric, ...]:
    """Compute per-channel absolute residual peak and RMS without normalization."""

    _paired_views(views)
    floor = _finite_number(rms_floor_linear_fs, "rms_floor_linear_fs")
    if floor <= 0.0:
        raise AnalysisInputError("residual RMS floor must be greater than zero")
    _rationale(rationale)
    residual = views.candidate.astype(np.float64) - views.baseline.astype(np.float64)
    metrics: list[ResidualMetric] = []
    for channel in range(residual.shape[1]):
        values = residual[:, channel]
        peak = float(np.max(np.abs(values)))
        rms = math.sqrt(float(np.mean(values * values, dtype=np.float64)))
        metrics.append(
            ResidualMetric(
                channel,
                peak,
                rms,
                20.0 * math.log10(max(rms, floor)),
                floor,
                rms < floor,
            )
        )
    return tuple(metrics)


def compute_gain_metrics(
    views: AlignedViews, *, rms_floor_linear_fs: float, rationale: str
) -> tuple[GainMetric, ...]:
    """Measure candidate/reference RMS level ratio per channel in dB."""

    _paired_views(views)
    floor = _finite_number(rms_floor_linear_fs, "rms_floor_linear_fs")
    if floor <= 0.0:
        raise AnalysisInputError("gain RMS floor must be greater than zero")
    _rationale(rationale)
    metrics: list[GainMetric] = []
    for channel in range(views.baseline.shape[1]):
        baseline_values = views.baseline[:, channel].astype(np.float64)
        candidate_values = views.candidate[:, channel].astype(np.float64)
        baseline_rms = math.sqrt(float(np.mean(baseline_values * baseline_values, dtype=np.float64)))
        candidate_rms = math.sqrt(float(np.mean(candidate_values * candidate_values, dtype=np.float64)))
        metrics.append(
            GainMetric(
                channel,
                baseline_rms,
                candidate_rms,
                20.0 * math.log10(max(candidate_rms, floor) / max(baseline_rms, floor)),
                floor,
                baseline_rms < floor,
                candidate_rms < floor,
            )
        )
    return tuple(metrics)


def diagnose_polarity(
    views: AlignedViews,
    *,
    signal_rms_floor_linear_fs: float,
    minimum_abs_correlation: float,
    rationale: str,
) -> tuple[PolarityMetric, ...]:
    """Diagnose polarity separately from residual magnitude and gain."""

    _paired_views(views)
    floor = _finite_number(signal_rms_floor_linear_fs, "signal_rms_floor_linear_fs")
    minimum = _finite_number(minimum_abs_correlation, "minimum_abs_correlation")
    if floor < 0.0 or not 0.0 < minimum <= 1.0:
        raise AnalysisInputError("polarity floors require RMS >= 0 and correlation in (0, 1]")
    _rationale(rationale)
    metrics: list[PolarityMetric] = []
    for channel in range(views.baseline.shape[1]):
        baseline_values = views.baseline[:, channel].astype(np.float64)
        candidate_values = views.candidate[:, channel].astype(np.float64)
        baseline_energy = float(np.sum(baseline_values * baseline_values, dtype=np.float64))
        candidate_energy = float(np.sum(candidate_values * candidate_values, dtype=np.float64))
        baseline_rms = math.sqrt(baseline_energy / len(baseline_values))
        candidate_rms = math.sqrt(candidate_energy / len(candidate_values))
        if baseline_rms <= floor or candidate_rms <= floor:
            correlation = None
            diagnosis: Literal["normal", "inverted", "indeterminate"] = "indeterminate"
        else:
            correlation = float(np.sum(baseline_values * candidate_values, dtype=np.float64)) / math.sqrt(
                baseline_energy * candidate_energy
            )
            if correlation >= minimum:
                diagnosis = "normal"
            elif correlation <= -minimum:
                diagnosis = "inverted"
            else:
                diagnosis = "indeterminate"
        metrics.append(PolarityMetric(channel, diagnosis, correlation, minimum, floor))
    return tuple(metrics)


def analyze_stereo_channel_mapping(
    views: AlignedViews,
    *,
    expected_labels: tuple[str, str],
    config: ChannelMappingConfig,
) -> StereoChannelMapping:
    """Score both stereo permutations using absolute normalized correlation.

    Mapping score is the mean assigned-channel score; confidence is the weakest
    assigned-channel score; margin is best permutation score minus runner-up.
    """

    _paired_views(views)
    if views.baseline.shape[1] != 2 or len(expected_labels) != 2 or len(set(expected_labels)) != 2:
        raise AnalysisInputError("stereo mapping requires two channels and two unique expected labels")
    margin_minimum = _finite_number(config.minimum_mapping_margin, "minimum_mapping_margin")
    floor = _finite_number(config.signal_rms_floor_linear_fs, "signal_rms_floor_linear_fs")
    if not 0.0 <= margin_minimum <= 1.0 or floor < 0.0:
        raise AnalysisInputError("mapping margin must be in [0, 1] and RMS floor non-negative")
    _rationale(config.rationale)
    scores: list[list[float | None]] = [[None, None], [None, None]]
    for expected in range(2):
        baseline_values = views.baseline[:, expected].astype(np.float64)
        baseline_energy = float(np.sum(baseline_values * baseline_values, dtype=np.float64))
        baseline_rms = math.sqrt(baseline_energy / len(baseline_values))
        for observed in range(2):
            candidate_values = views.candidate[:, observed].astype(np.float64)
            candidate_energy = float(np.sum(candidate_values * candidate_values, dtype=np.float64))
            candidate_rms = math.sqrt(candidate_energy / len(candidate_values))
            if baseline_rms <= floor or candidate_rms <= floor:
                continue
            signed = float(np.sum(baseline_values * candidate_values, dtype=np.float64)) / math.sqrt(
                baseline_energy * candidate_energy
            )
            scores[expected][observed] = abs(signed)
    matrix = (tuple(scores[0]), tuple(scores[1]))
    if any(value is None for row in scores for value in row):
        return StereoChannelMapping(
            "invalid", None, None, matrix, None, None, None, margin_minimum,
            "absolute normalized cross-correlation; mean one-to-one permutation score",
        )
    numeric = [[float(value) for value in row] for row in scores]
    identity_channels = (numeric[0][0], numeric[1][1])
    swapped_channels = (numeric[1][0], numeric[0][1])
    identity_score = sum(identity_channels) / 2.0
    swapped_score = sum(swapped_channels) / 2.0
    if identity_score >= swapped_score:
        mapping = (0, 1)
        assigned = identity_channels
        best, alternative = identity_score, swapped_score
    else:
        mapping = (1, 0)
        assigned = swapped_channels
        best, alternative = swapped_score, identity_score
    margin = best - alternative
    status: Literal["confident", "ambiguous", "invalid"] = (
        "confident" if margin >= margin_minimum else "ambiguous"
    )
    return StereoChannelMapping(
        status,
        mapping,
        (expected_labels[mapping[0]], expected_labels[mapping[1]]),
        matrix,
        best,
        min(assigned),
        margin,
        margin_minimum,
        "absolute normalized cross-correlation; mean one-to-one permutation score",
    )


def detect_dropouts(
    views: AlignedViews,
    *,
    sample_rate_hz: int,
    config: DropoutConfig,
) -> tuple[DropoutEvent, ...]:
    """Detect candidate silence only where the aligned reference is active."""

    _paired_views(views)
    rate = _positive_int(sample_rate_hz, "sample_rate_hz")
    active_floor = _finite_number(config.active_reference_floor_linear_fs, "active_reference_floor_linear_fs")
    quiet_floor = _finite_number(config.near_silence_floor_linear_fs, "near_silence_floor_linear_fs")
    minimum = _positive_int(config.minimum_duration_frames, "minimum_duration_frames")
    if active_floor <= 0.0 or quiet_floor < 0.0 or quiet_floor >= active_floor:
        raise AnalysisInputError("dropout floors require 0 <= near-silence < active-reference")
    _rationale(config.rationale)
    active = np.abs(views.baseline) >= active_floor
    quiet = np.abs(views.candidate) <= quiet_floor
    mask = active & quiet
    grouped: dict[tuple[int, int, str], list[int]] = {}
    for channel in range(mask.shape[1]):
        values = mask[:, channel]
        index = 0
        while index < len(values):
            if not values[index]:
                index += 1
                continue
            start = index
            while index < len(values) and values[index]:
                index += 1
            end = index
            if end - start < minimum:
                continue
            classification = (
                "exact_zero"
                if np.all(views.candidate[start:end, channel] == np.float32(0.0))
                else "near_silence"
            )
            grouped.setdefault((start, end, classification), []).append(channel)
    events: list[DropoutEvent] = []
    for (local_start, local_end, classification), channels in grouped.items():
        start = views.baseline_start_frame + local_start
        end = views.baseline_start_frame + local_end
        candidate_start = views.candidate_start_frame + local_start
        candidate_end = views.candidate_start_frame + local_end
        events.append(
            DropoutEvent(
                start,
                end,
                start / rate,
                end / rate,
                end - start,
                (end - start) / rate,
                candidate_start,
                candidate_end,
                tuple(channels),
                classification,  # type: ignore[arg-type]
            )
        )
    return tuple(sorted(events, key=lambda item: (item.start_frame, item.end_frame, item.channel_indices)))


__all__ = [
    "AlignedViews",
    "AlignmentApplication",
    "AlignmentOperatingPoint",
    "AlignmentPolicyError",
    "AlignmentRequest",
    "AlignmentResult",
    "AnalysisInputError",
    "AudioDescription",
    "ChannelMappingConfig",
    "DropoutConfig",
    "DropoutEvent",
    "GainMetric",
    "LagObservation",
    "PolarityMetric",
    "ResidualMetric",
    "StereoChannelMapping",
    "StructuralIssue",
    "StructuralValidationConfig",
    "StructuralValidationResult",
    "TimeAlignmentRequest",
    "TimeCompensationRecord",
    "ValidatedAlignment",
    "analyze_stereo_channel_mapping",
    "apply_integer_time_alignment",
    "compute_gain_metrics",
    "compute_residual_metrics",
    "detect_dropouts",
    "diagnose_polarity",
    "estimate_integer_alignment",
    "load_m1_alignment_operating_point",
    "validate_and_estimate_integer_alignment",
    "validate_structure",
]
