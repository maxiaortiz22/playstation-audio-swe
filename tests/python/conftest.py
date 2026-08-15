"""Make the source-layout package importable for Python-only tests."""

from pathlib import Path
import sys


SOURCE_PACKAGE = Path(__file__).resolve().parents[2] / "python"
sys.path.insert(0, str(SOURCE_PACKAGE))
