"""One fast installed-wheel job covering all four DEMO-3 manifests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from avsys.contracts import validate_document


ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / "configs" / "manifests"


def _console_script() -> Path:
    name = "avsys.exe" if os.name == "nt" else "avsys"
    return Path(sys.executable).resolve().parent / name


def test_demo3_ci_run_001_002_009_installed_wheel_four_scenarios(
    tmp_path: Path,
) -> None:
    expected = {
        "clean": (0, "pass"),
        "delay": (1, "fail"),
        "channel-swap": (1, "fail"),
        "dropout": (1, "fail"),
    }
    results: dict[str, dict[str, object]] = {}
    for scenario, (exit_code, status) in expected.items():
        output = tmp_path / scenario
        completed = subprocess.run(
            [
                os.fspath(_console_script()),
                "run",
                "--manifest",
                os.fspath(MANIFESTS / f"demo3-{scenario}.json"),
                "--output",
                os.fspath(output),
            ],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == exit_code, completed.stderr
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        validate_document(result, contract="result")
        assert result["run_status"] == status
        assert (output / "report.html").is_file()
        results[scenario] = result

    assert results["delay"]["analysis"]["alignment"]["lag_frames"] == 16
    assert results["delay"]["analysis"]["residual"][0]["peak_linear_fs"] == 0.0
    assert results["channel-swap"]["analysis"]["channel_mapping"]["observed_to_expected_indices"] == [1, 0]
    assert results["dropout"]["events"][0]["start_frame"] == 320
    assert results["dropout"]["events"][0]["end_frame"] == 384
    assert results["dropout"]["events"][0]["channels"] == ["left", "right"]
    assert results["dropout"]["events"][0]["classification"] == "exact_zero"

    repeat = tmp_path / "clean-repeat"
    completed = subprocess.run(
        [
            os.fspath(_console_script()),
            "run",
            "--manifest",
            os.fspath(MANIFESTS / "demo3-clean.json"),
            "--output",
            os.fspath(repeat),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "clean" / "result.json").read_bytes() == (
        repeat / "result.json"
    ).read_bytes()
