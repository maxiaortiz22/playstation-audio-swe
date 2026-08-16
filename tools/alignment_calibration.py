"""Reproducible T-CMP-CAL-001 calibration spike; not a production comparator."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import struct
import subprocess
import sys
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_VERSION = "1.0.0"
METHOD_VERSION = "t-cmp-cal-001-alignment-v1"
OPERATING_POINT_PARAMETER_NAMES = (
    "plateau_epsilon",
    "maximum_primary_plateau_width_frames",
    "secondary_exclusion_radius_frames",
    "minimum_primary_abs_correlation",
    "minimum_accepted_peak_ratio",
    "sync_rms_floor_linear_fs",
    "minimum_overlap_frames",
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_non_finite(token: str) -> None:
    raise ValueError(f"non-finite JSON token: {token}")


def load_config(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    document = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_finite,
    )
    if not isinstance(document, dict):
        raise ValueError("calibration configuration root must be an object")
    return document, hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _float32_bytes(values: Sequence[float]) -> bytes:
    if not values:
        return b""
    return struct.pack(f"<{len(values)}f", *values)


def _as_float32(values: Iterable[float]) -> tuple[float, ...]:
    source = tuple(values)
    if not source:
        return ()
    return tuple(struct.unpack(f"<{len(source)}f", _float32_bytes(source)))


class XorShift32:
    """Named, versioned 32-bit PRNG used only by this deterministic corpus."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF or 0x6D2B79F5

    def next_u32(self) -> int:
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x & 0xFFFFFFFF
        return self.state

    def uniform_signed(self) -> float:
        return 2.0 * ((self.next_u32() >> 8) / float(1 << 24)) - 1.0

    def rademacher(self) -> float:
        return 1.0 if self.next_u32() & 1 else -1.0


