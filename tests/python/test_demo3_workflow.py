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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_dump = workflow.dump_contract

    def fail_result(document, *, contract: str):
        if contract == "result":
            raise ContractError(
                "forced result failure", document_path="/", schema_path="<test>"
            )
        return real_dump(document, contract=contract)

    monkeypatch.setattr(workflow, "dump_contract", fail_result)

    assert cli.main(
        [
            "run",
            "--manifest",
            str(MANIFESTS / "demo3-clean.json"),
            "--output",
            str(tmp_path),
        ]
    ) == 3
