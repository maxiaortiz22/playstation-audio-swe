"""Verify dependency gitlinks against the versioned toolchain record."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    record = json.loads((ROOT / "toolchain" / "m1-v1.json").read_text(encoding="utf-8"))
    for relative_path, expected in record["submodules"].items():
        actual = subprocess.check_output(
            ["git", "-C", str(ROOT / relative_path), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        if actual != expected:
            raise RuntimeError(
                f"submodule {relative_path} expected {expected}, resolved {actual}"
            )
        print(f"{relative_path} {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
