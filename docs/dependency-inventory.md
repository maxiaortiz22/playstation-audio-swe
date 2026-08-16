# Dependency and toolchain inventory

This inventory is the reviewed supply-chain boundary for the M1 foundation
slice. Exact Python transitives and distribution hashes are in
[`requirements/runtime.lock`](../requirements/runtime.lock) and
[`requirements/build-test.lock`](../requirements/build-test.lock). Toolchain
archive checksums and immutable action revisions are in
[`toolchain/m1-v1.json`](../toolchain/m1-v1.json).

## Direct dependencies

| Dependency | Version/revision | Source | License | Scope and purpose |
|---|---|---|---|---|
| pybind11 | v3.1.0 / `97bf890db679505a14dfe547a5e77bb2bd05dc90` | `https://github.com/pybind/pybind11.git` submodule | BSD-3-Clause | Minimal coarse native/Python linkage boundary |
| GoogleTest | v1.17.0 / `52eb8108c5bdec04579160ae17225d66034bd723` | `https://github.com/google/googletest.git` submodule | BSD-3-Clause | Native unit-test runner; no configure-time download |
| jsonschema | 4.26.0 | PyPI | MIT | Draft 2020-12 validation and path-rich diagnostics |
| Jinja2 | 3.1.6 | PyPI | BSD-3-Clause | Autoescaped, deterministic, self-contained DEMO-3 HTML report rendering required by SPEC-004 |
| NumPy | 2.4.6 | PyPI | BSD-3-Clause | Canonical float32 `(frames, channels)` buffers, finite/range checks, and explicit copies; random and transcendental APIs do not define golden PCM |
| scikit-build-core | 1.0.3 | PyPI | Apache-2.0 | PEP 517 CMake wheel backend |
| build | 1.5.0 | PyPI | MIT | Non-isolated wheel frontend after locked installation |
| wheel | 0.47.0 | PyPI | MIT | Wheel command/tooling used by the build environment |
| pytest | 9.1.1 | PyPI | MIT | Python/schema and installed-wheel integration tests |

SciPy and Matplotlib remain accepted M1 dependencies but are not introduced by
this slice because DEMO-3 reuses the implemented NumPy analysis and produces no
plots or spectral evidence. Jinja2 is introduced only for the SPEC-004 HTML
contract; no web framework or network resource is added.

## Locked Python transitives

| Dependency | Version | License family | Introduced by |
|---|---:|---|---|
| attrs | 26.1.0 | MIT | jsonschema |
| jsonschema-specifications | 2025.9.1 | MIT | jsonschema |
| referencing | 0.37.0 | MIT | jsonschema |
| rpds-py | 2026.6.3 | MIT | referencing/jsonschema |
| typing-extensions | 4.16.0 | PSF-2.0 | referencing |
| MarkupSafe | 3.0.3 | BSD-3-Clause | Jinja2 autoescaping |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | scikit-build-core/build/pytest |
| pathspec | 1.1.1 | MPL-2.0 | scikit-build-core |
| pyproject-hooks | 1.2.0 | MIT | build |
| colorama | 0.4.6 | BSD-3-Clause | build on Windows |
| iniconfig | 2.3.0 | MIT | pytest |
| pluggy | 1.6.0 | MIT | pytest |
| Pygments | 2.20.0 | BSD-2-Clause | pytest |

## Toolchain inputs

- CMake 3.31.6 and Ninja 1.12.1 are downloaded only by the CI bootstrap,
  verified against the SHA-256 values in the toolchain record, and then added
  to `PATH`. They are not Python runtime dependencies.
- CPython patches are fixed to 3.11.16, 3.12.10, and 3.13.15. Python 3.12.10
  is intentionally selected because it has provisionable Windows and Linux
  x64 artifacts for the ADR-0006 matrix.
- Runner image, compiler patch, resolved executable paths, and dependency-lock
  digest are execution evidence. Hosted runner labels are not claimed to be a
  complete immutable operating-system image.

No listed dependency may be advanced implicitly. Version, hash, license, and
compatibility changes require review under ADR-0002 or ADR-0006 as applicable.
