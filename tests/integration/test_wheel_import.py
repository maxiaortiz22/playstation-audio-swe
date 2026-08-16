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


def test_sys_bnd_002_wheel_exposes_coarse_native_passthrough() -> None:
    pcm = np.array([[0.25, -0.5], [1.0, -0.0]], dtype=np.float32)
    result = avsys.native_passthrough(pcm, block_size=64)
    np.testing.assert_array_equal(result.view(np.uint32), pcm.view(np.uint32))
    assert result.flags.owndata