@dataclass(frozen=True)
class OperatingPoint:
    id: str
    plateau_epsilon: float
    maximum_primary_plateau_width_frames: int
    secondary_exclusion_radius_frames: int
    minimum_primary_abs_correlation: float
    minimum_accepted_peak_ratio: float
    sync_rms_floor_linear_fs: float
    minimum_overlap_frames: int
    risk_posture: str = "OFAT exploration point"

    @classmethod
    def from_mapping(cls, value: dict[str, Any], *, point_id: str | None = None) -> "OperatingPoint":
        point = cls(
            id=point_id or str(value["id"]),
            plateau_epsilon=float(value["plateau_epsilon"]),
            maximum_primary_plateau_width_frames=int(value["maximum_primary_plateau_width_frames"]),
            secondary_exclusion_radius_frames=int(value["secondary_exclusion_radius_frames"]),
            minimum_primary_abs_correlation=float(value["minimum_primary_abs_correlation"]),
            minimum_accepted_peak_ratio=float(value["minimum_accepted_peak_ratio"]),
            sync_rms_floor_linear_fs=float(value["sync_rms_floor_linear_fs"]),
            minimum_overlap_frames=int(value["minimum_overlap_frames"]),
            risk_posture=str(value.get("risk_posture", "OFAT exploration point")),
        )
        point.validate()
        return point

    def validate(self, *, search_span_frames: int = 128) -> None:
        numeric = (
            self.plateau_epsilon,
            self.minimum_primary_abs_correlation,
            self.minimum_accepted_peak_ratio,
            self.sync_rms_floor_linear_fs,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError(f"{self.id}: operating-point values must be finite")
        if not 0.0 <= self.plateau_epsilon < 1.0:
            raise ValueError(f"{self.id}: plateau_epsilon outside [0, 1)")
        if self.maximum_primary_plateau_width_frames <= 0:
            raise ValueError(f"{self.id}: plateau width must be positive")
        if not 0 <= self.secondary_exclusion_radius_frames < search_span_frames:
            raise ValueError(f"{self.id}: exclusion radius outside search span")
        if not 0.0 < self.minimum_primary_abs_correlation <= 1.0:
            raise ValueError(f"{self.id}: primary correlation outside (0, 1]")
        if self.minimum_accepted_peak_ratio < 1.0:
            raise ValueError(f"{self.id}: peak ratio must be at least 1")
        if self.sync_rms_floor_linear_fs < 0.0:
            raise ValueError(f"{self.id}: RMS floor must be non-negative")
        if self.minimum_overlap_frames <= 0:
            raise ValueError(f"{self.id}: minimum overlap must be positive")

    def parameter_digest(self) -> str:
        values = asdict(self)
        values.pop("risk_posture")
        return _sha256_bytes(_canonical_json(values))


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    split: str
    family_id: str
    oracle_class: str
    oracle_lag_frames: int | None
    oracle_reason: str
    generator_id: str
    generator_version: str
    seed: int
    parameters: dict[str, Any]
    strata: dict[str, str]
    baseline: tuple[float, ...]
    candidate: tuple[float, ...]
    baseline_sync_origin_frames: int
    candidate_sync_origin_frames: int
    baseline_sync_length_frames: int
    candidate_sync_length_frames: int
    search_min_reported_lag_frames: int
    search_max_reported_lag_frames: int
    sync_copy_transform: str = "none"

    @property
    def baseline_sync(self) -> tuple[float, ...]:
        start = self.baseline_sync_origin_frames
        return self.baseline[start : start + self.baseline_sync_length_frames]

    @property
    def candidate_sync(self) -> tuple[float, ...]:
        start = self.candidate_sync_origin_frames
        return self.candidate[start : start + self.candidate_sync_length_frames]

    def provenance(self) -> dict[str, Any]:
        baseline_raw = _float32_bytes(self.baseline)
        candidate_raw = _float32_bytes(self.candidate)
        return {
            "case_id": self.case_id,
            "split": self.split,
            "family_id": self.family_id,
            "oracle_class": self.oracle_class,
            "oracle_lag_frames": self.oracle_lag_frames,
            "oracle_reason": self.oracle_reason,
            "generator_id": self.generator_id,
            "generator_version": self.generator_version,
            "seed": self.seed,
            "parameters": self.parameters,
            "parameter_digest": _sha256_bytes(_canonical_json(self.parameters)),
            "strata": self.strata,
            "baseline_sha256_float32_le": _sha256_bytes(baseline_raw),
            "candidate_sha256_float32_le": _sha256_bytes(candidate_raw),
            "pcm_pair_sha256": _sha256_bytes(baseline_raw + candidate_raw),
            "baseline_sync_sha256_float32_le": _sha256_bytes(_float32_bytes(self.baseline_sync)),
            "candidate_sync_sha256_float32_le": _sha256_bytes(_float32_bytes(self.candidate_sync)),
            "baseline_frames": len(self.baseline),
            "candidate_frames": len(self.candidate),
            "baseline_sync_origin_frames": self.baseline_sync_origin_frames,
            "candidate_sync_origin_frames": self.candidate_sync_origin_frames,
            "baseline_sync_length_frames": self.baseline_sync_length_frames,
            "candidate_sync_length_frames": self.candidate_sync_length_frames,
            "search_min_reported_lag_frames": self.search_min_reported_lag_frames,
            "search_max_reported_lag_frames": self.search_max_reported_lag_frames,
            "sync_copy_transform": self.sync_copy_transform,
        }


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
    classification: str
    reason: str
    reported_lag_frames: int | None
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
    valid_lag_count: int
    input_buffers_unchanged: bool


def _signal_rms(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(math.fsum(value * value for value in values) / len(values))


def _base_signal(generator_id: str, length: int, seed: int, parameters: dict[str, Any]) -> tuple[float, ...]:
    rng = XorShift32(seed)
    if generator_id == "uniform-noise-v1":
        values = [rng.uniform_signed() for _ in range(length)]
    elif generator_id == "rademacher-noise-v1":
        values = [rng.rademacher() for _ in range(length)]
    elif generator_id == "lfsr-prbs15-v1":
        state = (seed & 0x7FFF) or 1
        values = []
        for _ in range(length):
            values.append(1.0 if state & 1 else -1.0)
            feedback = ((state >> 0) ^ (state >> 1)) & 1
            state = ((state >> 1) | (feedback << 14)) & 0x7FFF
    elif generator_id == "integer-chirp-v1":
        f0 = float(parameters["start_cycles_per_frame"])
        f1 = float(parameters["end_cycles_per_frame"])
        denom = max(length - 1, 1)
        values = [
            math.sin(2.0 * math.pi * (f0 * n + 0.5 * (f1 - f0) * n * n / denom))
            for n in range(length)
        ]
    elif generator_id in {"integer-periodic-v1", "harmonic-comb-v1"}:
        period = int(parameters["period_frames"])
        if generator_id == "integer-periodic-v1":
            values = [math.sin(2.0 * math.pi * (n % period) / period) for n in range(length)]
        else:
            values = [
                0.65 * math.sin(2.0 * math.pi * (n % period) / period)
                + 0.25 * math.sin(4.0 * math.pi * (n % period) / period)
                + 0.10 * math.cos(6.0 * math.pi * (n % period) / period)
                for n in range(length)
            ]
    elif generator_id == "repeated-block-v1":
        block_length = int(parameters["block_length_frames"])
        block = [rng.rademacher() * (0.35 + 0.65 * ((index + 1) / block_length)) for index in range(block_length)]
        values = [block[index % block_length] for index in range(length)]
    elif generator_id == "multi-transient-v1":
        background_amplitude = float(parameters.get("background_amplitude", 0.001))
        values = [background_amplitude * rng.rademacher() for _ in range(length)]
        positions = [int(position) for position in parameters["positions_frames"]]
        amplitudes = [1.0, -0.7, 0.45, -0.25]
        for index, position in enumerate(positions):
            if 0 <= position < length:
                values[position] = amplitudes[index % len(amplitudes)]
            if 0 <= position + 1 < length:
                values[position + 1] = -0.31 * amplitudes[index % len(amplitudes)]
    elif generator_id in {"exact-silence-v1", "short-sync-v1", "short-sync-offset-v1"}:
        values = [0.0] * length if generator_id == "exact-silence-v1" else [rng.uniform_signed() for _ in range(length)]
    elif generator_id == "near-silence-v1":
        values = [rng.rademacher() for _ in range(length)]
    elif generator_id in {"constant-plateau-v1", "tapered-plateau-v1"}:
        values = [1.0] * length
    else:
        raise ValueError(f"unknown generator: {generator_id}")
    return _as_float32(values)


def _shift_candidate(
    baseline: Sequence[float],
    *,
    lag_frames: int,
    polarity: int,
    candidate_gain: float,
    snr_db: float | None,
    noise_seed: int,
) -> tuple[float, ...]:
    length = len(baseline)
    result = [0.0] * length
    for candidate_index in range(length):
        baseline_index = candidate_index - lag_frames
        if 0 <= baseline_index < length:
            result[candidate_index] = polarity * candidate_gain * baseline[baseline_index]
    if snr_db is not None:
        active_rms = _signal_rms(result)
        noise_rms = active_rms * 10.0 ** (-snr_db / 20.0)
        rng = XorShift32(noise_seed)
        raw = [rng.rademacher() for _ in range(length)]
        raw_rms = _signal_rms(raw)
        for index in range(length):
            result[index] += noise_rms * raw[index] / raw_rms
    return _as_float32(result)


def make_case(
    *,
    split: str,
    family_id: str,
    case_index: int,
    generator_id: str,
    seed: int,
    length: int,
    lag_frames: int,
    oracle_class: str,
    oracle_reason: str,
    level: float = 0.8,
    polarity: int = 1,
    candidate_gain: float = 1.0,
    snr_db: float | None = None,
    origins: tuple[int, int] = (0, 0),
    sync_lengths: tuple[int, int] | None = None,
    generator_parameters: dict[str, Any] | None = None,
    strata_overrides: dict[str, str] | None = None,
    search_bounds: tuple[int, int] = (-64, 64),
    sync_copy_transform: str = "none",
) -> CalibrationCase:
    parameters = dict(generator_parameters or {})
    base = _base_signal(generator_id, length, seed, parameters)
    baseline = _as_float32(level * value for value in base)
    candidate = _shift_candidate(
        baseline,
        lag_frames=lag_frames,
        polarity=polarity,
        candidate_gain=candidate_gain,
        snr_db=snr_db,
        noise_seed=seed ^ 0xA5A55A5A,
    )
    if generator_id == "near-silence-v1":
        amplitude = float(parameters["amplitude_linear_fs"])
        baseline = _as_float32(amplitude * value for value in base)
        candidate = _shift_candidate(
            baseline,
            lag_frames=lag_frames,
            polarity=polarity,
            candidate_gain=candidate_gain,
            snr_db=snr_db,
            noise_seed=seed ^ 0xA5A55A5A,
        )
    ob, oc = origins
    if sync_lengths is None:
        sync_lengths = (length - ob, length - oc)
    lag_position = (
        "lower_boundary" if lag_frames == search_bounds[0] else
        "upper_boundary" if lag_frames == search_bounds[1] else
        "negative" if lag_frames < 0 else
        "positive" if lag_frames > 0 else "zero"
    )
    effective_rms = _signal_rms(baseline)
    strata = {
        "polarity": "inverted" if polarity < 0 else "normal",
        "level": "near_silence" if effective_rms < 1e-6 else "very_low" if effective_rms < 0.001 else "low" if effective_rms < 0.1 else "nominal",
        "lag_position": lag_position if oracle_class == "unique" else "not_applicable",
        "noise": "none" if snr_db is None else "low_snr" if snr_db < 10 else "medium_snr" if snr_db < 25 else "high_snr",
        "energy": "silence" if effective_rms == 0 else "near_silence" if effective_rms < 1e-6 else "active",
        "overlap": "short" if min(sync_lengths) < 32 else "normal",
        "sync_origin": "zero" if origins == (0, 0) else "offset",
        "duration": "short" if length < 700 else "medium" if length < 1000 else "long",
    }
    strata.update(strata_overrides or {})
    recorded_parameters = {
        **parameters,
        "length_frames": length,
        "lag_frames": lag_frames,
        "level_linear_fs": level,
        "polarity": polarity,
        "candidate_gain": candidate_gain,
        "snr_db": snr_db,
        "baseline_sync_origin_frames": ob,
        "candidate_sync_origin_frames": oc,
        "baseline_sync_length_frames": sync_lengths[0],
        "candidate_sync_length_frames": sync_lengths[1],
        "search_bounds_reported_lag_frames": list(search_bounds),
        "sync_copy_transform": sync_copy_transform,
    }
    return CalibrationCase(
        case_id=f"{split}-{family_id}-{case_index:02d}",
        split=split,
        family_id=family_id,
        oracle_class=oracle_class,
        oracle_lag_frames=lag_frames if oracle_class == "unique" else None,
        oracle_reason=oracle_reason,
        generator_id=generator_id,
        generator_version=GENERATOR_VERSION,
        seed=seed,
        parameters=recorded_parameters,
        strata=strata,
        baseline=baseline,
        candidate=candidate,
        baseline_sync_origin_frames=ob,
        candidate_sync_origin_frames=oc,
        baseline_sync_length_frames=sync_lengths[0],
        candidate_sync_length_frames=sync_lengths[1],
        search_min_reported_lag_frames=search_bounds[0],
        search_max_reported_lag_frames=search_bounds[1],
        sync_copy_transform=sync_copy_transform,
    )


def _prepare_sync_copy(values: Sequence[float], transform: str) -> tuple[float, ...]:
    copied = tuple(values)
    if transform == "none":
        return copied
    if transform == "remove_dc":
        if not copied:
            return copied
        mean = math.fsum(copied) / len(copied)
        return tuple(value - mean for value in copied)
    raise ValueError(f"unsupported synchronization-copy transform: {transform}")


def compute_lag_observations(case: CalibrationCase) -> list[LagObservation]:
    baseline_sync = _prepare_sync_copy(case.baseline_sync, case.sync_copy_transform)
    candidate_sync = _prepare_sync_copy(case.candidate_sync, case.sync_copy_transform)
    n_baseline = len(baseline_sync)
    n_candidate = len(candidate_sync)
    observations: list[LagObservation] = []
    for reported_lag in range(case.search_min_reported_lag_frames, case.search_max_reported_lag_frames + 1):
        local_lag = reported_lag - case.candidate_sync_origin_frames + case.baseline_sync_origin_frames
        start = max(0, -local_lag)
        stop = min(n_baseline, n_candidate - local_lag)
        overlap = max(0, stop - start)
        if overlap == 0:
            observations.append(LagObservation(reported_lag, local_lag, 0, None, None, None))
            continue
        products: list[float] = []
        baseline_squares: list[float] = []
        candidate_squares: list[float] = []
        for index in range(start, stop):
            baseline_value = baseline_sync[index]
            candidate_value = candidate_sync[index + local_lag]
            products.append(baseline_value * candidate_value)
            baseline_squares.append(baseline_value * baseline_value)
            candidate_squares.append(candidate_value * candidate_value)
        baseline_energy = math.fsum(baseline_squares)
        candidate_energy = math.fsum(candidate_squares)
        baseline_rms = math.sqrt(baseline_energy / overlap)
        candidate_rms = math.sqrt(candidate_energy / overlap)
        denominator = math.sqrt(baseline_energy * candidate_energy)
        correlation = math.fsum(products) / denominator if denominator > 0.0 else None
        if correlation is not None and (not math.isfinite(correlation) or abs(correlation) > 1.0 + 1e-12):
            raise ArithmeticError(f"non-physical correlation {correlation} for {case.case_id} lag {reported_lag}")
        observations.append(
            LagObservation(reported_lag, local_lag, overlap, baseline_rms, candidate_rms, correlation)
        )
    return observations


def evaluate_observations(
    observations: Sequence[LagObservation],
    point: OperatingPoint,
    *,
    inputs_unchanged: bool = True,
) -> AlignmentResult:
    valid = [
        observation
        for observation in observations
        if observation.overlap_frames >= point.minimum_overlap_frames
        and observation.baseline_rms_linear_fs is not None
        and observation.candidate_rms_linear_fs is not None
        and observation.baseline_rms_linear_fs > point.sync_rms_floor_linear_fs
        and observation.candidate_rms_linear_fs > point.sync_rms_floor_linear_fs
        and observation.signed_correlation is not None
    ]
    if not valid:
        return AlignmentResult("invalid", "no_lag_passed_energy_and_overlap", None, None, None, None, None, None, None, 0, None, None, False, None, "unavailable", 0, inputs_unchanged)

    def tie_key(observation: LagObservation) -> tuple[float, int, int]:
        assert observation.signed_correlation is not None
        return (-abs(observation.signed_correlation), abs(observation.reported_lag_frames), observation.reported_lag_frames)

    representative = min(valid, key=tie_key)
    assert representative.signed_correlation is not None
    primary_score = abs(representative.signed_correlation)
    exact_maxima = [observation for observation in valid if abs(observation.signed_correlation or 0.0) == primary_score]
    by_lag = {observation.reported_lag_frames: observation for observation in valid}
    plateau_lags = {representative.reported_lag_frames}
    for direction in (-1, 1):
        lag = representative.reported_lag_frames + direction
        while lag in by_lag:
            score = abs(by_lag[lag].signed_correlation or 0.0)
            if primary_score - score > point.plateau_epsilon:
                break
            plateau_lags.add(lag)
            lag += direction
    plateau_min = min(plateau_lags)
    plateau_max = max(plateau_lags)
    plateau_width = plateau_max - plateau_min + 1

    local_peaks: list[LagObservation] = []
    for observation in valid:
        score = abs(observation.signed_correlation or 0.0)
        left = by_lag.get(observation.reported_lag_frames - 1)
        right = by_lag.get(observation.reported_lag_frames + 1)
        if left is not None and score < abs(left.signed_correlation or 0.0):
            continue
        if right is not None and score < abs(right.signed_correlation or 0.0):
            continue
        local_peaks.append(observation)
    exclusion_min = plateau_min - point.secondary_exclusion_radius_frames
    exclusion_max = plateau_max + point.secondary_exclusion_radius_frames
    secondary_candidates = [
        peak for peak in local_peaks
        if peak.reported_lag_frames < exclusion_min or peak.reported_lag_frames > exclusion_max
    ]
    secondary = min(secondary_candidates, key=tie_key) if secondary_candidates else None
    secondary_score = abs(secondary.signed_correlation or 0.0) if secondary is not None else None
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
        "reported_lag_frames": representative.reported_lag_frames,
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
        "valid_lag_count": len(valid),
        "input_buffers_unchanged": inputs_unchanged,
    }
    if not inputs_unchanged:
        return AlignmentResult(classification="invalid", reason="input_buffer_mutation", **common)
    if primary_score < point.minimum_primary_abs_correlation:
        return AlignmentResult(classification="invalid", reason="primary_below_minimum", **common)
    if len(exact_maxima) > 1:
        return AlignmentResult(classification="ambiguous", reason="equivalent_primary_peaks", **common)
    if plateau_width > point.maximum_primary_plateau_width_frames:
        return AlignmentResult(classification="ambiguous", reason="primary_plateau_too_wide", **common)
    if ratio_kind == "degenerate_zero_secondary":
        return AlignmentResult(classification="invalid", reason="degenerate_zero_secondary", **common)
    if ratio is not None and ratio < point.minimum_accepted_peak_ratio:
        return AlignmentResult(classification="ambiguous", reason="peak_ratio_below_minimum", **common)
    return AlignmentResult(classification="valid", reason="accepted", **common)


def estimate_case(case: CalibrationCase, point: OperatingPoint) -> tuple[AlignmentResult, list[LagObservation]]:
    before_baseline = _sha256_bytes(_float32_bytes(case.baseline))
    before_candidate = _sha256_bytes(_float32_bytes(case.candidate))
    observations = compute_lag_observations(case)
    after_baseline = _sha256_bytes(_float32_bytes(case.baseline))
    after_candidate = _sha256_bytes(_float32_bytes(case.candidate))
    unchanged = before_baseline == after_baseline and before_candidate == after_candidate
    return evaluate_observations(observations, point, inputs_unchanged=unchanged), observations


def build_corpus(config: dict[str, Any]) -> list[CalibrationCase]:
    cases: list[CalibrationCase] = []
    bounds_value = config["search_bounds_reported_lag_frames"]
    bounds = (int(bounds_value["minimum"]), int(bounds_value["maximum"]))

    calibration = config["corpus"]["calibration"]
    cal_seed = int(calibration["seed_base"])
    cal_lengths = [int(value) for value in calibration["durations_frames"]]
    cal_lags = [int(value) for value in calibration["interior_lags_frames"]]
    cal_levels = [float(value) for value in calibration["levels_linear_fs"]]
    cal_snr = [float(value) for value in calibration["snr_db"]]
    cal_origins = [tuple(int(item) for item in value) for value in calibration["sync_origins_frames"]]
    index = 0

    def add_cal(**kwargs: Any) -> None:
        nonlocal index
        cases.append(make_case(split="calibration", case_index=index, search_bounds=bounds, **kwargs))
        index += 1

    for offset, lag in enumerate((bounds[0], cal_lags[0], cal_lags[1], cal_lags[2], bounds[1])):
        add_cal(
            family_id="uniform-noise-v1",
            generator_id="uniform-noise-v1",
            seed=cal_seed + index,
            length=cal_lengths[offset % 3],
            lag_frames=lag,
            oracle_class="unique",
            oracle_reason="Seeded broadband noise has one constructed integer correspondence.",
            level=cal_levels[offset % 2],
            origins=cal_origins[offset % 3],
        )
    add_cal(
        family_id="uniform-noise-v1", generator_id="uniform-noise-v1", seed=cal_seed + index,
        length=cal_lengths[2], lag_frames=cal_lags[2], oracle_class="unique",
        oracle_reason="Polarity changes score sign but not the constructed correspondence.",
        level=cal_levels[0], polarity=-1, origins=cal_origins[1], sync_copy_transform="remove_dc",
    )
    add_cal(
        family_id="uniform-noise-v1", generator_id="uniform-noise-v1", seed=cal_seed + index,
        length=cal_lengths[1], lag_frames=cal_lags[0], oracle_class="unique",
        oracle_reason="Positive level scaling preserves the unique broadband correspondence.",
        level=cal_levels[2], candidate_gain=0.4, origins=cal_origins[2],
    )
    for snr in cal_snr:
        add_cal(
            family_id="uniform-noise-v1", generator_id="uniform-noise-v1", seed=cal_seed + index,
            length=cal_lengths[1], lag_frames=cal_lags[2], oracle_class="unique",
            oracle_reason="Independent controlled noise perturbs but does not duplicate the constructed correspondence.",
            level=cal_levels[1], snr_db=snr, origins=cal_origins[0],
        )
    add_cal(
        family_id="uniform-noise-v1", generator_id="uniform-noise-v1", seed=cal_seed + index,
        length=cal_lengths[0], lag_frames=cal_lags[2], oracle_class="unique",
        oracle_reason="A 48-frame sync region is sufficient for the permissive profile and probes overlap sensitivity.",
        level=cal_levels[0], sync_lengths=(48, 48),
    )

    for lag, origin in zip((bounds[0], 0, bounds[1], cal_lags[0]), cal_origins + [cal_origins[1]]):
        add_cal(
            family_id="lfsr-prbs15-v1", generator_id="lfsr-prbs15-v1", seed=cal_seed + index,
            length=cal_lengths[index % 3], lag_frames=lag, oracle_class="unique",
            oracle_reason="The non-repeating PRBS window has one constructed correspondence in the search range.",
            level=cal_levels[index % 2], polarity=-1 if index % 2 else 1, origins=origin,
        )

    for period in (11, 17, 23):
        add_cal(
            family_id="integer-periodic-v1", generator_id="integer-periodic-v1", seed=cal_seed + index,
            length=cal_lengths[1], lag_frames=0, oracle_class="ambiguous",
            oracle_reason="Integer-period repetition creates separated equivalent correlation maxima.",
            generator_parameters={"period_frames": period},
        )

    transient_sets = ([61, 173, 349, 463], [97, 211, 397], [43, 281, 617], [151, 509, 701])
    for case_offset, positions in enumerate(transient_sets):
        lag = (bounds[0], cal_lags[0], cal_lags[2], bounds[1])[case_offset]
        add_cal(
            family_id="multi-transient-v1", generator_id="multi-transient-v1", seed=cal_seed + index,
            length=cal_lengths[2], lag_frames=lag, oracle_class="unique",
            oracle_reason="An asymmetric multi-transient pattern has one constructed correspondence.",
            generator_parameters={"positions_frames": positions, "background_amplitude": 0.001},
            polarity=-1 if case_offset == 2 else 1, origins=cal_origins[case_offset % 3],
        )

    for _ in range(2):
        add_cal(
            family_id="exact-silence-v1", generator_id="exact-silence-v1", seed=cal_seed + index,
            length=cal_lengths[index % 3], lag_frames=0, oracle_class="invalid",
            oracle_reason="Exact silence has RMS equal to every non-negative floor.", level=0.0,
        )
    for origin in ((0, 0), cal_origins[1]):
        add_cal(
            family_id="short-sync-v1", generator_id="short-sync-v1", seed=cal_seed + index,
            length=cal_lengths[0], lag_frames=0, oracle_class="invalid",
            oracle_reason="Every eligible sync overlap is shorter than the smallest explored minimum.",
            origins=origin, sync_lengths=(15, 15),
        )
    for length in (cal_lengths[0], cal_lengths[2]):
        add_cal(
            family_id="constant-plateau-v1", generator_id="constant-plateau-v1", seed=cal_seed + index,
            length=length, lag_frames=0, oracle_class="ambiguous",
            oracle_reason="Constant non-zero signals produce an artificial primary plateau across lags.",
            level=cal_levels[0],
        )

    holdout = config["corpus"]["holdout"]
    hold_seed = int(holdout["seed_base"])
    hold_lengths = [int(value) for value in holdout["durations_frames"]]
    hold_lags = [int(value) for value in holdout["interior_lags_frames"]]
    hold_levels = [float(value) for value in holdout["levels_linear_fs"]]
    hold_snr = [float(value) for value in holdout["snr_db"]]
    hold_origins = [tuple(int(item) for item in value) for value in holdout["sync_origins_frames"]]
    index = 0

    def add_hold(**kwargs: Any) -> None:
        nonlocal index
        cases.append(make_case(split="holdout", case_index=index, search_bounds=bounds, **kwargs))
        index += 1

    for offset, lag in enumerate((bounds[0], hold_lags[0], hold_lags[1], hold_lags[2], bounds[1])):
        add_hold(
            family_id="rademacher-noise-v1", generator_id="rademacher-noise-v1", seed=hold_seed + index,
            length=hold_lengths[offset % 3], lag_frames=lag, oracle_class="unique",
            oracle_reason="Seeded Rademacher broadband content has one constructed integer correspondence.",
            level=hold_levels[offset % 2], origins=hold_origins[offset % 3],
        )
    add_hold(
        family_id="rademacher-noise-v1", generator_id="rademacher-noise-v1", seed=hold_seed + index,
        length=hold_lengths[2], lag_frames=hold_lags[2], oracle_class="unique",
        oracle_reason="Polarity inversion preserves the Rademacher correspondence and reverses peak sign.",
        level=hold_levels[0], polarity=-1, origins=hold_origins[1],
    )
    add_hold(
        family_id="rademacher-noise-v1", generator_id="rademacher-noise-v1", seed=hold_seed + index,
        length=hold_lengths[0], lag_frames=hold_lags[0], oracle_class="unique",
        oracle_reason="Very-low-level broadband content probes the RMS-floor tradeoff.",
        level=hold_levels[2], origins=hold_origins[2],
    )
    for snr in hold_snr:
        add_hold(
            family_id="rademacher-noise-v1", generator_id="rademacher-noise-v1", seed=hold_seed + index,
            length=hold_lengths[1], lag_frames=hold_lags[2], oracle_class="unique",
            oracle_reason="Controlled holdout noise perturbs a unique correspondence.",
            level=hold_levels[1], snr_db=snr, origins=hold_origins[0],
        )
    add_hold(
        family_id="rademacher-noise-v1", generator_id="rademacher-noise-v1", seed=hold_seed + index,
        length=hold_lengths[0], lag_frames=hold_lags[2], oracle_class="unique",
        oracle_reason="A 48-frame holdout sync region probes minimum-overlap generalization.",
        level=hold_levels[0], sync_lengths=(48, 48),
    )

    chirp_parameters = (
        {"start_cycles_per_frame": 0.0031, "end_cycles_per_frame": 0.083},
        {"start_cycles_per_frame": 0.0073, "end_cycles_per_frame": 0.137},
        {"start_cycles_per_frame": 0.011, "end_cycles_per_frame": 0.191},
        {"start_cycles_per_frame": 0.017, "end_cycles_per_frame": 0.223},
    )
    for case_offset, parameters in enumerate(chirp_parameters):
        lag = (bounds[0], hold_lags[0], hold_lags[2], bounds[1])[case_offset]
        add_hold(
            family_id="integer-chirp-v1", generator_id="integer-chirp-v1", seed=hold_seed + index,
            length=hold_lengths[case_offset % 3], lag_frames=lag, oracle_class="unique",
            oracle_reason="A non-repeating deterministic chirp has one constructed correspondence.",
            level=hold_levels[case_offset % 2], polarity=-1 if case_offset == 1 else 1,
            origins=hold_origins[case_offset % 3], generator_parameters=parameters,
        )

    for period in (19, 27, 31):
        add_hold(
            family_id="harmonic-comb-v1", generator_id="harmonic-comb-v1", seed=hold_seed + index,
            length=hold_lengths[1], lag_frames=0, oracle_class="ambiguous",
            oracle_reason="A harmonic periodic construction has multiple equivalent maxima.",
            generator_parameters={"period_frames": period},
        )
    for block_length in (21, 29, 37):
        add_hold(
            family_id="repeated-block-v1", generator_id="repeated-block-v1", seed=hold_seed + index,
            length=hold_lengths[2], lag_frames=0, oracle_class="ambiguous",
            oracle_reason="Repeated deterministic blocks create equivalent peaks beyond every candidate exclusion radius.",
            generator_parameters={"block_length_frames": block_length},
        )
    for amplitude in (1e-9, 5e-8, 9e-8):
        add_hold(
            family_id="near-silence-v1", generator_id="near-silence-v1", seed=hold_seed + index,
            length=hold_lengths[0], lag_frames=hold_lags[1], oracle_class="invalid",
            oracle_reason="Near-silence is below the smallest frozen candidate RMS floor.",
            generator_parameters={"amplitude_linear_fs": amplitude}, level=1.0,
        )
    for origin in ((0, 0), hold_origins[2]):
        add_hold(
            family_id="short-sync-offset-v1", generator_id="short-sync-offset-v1", seed=hold_seed + index,
            length=hold_lengths[0], lag_frames=0, oracle_class="invalid",
            oracle_reason="Every eligible holdout overlap is shorter than 16 frames.",
            origins=origin, sync_lengths=(15, 15),
        )
    for length in (hold_lengths[0], hold_lengths[2]):
        add_hold(
            family_id="tapered-plateau-v1", generator_id="tapered-plateau-v1", seed=hold_seed + index,
            length=length, lag_frames=0, oracle_class="ambiguous",
            oracle_reason="A disjoint constant-level construction creates a broad artificial holdout plateau.",
            level=hold_levels[0], generator_parameters={"construction": "constant-level-holdout"},
        )

    validate_corpus_separation(cases, config)
    return cases


def validate_corpus_separation(cases: Sequence[CalibrationCase], config: dict[str, Any]) -> dict[str, Any]:
    calibration = [case for case in cases if case.split == "calibration"]
    holdout = [case for case in cases if case.split == "holdout"]
    if not calibration or not holdout:
        raise ValueError("both calibration and holdout cases are required")
    checks: dict[str, tuple[set[Any], set[Any]]] = {
        "case_ids": ({case.case_id for case in calibration}, {case.case_id for case in holdout}),
        "seeds": ({case.seed for case in calibration}, {case.seed for case in holdout}),
        "generator_families": ({case.family_id for case in calibration}, {case.family_id for case in holdout}),
        "parameter_digests": (
            {_sha256_bytes(_canonical_json(case.parameters)) for case in calibration},
            {_sha256_bytes(_canonical_json(case.parameters)) for case in holdout},
        ),
        "pcm_pair_digests": (
            {_sha256_bytes(_float32_bytes(case.baseline) + _float32_bytes(case.candidate)) for case in calibration},
            {_sha256_bytes(_float32_bytes(case.baseline) + _float32_bytes(case.candidate)) for case in holdout},
        ),
    }
    results: dict[str, Any] = {}
    for name, (left, right) in checks.items():
        intersection = left & right
        if intersection:
            raise ValueError(f"calibration/holdout leakage in {name}: {sorted(intersection, key=str)}")
        results[name] = {"disjoint": True, "calibration_count": len(left), "holdout_count": len(right)}
    declared_cal = set(config["corpus"]["calibration"]["generator_families"])
    declared_hold = set(config["corpus"]["holdout"]["generator_families"])
    actual_cal = {case.family_id for case in calibration}
    actual_hold = {case.family_id for case in holdout}
    if declared_cal != actual_cal or declared_hold != actual_hold:
        raise ValueError("generated corpus families differ from the frozen configuration")
    return results


def build_sweep(config: dict[str, Any]) -> list[OperatingPoint]:
    sweep = config["sweep"]
    reference = dict(sweep["reference"])
    points = [OperatingPoint.from_mapping(reference, point_id="OFAT-reference")]
    for axis, values in sweep["axes"].items():
        for index, value in enumerate(values):
            if value == reference[axis]:
                continue
            parameters = dict(reference)
            parameters[axis] = value
            points.append(OperatingPoint.from_mapping(parameters, point_id=f"OFAT-{axis}-{index}"))
    if len(points) != 24:
        raise ValueError(f"expected 24 unique OFAT points, got {len(points)}")
    digests = {point.parameter_digest() for point in points}
    if len(digests) != len(points):
        raise ValueError("duplicate OFAT parameter configuration")
    return points


def build_candidates(config: dict[str, Any]) -> list[OperatingPoint]:
    candidates = [OperatingPoint.from_mapping(value) for value in config["frozen_operating_point_candidates"]]
    if len(candidates) not in {2, 3}:
        raise ValueError("the frozen decision set must contain two or three candidates")
    return candidates


def _operating_point_parameters(point: OperatingPoint) -> dict[str, Any]:
    return {name: getattr(point, name) for name in OPERATING_POINT_PARAMETER_NAMES}


def _pending_decision() -> dict[str, Any]:
    return {
        "status": "human_selection_required",
        "selection_method": None,
        "selected_operating_point": None,
        "selected_parameters": None,
        "automatic_selection": False,
        "fallback_operating_point_id": None,
        "scope": None,
        "universal_default": False,
        "error_budget_satisfied": None,
        "spec_001_status": "Review",
    }


def validate_m1_decision(
    decision: dict[str, Any],
    *,
    decision_digest: str,
    config_digest: str,
    candidate_set_digest: str,
    corpus_provenance_digest: str,
    candidates: Sequence[OperatingPoint],
    candidate_results: Sequence[dict[str, Any]],
    cases: Sequence[CalibrationCase],
) -> dict[str, Any]:
    required_fields = {
        "decision_id",
        "decision_version",
        "decision_date",
        "owner",
        "selection_method",
        "automatic_selection",
        "fallback_operating_point_id",
        "scope",
        "experiment_id",
        "experiment_version",
        "frozen_calibration_config_sha256",
        "frozen_candidate_set_sha256",
        "frozen_corpus_provenance_sha256",
        "selected_operating_point_id",
        "selected_operating_point_digest",
        "selected_parameters",
        "approved_holdout_error_budget",
        "accepted_false_invalid",
        "rationale",
        "specification_transition",
        "universal_default",
    }
    if set(decision) != required_fields:
        missing = sorted(required_fields - set(decision))
        unknown = sorted(set(decision) - required_fields)
        raise ValueError(f"decision fields mismatch; missing={missing}, unknown={unknown}")
    fixed_values = {
        "decision_id": "M1-ALIGNMENT-OP-001",
        "decision_version": "1.0.0",
        "decision_date": "2026-08-15",
        "owner": "repository-maintainer",
        "selection_method": "explicit_human_owner_decision",
        "automatic_selection": False,
        "fallback_operating_point_id": None,
        "scope": "m1-manifest-policy-only",
        "experiment_id": "T-CMP-CAL-001",
        "experiment_version": "1.0.0",
        "frozen_calibration_config_sha256": config_digest,
        "frozen_candidate_set_sha256": candidate_set_digest,
        "frozen_corpus_provenance_sha256": corpus_provenance_digest,
        "specification_transition": "Accepted",
        "universal_default": False,
    }
    for name, expected in fixed_values.items():
        actual = decision[name]
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f"decision {name} must be exactly {expected!r}, got {actual!r}")
    if not isinstance(decision["rationale"], list) or not decision["rationale"]:
        raise ValueError("decision rationale must be a non-empty list")
    if not all(isinstance(item, str) and item for item in decision["rationale"]):
        raise ValueError("every decision rationale entry must be non-empty text")

    selected_id = decision["selected_operating_point_id"]
    matching_candidates = [point for point in candidates if point.id == selected_id]
    if len(matching_candidates) != 1:
        raise ValueError(f"selected operating point is not exactly one frozen candidate: {selected_id!r}")
    selected = matching_candidates[0]
    expected_parameters = _operating_point_parameters(selected)
    if set(decision["selected_parameters"]) != set(OPERATING_POINT_PARAMETER_NAMES):
        raise ValueError("selected_parameters must contain exactly the seven calibrated parameters")
    for name, expected in expected_parameters.items():
        actual = decision["selected_parameters"][name]
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f"selected parameter {name} must be exactly {expected!r}, got {actual!r}")
    if decision["selected_operating_point_digest"] != selected.parameter_digest():
        raise ValueError("selected operating-point digest does not match the frozen candidate")

    matching_results = [item for item in candidate_results if item["operating_point"]["id"] == selected_id]
    if len(matching_results) != 1:
        raise ValueError("selected operating point does not have exactly one evaluation result")
    selected_result = matching_results[0]
    holdout_summary = selected_result["holdout"]["summary"]
    budget_names = ("false_valid", "wrong_lag_valid", "false_ambiguous", "false_invalid")
    approved_budget = decision["approved_holdout_error_budget"]
    if set(approved_budget) != set(budget_names):
        raise ValueError("approved holdout budget has missing or unknown counters")
    observed_budget = {name: holdout_summary[name] for name in budget_names}
    for name in budget_names:
        if type(approved_budget[name]) is not int or approved_budget[name] != observed_budget[name]:
            raise ValueError(
                f"selected holdout budget mismatch for {name}: approved={approved_budget[name]!r}, observed={observed_budget[name]!r}"
            )

    false_invalid_records = [
        record for record in selected_result["holdout"]["case_results"] if record["false_invalid"]
    ]
    if len(false_invalid_records) != approved_budget["false_invalid"]:
        raise ValueError("selected false-invalid records do not match the approved count")
    limitation = decision["accepted_false_invalid"]
    if len(false_invalid_records) != 1 or false_invalid_records[0]["case_id"] != limitation.get("case_id"):
        raise ValueError("accepted false-invalid case does not match the selected holdout result")
    false_invalid = false_invalid_records[0]
    case_by_id = {case.case_id: case for case in cases}
    limitation_case = case_by_id[false_invalid["case_id"]]
    limitation_expected = {
        "case_id": false_invalid["case_id"],
        "oracle_class": false_invalid["oracle_class"],
        "oracle_lag_frames": false_invalid["oracle_lag_frames"],
        "classification": false_invalid["classification"],
        "reason": false_invalid["reason"],
        "sync_region_length_frames": min(
            limitation_case.baseline_sync_length_frames,
            limitation_case.candidate_sync_length_frames,
        ),
        "minimum_overlap_frames": selected.minimum_overlap_frames,
    }
    for name, expected in limitation_expected.items():
        if limitation.get(name) != expected:
            raise ValueError(f"accepted limitation {name} must be {expected!r}, got {limitation.get(name)!r}")
    if not isinstance(limitation.get("rationale"), str) or not limitation["rationale"]:
        raise ValueError("accepted false-invalid limitation requires rationale")

    return {
        "status": "approved",
        "decision_id": decision["decision_id"],
        "decision_version": decision["decision_version"],
        "decision_date": decision["decision_date"],
        "decision_sha256": decision_digest,
        "owner": decision["owner"],
        "selection_method": decision["selection_method"],
        "selected_operating_point": selected.id,
        "selected_operating_point_digest": selected.parameter_digest(),
        "selected_parameters": expected_parameters,
        "automatic_selection": False,
        "fallback_operating_point_id": None,
        "scope": decision["scope"],
        "universal_default": False,
        "frozen_calibration_config_sha256": config_digest,
        "frozen_candidate_set_sha256": candidate_set_digest,
        "frozen_corpus_provenance_sha256": corpus_provenance_digest,
        "approved_holdout_error_budget": dict(approved_budget),
        "observed_holdout_error_budget": observed_budget,
        "error_budget_satisfied": True,
        "accepted_false_invalid": dict(limitation),
        "rationale": list(decision["rationale"]),
        "spec_001_status": decision["specification_transition"],
    }


