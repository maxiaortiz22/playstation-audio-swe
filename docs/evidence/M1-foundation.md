# M1 foundation vertical-slice evidence

- **Roadmap item:** 2 in [`M1-acceptance-review.md`](../sdd/M1-acceptance-review.md)
- **Branch:** `codex/m1-foundation`
- **Scope:** build, packaging, strict JSON contracts, and separated CI jobs
- **Specification status:** SPEC-000 and SPEC-004 remain `Accepted`

This slice records evidence for a subset of two accepted specifications. It
does not claim that either specification is fully implemented or verified.

## Requirement traceability

| Requirement | Evidence in this slice | Coverage statement |
|---|---|---|
| `SYS-BND-001` | `SysBnd001NativeOnly.CoreMetadataDoesNotRequirePython`; native preset disables bindings; installed-wheel linkage smoke | Implemented for the metadata-only core |
| `SYS-REP-003` | `T-SYS-001` schema tests require manifest digest, source revision, dependency revisions, toolchain, and platform fingerprint | Initial result contract only; no full runner result yet |
| `SYS-EXE-006` | `T-SYS-003` complete-manifest positive/negative tests | Schema structure covered; ordering before native execution remains pending until a runner exists |
| `SYS-EXE-007` | `T-SYS-003` strict UTF-8, duplicate-key, non-finite, comment, trailing-comma, coercion, unknown-field, and path-diagnostic tests | Implemented for the initial manifest reader |
| `RPT-SCHEMA-001..009` | `T-RPT-001` Draft 2020-12 validation, required fields, typed evidence, additive-field round-trip, and non-finite tests | Implemented for the initial v1 result contract |
| `CI-RUN-006` | Distinct `native`, `python-schema`, `wheel-import`, and `sanitizers` workflow jobs; [Actions run 31916250302](https://github.com/maxiaortiz22/playstation-audio-swe/actions/runs/31916250302) | All ten visible matrix checks passed for commit `e0409f4` |

## Local validation record

Validated on Windows x64 with Visual Studio 2022 17.14.7, MSVC
19.44.35211, Windows SDK 10.0.26100.0, CMake 3.31.6, Ninja 1.12.1, and
CPython 3.12.7. The local Python patch is evidence for this machine, not a
replacement for the exact CI patches in the toolchain record.

The following commands passed in the current worktree:

```text
python -m pip install --require-hashes -r requirements/build-test.lock
python tools/verify_submodules.py
python tools/bootstrap_toolchain.py --destination build/toolchain-test
cmake --fresh --preset native-debug -DCMAKE_CXX_COMPILER=cl.exe
cmake --build --preset native-debug
ctest --preset native-debug
python -m pytest tests/python
python -m build --wheel --no-isolation
python -m pip install --require-hashes -r requirements/runtime.lock
python -m pip install --no-deps <freshly-built-wheel>
python -c "import avsys; assert avsys.native_version() == avsys.__version__"
git diff --check
```

Observed results:

- Fresh MSVC/Ninja configure and native build succeeded; CTest passed `1/1`.
- Pytest passed `88` strict-parser/schema cases, including positive,
  negative, boundary, additive round-trip, and non-finite serialization cases.
- scikit-build-core produced a CPython 3.12 Windows x64 wheel using Ninja.
- A second clean venv installed the hash-locked runtime and wheel with
  `--no-deps`; native import and packaged-schema validation passed from
  `%TEMP%`, outside the source tree.
- The checksum bootstrap resolved CMake 3.31.6 and Ninja 1.12.1; both
  submodules matched the versioned gitlinks.
- JSON/TOML parsing, Python compilation, all 21 local Markdown link/fence
  checks, requirement-ID existence, and diff whitespace checks passed.

The draft PR's hosted run passed Windows/MSVC, Linux/GCC 13, Linux/Clang 18,
Python 3.11.16/3.12.10/3.13.15, wheel/import on all three compiler rows, and
ASan+UBSan. TSan is not introduced in this slice because no SPSC implementation
exists yet.
