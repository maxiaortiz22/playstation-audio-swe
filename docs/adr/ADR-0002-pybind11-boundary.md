# ADR-0002: Use pybind11 as a pinned Git submodule

- **Status:** Accepted
- **Date:** 2026-08-14

## Context

The project needs to demonstrate both production-style C++ and ergonomic Python orchestration. The boundary must support NumPy-compatible audio buffers without introducing per-sample interpreter overhead or ambiguous ownership.

Dependency reproducibility is important: silently following the latest upstream branch could change compiler, Python, or CMake behavior between runs.

## Decision

Use `pybind11` as a Git submodule at `third_party/pybind11`, pinned to tag `v3.1.0`, commit `97bf890db679505a14dfe547a5e77bb2bd05dc90`.

The binding design SHALL:

- Expose coarse-grained buffer or block operations, never per-sample Python callbacks.
- Validate dtype, dimensionality, channel layout, contiguity, writability, and sample rate at the boundary.
- Make copied versus borrowed memory explicit.
- Keep Python object access outside the simulated real-time callback.
- Release the GIL for bounded native processing that does not touch Python objects.
- Translate native failures to documented Python exceptions outside real-time processing.
- Keep core C++ APIs independent of Python and pybind11.

## Consequences

### Positive

- Native components remain directly testable with GTest.
- Python can orchestrate realistic audio arrays with low crossing overhead.
- The exact dependency revision is reproducible.
- CMake integration is self-contained.

### Costs and risks

- Contributors must initialize submodules.
- Python ABI and compiler compatibility must be tested across supported environments.
- Zero-copy views can create lifetime hazards; the first milestone will prefer explicit ownership and only introduce borrowing where benchmarks justify it.
- Binding exceptions and reference counting are not real-time safe.

## Upgrade policy

A pybind11 upgrade requires:

1. An amended decision record.
2. C++ build verification on every supported compiler.
3. Python import and buffer-contract tests.
4. NumPy ownership/lifetime tests.
5. Updated pinned commit documentation.

## Alternatives considered

- **Python C API:** maximum control but significantly more boilerplate and ownership risk for this demonstration.
- **CFFI/ctypes:** weaker C++ type integration and less natural NumPy support.
- **Vendored source copy:** loses upstream history and makes upgrades harder to audit.
- **Package-manager-only dependency:** convenient, but less visible and less deterministic for a repository intended to demonstrate its complete native boundary.
