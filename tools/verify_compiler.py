"""Fail CI if the resolved compiler is outside its declared M1 family."""

from __future__ import annotations

import argparse
import re
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True)
    parser.add_argument("--family", choices=("gcc13", "clang18", "msvc-v143"), required=True)
    args = parser.parse_args()

    command = [args.executable] if args.family == "msvc-v143" else [args.executable, "--version"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output = f"{completed.stdout}\n{completed.stderr}"
    expectations = {
        "gcc13": r"(?im)(?:gcc|g\+\+)(?:-\d+)?[^\n]*\b13\.",
        "clang18": r"(?im)clang version 18\.",
        "msvc-v143": r"(?is)microsoft.*19\.(?:3|4)\d",
    }
    if not re.search(expectations[args.family], output):
        raise RuntimeError(
            f"{args.executable} does not match {args.family}; resolved output:\n{output}"
        )
    print(output.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
