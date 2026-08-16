"""Cross-language smoke test intended to run against an installed wheel."""

import avsys
import numpy as np

from avsys.stimuli import canonical_pcm_bytes


def test_sys_bnd_001_wheel_loads_linked_native_component() -> None:
    assert avsys.__version__ == "0.1.0"
    assert avsys.native_version() == avsys.__version__


def test_sys_rep_004_wheel_imports_numpy_stimulus_boundary() -> None:
    pcm = np.zeros((1, 1), dtype=np.float32)
    assert canonical_pcm_bytes(pcm) == b"\x00\x00\x00\x00"