def _empty_matrix() -> dict[str, dict[str, int]]:
    return {
        oracle: {classification: 0 for classification in ("valid", "ambiguous", "invalid")}
        for oracle in ("unique", "ambiguous", "invalid")
    }


def _case_evaluation(case: CalibrationCase, point: OperatingPoint, observations: Sequence[LagObservation], *, unchanged: bool) -> dict[str, Any]:
    result = evaluate_observations(observations, point, inputs_unchanged=unchanged)
    wrong_lag = (
        case.oracle_class == "unique"
        and result.classification == "valid"
        and result.reported_lag_frames != case.oracle_lag_frames
    )
    ambiguous_as_valid = case.oracle_class == "ambiguous" and result.classification == "valid"
    invalid_as_valid = case.oracle_class == "invalid" and result.classification == "valid"
    false_valid = wrong_lag or ambiguous_as_valid or invalid_as_valid
    false_ambiguous = case.oracle_class == "unique" and result.classification == "ambiguous"
    false_invalid = case.oracle_class == "unique" and result.classification == "invalid"
    correct_unique = (
        case.oracle_class == "unique"
        and result.classification == "valid"
        and result.reported_lag_frames == case.oracle_lag_frames
    )
    correct_ambiguous = case.oracle_class == "ambiguous" and result.classification == "ambiguous"
    correct_invalid = case.oracle_class == "invalid" and result.classification == "invalid"
    return {
        "case_id": case.case_id,
        "split": case.split,
        "family_id": case.family_id,
        "oracle_class": case.oracle_class,
        "oracle_lag_frames": case.oracle_lag_frames,
        "classification": result.classification,
        "reason": result.reason,
        "reported_lag_frames": result.reported_lag_frames,
        "local_lag_frames": result.local_lag_frames,
        "signed_primary_correlation": result.signed_primary_correlation,
        "primary_abs_correlation": result.primary_abs_correlation,
        "primary_plateau_width_frames": result.primary_plateau_width_frames,
        "equivalent_primary_peak_count": result.equivalent_primary_peak_count,
        "secondary_peak_lag_frames": result.secondary_peak_lag_frames,
        "secondary_peak_abs_correlation": result.secondary_peak_abs_correlation,
        "secondary_peak_present": result.secondary_peak_present,
        "peak_ratio_value": result.peak_ratio_value,
        "peak_ratio_kind": result.peak_ratio_kind,
        "valid_lag_count": result.valid_lag_count,
        "input_buffers_unchanged": result.input_buffers_unchanged,
        "wrong_lag_valid": wrong_lag,
        "ambiguous_as_valid": ambiguous_as_valid,
        "invalid_as_valid": invalid_as_valid,
        "false_valid": false_valid,
        "false_ambiguous": false_ambiguous,
        "false_invalid": false_invalid,
        "correct_unique": correct_unique,
        "correct_ambiguous": correct_ambiguous,
        "correct_invalid": correct_invalid,
        "correct_outcome": correct_unique or correct_ambiguous or correct_invalid,
        "strata": case.strata,
    }


