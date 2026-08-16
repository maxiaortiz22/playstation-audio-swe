"""DEMO-1 tests that execute against an installed wheel."""

import numpy as np
import pytest

import avsys
from avsys import _native


def _assert_error(
    input_buffer: np.ndarray,
    *,
    code: str,
    category: str = "buffer_contract",
    block_size: int = 128,
) -> None:
    with pytest.raises(ValueError) as caught:
        avsys.native_passthrough(input_buffer, block_size=block_size)

    error = caught.value
    assert error.code == code
    assert error.category == category
    assert error.detail
    assert str(error).startswith(f"[{code}][{category}] ")


@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize("block_size", [64, 128])
def test_sys_bnd_002_rt_blk_002_valid_mono_stereo_is_bit_exact(
    channels: int, block_size: int
) -> None:
    frames = block_size * 2 + 17
    samples = np.arange(frames * channels, dtype=np.uint32)
    input_buffer = (samples ^ np.uint32(0x80000000)).view(np.float32).reshape(frames, channels)
    before = input_buffer.view(np.uint32).copy()

    output = avsys.native_passthrough(input_buffer, block_size=block_size)

    np.testing.assert_array_equal(output.view(np.uint32), before)
    np.testing.assert_array_equal(input_buffer.view(np.uint32), before)


@pytest.mark.parametrize(
    ("input_buffer", "code"),
    [
        (np.zeros((4, 1), dtype=np.float64), "AVSYS_BUFFER_DTYPE"),
        (np.zeros(4, dtype=np.float32), "AVSYS_BUFFER_RANK"),
        (np.zeros((1, 1, 1), dtype=np.float32), "AVSYS_BUFFER_RANK"),
        (np.zeros((0, 1), dtype=np.float32), "AVSYS_BUFFER_SHAPE"),
        (np.zeros((4, 3), dtype=np.float32), "AVSYS_BUFFER_CHANNELS"),
        (np.zeros((6, 4), dtype=np.float32)[:, ::2], "AVSYS_BUFFER_CONTIGUITY"),
        (np.asfortranarray(np.zeros((6, 2), dtype=np.float32)), "AVSYS_BUFFER_CONTIGUITY"),
    ],
)
def test_sys_bnd_003_rejects_invalid_buffer_contract(
    input_buffer: np.ndarray, code: str
) -> None:
    _assert_error(input_buffer, code=code)


def test_sys_bnd_003_rejects_misaligned_float32_pointer_before_native_access() -> None:
    backing_buffer = bytearray(4 * 4 + 1)
    input_buffer = np.ndarray(
        shape=(4, 1), dtype=np.float32, buffer=backing_buffer, offset=1
    )
    assert input_buffer.flags.c_contiguous
    assert not input_buffer.flags.aligned
    assert input_buffer.ctypes.data % np.dtype(np.float32).alignment == 1

    with pytest.raises(_native.NativeRuntimeError) as caught:
        avsys.native_passthrough(input_buffer, block_size=64)

    error = caught.value
    assert error.code == "AVSYS_BUFFER_ALIGNMENT"
    assert error.category == "buffer_contract"
    assert error.detail == (
        "input data pointer is not aligned to alignof(float): "
        "required alignment=4 bytes, address remainder=1"
    )
    assert str(error) == f"[{error.code}][{error.category}] {error.detail}"


def test_sys_exe_004_rejects_invalid_block_size_with_structured_error() -> None:
    _assert_error(
        np.zeros((4, 1), dtype=np.float32),
        code="AVSYS_BLOCK_SIZE",
        category="native_runtime",
        block_size=0,
    )


def test_sys_bnd_005_result_has_independent_python_ownership_and_mutability() -> None:
    input_buffer = np.arange(10, dtype=np.float32).reshape(5, 2)
    input_buffer.flags.writeable = False

    output = avsys.native_passthrough(input_buffer, block_size=64)

    assert output.dtype == np.float32
    assert output.shape == input_buffer.shape
    assert output.flags.c_contiguous
    assert output.flags.owndata
    assert output.flags.writeable
    assert not np.shares_memory(output, input_buffer)
    np.testing.assert_array_equal(output, input_buffer)
    output[0, 0] = 99.0
    assert input_buffer[0, 0] == 0.0
