# M1 deterministic stimuli and baseline-boundary evidence

- **Evidence date:** 2026-08-16
- **Branch:** `codex/m1-deterministic-stimuli`
- **Scope:** Roadmap M1 item 3 only
- **Specification status:** SPEC-000 and SPEC-004 remain `Accepted`

## Implemented contract

The slice resolves a strict manifest to exactly one versioned `constant`,
`impulse`, `channel-identification`, or integer `prbs15` generator. Canonical
PCM is immutable C-contiguous NumPy float32 shaped `(frames, channels)`.
Digest bytes are headerless little-endian IEEE 754 binary32 in C-order.

The approved-baseline descriptor is separately versioned and binds test,
manifest, SUT, environment class, generator metadata, PCM, and explicit
approval. Creation and replacement are distinct from generation; replacement
retains previous PCM and provenance. The normal loader has no write operation
and returns a structured `invalid_input` outcome for absent or corrupt input.

## Requirement traceability

| Requirement | Evidence in this slice | Completeness |
|---|---|---|
| `SYS-REP-001` | `test_t_sys_001_sys_rep_001_*`: explicit PRBS seed, repeatability, seed divergence, reviewed vector | Complete for generated stimuli; result-runner recording remains future work |
| `SYS-REP-003` | Exact manifest digest in stimulus metadata; existing result schema/provenance tests | Partial: no production result runner yet |
| `SYS-REP-004` | Repeated in-process and artifact-package byte equality; wheel/platform CI matrix configured | Partial: deterministic generation is covered, raw metric equivalence awaits SUT/analysis |
| `SYS-REP-005` | Immutable bytes-backed stimulus and approved-baseline PCM; explicit writable candidate copy; create/replace separation | Complete at the input boundary; future validation integration remains to exercise it end to end |
| `SYS-EXE-001` | Strict manifest schema retains exactly one SUT object and zero-or-more fault list; demo manifest conforms | Partial: no SUT or faults execute in this slice |
| `POL-BASE-001` | Generation writes no baseline; duplicate create refuses implicit update | Complete at the baseline boundary |
| `POL-BASE-002` | Separate create/replace APIs and CLI commands; blank rationale rejected | Complete at the baseline boundary |
| `POL-BASE-003` | Strict descriptor binds test, manifest/schema, SUT, environment, generator, PCM digest | Complete at the baseline boundary |
| `POL-BASE-004` | Missing/corrupt baseline returns `invalid_input` with no buffer and no candidate substitution | Partial: future runner must propagate this into full run/result/report status |
| `POL-BASE-005` | Replacement increments generation, retains prior PCM, descriptor digest, PCM digest, and approval | Complete at the baseline boundary |
| `RPT-REP-003` | Canonical command packages byte-identical manifest and deterministic stimulus metadata | Partial: report-package integration remains future work |
| `RPT-REP-004` | Stimulus and approved-baseline PCM identified by SHA-256 | Partial: future native candidate/report artifact remains absent |
| `CI-RUN-009` | Generators use repository JSON/integer construction/NumPy arrays; socket-blocked unit case and CI fast tests | Complete for this slice |

## Representative deterministic artifact

Command:

```powershell
$env:PYTHONPATH = "python"
python -m avsys generate --manifest configs/manifests/m1-deterministic-stereo.json --output artifacts/m1-deterministic-stereo-run1
python -m avsys generate --manifest configs/manifests/m1-deterministic-stereo.json --output artifacts/m1-deterministic-stereo-run2
Remove-Item Env:PYTHONPATH
```

Representative SHA-256 values:

| Object | SHA-256 |
|---|---|
| Exact manifest bytes | `7809a2f997c0df629d7703d99be33f65bb69d99b5d11f0bc5b0221d5c41c5c58` |
| Canonical stereo PCM | `b8af998ce315e231b8768fd8a2dbbdfacb5551b45e7d9f7ac7bfc96898d773d7` |
| Deterministic metadata JSON | `143c5c5fafa1a4fe400bec1fb90777482cb3a47f0b824d1f1a9be806462c64b5` |

All three files compared byte-identically across the two local runs. Generated
PCM, baseline generations, caches, and artifact packages remain ignored and
are not committed.

## Validation record

Local platform: Windows 11 `10.0.26200` x64, CPython 3.12.7, NumPy 2.4.6,
MSVC 19.44, CMake 3.31.6, and Ninja 1.12.0. The slice started from
`6cbe377bfddd7e8f4ea3709829065e3d679d693e`.

Executed successfully in this worktree:

```powershell
python -m venv build/locked-venv
build/locked-venv/Scripts/python.exe -m pip install --require-hashes -r requirements/build-test.lock
$env:PYTHONPATH = "python"
build/locked-venv/Scripts/python.exe -m pytest tests/python --basetemp build/pytest-locked
Remove-Item Env:PYTHONPATH
```

Result: 152 Python tests passed, including focused missing/corrupt baseline,
explicit replacement, no-network generation, PRBS vectors, schema, and
repeatability cases. Runtime/build-test lock SHA-256 values were
`df062959c5116a37f7b1c55c8dbaddf353dd631d6a231eb00f0d307330ea8587` and
`6e5c56d33450d20b1ad9d2e781ae6fb22b46d32f59c44178d3eed1a5a7bb0c5c`.

```powershell
cmake --fresh --preset native-debug -DCMAKE_CXX_COMPILER=cl.exe
cmake --build --preset native-debug
ctest --preset native-debug
```

Result: the native build completed and 1/1 CTest passed.

```powershell
$env:CMAKE_ARGS = "-DCMAKE_CXX_COMPILER=cl.exe"
$env:SKBUILD_BUILD_DIR = "build/wheel-m1/{wheel_tag}"
build/locked-venv/Scripts/python.exe -m build --wheel --no-isolation --outdir build/dist-m1
python -m venv build/smoke-m1
build/smoke-m1/Scripts/python.exe -m pip install --require-hashes -r requirements/runtime.lock
$wheel = (Get-ChildItem -LiteralPath build/dist-m1 -Filter *.whl).FullName
build/smoke-m1/Scripts/python.exe -m pip install --no-deps $wheel
Remove-Item Env:CMAKE_ARGS
Remove-Item Env:SKBUILD_BUILD_DIR
```

The installed wheel was imported from outside the source tree, linked the
native component, imported NumPy 2.4.6, loaded its packaged schema, and
regenerated the representative `(32, 2)` PCM digest. The two installed-wheel
integration tests also passed. One initial wheel command supplied a trailing
space in `SKBUILD_BUILD_DIR` and failed before configuration; the corrected
quoted environment assignment above built successfully in a fresh named
directory.

All four JSON schemas passed Draft 2020-12 schema checking. Versioned JSON
fixtures/manifests parsed, requested requirement IDs exist, local Markdown
links and fences passed, `git diff --check` passed, and both submodule pins
passed `tools/verify_submodules.py` plus `git submodule status`.

## Known limitations

- No native audio SUT, pybind11 audio buffer call, fault injector, comparator,
  metric/policy engine, HTML reporter, SPSC, or filter is introduced.
- `POL-BASE-004`, `SYS-REP-003..004`, `SYS-EXE-001`, and `RPT-REP-003..004`
  retain explicitly listed future runner/report evidence; no containing
  specification is marked `Verified`.
- Local execution supplies Windows x64 / CPython 3.12 evidence. Other M1 rows
  remain CI evidence and are not inferred from the local run.