def _summarize_records(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    matrix = _empty_matrix()
    for record in records:
        matrix[record["oracle_class"]][record["classification"]] += 1
    counters = {
        name: sum(1 for record in records if record[name])
        for name in (
            "false_valid",
            "wrong_lag_valid",
            "ambiguous_as_valid",
            "invalid_as_valid",
            "false_ambiguous",
            "false_invalid",
            "correct_unique",
            "correct_ambiguous",
            "correct_invalid",
            "correct_outcome",
        )
    }
    by_family: dict[str, Any] = {}
    for family in sorted({record["family_id"] for record in records}):
        family_records = [record for record in records if record["family_id"] == family]
        family_matrix = _empty_matrix()
        for record in family_records:
            family_matrix[record["oracle_class"]][record["classification"]] += 1
        by_family[family] = {
            "case_count": len(family_records),
            "matrix": family_matrix,
            **{
                name: sum(1 for record in family_records if record[name])
                for name in (
                    "false_valid",
                    "wrong_lag_valid",
                    "false_ambiguous",
                    "false_invalid",
                    "correct_ambiguous",
                    "correct_invalid",
                )
            },
        }
    sensitivity: dict[str, Any] = {}
    strata_names = sorted({name for record in records for name in record["strata"]})
    for stratum in strata_names:
        sensitivity[stratum] = {}
        categories = sorted({record["strata"][stratum] for record in records})
        for category in categories:
            category_records = [record for record in records if record["strata"][stratum] == category]
            sensitivity[stratum][category] = {
                "case_count": len(category_records),
                "false_valid": sum(1 for record in category_records if record["false_valid"]),
                "wrong_lag_valid": sum(1 for record in category_records if record["wrong_lag_valid"]),
                "false_ambiguous": sum(1 for record in category_records if record["false_ambiguous"]),
                "false_invalid": sum(1 for record in category_records if record["false_invalid"]),
            }
    return {
        "case_count": len(records),
        "classification_matrix": matrix,
        **counters,
        "by_family": by_family,
        "sensitivity": sensitivity,
    }


def _evaluate_point(
    point: OperatingPoint,
    cases: Sequence[CalibrationCase],
    observation_cache: dict[str, list[LagObservation]],
    unchanged_by_case: dict[str, bool],
) -> dict[str, Any]:
    records = [
        _case_evaluation(
            case,
            point,
            observation_cache[case.case_id],
            unchanged=unchanged_by_case[case.case_id],
        )
        for case in cases
    ]
    return {
        "operating_point": asdict(point),
        "operating_point_digest": point.parameter_digest(),
        "summary": _summarize_records(records),
        "case_results": records,
    }


def _command_output(command: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def collect_provenance(config_digest: str) -> dict[str, Any]:
    revision = _command_output(["git", "rev-parse", "HEAD"]) or "unavailable"
    status = _command_output(["git", "status", "--porcelain", "--untracked-files=normal"])
    dirty_state = status is None or bool(status)
    toolchain_path = ROOT / "toolchain" / "m1-v1.json"
    toolchain = json.loads(toolchain_path.read_text(encoding="utf-8"))
    submodules = {
        path: _command_output(["git", "-C", str(ROOT / path), "rev-parse", "HEAD"]) or "unavailable"
        for path in toolchain["submodules"]
    }
    versions: dict[str, str | None] = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "git": (_command_output(["git", "--version"]) or "").splitlines()[0] or None,
        "cmake": (_command_output(["cmake", "--version"]) or "").splitlines()[0] or None,
        "ninja": (_command_output(["ninja", "--version"]) or "").splitlines()[0] or None,
    }
    return {
        "source_revision": revision,
        "dirty_state": dirty_state,
        "method_version": METHOD_VERSION,
        "generator_suite_version": GENERATOR_VERSION,
        "configuration_sha256": config_digest,
        "toolchain_record_sha256": _sha256_file(toolchain_path),
        "dependency_lock_sha256": {
            "requirements/runtime.lock": _sha256_file(ROOT / "requirements" / "runtime.lock"),
            "requirements/build-test.lock": _sha256_file(ROOT / "requirements" / "build-test.lock"),
        },
        "dependency_revisions": submodules,
        "runtime_dependencies": "Python standard library only",
        "tool_versions": versions,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
    }


def run_experiment(config_path: Path, decision_path: Path | None = None) -> dict[str, Any]:
    config, config_digest = load_config(config_path)
    if config.get("experiment_id") != "T-CMP-CAL-001":
        raise ValueError("unexpected experiment_id")
    cases = build_corpus(config)
    leakage_checks = validate_corpus_separation(cases, config)
    observation_cache: dict[str, list[LagObservation]] = {}
    unchanged_by_case: dict[str, bool] = {}
    for case in cases:
        before = (_sha256_bytes(_float32_bytes(case.baseline)), _sha256_bytes(_float32_bytes(case.candidate)))
        observation_cache[case.case_id] = compute_lag_observations(case)
        after = (_sha256_bytes(_float32_bytes(case.baseline)), _sha256_bytes(_float32_bytes(case.candidate)))
        unchanged_by_case[case.case_id] = before == after
    if not all(unchanged_by_case.values()):
        raise RuntimeError("measurement input changed during correlation observation")

    calibration_cases = [case for case in cases if case.split == "calibration"]
    holdout_cases = [case for case in cases if case.split == "holdout"]
    sweep_results = [
        _evaluate_point(point, calibration_cases, observation_cache, unchanged_by_case)
        for point in build_sweep(config)
    ]
    candidates = build_candidates(config)
    frozen_candidate_digest = _sha256_bytes(_canonical_json([asdict(point) for point in candidates]))
    candidate_results = []
    for point in candidates:
        candidate_results.append(
            {
                "operating_point": asdict(point),
                "operating_point_digest": point.parameter_digest(),
                "calibration": _evaluate_point(point, calibration_cases, observation_cache, unchanged_by_case),
                "holdout": _evaluate_point(point, holdout_cases, observation_cache, unchanged_by_case),
            }
        )
    case_provenance = [case.provenance() for case in cases]
    corpus_provenance_digest = _sha256_bytes(_canonical_json(case_provenance))
    if decision_path is None:
        decision_record = _pending_decision()
    else:
        decision, decision_digest = load_config(decision_path)
        decision_record = validate_m1_decision(
            decision,
            decision_digest=decision_digest,
            config_digest=config_digest,
            candidate_set_digest=frozen_candidate_digest,
            corpus_provenance_digest=corpus_provenance_digest,
            candidates=candidates,
            candidate_results=candidate_results,
            cases=cases,
        )
    raw_observations = {
        case.case_id: [asdict(observation) for observation in observation_cache[case.case_id]]
        for case in cases
    }
    reproduction_arguments = [
        "python", "tools/alignment_calibration.py", "--config", "configs/calibration/t_cmp_cal_001.json",
    ]
    if decision_path is not None:
        reproduction_arguments.extend(["--decision", "configs/policies/m1-alignment-operating-point.json"])
    reproduction_arguments.extend(["--output", "artifacts/t_cmp_cal_001"])
    return {
        "schema_version": "1.0.0",
        "experiment_id": "T-CMP-CAL-001",
        "experiment_version": config["experiment_version"],
        "requirements": config["requirements"],
        "provenance": collect_provenance(config_digest),
        "reproduction": {
            "display_command": " ".join(reproduction_arguments),
            "arguments": reproduction_arguments,
        },
        "method_document": "docs/calibration/T-CMP-CAL-001-method.md",
        "search_bounds_reported_lag_frames": config["search_bounds_reported_lag_frames"],
        "leakage_checks": leakage_checks,
        "frozen_candidate_set_sha256": frozen_candidate_digest,
        "frozen_corpus_provenance_sha256": corpus_provenance_digest,
        "case_provenance": case_provenance,
        "calibration_sweep": sweep_results,
        "candidate_results": candidate_results,
        "decision": decision_record,
        "raw_lag_observations": raw_observations,
    }


def _curated_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": result["schema_version"],
        "experiment_id": result["experiment_id"],
        "experiment_version": result["experiment_version"],
        "requirements": result["requirements"],
        "provenance": result["provenance"],
        "reproduction": result["reproduction"],
        "method_document": result["method_document"],
        "search_bounds_reported_lag_frames": result["search_bounds_reported_lag_frames"],
        "leakage_checks": result["leakage_checks"],
        "frozen_candidate_set_sha256": result["frozen_candidate_set_sha256"],
        "frozen_corpus_provenance_sha256": result["frozen_corpus_provenance_sha256"],
        "case_provenance": result["case_provenance"],
        "calibration_sweep": [
            {
                "operating_point": item["operating_point"],
                "operating_point_digest": item["operating_point_digest"],
                "summary": item["summary"],
            }
            for item in result["calibration_sweep"]
        ],
        "candidate_results": [
            {
                "operating_point": item["operating_point"],
                "operating_point_digest": item["operating_point_digest"],
                "calibration": {"summary": item["calibration"]["summary"]},
                "holdout": {"summary": item["holdout"]["summary"]},
                "holdout_zero_false_valid": item["holdout"]["summary"]["false_valid"] == 0,
            }
            for item in result["candidate_results"]
        ],
        "decision": result["decision"],
    }


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _configuration_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in result["calibration_sweep"]:
        summary = item["summary"]
        point = item["operating_point"]
        rows.append({
            "configuration_kind": "OFAT", "split": "calibration", "operating_point_id": point["id"],
            "operating_point_digest": item["operating_point_digest"],
            **{key: point[key] for key in (
                "plateau_epsilon", "maximum_primary_plateau_width_frames", "secondary_exclusion_radius_frames",
                "minimum_primary_abs_correlation", "minimum_accepted_peak_ratio", "sync_rms_floor_linear_fs",
                "minimum_overlap_frames",
            )},
            **{key: summary[key] for key in (
                "case_count", "false_valid", "wrong_lag_valid", "ambiguous_as_valid", "invalid_as_valid",
                "false_ambiguous", "false_invalid", "correct_unique", "correct_ambiguous", "correct_invalid",
            )},
        })
    for item in result["candidate_results"]:
        for split in ("calibration", "holdout"):
            summary = item[split]["summary"]
            point = item["operating_point"]
            rows.append({
                "configuration_kind": "frozen_candidate", "split": split, "operating_point_id": point["id"],
                "operating_point_digest": item["operating_point_digest"],
                **{key: point[key] for key in (
                    "plateau_epsilon", "maximum_primary_plateau_width_frames", "secondary_exclusion_radius_frames",
                    "minimum_primary_abs_correlation", "minimum_accepted_peak_ratio", "sync_rms_floor_linear_fs",
                    "minimum_overlap_frames",
                )},
                **{key: summary[key] for key in (
                    "case_count", "false_valid", "wrong_lag_valid", "ambiguous_as_valid", "invalid_as_valid",
                    "false_ambiguous", "false_invalid", "correct_unique", "correct_ambiguous", "correct_invalid",
                )},
            })
    return rows


