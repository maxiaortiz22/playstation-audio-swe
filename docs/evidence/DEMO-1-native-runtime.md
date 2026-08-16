# DEMO-1 native runtime evidence

- **Evidence date:** 2026-08-16
- **Base:** `main` at merge `5b34c5e6d0c21fb22e7fe00d8548ceb37c60a1f0`
- **Branch:** `codex/demo-native-runtime`
- **Local platform:** Windows x64, Visual Studio Community 2022 17.14.7,
  MSVC 19.44.35211, CMake 3.31.6, CPython 3.12.7
- **Dependency pins:** GoogleTest `52eb8108c5bdec04579160ae17225d66034bd723`;
  pybind11 `97bf890db679505a14dfe547a5e77bb2bd05dc90`

## Demonstrated slice

The native-only `passthrough_stream` processes interleaved float32 mono and
stereo buffers in 64- and 128-frame partitions. Its final block calls
`passthrough_block` with the exact remaining `valid_frames`; the tests compare
all output sample bits, including signed zero, and verify that samples outside
a block's valid region remain untouched.

The single `native_passthrough` Python operation validates a NumPy input before
native execution, borrows it read-only, allocates a distinct Python-owned
output, and releases the GIL only around C++ processing that uses captured raw
pointers. Boundary failures are `ValueError` subclasses with stable `code`,
`category`, and `detail` attributes for dtype, rank, shape, channel count,
contiguity, and block-size errors.

The independent `SpscRingBuffer<T>` exposes all configured slots as usable,
rejects zero and non-power-of-two capacities, is non-copyable/non-movable, and
uses acquire/release publication with construction-time storage allocation.
Functional evidence covers capacities 1, 2, and 8; empty/full transitions;
FIFO; failed-operation preservation; repeated storage wraparound; and actual
unsigned counter rollover through a reduced-width deterministic test type.

## Requirement-linked evidence

| Area | Requirement IDs | Automated evidence |
|---|---|---|
| Native boundary and execution | `SYS-BND-001`, `SYS-EXE-002`, `SYS-EXE-003`, `SYS-EXE-004`, `RT-BLK-002`, `RT-BLK-004` | `cpp/tests/native_runtime_test.cpp`, native metadata test |
| Coarse Python boundary | `SYS-BND-002`, `SYS-BND-003`, `SYS-BND-005`, partial `RT-PY-001`, `RT-PY-002`, `RT-PY-003` | `tests/integration/test_native_runtime_binding.py`, `tests/integration/test_wheel_import.py` |
| SPSC functional behavior | `RT-SPSC-001`, `RT-SPSC-002`, partial `RT-SPSC-003`, `RT-SPSC-004`, `RT-SPSC-005`, `RT-SPSC-006`, `RT-QUE-001`, `RT-QUE-002`, `RT-QUE-003`, `RT-QUE-004`, `RT-QUE-005`, `RT-QUE-006` | `cpp/tests/spsc_ring_buffer_test.cpp` |

## Local verification

| Check | Result |
|---|---|
| `python tools/verify_submodules.py` | Passed; both accepted pins matched |
| `cmake --fresh --preset native-debug -DCMAKE_CXX_COMPILER=cl.exe` | Passed |
| `cmake --build --preset native-debug` | Passed |
| `ctest --preset native-debug` | Passed, 14/14 tests |
| `python -m pytest tests/python` in the hash-locked DEMO-1 venv | Passed, 152/152 tests |
| Clean `python -m build --wheel --no-isolation` | Passed; exactly one CPython 3.12 Windows x64 wheel produced |
| Installed-wheel import from outside the source tree | Passed; import resolved from the clean smoke venv `site-packages` |
| Installed-wheel `python -m pytest tests/integration` | Passed, 16/16 tests |
| `git diff --check 5b34c5e` | Passed |

The first Python-only attempt used the pre-existing global pytest temporary
root and encountered 13 setup errors because that directory denied access.
No test body failed. Re-running once with the reviewed dependency lock and an
isolated writable temporary directory produced the 152/152 result above.

## Explicit limits

This is Interview Demo Core DEMO-1 evidence only. It does not implement or
claim a complete callback harness, audio/telemetry payloads, cancellation,
timing, performance, concurrent or long stress, TSan coverage, or complete
`RT-MEM-*`, `RT-CB-*`, `RT-OVR-*`, `RT-TIME-*`, or `RT-PY-*` verification. It
does not change any specification status to `Verified`.

GitHub Actions remains the authoritative multi-platform CI record on the draft
pull request for this branch.
