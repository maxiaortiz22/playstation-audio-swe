"""Requirement-traced tests for the initial strict JSON contracts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from avsys.contracts import (
    ContractError,
    dump_contract,
    load_contract,
    load_contract_bytes,
    validate_document,
)


ROOT = Path(__file__).resolve().parents[2]
VALID_MANIFEST = ROOT / "tests" / "fixtures" / "manifest" / "valid.json"
VALID_RESULT = ROOT / "tests" / "fixtures" / "result" / "valid.json"


def _document(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_t_sys_001_sys_rep_003_exact_input_digest_and_provenance() -> None:
    raw = VALID_MANIFEST.read_bytes()
    loaded = load_contract_bytes(raw, contract="manifest")

    assert loaded.sha256 == hashlib.sha256(raw).hexdigest()

    result = _document(VALID_RESULT)
    validate_document(result, contract="result")
    assert result["manifest_digest"]
    assert result["source_revision"]
    provenance = result["provenance"]
    assert provenance["dependency_revisions"]
    assert provenance["toolchain"]
    assert provenance["platform"]["fingerprint"]


@pytest.mark.parametrize(
    "missing_path",
    [
        ("manifest_digest",),
        ("source_revision",),
        ("provenance", "dependency_revisions"),
        ("provenance", "dependency_lock_digests"),
        ("provenance", "toolchain"),
        ("provenance", "toolchain_record_digest"),
        ("provenance", "platform", "fingerprint"),
    ],
    ids=[
        "manifest-digest",
        "source-revision",
        "dependency-revisions",
        "dependency-lock-digests",
        "toolchain",
        "toolchain-record-digest",
        "platform-fingerprint",
    ],
)
def test_t_sys_001_sys_rep_003_rejects_missing_provenance(
    missing_path: tuple[str, ...],
) -> None:
    result = _document(VALID_RESULT)
    parent = result
    for part in missing_path[:-1]:
        parent = parent[part]
    del parent[missing_path[-1]]

    with pytest.raises(ContractError):
        validate_document(result, contract="result")


@pytest.mark.parametrize(
    "required_section",
    [
        "schema_version",
        "test",
        "stimulus",
        "audio_format",
        "channel_map",
        "block_sizes_frames",
        "sut",
        "faults",
        "permitted_transforms",
        "metrics",
        "policies",
        "artifact_policy",
        "execution_tier",
    ],
)
def test_t_sys_003_sys_exe_006_requires_complete_manifest(
    required_section: str,
) -> None:
    manifest = _document(VALID_MANIFEST)
    del manifest[required_section]

    with pytest.raises(ContractError) as caught:
        validate_document(manifest, contract="manifest")

    assert caught.value.document_path == "/"
    assert caught.value.schema_path


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":"1.0.0","schema_version":"1.0.0"}',
        b'{"outer":{"key":1,"key":2}}',
    ],
    ids=["duplicate-root", "duplicate-nested"],
)
def test_t_sys_003_sys_exe_007_rejects_duplicate_keys(raw: bytes) -> None:
    with pytest.raises(ContractError, match="duplicate object key"):
        load_contract_bytes(raw, contract="manifest")


@pytest.mark.parametrize(
    "token",
    [b"NaN", b"Infinity", b"-Infinity"],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_t_sys_003_sys_exe_007_rejects_non_finite_tokens(token: bytes) -> None:
    raw = b'{"schema_version":"1.0.0","value":' + token + b"}"
    with pytest.raises(ContractError, match="non-finite") as caught:
        load_contract_bytes(raw, contract="manifest")

    assert caught.value.schema_path == "<parse>"


@pytest.mark.parametrize(
    "raw",
    [
        b'{// comment\n"schema_version":"1.0.0"}',
        b'{/* comment */"schema_version":"1.0.0"}',
        b'{"schema_version":"1.0.0",}',
        b'{"schema_version":"1.0.0","items":[1,]}',
    ],
    ids=["line-comment", "block-comment", "object-trailing-comma", "array-trailing-comma"],
)
def test_t_sys_003_sys_exe_007_rejects_nonstandard_json(raw: bytes) -> None:
    with pytest.raises(ContractError, match="invalid JSON") as caught:
        load_contract_bytes(raw, contract="manifest")

    assert caught.value.document_path == "/"
    assert caught.value.schema_path == "<parse>"


def test_t_sys_003_sys_exe_007_rejects_invalid_utf8() -> None:
    with pytest.raises(ContractError, match="strict UTF-8"):
        load_contract_bytes(b'{"owner":"\xff"}', contract="manifest")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("stimulus", "seed"), "0"),
        (("audio_format", "sample_rate_hz"), "48000"),
        (("policies", 0, "mandatory"), "true"),
    ],
    ids=["integer-string", "number-string", "boolean-string"],
)
def test_t_sys_003_sys_exe_007_does_not_coerce_types(
    path: tuple[str | int, ...], value: str
) -> None:
    manifest = _document(VALID_MANIFEST)
    parent = manifest
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value

    with pytest.raises(ContractError):
        validate_document(manifest, contract="manifest")


@pytest.mark.parametrize(
    "mutation",
    ["root", "nested"],
)
def test_t_sys_003_sys_exe_007_rejects_unknown_authoring_fields(mutation: str) -> None:
    manifest = _document(VALID_MANIFEST)
    if mutation == "root":
        manifest["typo_field"] = True
    else:
        manifest["audio_format"]["typo_field"] = True

    with pytest.raises(ContractError) as caught:
        validate_document(manifest, contract="manifest")

    assert "Additional properties are not allowed" in str(caught.value)


def test_t_sys_003_sys_exe_007_allows_declared_parameter_extension_points() -> None:
    manifest = _document(VALID_MANIFEST)
    manifest["stimulus"]["parameters"]["future_generator_parameter"] = {
        "nested": [1, "two", True]
    }
    validate_document(manifest, contract="manifest")


def test_t_sys_003_sys_exe_007_reports_document_and_schema_paths() -> None:
    manifest = _document(VALID_MANIFEST)
    manifest["audio_format"]["sample_rate_hz"] = "48000"

    with pytest.raises(ContractError) as caught:
        validate_document(manifest, contract="manifest")

    assert caught.value.document_path == "/audio_format/sample_rate_hz"
    assert caught.value.schema_path.endswith("/sample_rate_hz/type")


def test_t_sys_003_sys_exe_006_and_007_manifest_round_trip() -> None:
    loaded = load_contract(VALID_MANIFEST, contract="manifest")
    encoded = dump_contract(loaded.document, contract="manifest")
    round_tripped = load_contract_bytes(encoded, contract="manifest")

    assert round_tripped.document == loaded.document


def test_t_rpt_001_rpt_schema_001_uses_draft_2020_12_and_versioned_files() -> None:
    for schema_name in ("manifest.schema.json", "result.schema.json"):
        schema = _document(ROOT / "schemas" / "v1" / schema_name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(schema)

    result = _document(VALID_RESULT)
    result["schema_version"] = "2.0.0"
    with pytest.raises(ContractError):
        validate_document(result, contract="result")


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "timestamps",
        "test_id",
        "manifest_digest",
        "source_revision",
        "dirty_state",
        "validation_status",
        "run_status",
        "completion_status",
    ],
)
def test_t_rpt_001_rpt_schema_002_requires_identity_and_separate_statuses(
    field: str,
) -> None:
    result = _document(VALID_RESULT)
    del result[field]
    with pytest.raises(ContractError):
        validate_document(result, contract="result")


@pytest.mark.parametrize(
    ("validity", "value", "accepted"),
    [
        ("valid", 0.0, True),
        ("valid", None, False),
        ("invalid_input", None, True),
        ("invalid_input", 0.0, False),
    ],
    ids=["valid-number", "valid-null", "invalid-null", "invalid-number"],
)
def test_t_rpt_001_rpt_schema_003_metric_value_validity_contract(
    validity: str, value: float | None, accepted: bool
) -> None:
    result = _document(VALID_RESULT)
    result["metrics"][0]["validity"] = validity
    result["metrics"][0]["value"] = value
    if accepted:
        validate_document(result, contract="result")
    else:
        with pytest.raises(ContractError):
            validate_document(result, contract="result")


@pytest.mark.parametrize(
    "field",
    ["metric_id", "value", "unit", "validity", "method", "scope"],
)
def test_t_rpt_001_rpt_schema_003_requires_structured_metric_fields(
    field: str,
) -> None:
    result = _document(VALID_RESULT)
    del result["metrics"][0][field]
    with pytest.raises(ContractError):
        validate_document(result, contract="result")


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("policy_evaluations", "expected_condition"),
        ("policy_evaluations", "actual_value"),
        ("policy_evaluations", "status"),
        ("policy_evaluations", "severity"),
        ("policy_evaluations", "requirement_ids"),
        ("compensations", "name"),
        ("compensations", "measured_parameters"),
        ("events", "type"),
        ("events", "channels"),
        ("events", "start_frame"),
        ("events", "end_frame"),
        ("events", "start_seconds"),
        ("events", "end_seconds"),
        ("events", "confidence"),
        ("events", "evidence_references"),
        ("artifacts", "relative_path"),
        ("artifacts", "media_type"),
        ("artifacts", "content_hash"),
        ("artifacts", "size_bytes"),
        ("artifacts", "role"),
        ("artifacts", "generation_status"),
    ],
)
def test_t_rpt_001_rpt_schema_004_through_007_require_structured_evidence(
    section: str, field: str
) -> None:
    result = _document(VALID_RESULT)
    del result[section][0][field]
    with pytest.raises(ContractError):
        validate_document(result, contract="result")


@pytest.mark.parametrize("field", ["name", "value", "unit"])
def test_t_rpt_001_rpt_schema_005_requires_measured_compensation_fields(
    field: str,
) -> None:
    result = _document(VALID_RESULT)
    del result["compensations"][0]["measured_parameters"][0][field]
    with pytest.raises(ContractError):
        validate_document(result, contract="result")


def test_t_rpt_001_rpt_schema_008_preserves_additive_result_fields() -> None:
    result = _document(VALID_RESULT)
    result["future_root"] = {"enabled": True}
    result["metrics"][0]["future_metric_detail"] = "preserved"
    result["policy_evaluations"][0]["future_policy_detail"] = 7
    result["compensations"][0]["future_compensation_detail"] = None
    result["events"][0]["future_event_detail"] = ["x"]
    result["artifacts"][0]["future_artifact_detail"] = {"x": 1}
    result["provenance"]["future_provenance_detail"] = "preserved"
    result["reproduction"]["future_reproduction_detail"] = True

    encoded = dump_contract(result, contract="result")
    round_tripped = load_contract_bytes(encoded, contract="result").document

    assert round_tripped == result


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_t_rpt_001_rpt_schema_009_serializer_rejects_non_finite_numbers(
    value: float,
) -> None:
    result = _document(VALID_RESULT)
    result["metrics"][0]["value"] = value

    with pytest.raises(ContractError, match="non-finite") as caught:
        dump_contract(result, contract="result")

    assert caught.value.document_path == "/metrics/0/value"


def test_t_rpt_001_rpt_schema_001_through_009_full_round_trip() -> None:
    loaded = load_contract(VALID_RESULT, contract="result")
    encoded = dump_contract(loaded.document, contract="result")
    round_tripped = load_contract_bytes(encoded, contract="result")

    assert round_tripped.document == loaded.document
    assert b"NaN" not in encoded
    assert b"Infinity" not in encoded
