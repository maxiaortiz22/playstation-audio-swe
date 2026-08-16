# DEMO-2 audio analysis evidence

- **Profile:** Interview Demo Core, DEMO-2 only
- **Base:** `5b34c5e6d0c21fb22e7fe00d8548ceb37c60a1f0`
- **Branch:** `codex/demo-analysis-core`
- **Date:** 2026-08-16
- **Specification status effect:** none; SPEC-000 and SPEC-001 remain
  `Accepted`, not `Verified`

## Implemented boundary

Production behavior is confined to
[`python/avsys/faults.py`](../../python/avsys/faults.py) and
[`python/avsys/analysis.py`](../../python/avsys/analysis.py). It does not import
behavior from `tools/alignment_calibration.py` and does not add a CLI, policy
engine, schema, JSON result, HTML report, workflow runner, native change, or
dependency.

The following remain explicitly out of scope: fractional delay, drift,
spectral aggregation, crosstalk, click, repeated-block, clipping, and DC-offset
metrics.

## Fault semantics

Every injector accepts only finite, non-empty, C-contiguous `float32` PCM with
shape `(frames, channels)`. It returns a detached writable candidate with the
same dtype, shape, and layout plus an immutable record containing fault type,
label, exact parameters, and units.

- Integer delay preserves frame count. Positive delay means candidate later:
  leading frames are positive zero and trailing source frames are discarded.
  Negative delay advances the candidate, discards leading source frames, and
  appends positive-zero frames. Zero delay is a detached exact copy. The
  allowed domain is `abs(delay_frames) < frame_count` so at least one physical
  pair remains.
- Stereo swap requires exactly two channels and maps observed columns to source
  columns `(1, 0)`.
- Dropout replaces the zero-based half-open interval `[start_frame, end_frame)`
  on a non-empty unique in-range channel set with an explicitly supplied finite
  binary32 value in inclusive nominal full scale `[-1, 1]`. Zero represents an
  exact-zero fault; a declared non-zero low-level value supports near-silence
  fixtures.

No injector writes through the input array.

## Structural and alignment contracts

`validate_and_estimate_integer_alignment` is the guarded production path. It
does not call correlation after a structural failure. Structural issues cover
sample rate, `float32` dtype, rank two, frame/channel layout and contiguity,
channel count and unique non-empty labels, empty input, first non-finite
frame/channel, and insufficient maximum overlap. The result records whether
both input snapshots remained unchanged.

The alignment operating point has no implicit path or fallback. The caller
must load the versioned
[`m1-alignment-operating-point.json`](../../configs/policies/m1-alignment-operating-point.json).
The loader requires the explicit human OP-B selection, M1-only scope, disabled
automatic selection, null fallback, non-universal-default marker, exact seven
parameter names and types, and the recorded parameter digest.

For each inclusive reported lag `l`, sync origins convert it to local lag
`q = l + o_b - o_c`. The estimator correlates only pairs in
`[max(0, -q), min(N_bs, N_cs - q))`, with float64 accumulation and no zero
padding. A lag is eligible only when overlap is at least 64 frames and both RMS
values are strictly greater than `1e-5` linear FS, as loaded from OP-B.

Selection maximizes absolute cross-correlation while preserving the signed
peak. Exact score ties use smallest absolute reported lag then lowest signed
lag for deterministic representation, but equivalent maxima remain
ambiguous. The result records plateau bounds/width, equivalent-maximum count,
secondary peak, ratio kind/value, selected overlap, search range, signed lag in
frames and milliseconds, policy identity/digest, optional sync-only DC removal,
and one of `valid`, `ambiguous`, or `invalid`.

Only a `valid` estimate plus an explicitly enabled time-alignment request can
create measurement views. Those views use exactly baseline `B[i]` and candidate
`C[i + l]`; missing counterparts are excluded. The compensation record stores
the measured frame transform, method, units, and affected metrics. Raw latency
remains in the separate alignment result.

## Measurement semantics and fixture policies

All numeric detector parameters are caller-supplied and require a non-empty
rationale. These values are test-fixture policy, not repository defaults.

