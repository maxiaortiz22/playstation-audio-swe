"""Small manifest-to-report runner for Interview Demo Core DEMO-3 only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping

import numpy as np

from .analysis import (
    AlignmentOperatingPoint,
    AlignmentRequest,
    AnalysisInputError,
    AudioDescription,
    ChannelMappingConfig,
    DropoutConfig,
    StructuralValidationConfig,
    TimeAlignmentRequest,
    ValidatedAlignment,
    analyze_stereo_channel_mapping,
    apply_integer_time_alignment,
    compute_gain_metrics,
    compute_residual_metrics,
    detect_dropouts,
    diagnose_polarity,
    estimate_integer_alignment,
    validate_structure,
)
from .contracts import LoadedContract, dump_contract, load_contract
from .faults import (
    FaultInjection,
    inject_dropout,
    inject_integer_delay,
    inject_stereo_channel_swap,
)
from .reporting import render_report
from .stimuli import generate_stimulus


EXIT_PASS = 0
EXIT_POLICY_FAILURE = 1
EXIT_INVALID = 2
EXIT_INTERNAL_ERROR = 3

_DEMO_METRICS = {
    "latency_frames",
    "residual_peak_linear_fs",
    "gain_delta_db",
    "polarity",
    "channel_mapping",
    "dropout_event_count",
}
_OP_B_VALUES = {
    "plateau_epsilon": 0.00001,
    "maximum_primary_plateau_width_frames": 2,
    "secondary_exclusion_radius_frames": 4,
    "minimum_primary_abs_correlation": 0.5,
    "minimum_accepted_peak_ratio": 1.1,
    "sync_rms_floor_linear_fs": 0.00001,
    "minimum_overlap_frames": 64,
}


class DemoInputError(ValueError):
    """A schema-valid document is outside the explicit DEMO-3 contract."""


class DemoReportingError(RuntimeError):
    """Mandatory result/report generation could not complete trustworthily."""


@dataclass(frozen=True)
class WorkflowOutcome:
    exit_code: int
    result_path: Path
    report_path: Path
    result: dict[str, Any]


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise DemoInputError(f"{name} must be an object")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DemoInputError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DemoInputError(f"{name} must be a number")
    result = float(value)
    if not np.isfinite(result):
        raise DemoInputError(f"{name} must be finite")
    return result


def _non_empty_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DemoInputError(f"{name} must be a non-empty string")
    return value


def _exact_parameters(
    metrics: Mapping[str, Mapping[str, Any]], metric_id: str, expected: set[str]
) -> Mapping[str, Any]:
    parameters = _mapping(metrics[metric_id]["parameters"], f"{metric_id} parameters")
    if set(parameters) != expected:
        raise DemoInputError(f"{metric_id} requires exactly {sorted(expected)}")
    _non_empty_text(parameters["rationale"], f"{metric_id} rationale")
    return parameters


def _metric_documents(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    metrics = {item["id"]: item for item in document["metrics"]}
    if len(metrics) != len(document["metrics"]):
        raise DemoInputError("DEMO-3 metric IDs must be unique")
    if set(metrics) != _DEMO_METRICS:
        raise DemoInputError(
            f"DEMO-3 requires the exact focused metric set {sorted(_DEMO_METRICS)}"
        )
    return metrics


def _alignment_operating_point(parameters: Mapping[str, Any]) -> AlignmentOperatingPoint:
    operating = _mapping(parameters.get("operating_point"), "latency operating_point")
    required = {
        "id",
        "decision_id",
        "decision_version",
        "scope",
        "source_sha256",
        "selected_operating_point_digest",
        *_OP_B_VALUES,
    }
    if set(operating) != required:
        raise DemoInputError("latency operating_point must contain the exact OP-B fields")
    if operating["id"] != "OP-B-intermediate":
        raise DemoInputError("DEMO-3 requires the manifest-declared OP-B-intermediate choice")
    if operating["decision_id"] != "M1-ALIGNMENT-OP-001":
        raise DemoInputError("alignment decision_id must be M1-ALIGNMENT-OP-001")
    if operating["scope"] != "m1-manifest-policy-only":
        raise DemoInputError("alignment operating point must retain its M1-only scope")
    source_sha = operating["source_sha256"]
    digest = operating["selected_operating_point_digest"]
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise DemoInputError("alignment source_sha256 must be a lowercase SHA-256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise DemoInputError("selected operating-point digest must be a lowercase SHA-256")
    for name, expected in _OP_B_VALUES.items():
        if operating[name] != expected:
            raise DemoInputError(f"{name} must equal the accepted manifest-scoped OP-B value")
    digest_input = {"id": operating["id"], **_OP_B_VALUES}
    calculated = hashlib.sha256(
        (json.dumps(digest_input, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    if calculated != digest:
        raise DemoInputError("selected operating-point digest does not match OP-B parameters")
    return AlignmentOperatingPoint(
        id=operating["id"],
        decision_id=operating["decision_id"],
        decision_version=operating["decision_version"],
        scope=operating["scope"],
        source_sha256=source_sha,
        selected_operating_point_digest=digest,
        plateau_epsilon=float(operating["plateau_epsilon"]),
        maximum_primary_plateau_width_frames=int(
            operating["maximum_primary_plateau_width_frames"]
        ),
        secondary_exclusion_radius_frames=int(
            operating["secondary_exclusion_radius_frames"]
        ),
        minimum_primary_abs_correlation=float(
            operating["minimum_primary_abs_correlation"]
        ),
        minimum_accepted_peak_ratio=float(operating["minimum_accepted_peak_ratio"]),
        sync_rms_floor_linear_fs=float(operating["sync_rms_floor_linear_fs"]),
        minimum_overlap_frames=int(operating["minimum_overlap_frames"]),
        rationale=("Explicit OP-B-intermediate values embedded by this manifest.",),
    )


def _validate_timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) < 20 or not value.endswith("Z"):
        raise DemoInputError("sut.parameters.result_timestamp_utc must be RFC 3339 UTC text")
    try:
        from datetime import datetime

        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DemoInputError("result_timestamp_utc is not a valid RFC 3339 timestamp") from error
    return value


def _validate_fault(document: Mapping[str, Any]) -> None:
    faults = document["faults"]
    if len(faults) > 1:
        raise DemoInputError("DEMO-3 supports zero or one labeled fault")
    if not faults:
        return
    fault = faults[0]
    parameters = _mapping(fault["parameters"], "fault parameters")
    frames = document["audio_format"]["frame_count"]
    channels = len(document["channel_map"])
    if fault["type"] == "integer_delay":
        if set(parameters) != {"delay_frames"}:
            raise DemoInputError("integer_delay requires only delay_frames")
        delay = _integer(parameters["delay_frames"], "delay_frames")
        if abs(delay) >= frames:
            raise DemoInputError("abs(delay_frames) must be smaller than frame_count")
    elif fault["type"] == "stereo_channel_swap":
        if parameters:
            raise DemoInputError("stereo_channel_swap parameters must be empty")
        if channels != 2:
            raise DemoInputError("stereo_channel_swap requires exactly two channels")
    elif fault["type"] == "dropout":
        required = {"start_frame", "end_frame", "channel_indices", "fill_value_linear_fs"}
        if set(parameters) != required:
            raise DemoInputError("dropout requires the exact interval/channel/fill parameters")
        start = _integer(parameters["start_frame"], "dropout start_frame")
        end = _integer(parameters["end_frame"], "dropout end_frame")
        indices = parameters["channel_indices"]
        fill = _number(parameters["fill_value_linear_fs"], "dropout fill_value_linear_fs")
        if not 0 <= start < end <= frames:
            raise DemoInputError("dropout interval must fit inside frame_count")
        if (
            not isinstance(indices, list)
            or not indices
            or any(isinstance(item, bool) or not isinstance(item, int) for item in indices)
            or len(set(indices)) != len(indices)
            or any(item < 0 or item >= channels for item in indices)
        ):
            raise DemoInputError("dropout channel_indices must be unique in-range integers")
        if not -1.0 <= fill <= 1.0:
            raise DemoInputError("dropout fill must be inside inclusive full scale [-1, 1]")
    else:
        raise DemoInputError(f"unsupported DEMO-3 fault type {fault['type']!r}")


def _validate_demo_manifest(manifest: LoadedContract) -> dict[str, Mapping[str, Any]]:
    document = manifest.document
    sut = document["sut"]
    if sut["id"] != "native_passthrough" or sut["version"] != "1":
        raise DemoInputError("DEMO-3 requires exactly native_passthrough/1")
    sut_parameters = _mapping(sut["parameters"], "sut parameters")
    if set(sut_parameters) != {"result_timestamp_utc"}:
        raise DemoInputError(
            "native_passthrough/1 DEMO-3 parameters require only result_timestamp_utc"
        )
    _validate_timestamp(sut_parameters["result_timestamp_utc"])
    if len(document["channel_map"]) != 2:
        raise DemoInputError("the four DEMO-3 scenarios require exactly stereo input")
    if document["block_sizes_frames"] != [127]:
        raise DemoInputError("DEMO-3 manifests use the explicit 127-frame native block size")
    transforms = document["permitted_transforms"]
    if len(transforms) != 1 or transforms[0]["name"] != "integer_time_alignment":
        raise DemoInputError("DEMO-3 requires one explicit integer_time_alignment transform")
    transform_parameters = _mapping(transforms[0]["parameters"], "time alignment parameters")
    if set(transform_parameters) != {"enabled", "affected_metrics"}:
        raise DemoInputError("time alignment requires enabled and affected_metrics")
    if transform_parameters["enabled"] is not True:
        raise DemoInputError("DEMO-3 explicitly enables integer time alignment")
    if transform_parameters["affected_metrics"] != [
        "residual_peak_linear_fs",
        "gain_delta_db",
        "polarity",
        "dropout_event_count",
    ]:
        raise DemoInputError("time alignment affected_metrics must name the focused set")
    metrics = _metric_documents(document)
    latency_parameters = _mapping(metrics["latency_frames"]["parameters"], "latency parameters")
    _alignment_operating_point(latency_parameters)
    for required in (
        "search_min_lag_frames",
        "search_max_lag_frames",
        "sync_method",
        "remove_dc_from_sync",
        "rationale",
        "operating_point",
    ):
        if required not in latency_parameters:
            raise DemoInputError(f"latency parameters are missing {required}")
    if set(latency_parameters) != {
        "search_min_lag_frames",
        "search_max_lag_frames",
        "sync_method",
        "remove_dc_from_sync",
        "rationale",
        "operating_point",
    }:
        raise DemoInputError("latency parameters contain an unsupported DEMO-3 field")
    search_min = _integer(latency_parameters["search_min_lag_frames"], "search minimum")
    search_max = _integer(latency_parameters["search_max_lag_frames"], "search maximum")
    if search_min > search_max:
        raise DemoInputError("latency search minimum must not exceed maximum")
    if latency_parameters["sync_method"] != "mean_all_channels":
        raise DemoInputError("DEMO-3 uses the explicit mean_all_channels sync downmix")
    if not isinstance(latency_parameters["remove_dc_from_sync"], bool):
        raise DemoInputError("remove_dc_from_sync must be Boolean")
    _non_empty_text(latency_parameters["rationale"], "latency rationale")
    if search_max - search_min <= _OP_B_VALUES["secondary_exclusion_radius_frames"]:
        raise DemoInputError("latency search span must exceed the OP-B exclusion radius")

    residual_parameters = _exact_parameters(
        metrics, "residual_peak_linear_fs", {"rms_floor_linear_fs", "rationale"}
    )
    if _number(residual_parameters["rms_floor_linear_fs"], "residual RMS floor") <= 0.0:
        raise DemoInputError("residual RMS floor must be greater than zero")
    gain_parameters = _exact_parameters(
        metrics, "gain_delta_db", {"rms_floor_linear_fs", "rationale"}
    )
    if _number(gain_parameters["rms_floor_linear_fs"], "gain RMS floor") <= 0.0:
        raise DemoInputError("gain RMS floor must be greater than zero")
    polarity_parameters = _exact_parameters(
        metrics,
        "polarity",
        {"signal_rms_floor_linear_fs", "minimum_abs_correlation", "rationale"},
    )
    polarity_floor = _number(
        polarity_parameters["signal_rms_floor_linear_fs"], "polarity signal RMS floor"
    )
    polarity_minimum = _number(
        polarity_parameters["minimum_abs_correlation"], "polarity correlation minimum"
    )
    if polarity_floor < 0.0 or not 0.0 < polarity_minimum <= 1.0:
        raise DemoInputError("polarity parameters require RMS >= 0 and correlation in (0, 1]")
    mapping_parameters = _exact_parameters(
        metrics,
        "channel_mapping",
        {"minimum_mapping_margin", "signal_rms_floor_linear_fs", "rationale"},
    )
    mapping_margin = _number(
        mapping_parameters["minimum_mapping_margin"], "mapping margin"
    )
    mapping_floor = _number(
        mapping_parameters["signal_rms_floor_linear_fs"], "mapping signal RMS floor"
    )
    if not 0.0 <= mapping_margin <= 1.0 or mapping_floor < 0.0:
        raise DemoInputError("mapping parameters require margin in [0, 1] and RMS floor >= 0")
    dropout_parameters = _exact_parameters(
        metrics,
        "dropout_event_count",
        {
            "active_reference_floor_linear_fs",
            "near_silence_floor_linear_fs",
            "minimum_duration_frames",
            "rationale",
        },
    )
    active_floor = _number(
        dropout_parameters["active_reference_floor_linear_fs"],
        "dropout active-reference floor",
    )
    quiet_floor = _number(
        dropout_parameters["near_silence_floor_linear_fs"],
        "dropout near-silence floor",
    )
    minimum_duration = _integer(
        dropout_parameters["minimum_duration_frames"], "dropout minimum duration"
    )
    if active_floor <= 0.0 or quiet_floor < 0.0 or quiet_floor >= active_floor:
        raise DemoInputError("dropout floors require 0 <= near-silence < active-reference")
    if minimum_duration <= 0:
        raise DemoInputError("dropout minimum duration must be positive frames")
    policies = document["policies"]
    policy_ids = [policy["id"] for policy in policies]
    if len(set(policy_ids)) != len(policy_ids):
        raise DemoInputError("DEMO-3 policy IDs must be unique")
    for policy in policies:
        metric_id = policy["metric_id"]
        if metric_id not in metrics:
            raise DemoInputError(f"policy {policy['id']} references an unknown focused metric")
        if policy["expected_unit"] != metrics[metric_id]["unit"]:
            raise DemoInputError(f"policy {policy['id']} unit does not match its metric")
        if policy["scope"] != metrics[metric_id]["scope"]:
            raise DemoInputError(f"policy {policy['id']} scope does not match its metric")
        if policy["operator"] not in {"upper_bound", "exact_match", "event_count_bound"}:
            raise DemoInputError(f"policy {policy['id']} uses an unsupported focused operator")
        if policy["operator"] in {"upper_bound", "event_count_bound"}:
            _number(policy["threshold"], f"policy {policy['id']} threshold")
            if policy["directionality"] != "higher_is_worse":
                raise DemoInputError(
                    f"policy {policy['id']} upper/event bound must be higher_is_worse"
                )
        else:
            if not isinstance(policy["threshold"], str):
                raise DemoInputError(f"policy {policy['id']} exact threshold must be a string")
            if policy["directionality"] != "exact":
                raise DemoInputError(f"policy {policy['id']} exact match must use exact directionality")
        if policy["minimum_valid_observations"] != 1:
            raise DemoInputError("DEMO-3 policies require one valid observation")
        if policy["compensation_dependencies"] and metric_id == "latency_frames":
            raise DemoInputError("raw latency policy cannot depend on compensation")
    _validate_fault(document)
    if document["artifact_policy"]["output_directory"] != ".":
        raise DemoInputError(
            "DEMO-3 artifact_policy.output_directory must be '.'; CLI --output selects the root"
        )
    return metrics


def _inject_fault(candidate: np.ndarray, document: Mapping[str, Any]) -> FaultInjection | None:
    if not document["faults"]:
        return None
    fault = document["faults"][0]
    parameters = fault["parameters"]
    if fault["type"] == "integer_delay":
        return inject_integer_delay(
            candidate, delay_frames=parameters["delay_frames"], label=fault["label"]
        )
    if fault["type"] == "stereo_channel_swap":
        return inject_stereo_channel_swap(candidate, label=fault["label"])
    return inject_dropout(
        candidate,
        start_frame=parameters["start_frame"],
        end_frame=parameters["end_frame"],
        channel_indices=parameters["channel_indices"],
        fill_value_linear_fs=parameters["fill_value_linear_fs"],
        label=fault["label"],
    )


def _scope(kind: str = "aggregate", **parameters: Any) -> dict[str, Any]:
    return {"kind": kind, "parameters": parameters}


def _metric(
    metric_id: str,
    value: float | None,
    unit: str,
    *,
    validity: str = "valid",
    method: str,
    scope: dict[str, Any] | None = None,
    **details: Any,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "validity": validity,
        "method": {"name": method, "version": "1"},
        "scope": scope or _scope(),
        **details,
    }


def _evaluate_policy(policy: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, Any]:
    validity = observation["validity"]
    actual = observation["value"]
    if validity != "valid":
        status = "invalid" if policy["mandatory"] else "info"
    elif policy["operator"] in {"upper_bound", "event_count_bound"}:
        passed = float(actual) <= float(policy["threshold"])
        status = "pass" if passed else policy["severity"]
    else:
        passed = actual == policy["threshold"]
        status = "pass" if passed else policy["severity"]
    return {
        "policy_id": policy["id"],
        "metric_id": policy["metric_id"],
        "expected_condition": {
            "operator": policy["operator"],
            "threshold": policy["threshold"],
            "boundary": "inclusive" if policy["operator"] != "exact_match" else "exact",
        },
        "actual_value": actual,
        "unit": policy["expected_unit"],
        "status": status,
        "severity": policy["severity"],
        "mandatory": policy["mandatory"],
        "requirement_ids": policy["requirement_ids"],
        "rationale": policy["rationale"],
        "owner": policy["owner"],
    }


def _git_output(root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _repository_root(manifest_path: Path) -> Path | None:
    for candidate in (manifest_path.resolve().parent, Path.cwd().resolve()):
        output = _git_output(candidate, "rev-parse", "--show-toplevel")
        if output:
            return Path(output)
    return None


def _sha256_file(path: Path | None, fallback: str) -> str:
    if path is not None and path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def _installed_version(distribution: str, fallback: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return fallback


def _distribution_is_installed(distribution: str) -> bool:
    try:
        metadata.version(distribution)
        return True
    except metadata.PackageNotFoundError:
        return False


def _provenance(manifest_path: Path) -> tuple[str, bool, dict[str, Any]]:
    root = _repository_root(manifest_path)
    revision = _git_output(root, "rev-parse", "HEAD") if root else None
    dirty_text = _git_output(root, "status", "--porcelain", "--untracked-files=normal") if root else None
    pybind_revision = (
        _git_output(root, "rev-parse", "HEAD:third_party/pybind11") if root else None
    )
    runtime_lock = root / "requirements" / "runtime.lock" if root else None
    toolchain_record = root / "toolchain" / "m1-v1.json" if root else None
    import avsys

    dependency_versions = {
        "audio-validation-systems-lab": _installed_version(
            "audio-validation-systems-lab", avsys.__version__
        ),
        "jinja2": _installed_version("jinja2", "unavailable"),
        "jsonschema": _installed_version("jsonschema", "unavailable"),
        "numpy": np.__version__,
        "pybind11": pybind_revision or "unavailable-installed-wheel",
    }
    fingerprint = f"{platform.system()}-{platform.machine()}-cpython-{sys.version_info.major}.{sys.version_info.minor}"
    provenance = {
        "dependency_revisions": dependency_versions,
        "dependency_lock_digests": {
            "runtime.lock": _sha256_file(runtime_lock, "runtime.lock unavailable")
        },
        "dependency_lock_availability": {
            "runtime.lock": bool(runtime_lock and runtime_lock.is_file())
        },
        "toolchain": {
            "python": platform.python_version(),
            "native_component": avsys.native_version(),
            "native_build_type": (
                "installed-wheel"
                if _distribution_is_installed("audio-validation-systems-lab")
                else "source-or-test"
            ),
        },
        "toolchain_record_digest": _sha256_file(
            toolchain_record, "toolchain record unavailable"
        ),
        "platform": {
            "fingerprint": fingerprint,
            "operating_system": platform.system(),
            "architecture": platform.machine(),
        },
        "repository_root_available": root is not None,
        "toolchain_record_available": bool(toolchain_record and toolchain_record.is_file()),
    }
    return revision or "unavailable-installed-wheel", bool(dirty_text), provenance


def _fault_document(injection: FaultInjection | None) -> list[dict[str, Any]]:
    if injection is None:
        return []
    return [
        {
            "type": injection.record.type,
            "label": injection.record.label,
            "parameters": dict(injection.record.parameters),
            "units": dict(injection.record.units),
        }
    ]


def run_workflow(manifest_path: str | Path, output_directory: str | Path) -> WorkflowOutcome:
    """Execute the intentionally narrow DEMO-3 pipeline and write JSON/HTML."""

    source_path = Path(manifest_path)
    manifest = load_contract(source_path, contract="manifest")
    metric_documents = _validate_demo_manifest(manifest)
    stimulus = generate_stimulus(manifest)
    document = manifest.document
    from . import native_passthrough

    native_candidate = native_passthrough(
        stimulus.candidate_copy(), block_size=document["block_sizes_frames"][0]
    )
    injection = _inject_fault(native_candidate, document)
    candidate = injection.candidate if injection else native_candidate
    baseline = stimulus.pcm
    labels = tuple(item["id"] for item in document["channel_map"])
    description = AudioDescription(
        document["audio_format"]["sample_rate_hz"],
        labels,
        document["audio_format"]["layout"],
    )
    latency_parameters = metric_documents["latency_frames"]["parameters"]
    operating_point = _alignment_operating_point(latency_parameters)
    structural_config = StructuralValidationConfig(
        operating_point.minimum_overlap_frames,
        "OP-B minimum overlap is the structural floor for DEMO-3.",
    )
    alignment_request = AlignmentRequest(
        latency_parameters["search_min_lag_frames"],
        latency_parameters["search_max_lag_frames"],
        0,
        len(baseline),
        0,
        len(candidate),
        0,
        latency_parameters["remove_dc_from_sync"],
    )
    structural = validate_structure(
        baseline,
        candidate,
        description,
        description,
        structural_config,
    )
    alignment = None
    if structural.status == "valid":
        baseline_sync = np.mean(baseline, axis=1, dtype=np.float64).astype(
            np.float32
        ).reshape(-1, 1)
        candidate_sync = np.mean(candidate, axis=1, dtype=np.float64).astype(
            np.float32
        ).reshape(-1, 1)
        alignment = estimate_integer_alignment(
            baseline_sync,
            candidate_sync,
            sample_rate_hz=description.sample_rate_hz,
            request=alignment_request,
            operating_point=operating_point,
        )
    validated = ValidatedAlignment(structural, alignment)
    metrics: list[dict[str, Any]] = []
    observations: dict[str, dict[str, Any]] = {}
    if validated.alignment is None:
        alignment_document: dict[str, Any] = {
            "status": "invalid",
            "reason": "structural_validation_failed",
            "lag_frames": None,
            "latency_ms": None,
            "signed_primary_correlation": None,
            "search_min_lag_frames": alignment_request.search_min_lag_frames,
            "search_max_lag_frames": alignment_request.search_max_lag_frames,
        }
        latency_observation = {"value": None, "validity": "invalid_input"}
    else:
        alignment_document = asdict(validated.alignment)
        latency_validity = "valid" if validated.alignment.status == "valid" else "insufficient_data"
        latency_observation = {
            "value": validated.alignment.lag_frames,
            "validity": latency_validity,
        }
    observations["latency_frames"] = latency_observation
    metrics.append(
        _metric(
            "latency_frames",
            latency_observation["value"],
            "frames",
            validity=latency_observation["validity"],
            method="normalized-cross-correlation",
            stage="raw_before_alignment",
        )
    )
    metrics.append(
        _metric(
            "latency_ms",
            alignment_document["latency_ms"],
            "ms",
            validity=latency_observation["validity"],
            method="normalized-cross-correlation",
            stage="raw_before_alignment",
        )
    )
    policy_evaluations: list[dict[str, Any]] = []
    for policy in document["policies"]:
        if policy["metric_id"] == "latency_frames":
            policy_evaluations.append(_evaluate_policy(policy, latency_observation))

    transform = document["permitted_transforms"][0]["parameters"]
    application = None
    if validated.alignment is not None:
        application = apply_integer_time_alignment(
            baseline,
            candidate,
            validated.alignment,
            TimeAlignmentRequest(
                transform["enabled"], tuple(transform["affected_metrics"])
            ),
            minimum_overlap_frames=operating_point.minimum_overlap_frames,
        )
    if application is None or application.views is None:
        reason = (
            "structural validation failed"
            if validated.alignment is None
            else f"alignment status={validated.alignment.status} reason={validated.alignment.reason}"
        )
        raise AnalysisInputError(
            f"mandatory integer-time compensation could not be applied: {reason}"
        )
    views = application.views
    measurement_view = "aligned_valid_overlap"

    residual_parameters = metric_documents["residual_peak_linear_fs"]["parameters"]
    residual = compute_residual_metrics(
        views,
        rms_floor_linear_fs=residual_parameters["rms_floor_linear_fs"],
        rationale=residual_parameters["rationale"],
    )
    max_residual = max(item.peak_linear_fs for item in residual)
    observations["residual_peak_linear_fs"] = {"value": max_residual, "validity": "valid"}
    metrics.append(
        _metric(
            "residual_peak_linear_fs",
            max_residual,
            "linear_FS",
            method="aligned-absolute-residual",
            stage=measurement_view,
        )
    )
    for item in residual:
        metrics.append(
            _metric(
                "residual_peak_linear_fs",
                item.peak_linear_fs,
                "linear_FS",
                method="aligned-absolute-residual",
                scope=_scope("channel", channel_index=item.channel_index, channel_id=labels[item.channel_index]),
                rms_linear_fs=item.rms_linear_fs,
                rms_dbfs=item.rms_dbfs,
                rms_floor_linear_fs=item.rms_floor_linear_fs,
                stage=measurement_view,
            )
        )
    gain_parameters = metric_documents["gain_delta_db"]["parameters"]
    gain = compute_gain_metrics(
        views,
        rms_floor_linear_fs=gain_parameters["rms_floor_linear_fs"],
        rationale=gain_parameters["rationale"],
    )
    observations["gain_delta_db"] = {
        "value": max(abs(item.gain_delta_db) for item in gain),
        "validity": "valid",
    }
    metrics.append(
        _metric(
            "gain_delta_db",
            observations["gain_delta_db"]["value"],
            "dB",
            method="maximum-absolute-channel-rms-ratio",
            stage=measurement_view,
        )
    )
    for item in gain:
        metrics.append(
            _metric(
                "gain_delta_db",
                item.gain_delta_db,
                "dB",
                method="rms-ratio",
                scope=_scope("channel", channel_index=item.channel_index, channel_id=labels[item.channel_index]),
                stage=measurement_view,
            )
        )
    polarity_parameters = metric_documents["polarity"]["parameters"]
    polarity = diagnose_polarity(
        views,
        signal_rms_floor_linear_fs=polarity_parameters["signal_rms_floor_linear_fs"],
        minimum_abs_correlation=polarity_parameters["minimum_abs_correlation"],
        rationale=polarity_parameters["rationale"],
    )
    polarity_text = ", ".join(item.diagnosis for item in polarity)
    observations["polarity"] = {"value": polarity_text, "validity": "valid"}
    for item in polarity:
        metrics.append(
            _metric(
                "polarity_correlation",
                item.signed_correlation,
                "unitless",
                validity="valid" if item.signed_correlation is not None else "insufficient_data",
                method="signed-normalized-correlation",
                scope=_scope("channel", channel_index=item.channel_index, channel_id=labels[item.channel_index]),
                diagnosis=item.diagnosis,
                stage=measurement_view,
            )
        )
    mapping_parameters = metric_documents["channel_mapping"]["parameters"]
    channel_mapping = analyze_stereo_channel_mapping(
        views,
        expected_labels=(labels[0], labels[1]),
        config=ChannelMappingConfig(
            mapping_parameters["minimum_mapping_margin"],
            mapping_parameters["signal_rms_floor_linear_fs"],
            mapping_parameters["rationale"],
        ),
    )
    mapping_text = (
        str(channel_mapping.observed_to_expected_indices)
        if channel_mapping.observed_to_expected_indices is not None
        else "unavailable"
    )
    observations["channel_mapping"] = {
        "value": mapping_text,
        "validity": "valid" if channel_mapping.status == "confident" else "insufficient_data",
    }
    metrics.append(
        _metric(
            "channel_mapping_margin",
            channel_mapping.mapping_margin,
            "unitless",
            validity="valid" if channel_mapping.mapping_margin is not None else "insufficient_data",
            method="stereo-permutation-correlation",
            observed_to_expected_indices=mapping_text,
            minimum_mapping_margin=channel_mapping.minimum_mapping_margin,
            stage=measurement_view,
        )
    )
    dropout_parameters = metric_documents["dropout_event_count"]["parameters"]
    dropouts = detect_dropouts(
        views,
        sample_rate_hz=document["audio_format"]["sample_rate_hz"],
        config=DropoutConfig(
            dropout_parameters["active_reference_floor_linear_fs"],
            dropout_parameters["near_silence_floor_linear_fs"],
            dropout_parameters["minimum_duration_frames"],
            dropout_parameters["rationale"],
        ),
    )
    observations["dropout_event_count"] = {"value": len(dropouts), "validity": "valid"}
    metrics.append(
        _metric(
            "dropout_event_count",
            float(len(dropouts)),
            "count",
            method="active-reference-near-silence-intervals",
            stage=measurement_view,
        )
    )
    for policy in document["policies"]:
        if policy["metric_id"] != "latency_frames":
            policy_evaluations.append(
                _evaluate_policy(policy, observations[policy["metric_id"]])
            )

    structural_invalid = validated.structural.status != "valid"
    mandatory_invalid = any(
        item["status"] == "invalid" and item["mandatory"] for item in policy_evaluations
    )
    policy_failed = any(item["status"] == "fail" for item in policy_evaluations)
    warned = any(item["status"] == "warning" for item in policy_evaluations)
    if structural_invalid or mandatory_invalid:
        validation_status = "invalid"
        exit_code = EXIT_INVALID
    elif policy_failed:
        validation_status = "fail"
        exit_code = EXIT_POLICY_FAILURE
    elif warned:
        validation_status = "warning"
        exit_code = EXIT_PASS
    else:
        validation_status = "pass"
        exit_code = EXIT_PASS

    source_revision, dirty_state, provenance = _provenance(source_path)
    timestamp = document["sut"]["parameters"]["result_timestamp_utc"]
    requirements = sorted(
        {
            requirement
            for policy in document["policies"]
            for requirement in policy["requirement_ids"]
        }
        | {
            "SYS-EXE-001",
            "SYS-DIAG-001",
            "SYS-DIAG-002",
            "SYS-DIAG-003",
            "RPT-SCHEMA-003",
            "RPT-SCHEMA-004",
            "RPT-HTML-001",
            "RPT-HTML-008",
            "RPT-REP-001",
            "CI-RUN-010",
        }
    )
    events = [
        {
            "type": "dropout",
            "channels": [labels[index] for index in item.channel_indices],
            "start_frame": item.start_frame,
            "end_frame": item.end_frame,
            "start_seconds": item.start_seconds,
            "end_seconds": item.end_seconds,
            "confidence": 1.0,
            "confidence_method": "deterministic_rule_match",
            "evidence_references": ["manifest.json"],
            "duration_frames": item.duration_frames,
            "duration_seconds": item.duration_seconds,
            "candidate_start_frame": item.candidate_start_frame,
            "candidate_end_frame": item.candidate_end_frame,
            "classification": item.classification,
        }
        for item in dropouts
    ]
    compensations = []
    if application is not None and application.compensation is not None:
        compensations.append(
            {
                "name": application.compensation.type,
                "method": application.compensation.method,
                "measured_parameters": [
                    {
                        "name": "lag",
                        "value": application.compensation.measured_lag_frames,
                        "unit": application.compensation.units,
                    }
                ],
                "affected_metrics": list(application.compensation.affected_metrics),
            }
        )
    result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": f"demo3-{manifest.sha256[:20]}",
        "timestamps": {
            "started_at": timestamp,
            "finished_at": timestamp,
            "basis": "manifest_declared_fixture",
            "wall_clock_recorded": False,
        },
        "test_id": document["test"]["id"],
        "requirement_ids": requirements,
        "manifest_digest": manifest.sha256,
        "source_revision": source_revision,
        "dirty_state": dirty_state,
        "validation_status": validation_status,
        "run_status": validation_status,
        "completion_status": "complete",
        "provenance": provenance,
        "metrics": metrics,
        "policy_evaluations": policy_evaluations,
        "compensations": compensations,
        "events": events,
        "categorical_observations": [
            {
                "metric_id": "polarity",
                "value": polarity_text,
                "unit": "categorical",
                "validity": observations["polarity"]["validity"],
                "method": {"name": "per-channel-polarity-diagnosis", "version": "1"},
                "scope": _scope(),
            },
            {
                "metric_id": "channel_mapping",
                "value": mapping_text,
                "unit": "channel_mapping",
                "validity": observations["channel_mapping"]["validity"],
                "method": {"name": "stereo-permutation-correlation", "version": "1"},
                "scope": _scope(),
                "structured_value": list(channel_mapping.observed_to_expected_indices)
                if channel_mapping.observed_to_expected_indices is not None
                else None,
            },
        ],
        "artifacts": [],
        "reproduction": {
            "display_command": "avsys run --manifest manifest.json --output reproduced",
            "arguments": [
                "avsys",
                "run",
                "--manifest",
                "manifest.json",
                "--output",
                "reproduced",
            ],
        },
        "faults": _fault_document(injection),
        "stimulus": stimulus.metadata.to_document(),
        "analysis": {
            "structural": asdict(validated.structural),
            "alignment": alignment_document,
            "measurement_view": measurement_view,
            "residual": [asdict(item) for item in residual],
            "gain": [asdict(item) for item in gain],
            "polarity": [asdict(item) for item in polarity],
            "channel_mapping": asdict(channel_mapping),
            "dropout_events": [asdict(item) for item in dropouts],
        },
    }

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    packaged_manifest = output / "manifest.json"
    metadata_path = output / "stimulus.metadata.json"
    result_path = output / "result.json"
    report_path = output / "report.html"
    packaged_manifest.write_bytes(manifest.raw)
    try:
        metadata_bytes = dump_contract(
            stimulus.metadata.to_document(), contract="stimulus_metadata"
        )
        metadata_path.write_bytes(metadata_bytes)
        result["artifacts"] = [
            {
                "relative_path": "manifest.json",
                "media_type": "application/json",
                "content_hash": manifest.sha256,
                "size_bytes": len(manifest.raw),
                "role": "byte-identical-input-manifest",
                "generation_status": "generated",
            },
            {
                "relative_path": "stimulus.metadata.json",
                "media_type": "application/json",
                "content_hash": hashlib.sha256(metadata_bytes).hexdigest(),
                "size_bytes": len(metadata_bytes),
                "role": "stimulus-provenance",
                "generation_status": "generated",
            },
        ]
        report_bytes = render_report(result)
        result["artifacts"].append(
            {
                "relative_path": "report.html",
                "media_type": "text/html",
                "content_hash": hashlib.sha256(report_bytes).hexdigest(),
                "size_bytes": len(report_bytes),
                "role": "human-readable-diagnostics",
                "generation_status": "generated",
            }
        )
        result_bytes = dump_contract(result, contract="result")
        report_path.write_bytes(report_bytes)
        result_path.write_bytes(result_bytes)
    except ContractError as error:
        raise DemoReportingError(f"result contract generation failed: {error}") from error
    return WorkflowOutcome(exit_code, result_path, report_path, result)


__all__ = [
    "DemoInputError",
    "DemoReportingError",
    "EXIT_INTERNAL_ERROR",
    "EXIT_INVALID",
    "EXIT_PASS",
    "EXIT_POLICY_FAILURE",
    "WorkflowOutcome",
    "run_workflow",
]