def _case_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for case in result["case_provenance"]:
        rows.append({
            "case_id": case["case_id"], "split": case["split"], "family_id": case["family_id"],
            "oracle_class": case["oracle_class"], "oracle_lag_frames": case["oracle_lag_frames"],
            "oracle_reason": case["oracle_reason"], "generator_id": case["generator_id"],
            "generator_version": case["generator_version"], "seed": case["seed"],
            "parameters_json": json.dumps(case["parameters"], allow_nan=False, sort_keys=True, separators=(",", ":")),
            "parameter_digest": case["parameter_digest"],
            "baseline_sha256_float32_le": case["baseline_sha256_float32_le"],
            "candidate_sha256_float32_le": case["candidate_sha256_float32_le"],
            "pcm_pair_sha256": case["pcm_pair_sha256"],
            "strata_json": json.dumps(case["strata"], sort_keys=True, separators=(",", ":")),
        })
    return rows


def _candidate_case_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for candidate in result["candidate_results"]:
        point_id = candidate["operating_point"]["id"]
        for split in ("calibration", "holdout"):
            for record in candidate[split]["case_results"]:
                rows.append({
                    "operating_point_id": point_id, "split": split, "case_id": record["case_id"],
                    "family_id": record["family_id"], "oracle_class": record["oracle_class"],
                    "oracle_lag_frames": record["oracle_lag_frames"], "classification": record["classification"],
                    "reason": record["reason"], "reported_lag_frames": record["reported_lag_frames"],
                    "signed_primary_correlation": record["signed_primary_correlation"],
                    "primary_abs_correlation": record["primary_abs_correlation"],
                    "primary_plateau_width_frames": record["primary_plateau_width_frames"],
                    "peak_ratio_value": record["peak_ratio_value"], "peak_ratio_kind": record["peak_ratio_kind"],
                    "false_valid": record["false_valid"], "wrong_lag_valid": record["wrong_lag_valid"],
                    "false_ambiguous": record["false_ambiguous"], "false_invalid": record["false_invalid"],
                    "correct_outcome": record["correct_outcome"],
                })
    return rows


