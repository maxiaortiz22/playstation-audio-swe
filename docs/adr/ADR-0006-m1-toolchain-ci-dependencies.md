# ADR-0006: Bound the M1 toolchain, CI matrix, and dependencies

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

The repository must demonstrate both a native C++ core and a Python extension
without claiming support that has not been built and tested. GitHub-hosted
runner images evolve, so runner labels alone do not reproduce the exact
environment. M1 also needs a deliberately small dependency set whose licenses
and roles are reviewable.

## Decision

M1 uses C++20 with compiler extensions disabled. The supported floor is CMake
3.25 and Ninja 1.12; initial CI provisions exactly CMake 3.31.6 and Ninja
1.12.1 for single-configuration builds. A toolchain update is a reviewed change
to the versioned CI toolchain record, never an implicit consequence of PATH.
Supported production build platforms are Windows x64 and Linux x86_64. macOS,
ARM, and MinGW are outside M1 support until dedicated evidence exists.

The required CI matrix is intentionally not a full Cartesian product:

| Job | Environment | Python | Required evidence |
|---|---|---:|---|
| Windows integration | `windows-2022`, VS 2022/v143 MSVC | 3.12 | Native, binding, wheel/import, integration |
| Linux minimum | `ubuntu-24.04`, GCC 13 | 3.11 | Native, binding, wheel/import, integration |
| Linux alternate | `ubuntu-24.04`, Clang 18 | 3.13 | Native, binding, integration |
| Python compatibility | `ubuntu-24.04` | 3.11, 3.12, 3.13 | Python, schema, and report tests |
| ASan/UBSan | `ubuntu-24.04`, Clang 18 | 3.12 | Native correctness only |
| TSan extended | `ubuntu-24.04`, Clang 18 | none | Native SPSC stress only |

The first five jobs run on pull requests, subject to path filtering that does
not hide relevant changes. The long TSan stress, realistic drift sweeps, and
host timing characterization run scheduled or manually; deterministic short
functional cases remain in pull-request CI. Sanitizer results never supply
performance thresholds.

Actions use immutable commit SHAs with a human-readable release comment.
Python direct and transitive dependencies use reviewed lock/constraints files
with hashes. The first packaging/CI PR creates a versioned toolchain record with
the exact CPython patch selected for each supported minor, the exact CMake and
Ninja versions above, action SHAs, and installer/checksum provenance. Each
result records that record's digest plus the resolved runner image, compiler,
CMake, Ninja, Python, dependency-lock digest, and submodule revisions. Minor
Python versions define compatibility; exact patches define reproducible CI
environments and move only through review.

M1 production/runtime dependencies are limited to:

- The pinned `pybind11` submodule for bindings.
- NumPy for array and buffer operations.
- SciPy for offline correlation and spectral analysis.
- `jsonschema` for Draft 2020-12 validation.
- Jinja2 with autoescaping for HTML templates.
- Matplotlib using the non-interactive Agg backend for static plots.

Build and test dependencies are `scikit-build-core`, `build`, `wheel`, pytest,
and a pinned GoogleTest revision. CMake and Ninja are toolchain inputs, not
runtime package dependencies. The implementation PR that introduces each
dependency records its exact version, license, source, lock hash, and why the
standard library or an existing dependency was insufficient.

The deterministic-stimulus slice introduces NumPy 2.4.6, the newest version
with published wheels covering every selected CPython 3.11-3.13 Linux row and
the CPython 3.12 Windows row when the slice was implemented. Its reviewed wheel
hashes are recorded in both Python locks. NumPy owns canonical float32 array
representation only; no random or transcendental API defines golden PCM.

PyYAML, libsndfile, FFTW, Plotly, and an external resampler library are not M1
dependencies. Adding one requires a specification or ADR amendment.

## Local evidence at acceptance review

The 2026-08-15 Windows x64 audit found Visual Studio Community 2022 17.14.7
with MSVC 19.44, Windows SDK 10.0.26100.0, CMake 3.31.6, Ninja 1.12.1 in the
Visual Studio installation, and Anaconda CPython 3.12.7. `cl` is available
through the Visual Studio developer environment, not the ordinary shell PATH.
Strawberry MinGW GCC 13.2 is present but is not an M1-supported Windows ABI.

There was no local Linux, Clang, TSan, Python 3.11, or Python 3.13 evidence and
no build or CI scaffolding. Those rows remain proposed support targets until
their implementation PRs pass; they are not `Verified` by this ADR.

## Consequences

- The matrix covers two operating systems, three compiler configurations, and
  the supported Python range without an expensive cross product.
- Exact resolved provenance remains necessary because hosted images can roll;
  reconstructing a retired hosted image may require its recorded SBOM or a
  future container image and is not implied by an OS label alone.
- SciPy and Matplotlib increase installation size but avoid ad-hoc DSP and
  report implementations; their necessity is re-evaluated if packaging cost
  becomes material.
- TSan coverage is Linux-only in M1.

## Alternatives considered

- **Use `*-latest` runner labels:** less maintenance, but weaker repeatability.
- **Support the locally visible MinGW toolchain:** it does not match the
  supported CPython Windows extension ABI selected for M1.
- **One OS/compiler only:** cheaper, but insufficient evidence for a portable
  C++/Python boundary.
- **Full OS/compiler/Python cross product:** more coverage than M1 can justify.

## References

- [GitHub-hosted runner selection](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
- [Clang ThreadSanitizer supported platforms](https://clang.llvm.org/docs/ThreadSanitizer.html)
- [`actions/setup-python` version behavior](https://github.com/actions/setup-python/blob/main/README.md)