| Measurement | Explicit fixture value | Unit | Rationale |
|---|---:|---|---|
| Residual RMS floor | `1e-12` | linear FS | Keeps an exact null finite at `-240 dBFS` for the float32 fixture. |
| Gain RMS floor | `1e-9` | linear FS | Sits 168 dB below the fixture's `0.25` FS active channel. |
| Polarity signal floor | `1e-5` | linear FS RMS | Matches the accepted sync-energy order for active fixture content. |
| Polarity minimum correlation | `0.99` | unitless | Separates exact identity/inversion from unrelated deterministic content. |
| Stereo mapping minimum margin | `0.25` | unitless mean-score delta | Is below the independent fixture's near-1.0 permutation separation. |
| Stereo mapping signal floor | `1e-5` | linear FS RMS | Rejects unsupported silent mapping evidence. |
| Dropout active-reference floor | `0.10` | linear FS magnitude | Is below both active fixture channel magnitudes. |
| Dropout near-silence floor | `1e-6` | linear FS magnitude | Includes the `1e-7` fixture and excludes active content. |
| Dropout minimum duration | `16` | frames | Exercises equality at the declared boundary and rejection at 15 frames. |

Residual peak and RMS remain per channel; dBFS is
`20*log10(max(rms, explicit_floor))`. Gain is the unnormalized per-channel RMS
ratio in dB. Polarity uses signed normalized correlation and is returned as a
separate diagnosis.

Stereo mapping scores the two one-to-one permutations with absolute normalized
cross-correlation. The result exposes the full score matrix, observed-to-
expected indices and labels, mean assigned score, weakest assigned-channel
confidence, best-minus-runner-up margin, configured minimum margin, method, and
confidence/ambiguity status.

Dropout detection requires the aligned reference to be active and candidate to
be at or below the declared near-silence floor for the declared minimum
duration. Events use half-open baseline-timeline frame intervals, seconds,
duration, candidate frame interval, grouped channel set, and exact-zero versus
near-silence classification. Reference silence cannot create an event.

## Requirement-linked automated evidence

| Requirements | Evidence |
|---|---|
| `SYS-TTV-001..002` | Deterministic repeated fault candidates and reproduction records; valid, invalid, boundary, target-fault, and legitimate-negative fixtures. |
| `SYS-ANL-001..002` | Raw lag remains separate; compensation requires explicit enablement and records method/value/units/affected metrics. |
| `SYS-ANL-005` | Guarded analysis returns no alignment when structural validation fails. |
| `CMP-STR-001..005` | Sample-rate/channel/label/format mismatch, empty/short input, localized NaN/Inf, and before/after input equality tests. |
| `CMP-ALIGN-001..007` | Cross-correlation sign/bounds/origins, negative/zero/positive/boundary/out-of-range delay, periodic ambiguity/plateau, signed polarity peak, OP-B loading, and sync-only DC removal. |
| `CMP-COMP-001..003`, `CMP-COMP-005` | Disabled/rejected compensation and exact non-padded valid pairs with retained raw lag. |
| `CMP-MET-001..002`, `CMP-MET-008..009` | Clean/null residual, per-channel localized error, explicit floor, and +1 dB unnormalized gain. |
| `CMP-CH-001..002`, `CMP-CH-004` | Independent stereo identity/swap, non-independent ambiguity, explicit scores/confidence/margin, and separate polarity. |
| `CMP-EVT-002` | Exact-zero and near-silence intervals, channels, frame/second coordinates, duration boundary, and legitimate silence negative. |

The executable tests are in
[`test_demo2_faults_and_structure.py`](../../tests/python/test_demo2_faults_and_structure.py),
[`test_demo2_alignment.py`](../../tests/python/test_demo2_alignment.py), and
[`test_demo2_metrics.py`](../../tests/python/test_demo2_metrics.py).

## Local verification

Environment: Windows x64, CPython 3.12.7, locked pytest 9.1.1, locked NumPy
2.4.6, CMake 3.31.6, Ninja 1.12.0, MSVC 19.44.35211, pybind11 3.1.0,
GoogleTest gitlink `52eb8108c5bdec04579160ae17225d66034bd723`.

- `python -m pip install --require-hashes -r requirements/build-test.lock`:
  passed in a fresh `.venv`.
- `PYTHONPATH=python python -m pytest tests/python`: 212 passed.
- The focused three-file DEMO-2 suite was repeated twice without changing
  inputs or parameters: 60 passed in each run.
- `python tools/verify_submodules.py`: both gitlinks matched the versioned pins.
- Native MSVC configure/build plus `ctest --preset native-debug`: 1/1 passed.
- `python -m build --wheel --no-isolation`: built
  `audio_validation_systems_lab-0.1.0-cp312-cp312-win_amd64.whl`.
- The wheel installed with `requirements/runtime.lock` into a clean environment
  and imported `avsys`, `avsys.analysis`, and `avsys.faults` from outside the
  source tree; Python/native versions were both `0.1.0` and NumPy was `2.4.6`.

Hosted pull-request CI is reported by GitHub checks and is not claimed by this
local evidence record. Linux sanitizer execution is likewise delegated to that
workflow.
