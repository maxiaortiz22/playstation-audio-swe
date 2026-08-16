"""Requirement-linked tests for the focused DEMO-3 runner and reports."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

import avsys
from avsys import cli
from avsys import workflow
from avsys.contracts import ContractError, load_contract
from avsys.workflow import run_workflow


ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / "configs" / "manifests"


@pytest.fixture(autouse=True)
def _native_passthrough_without_installed_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        avsys,
        "native_passthrough",
        lambda pcm, block_size=128: np.array(pcm, dtype=np.float32, order="C", copy=True),
    )
    monkeypatch.setattr(avsys, "native_version", lambda: "0.1.0-test-double")


def _result(output: Path) -> dict[str, object]:
    loaded = load_contract(output / "result.json", contract="result")
    return loaded.document


@pytest.mark.parametrize(
    ("scenario", "exit_code", "status"),
    [
        ("clean", 0, "pass"),
        ("delay", 1, "fail"),
        ("channel-swap", 1, "fail"),
        ("dropout", 1, "fail"),
    ],
)
def test_demo3_sys_exe_001_ci_run_001_and_010_four_scenarios(
    tmp_path: Path, scenario: str, exit_code: int, status: str
) -> None:
    output = tmp_path / scenario
    outcome = run_workflow(MANIFESTS / f"demo3-{scenario}.json", output)
    result = _result(output)

    assert outcome.exit_code == exit_code
    assert result["validation_status"] == status
    assert result["run_status"] == status
    assert result["completion_status"] == "complete"
    assert (output / "report.html").is_file()
    assert (output / "manifest.json").read_bytes() == (
        MANIFESTS / f"demo3-{scenario}.json"
    ).read_bytes()


def test_demo3_cmp_align_004_delay_fails_before_null_aligned_residual(
    tmp_path: Path,
) -> None:
    output = tmp_path / "delay"
    run_workflow(MANIFESTS / "demo3-delay.json", output)
    result = _result(output)

    assert result["analysis"]["alignment"]["lag_frames"] == 16
    assert result["analysis"]["alignment"]["latency_ms"] == pytest.approx(1.0 / 3.0)
    assert result["analysis"]["measurement_view"] == "aligned_valid_overlap"
    assert result["analysis"]["residual"][0]["peak_linear_fs"] == 0.0
    assert result["compensations"][0]["measured_parameters"][0] == {
        "name": "lag",
        "unit": "frames",
        "value": 16,
    }
    assert [(item["policy_id"], item["status"]) for item in result["policy_evaluations"]] == [
        ("delay-raw-latency", "fail"),
        ("delay-aligned-residual", "pass"),
    ]


def test_demo3_cmp_ch_002_swap_fails_with_structured_mapping(tmp_path: Path) -> None:
    output = tmp_path / "swap"
    run_workflow(MANIFESTS / "demo3-channel-swap.json", output)
    result = _result(output)

    mapping = result["analysis"]["channel_mapping"]
    assert result["analysis"]["alignment"]["lag_frames"] == 0
    assert mapping["observed_to_expected_indices"] == [1, 0]
    assert mapping["status"] == "confident"
    assert result["policy_evaluations"][0]["actual_value"] == "(1, 0)"
    assert result["policy_evaluations"][0]["status"] == "fail"


def test_demo3_cmp_evt_002_dropout_localizes_interval_channels_and_classification(
    tmp_path: Path,
) -> None:
    output = tmp_path / "dropout"
    run_workflow(MANIFESTS / "demo3-dropout.json", output)
    result = _result(output)

    assert result["events"] == [
        {
            "candidate_end_frame": 384,
            "candidate_start_frame": 320,
            "channels": ["left", "right"],
            "classification": "exact_zero",
            "confidence": 1.0,
            "confidence_method": "deterministic_rule_match",
            "duration_frames": 64,
            "duration_seconds": 64 / 48000,
            "end_frame": 384,
            "end_seconds": 384 / 48000,
            "evidence_references": ["manifest.json"],
            "start_frame": 320,
            "start_seconds": 320 / 48000,
            "type": "dropout",
        }
    ]
    assert result["policy_evaluations"][0]["actual_value"] == 1
    assert result["policy_evaluations"][0]["status"] == "fail"


def test_demo3_sys_exe_006_invalid_manifest_returns_2_before_native(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = tmp_path / "invalid.json"
    document = json.loads((MANIFESTS / "demo3-clean.json").read_text(encoding="utf-8"))
    document["sut"]["id"] = "unsupported-sut"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    native = mock.Mock()
    monkeypatch.setattr(avsys, "native_passthrough", native)

    exit_code = cli.main(["run", "--manifest", str(invalid), "--output", str(tmp_path / "out")])

    assert exit_code == 2
    native.assert_not_called()
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("invalid_part", ["metric-parameters", "policy-threshold"])
def test_demo3_sys_exe_006_pol_eval_002_semantic_input_fails_before_native(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_part: str
) -> None:
    invalid = tmp_path / f"{invalid_part}.json"
    document = json.loads((MANIFESTS / "demo3-clean.json").read_text(encoding="utf-8"))
    if invalid_part == "metric-parameters":
        del document["metrics"][1]["parameters"]["rms_floor_linear_fs"]
    else:
        document["policies"][0]["threshold"] = "not-a-number"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    native = mock.Mock()
    monkeypatch.setattr(avsys, "native_passthrough", native)

    assert cli.main(
        ["run", "--manifest", str(invalid), "--output", str(tmp_path / "out")]
    ) == 2
    native.assert_not_called()
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "metric_id",
    [
        "latency_frames",
        "residual_peak_linear_fs",
        "gain_delta_db",
        "polarity",
        "channel_mapping",
        "dropout_event_count",
    ],
)
@pytest.mark.parametrize("field", ["id", "method", "version", "unit", "scope"])
def test_demo3_pol_eval_002_canonical_metric_contract_fails_before_native(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metric_id: str,
    field: str,
) -> None:
    document = json.loads((MANIFESTS / "demo3-clean.json").read_text(encoding="utf-8"))
    metric = next(item for item in document["metrics"] if item["id"] == metric_id)
    matching_policies = [
        item for item in document["policies"] if item["metric_id"] == metric_id
    ]
    if field == "id":
        metric["id"] = f"altered_{metric_id}"
        for policy in matching_policies:
            policy["metric_id"] = metric["id"]
    elif field == "method":
        metric["method"] = "invented-method"
    elif field == "version":
        metric["version"] = "999"
    elif field == "unit":
        metric["unit"] = "invented_unit"
        for policy in matching_policies:
            policy["expected_unit"] = metric["unit"]
    else:
        metric["scope"] = {
            "kind": "channel",
            "parameters": {"channel_id": "left", "channel_index": 0},
        }
        for policy in matching_policies:
            policy["scope"] = metric["scope"]

    invalid = tmp_path / f"metric-{metric_id}-{field}.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    native = mock.Mock()
    monkeypatch.setattr(avsys, "native_passthrough", native)

    assert cli.main(
        ["run", "--manifest", str(invalid), "--output", str(tmp_path / "out")]
    ) == 2
    native.assert_not_called()
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        (
            "source_sha256",
            "67B6D1BE69196074986DA4B20F274D8AEC33AB92F65E5A0D672AC0561FAAACAB",
            "source_sha256 must be a lowercase SHA-256",
        ),
        (
            "source_sha256",
            "0" * 64,
            "source_sha256 must identify the accepted OP-B source",
        ),
        (
            "decision_version",
            "2.0.0",
            "decision_version must be 1.0.0",
        ),
    ],
)
def test_demo3_cmp_align_002_accepted_op_b_identity_fails_before_native(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: str,
    expected_message: str,
) -> None:
    document = json.loads((MANIFESTS / "demo3-clean.json").read_text(encoding="utf-8"))
    latency = next(item for item in document["metrics"] if item["id"] == "latency_frames")
    latency["parameters"]["operating_point"][field] = value
    invalid = tmp_path / f"op-b-{field}.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    native = mock.Mock()
    monkeypatch.setattr(avsys, "native_passthrough", native)

    assert cli.main(
        ["run", "--manifest", str(invalid), "--output", str(tmp_path / "out")]
    ) == 2
    assert expected_message in capsys.readouterr().err
    native.assert_not_called()
    assert not (tmp_path / "out").exists()


def test_demo3_pol_eval_003_invalid_mandatory_alignment_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_estimator = workflow.estimate_integer_alignment

    def ambiguous_alignment(*args, **kwargs):
        result = real_estimator(*args, **kwargs)
        return replace(result, status="ambiguous", reason="forced_test_ambiguity")

    monkeypatch.setattr(workflow, "estimate_integer_alignment", ambiguous_alignment)

    assert cli.main(
        [
            "run",
            "--manifest",
            str(MANIFESTS / "demo3-clean.json"),
            "--output",
            str(tmp_path / "out"),
        ]
    ) == 2


def test_demo3_rpt_schema_001_repeated_runs_are_byte_deterministic(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_workflow(MANIFESTS / "demo3-clean.json", first)
    run_workflow(MANIFESTS / "demo3-clean.json", second)

    assert (first / "result.json").read_bytes() == (second / "result.json").read_bytes()
    assert (first / "report.html").read_bytes() == (second / "report.html").read_bytes()


def test_demo3_rpt_html_001_to_004_and_008_report_is_offline_and_actionable(
    tmp_path: Path,
) -> None:
    output = tmp_path / "dropout"
    run_workflow(MANIFESTS / "demo3-dropout.json", output)
    html = (output / "report.html").read_text(encoding="utf-8")

    assert "Audio validation result" in html
    assert "dropout-count-zero" in html
    assert "CMP-EVT-002" in html
    assert "[320, 384)" in html
    assert "[0.006666666666666667, 0.008)" in html
    assert "exact_zero" in html
    assert "avsys run --manifest manifest.json --output reproduced" in html
    assert "Raw observations (before compensation)" in html
    assert "Compensated/aligned observations" in html
    assert html.index("Raw observations (before compensation)") < html.index(
        "Compensated/aligned observations"
    ) < html.index("Gain delta:")
    assert "<th>Severity</th>" in html
    assert "http://" not in html
    assert "https://" not in html


def test_demo3_ci_run_010_internal_runner_error_returns_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "run_workflow", mock.Mock(side_effect=RuntimeError("report failed")))

    assert cli.main(
        [
            "run",
            "--manifest",
            str(MANIFESTS / "demo3-clean.json"),
            "--output",
            str(tmp_path),
        ]
    ) == 3


def test_demo3_ci_run_010_result_contract_failure_returns_3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_dump = workflow.dump_contract

    def fail_result(document, *, contract: str):
        if contract == "result":
            raise ContractError(
                "forced result failure", document_path="/", schema_path="<test>"
            )
        return real_dump(document, contract=contract)

    monkeypatch.setattr(workflow, "dump_contract", fail_result)

    exit_code = cli.main(
        [
            "run",
            "--manifest",
            str(MANIFESTS / "demo3-clean.json"),
            "--output",
            str(tmp_path),
        ]
    )

    assert exit_code == 3
    assert (
        "avsys: internal runner/reporting error: result contract generation failed: "
        "forced result failure"
    ) in capsys.readouterr().err


@pytest.mark.parametrize("failure_stage", ["result_serialization", "reporting"])
def test_demo3_rpt_art_006_failed_reuse_retains_only_prior_complete_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_stage: str,
) -> None:
    output = tmp_path / "reused-output"
    run_workflow(MANIFESTS / "demo3-clean.json", output)
    prior = {item.name: item.read_bytes() for item in output.iterdir()}

    document = json.loads((MANIFESTS / "demo3-clean.json").read_text(encoding="utf-8"))
    document["test"]["id"] = "demo3.failed-reuse"
    second_manifest = tmp_path / "second.json"
    second_manifest.write_text(json.dumps(document), encoding="utf-8")
    expected_message = "forced reused-output result failure"
    if failure_stage == "result_serialization":
        real_dump = workflow.dump_contract

        def fail_result(document, *, contract: str):
            if contract == "result":
                raise ContractError(
                    expected_message,
                    document_path="/",
                    schema_path="<test>",
                )
            return real_dump(document, contract=contract)

        monkeypatch.setattr(workflow, "dump_contract", fail_result)
    else:
        expected_message = "forced reused-output reporting failure"
        monkeypatch.setattr(
            workflow, "render_report", mock.Mock(side_effect=RuntimeError(expected_message))
        )

    assert cli.main(
        ["run", "--manifest", str(second_manifest), "--output", str(output)]
    ) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert expected_message in captured.err
    assert {item.name: item.read_bytes() for item in output.iterdir()} == prior
    assert set(prior) == {
        "manifest.json",
        "stimulus.metadata.json",
        "result.json",
        "report.html",
    }
    assert _result(output)["test_id"] == "demo3.clean"
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["test"][
        "id"
    ] == "demo3.clean"
    assert not any(
        item.name.startswith(f".{output.name}.avsys-") for item in tmp_path.iterdir()
    )


def test_demo3_rpt_art_006_successful_reuse_replaces_complete_package(
    tmp_path: Path,
) -> None:
    output = tmp_path / "reused-output"
    run_workflow(MANIFESTS / "demo3-clean.json", output)
    prior_manifest = (output / "manifest.json").read_bytes()

    document = json.loads((MANIFESTS / "demo3-clean.json").read_text(encoding="utf-8"))
    document["test"]["id"] = "demo3.successful-reuse"
    second_manifest = tmp_path / "second.json"
    second_manifest.write_text(json.dumps(document), encoding="utf-8")

    run_workflow(second_manifest, output)

    assert (output / "manifest.json").read_bytes() != prior_manifest
    assert _result(output)["test_id"] == "demo3.successful-reuse"
    assert {item.name for item in output.iterdir()} == {
        "manifest.json",
        "stimulus.metadata.json",
        "result.json",
        "report.html",
    }