def _tradeoff_svg(result: dict[str, Any]) -> str:
    candidates = result["candidate_results"]
    values = [item[split]["summary"] for item in candidates for split in ("calibration", "holdout")]
    max_x = max([summary["false_valid"] for summary in values] + [1])
    max_y = max([summary["false_ambiguous"] + summary["false_invalid"] for summary in values] + [1])
    width, height = 760, 400
    left, top, plot_width, plot_height = 70, 50, 400, 260
    elements = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="400" viewBox="0 0 760 400" role="img" aria-labelledby="title desc">',
        '<title id="title">T-CMP-CAL-001 candidate tradeoff</title>',
        '<desc id="desc">False-valid versus unique-case rejection counts for calibration and holdout.</desc>',
        '<rect width="760" height="400" fill="white"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#222"/>',
        '<text x="270" y="365" text-anchor="middle" font-family="sans-serif" font-size="13">false-valid (includes wrong-lag valid)</text>',
        '<text x="18" y="180" text-anchor="middle" transform="rotate(-90 18 180)" font-family="sans-serif" font-size="13">unique rejected (ambiguous + invalid)</text>',
    ]
    for value in range(max_x + 1):
        x = left + (value / max_x) * plot_width
        elements.append(f'<line x1="{x:.2f}" y1="{top + plot_height}" x2="{x:.2f}" y2="{top + plot_height + 5}" stroke="#222"/>')
        elements.append(f'<text x="{x:.2f}" y="{top + plot_height + 20}" text-anchor="middle" font-family="sans-serif" font-size="11">{value}</text>')
    for value in range(max_y + 1):
        y = top + plot_height - (value / max_y) * plot_height
        elements.append(f'<line x1="{left - 5}" y1="{y:.2f}" x2="{left}" y2="{y:.2f}" stroke="#222"/>')
        elements.append(f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="sans-serif" font-size="11">{value}</text>')
    colors = {"calibration": "#2f6fbb", "holdout": "#d95f02"}
    for candidate_index, item in enumerate(candidates):
        for split_index, split in enumerate(("calibration", "holdout")):
            summary = item[split]["summary"]
            x_value = summary["false_valid"]
            y_value = summary["false_ambiguous"] + summary["false_invalid"]
            x = left + (x_value / max_x) * plot_width
            y = top + plot_height - (y_value / max_y) * plot_height
            x += 7 if split_index else 0
            y += (candidate_index - 1) * 8
            elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="8" fill="{colors[split]}" stroke="white" stroke-width="1"/>')
            elements.append(f'<text x="{x:.2f}" y="{y + 4:.2f}" text-anchor="middle" font-family="sans-serif" font-size="10" font-weight="bold" fill="white">{chr(65 + candidate_index)}</text>')
    elements.extend([
        '<text x="505" y="46" font-family="sans-serif" font-size="13" font-weight="bold">Legend: candidate / split</text>',
        '<text x="505" y="64" font-family="sans-serif" font-size="11">values = false-valid, unique rejected</text>',
        '<rect x="505" y="76" width="12" height="12" fill="#2f6fbb"/><text x="523" y="87" font-family="sans-serif" font-size="11">calibration</text>',
        '<rect x="610" y="76" width="12" height="12" fill="#d95f02"/><text x="628" y="87" font-family="sans-serif" font-size="11">holdout</text>',
    ])
    for candidate_index, item in enumerate(candidates):
        calibration = item["calibration"]["summary"]
        holdout = item["holdout"]["summary"]
        y = 122 + candidate_index * 72
        label = item["operating_point"]["id"]
        elements.extend([
            f'<text x="505" y="{y}" font-family="sans-serif" font-size="12" font-weight="bold">{chr(65 + candidate_index)} — {label}</text>',
            f'<text x="523" y="{y + 20}" font-family="sans-serif" font-size="11">calibration: {calibration["false_valid"]}, {calibration["false_ambiguous"] + calibration["false_invalid"]}</text>',
            f'<text x="523" y="{y + 38}" font-family="sans-serif" font-size="11">holdout: {holdout["false_valid"]}, {holdout["false_ambiguous"] + holdout["false_invalid"]}</text>',
        ])
    elements.extend([
        '</svg>',
    ])
    return "\n".join(elements) + "\n"


def _matrix_inline(matrix: dict[str, dict[str, int]]) -> str:
    return "; ".join(
        f"{oracle}: V={row['valid']} A={row['ambiguous']} I={row['invalid']}"
        for oracle, row in matrix.items()
    )


def _evidence_markdown(result: dict[str, Any], summary_sha256: str, raw_sha256: str) -> str:
    provenance = result["provenance"]
    decision = result["decision"]
    approved = decision["status"] == "approved"
    lines = [
        "# T-CMP-CAL-001 calibration evidence",
        "",
        (
            "- **Phase:** FASE B; explicit human operating-point decision recorded"
            if approved
            else "- **Phase:** FASE A; human operating-point decision pending"
        ),
        (
            "- **SPEC-001 status:** `Accepted` (not `Verified`)"
            if approved
            else "- **SPEC-001 status:** `Review` (unchanged)"
        ),
        f"- **Source revision:** `{provenance['source_revision']}`",
        f"- **Dirty at execution:** `{str(provenance['dirty_state']).lower()}`",
        f"- **Configuration SHA-256:** `{provenance['configuration_sha256']}`",
        f"- **Frozen candidate-set SHA-256:** `{result['frozen_candidate_set_sha256']}`",
        f"- **Frozen corpus-provenance SHA-256:** `{result['frozen_corpus_provenance_sha256']}`",
        *(
            [f"- **M1 decision SHA-256:** `{decision['decision_sha256']}`"]
            if approved
            else []
        ),
        f"- **Curated summary SHA-256:** `{summary_sha256}`",
        f"- **Ignored full raw result SHA-256:** `{raw_sha256}`",
        "",
        "The labels, formulas, tie/plateau/exclusion rules, error definitions,",
        "sweep bounds, and leakage interpretation were frozen in",
        "[`T-CMP-CAL-001-method.md`](../../calibration/T-CMP-CAL-001-method.md)",
        "before evaluating holdout. No production comparator is included.",
        "",
        "## Reproduction",
        "",
        "```text",
        result["reproduction"]["display_command"],
        "```",
        "",
        "The command writes full lag observations under ignored `artifacts/`.",
        "The checked-in summary omits those large curves but records their run digest.",
        "",
        "## Corpus separation",
        "",
        f"Calibration cases: {sum(1 for case in result['case_provenance'] if case['split'] == 'calibration')}; "
        f"holdout cases: {sum(1 for case in result['case_provenance'] if case['split'] == 'holdout')}.",
        "Case IDs, seeds, concrete generator families, canonical parameter digests,",
        "and generated PCM-pair digests have empty calibration/holdout intersections.",
        "See `cases.csv` and `summary.json` for the recorded generator provenance.",
        "",
        "## Frozen operating-point candidates",
        "",
        "| Candidate | Split | False-valid | Wrong-lag valid | False-ambiguous | False-invalid | Matrix |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for candidate in result["candidate_results"]:
        for split in ("calibration", "holdout"):
            item = candidate[split]["summary"]
            lines.append(
                f"| {candidate['operating_point']['id']} | {split} | {item['false_valid']} | "
                f"{item['wrong_lag_valid']} | {item['false_ambiguous']} | {item['false_invalid']} | "
                f"{_matrix_inline(item['classification_matrix'])} |"
            )
    lines.extend([
        "",
        "`false_valid` includes ambiguous-as-valid, invalid-as-valid, and wrong-lag",
        "valid outcomes. It is therefore the safety count used by the owner's initial",
        "zero-false-valid holdout criterion.",
        "",
        "![Candidate tradeoff](tradeoff.svg)",
        "",
        "## Holdout results by family",
        "",
        "| Candidate | Family | Cases | False-valid | Wrong-lag | False-ambiguous | False-invalid | Correct ambiguous | Correct invalid |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for candidate in result["candidate_results"]:
        by_family = candidate["holdout"]["summary"]["by_family"]
        for family, item in by_family.items():
            lines.append(
                f"| {candidate['operating_point']['id']} | {family} | {item['case_count']} | "
                f"{item['false_valid']} | {item['wrong_lag_valid']} | {item['false_ambiguous']} | "
                f"{item['false_invalid']} | {item['correct_ambiguous']} | {item['correct_invalid']} |"
            )
    lines.extend([
        "",
        "## Parameters and tradeoffs",
        "",
    ])
    for candidate in result["candidate_results"]:
        point = candidate["operating_point"]
        hold = candidate["holdout"]["summary"]
        lines.extend([
            f"### {point['id']}",
            "",
            point["risk_posture"],
            "",
            f"- `plateau_epsilon={point['plateau_epsilon']}` unitless absolute score difference",
            f"- `maximum_primary_plateau_width_frames={point['maximum_primary_plateau_width_frames']}` frames",
            f"- `secondary_exclusion_radius_frames={point['secondary_exclusion_radius_frames']}` frames",
            f"- `minimum_primary_abs_correlation={point['minimum_primary_abs_correlation']}` unitless",
            f"- `minimum_accepted_peak_ratio={point['minimum_accepted_peak_ratio']}` unitless",
            f"- `sync_rms_floor_linear_fs={point['sync_rms_floor_linear_fs']}` linear FS RMS",
            f"- `minimum_overlap_frames={point['minimum_overlap_frames']}` frames",
            f"- Holdout: false-valid={hold['false_valid']}, false-ambiguous={hold['false_ambiguous']}, false-invalid={hold['false_invalid']}.",
            "",
        ])
    lines.extend([
        "## Holdout sensitivity strata",
        "",
        "| Candidate | Factor | Category | Cases | False-valid | Wrong-lag | False-ambiguous | False-invalid |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for candidate in result["candidate_results"]:
        sensitivity = candidate["holdout"]["summary"]["sensitivity"]
        for factor in ("polarity", "level", "lag_position", "noise", "energy", "overlap"):
            for category, item in sensitivity[factor].items():
                lines.append(
                    f"| {candidate['operating_point']['id']} | {factor} | {category} | {item['case_count']} | "
                    f"{item['false_valid']} | {item['wrong_lag_valid']} | {item['false_ambiguous']} | "
                    f"{item['false_invalid']} |"
                )
    lines.extend([
        "",
        "## Sensitivity and limitations",
        "",
        "`summary.json` records candidate sensitivity strata for polarity, level, lag",
        "position/boundary, noise, energy, overlap, sync origins, and duration. Positive",
        "gain and polarity should not change `abs(rho)` except through sign or RMS-floor",
        "crossings; the evidence tests those invariants rather than claiming sensitivity",
        "where the normalized metric has none.",
        "",
        "This deterministic corpus demonstrates known-case coverage; it does not estimate",
        "a population error rate. OFAT does not cover all parameter interactions, variants",
        "from one construction are correlated, and reusing this holdout after changing a",
        "candidate would turn it into tuning data. Large per-lag score observations remain",
        "outside source control.",
    ])
    if approved:
        selected = decision["selected_parameters"]
        budget = decision["observed_holdout_error_budget"]
        limitation = decision["accepted_false_invalid"]
        lines.extend([
            "",
            "## Accepted M1 operating point",
            "",
            f"The repository owner explicitly selected **{decision['selected_operating_point']}**. ",
            "This decision applies only to the M1 manifest/policy; it is not a universal default.",
            "There is no automatic selection and no fallback operating point.",
            "",
            f"- `plateau_epsilon={selected['plateau_epsilon']}` unitless absolute score difference",
            f"- `maximum_primary_plateau_width_frames={selected['maximum_primary_plateau_width_frames']}` frames",
            f"- `secondary_exclusion_radius_frames={selected['secondary_exclusion_radius_frames']}` frames",
            f"- `minimum_primary_abs_correlation={selected['minimum_primary_abs_correlation']}` unitless",
            f"- `minimum_accepted_peak_ratio={selected['minimum_accepted_peak_ratio']}` unitless",
            f"- `sync_rms_floor_linear_fs={selected['sync_rms_floor_linear_fs']}` linear FS RMS",
            f"- `minimum_overlap_frames={selected['minimum_overlap_frames']}` frames",
            "",
            "The rerun satisfies the approved deterministic holdout budget: "
            f"false-valid={budget['false_valid']}, wrong-lag valid={budget['wrong_lag_valid']}, "
            f"false-ambiguous={budget['false_ambiguous']}, false-invalid={budget['false_invalid']}.",
            "",
            f"The accepted false-invalid is `{limitation['case_id']}`: its "
            f"{limitation['sync_region_length_frames']}-frame sync region cannot satisfy the selected "
            f"{limitation['minimum_overlap_frames']}-frame minimum overlap, so the result remains "
            f"`{limitation['classification']}` with reason `{limitation['reason']}`.",
            "",
            "The rationale is recorded in the M1 decision policy and in SPEC-001. The spike does",
            "not include a production comparator, and acceptance does not claim verification.",
            "",
        ])
    else:
        lines.extend([
            "",
            "## Decision required",
            "",
            "No candidate is selected automatically. The owner must apply the stated risk",
            "criterion, review family-level behavior, and explicitly choose an operating point",
            "before FASE B may record rationale or change SPEC-001 from `Review`.",
            "",
        ])
    return "\n".join(lines)


def write_outputs(result: dict[str, Any], output: Path, publish_small_evidence: Path | None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw-results.json"
    _write_json(raw_path, result)
    summary = _curated_summary(result)
    summary_path = output / "summary.json"
    _write_json(summary_path, summary)
    configuration_rows = _configuration_rows(result)
    case_rows = _case_rows(result)
    candidate_rows = _candidate_case_rows(result)
    _write_csv(output / "configurations.csv", tuple(configuration_rows[0]), configuration_rows)
    _write_csv(output / "cases.csv", tuple(case_rows[0]), case_rows)
    _write_csv(output / "candidate-case-results.csv", tuple(candidate_rows[0]), candidate_rows)
    (output / "tradeoff.svg").write_text(_tradeoff_svg(result), encoding="utf-8", newline="\n")
    raw_sha256 = _sha256_file(raw_path)
    summary_sha256 = _sha256_file(summary_path)
    markdown = _evidence_markdown(result, summary_sha256, raw_sha256)
    (output / "README.md").write_text(markdown, encoding="utf-8", newline="\n")
    if publish_small_evidence is not None:
        publish_small_evidence.mkdir(parents=True, exist_ok=True)
        _write_json(publish_small_evidence / "summary.json", summary)
        _write_csv(publish_small_evidence / "configurations.csv", tuple(configuration_rows[0]), configuration_rows)
        _write_csv(publish_small_evidence / "cases.csv", tuple(case_rows[0]), case_rows)
        _write_csv(publish_small_evidence / "candidate-case-results.csv", tuple(candidate_rows[0]), candidate_rows)
        (publish_small_evidence / "tradeoff.svg").write_text(_tradeoff_svg(result), encoding="utf-8", newline="\n")
        (publish_small_evidence / "README.md").write_text(markdown, encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish-small-evidence", type=Path)
    args = parser.parse_args(argv)
    result = run_experiment(args.config, args.decision)
    write_outputs(result, args.output, args.publish_small_evidence)
    for candidate in result["candidate_results"]:
        calibration = candidate["calibration"]["summary"]
        holdout = candidate["holdout"]["summary"]
        print(
            f"{candidate['operating_point']['id']}: "
            f"calibration false-valid={calibration['false_valid']} unique-rejected={calibration['false_ambiguous'] + calibration['false_invalid']}; "
            f"holdout false-valid={holdout['false_valid']} unique-rejected={holdout['false_ambiguous'] + holdout['false_invalid']}"
        )
    print(f"full results: {args.output.resolve()}")
    if args.publish_small_evidence:
        print(f"curated evidence: {args.publish_small_evidence.resolve()}")
    decision = result["decision"]
    if decision["status"] == "approved":
        budget = decision["observed_holdout_error_budget"]
        print(
            f"selected M1 operating point: {decision['selected_operating_point']}; "
            f"holdout false-valid={budget['false_valid']} wrong-lag-valid={budget['wrong_lag_valid']} "
            f"false-ambiguous={budget['false_ambiguous']} false-invalid={budget['false_invalid']}"
        )
        print("SPEC-001 acceptance evidence recorded; production verification remains outstanding.")
    else:
        print("SPEC-001 remains Review; human operating-point decision required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
